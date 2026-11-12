"""
/***************************************************************************

                            QGIS Swiss Locator Plugin

                             -------------------
        begin                : 2026-10-08
        copyright            : (C) 2026 by Tristan Carel
        email                : tristan.carel@protonmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

# Geocoder backed by the geo.admin.ch SearchServer API.

import json
import re
import time
import unicodedata

from qgis.PyQt.QtCore import QMetaType
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import (
    Qgis,
    QgsBlockingNetworkRequest,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsFeedback,
    QgsField,
    QgsFields,
    QgsGeocoderContext,
    QgsGeocoderInterface,
    QgsGeocoderResult,
    QgsGeometry,
    QgsNetworkRequestParameters,
    QgsPointXY,
    QgsRectangle,
)

from swiss_locator.core.constants import USER_AGENT_SUFFIX
from swiss_locator.core.filters.map_geo_admin import map_geo_admin_url
from swiss_locator.core.parameters import AVAILABLE_CRS
from swiss_locator.utils.html_stripper import strip_tags
from swiss_locator.utils.utils import InvalidBox, box2geometry, url_with_param

# Origins accepted by the SearchServer "locations" search, see
# https://api3.geo.admin.ch/services/sdiservices.html#search
GEOCODE_ORIGINS = (
    "address",
    "parcel",
    "zipcode",
    "gg25",
    "district",
    "kantone",
    "gazetteer",
)

# Largest value accepted by the "limit" parameter of the SearchServer
MAX_API_LIMIT = 50

# The SearchServer rejects a search text of more than 10 words, a word being
# anything between spaces
MAX_SEARCH_WORDS = 10

# Retry policy for transient failures (network errors, HTTP 429 and 5xx)
MAX_RETRIES = 3
RETRY_BASE_DELAY_S = 1.0
RETRY_AFTER_CAP_S = 30.0

# Batch geocoding stops when this many requests failed in a row, as the
# service is most likely down or refusing the client
MAX_CONSECUTIVE_ERRORS = 5

# Candidates are requested by batches of at least this size so that the
# candidates count can reveal ambiguous addresses
MIN_REQUEST_LIMIT = 10

# All fields appended by the geocoder share this prefix so that they stay
# grouped in attribute tables and do not clash with common CSV column names.
FIELD_PREFIX = "geocode_"

QUALITY_EXACT = "exact"
QUALITY_FUZZY = "fuzzy"

# Additional attribute holding the label as returned by the service, with
# its HTML markup. It is not an appended field, batch geocoding ignores it.
HTML_LABEL_ATTRIBUTE = "html_label"

# The "detail" attribute returned by the service transliterates umlauts the
# Swiss way (ö -> oe), so queries are normalised in the same manner before
# being compared.
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_NON_WORD = re.compile(r"[^\w]+")


class GeocoderRequestError(Exception):
    """Raised when a SearchServer request definitely failed."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def sleep_cancellable(seconds: float, feedback: QgsFeedback | None = None) -> bool:
    """
    Sleeps for the given duration in short slices so that a cancellation
    request stays responsive.
    :return: False if the feedback was cancelled during the sleep, True otherwise
    """
    end = time.monotonic() + max(0.0, seconds)
    while True:
        if feedback is not None and feedback.isCanceled():
            return False
        remaining = end - time.monotonic()
        if remaining <= 0:
            return True
        time.sleep(min(0.05, remaining))


def normalize_text(text: str | None) -> str:
    """
    Normalises a plain text, such as a query, for comparison: case folded,
    umlauts transliterated, accents stripped and punctuation replaced by
    single spaces.
    """
    if not text:
        return ""
    # Compose decomposed characters (e.g. "u" + combining diaeresis) first,
    # otherwise they would not match the precomposed umlauts to transliterate
    text = unicodedata.normalize("NFC", text)
    text = text.casefold().translate(_UMLAUTS)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(_NON_WORD.sub(" ", text).split())


def tokens(text: str | None) -> set[str]:
    """Returns the set of normalised words of a text."""
    return set(normalize_text(text).split())


def match_quality(query: str, detail: str | None, label: str | None) -> str:
    """
    Rates how well a result matches the query. The service performs a fuzzy
    search and always tries to return something, so a result is only rated
    "exact" when every word of the query appears in the result.

    The label, in HTML, holds the location as found, e.g. the street, house
    number, postal code and locality of an address. The detail adds the
    municipality and the canton, but also the number of the municipality:
    a word with a digit, such as a house number, must be in the label.
    """
    query_tokens = tokens(query)
    if not query_tokens:
        return QUALITY_FUZZY
    label_tokens = tokens(strip_tags(label or ""))
    detail_tokens = tokens(detail)
    for token in query_tokens - label_tokens:
        if token not in detail_tokens or any(c.isdigit() for c in token):
            return QUALITY_FUZZY
    return QUALITY_EXACT


class SwissGeocoder(QgsGeocoderInterface):
    """
    Geocoder using the geo.admin.ch SearchServer API.

    Results are returned in the Swiss projection given by ``sr`` (EPSG:2056 or
    EPSG:21781). The point is read from the full precision bounding box when
    the result is a single location, as the "x"/"y" attributes are rounded.
    """

    # Names of the attributes added to each result, in the order of appendedFields()
    FIELD_NAMES = (
        f"{FIELD_PREFIX}quality",
        f"{FIELD_PREFIX}candidates",
        f"{FIELD_PREFIX}label",
        f"{FIELD_PREFIX}detail",
        f"{FIELD_PREFIX}origin",
        f"{FIELD_PREFIX}feature_id",
        f"{FIELD_PREFIX}rank",
        f"{FIELD_PREFIX}weight",
    )
    _INTEGER_FIELDS = (
        f"{FIELD_PREFIX}candidates",
        f"{FIELD_PREFIX}rank",
        f"{FIELD_PREFIX}weight",
    )

    def __init__(
        self,
        origins: tuple[str, ...] | None = ("address",),
        sr: str = "2056",
        lang: str = "en",
        limit: int = 10,
        *,
        max_results: int | None = None,
        delay_s: float = 0.0,
        bbox: QgsRectangle | None = None,
        retries: int = MAX_RETRIES,
    ):
        super().__init__()
        self.configure(
            origins=origins,
            sr=sr,
            lang=lang,
            limit=limit,
            max_results=max_results,
            delay_s=delay_s,
            bbox=bbox,
            retries=retries,
        )

    def configure(
        self,
        origins: tuple[str, ...] | None = ("address",),
        sr: str = "2056",
        lang: str = "en",
        limit: int = 10,
        max_results: int | None = None,
        delay_s: float = 0.0,
        bbox: QgsRectangle | None = None,
        retries: int = MAX_RETRIES,
    ):
        """
        Sets the options of the geocoder and resets its cache and counters.
        A batch geocoding algorithm keeps a single geocoder instance for its
        whole lifetime, hence this method rather than a new instance.
        :param origins: kinds of locations to search for, None for all of them
        :param sr: Swiss spatial reference of the results, "2056" or "21781"
        :param lang: language of the labels
        :param limit: number of locations requested from the service
        :param max_results: number of locations returned by geocodeString,
            None for all of them. The candidates count still reflects every
            location returned by the service.
        :param delay_s: minimum delay between two requests, to spread the
            load on the service
        :param bbox: extent restricting the search, in the geocoder CRS, used
            when the geocoder context has no area of interest
        :param retries: number of retries on transient failures
        """
        if sr not in AVAILABLE_CRS:
            raise ValueError(f"Unsupported spatial reference: {sr}")
        if origins is not None:
            unknown = set(origins) - set(GEOCODE_ORIGINS)
            if unknown:
                raise ValueError(f"Unknown origins: {', '.join(sorted(unknown))}")
            origins = tuple(origins)
        self.origins = origins
        self.sr = sr
        self.lang = lang
        self.limit = max(1, min(int(limit), MAX_API_LIMIT))
        self.max_results = None if max_results is None else max(1, int(max_results))
        self.delay_s = max(0.0, float(delay_s))
        self.bbox = None if bbox is None or bbox.isNull() else QgsRectangle(bbox)
        self.retries = max(0, int(retries))
        self.crs = QgsCoordinateReferenceSystem(f"EPSG:{sr}")

        # Identical queries are requested only once
        self._cache = {}
        self._last_request = None
        self.requests = 0
        self.cache_hits = 0
        self.consecutive_errors = 0

    def flags(self):
        return QgsGeocoderInterface.Flag.GeocodesStrings

    def wkbType(self):
        return Qgis.WkbType.Point

    def appendedFields(self) -> QgsFields:
        fields = QgsFields()
        for name in self.FIELD_NAMES:
            field_type = (
                QMetaType.Type.Int
                if name in self._INTEGER_FIELDS
                else QMetaType.Type.QString
            )
            fields.append(QgsField(name, field_type))
        return fields

    def request(
        self, address: str, bbox: QgsRectangle | None = None
    ) -> QNetworkRequest:
        """
        Builds the SearchServer request for an address.
        :param bbox: optional extent, in the geocoder CRS, restricting the search
        """
        url, params = map_geo_admin_url(
            address, "locations", self.sr, self.lang, self.limit
        )
        if self.origins is not None:
            params["origins"] = ",".join(self.origins)
        if bbox is not None and not bbox.isNull():
            params["bbox"] = (
                f"{bbox.xMinimum():.3f},{bbox.yMinimum():.3f},{bbox.xMaximum():.3f},{bbox.yMaximum():.3f}"
            )
        request = QNetworkRequest(url_with_param(url, params))
        # QgsNetworkAccessManager replaces a User-Agent header with the one of
        # QGIS, to which QGIS 4 appends this suffix
        if hasattr(QgsNetworkRequestParameters, "AttributeUserAgentSuffix"):
            request.setAttribute(
                QNetworkRequest.Attribute(
                    QgsNetworkRequestParameters.AttributeUserAgentSuffix
                ),
                USER_AGENT_SUFFIX,
            )
        return request

    def fetch_json(
        self, request: QNetworkRequest, feedback: QgsFeedback | None = None
    ) -> dict:
        """
        Performs the request and returns the decoded JSON response.
        Transient failures are retried with an exponential backoff.
        :raises GeocoderRequestError: when the request failed or was cancelled
        """
        status = None
        message = ""
        for attempt in range(self.retries + 1):
            blocking = QgsBlockingNetworkRequest()
            code = blocking.get(request, forceRefresh=True, feedback=feedback)
            if feedback is not None and feedback.isCanceled():
                raise GeocoderRequestError("Request cancelled")
            reply = blocking.reply()
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            content = bytes(reply.content())

            if code == QgsBlockingNetworkRequest.ErrorCode.NoError:
                try:
                    return json.loads(content.decode("utf-8"))
                except (UnicodeDecodeError, ValueError) as e:
                    raise GeocoderRequestError(
                        f"Invalid response from the search service: {e}", status
                    ) from e

            message = blocking.errorMessage() or reply.errorString()
            retry_after = None
            if code == QgsBlockingNetworkRequest.ErrorCode.ServerExceptionError:
                # The service describes the error in a JSON body, e.g.
                # {"error": {"code": 400, "message": "Please provide a search text"}}
                try:
                    message = json.loads(content.decode("utf-8"))["error"]["message"]
                except (UnicodeDecodeError, ValueError, KeyError, TypeError):
                    pass
                if status is not None and status != 429 and status < 500:
                    # Client errors are not worth retrying
                    raise GeocoderRequestError(f"{message} (HTTP {status})", status)
                try:
                    retry_after = int(bytes(reply.rawHeader(b"Retry-After")))
                except ValueError:
                    retry_after = None

            if attempt == self.retries:
                break
            delay = RETRY_BASE_DELAY_S * 2**attempt
            if retry_after is not None:
                delay = min(float(retry_after), RETRY_AFTER_CAP_S)
            if not sleep_cancellable(delay, feedback):
                raise GeocoderRequestError("Request cancelled")

        if status:
            message = f"{message} (HTTP {status})"
        raise GeocoderRequestError(message, status)

    @staticmethod
    def parse_location(item) -> tuple[dict, QgsPointXY, QgsRectangle | None] | None:
        """
        Reads the attributes, point and bounding box of a SearchServer result.
        :return: None when the result has no usable location
        """
        attrs = item.get("attrs") if isinstance(item, dict) else None
        if not isinstance(attrs, dict):
            return None
        try:
            box = box2geometry(attrs.get("geom_st_box2d"))
        except (InvalidBox, TypeError):
            box = None
        if box is not None and box.width() < 0.01 and box.height() < 0.01:
            # Single location: the box carries the full precision coordinates
            return attrs, box.center(), box
        try:
            # In Swiss projections the service returns the northing as "x"
            # and the easting as "y"
            return attrs, QgsPointXY(float(attrs["y"]), float(attrs["x"])), box
        except (KeyError, TypeError, ValueError):
            return None

    def json_to_results(self, data: dict, query: str) -> list[QgsGeocoderResult]:
        """
        Converts a SearchServer response to geocoder results.
        Exact matches are listed first, the service order is kept otherwise.
        """
        items = data.get("results") if isinstance(data, dict) else None
        locations = [
            (item, location)
            for item in (items if isinstance(items, list) else [])
            if (location := self.parse_location(item)) is not None
        ]
        results = []
        for item, (attrs, point, box) in locations:
            label = attrs.get("label") or ""
            detail = attrs.get("detail") or ""
            quality = match_quality(query, detail, label)
            feature_id = attrs.get("featureId")
            identifier = (
                str(feature_id) if feature_id is not None else str(item.get("id", ""))
            )
            result = QgsGeocoderResult(
                identifier, QgsGeometry.fromPointXY(point), self.crs
            )
            result.setDescription(strip_tags(label))
            result.setGroup(attrs.get("origin") or "")
            if box is not None:
                result.setViewport(box)
            result.setAdditionalAttributes(
                {
                    f"{FIELD_PREFIX}quality": quality,
                    f"{FIELD_PREFIX}candidates": len(locations),
                    f"{FIELD_PREFIX}label": strip_tags(label),
                    f"{FIELD_PREFIX}detail": detail,
                    f"{FIELD_PREFIX}origin": attrs.get("origin"),
                    f"{FIELD_PREFIX}feature_id": str(feature_id)
                    if feature_id is not None
                    else None,
                    f"{FIELD_PREFIX}rank": attrs.get("rank"),
                    f"{FIELD_PREFIX}weight": item.get("weight"),
                    HTML_LABEL_ATTRIBUTE: label,
                }
            )
            results.append((quality, result))

        # sort() is stable: exact matches first, service order otherwise
        results.sort(key=lambda quality_result: quality_result[0] != QUALITY_EXACT)
        return [result for _, result in results]

    def geocodeString(
        self,
        string: str | None,
        context: QgsGeocoderContext,
        feedback: QgsFeedback | None = None,
    ) -> list[QgsGeocoderResult]:
        query = " ".join((string or "").split())
        if not query:
            # The service rejects empty searches, do not even ask
            return []

        bbox = self.bbox
        area = context.areaOfInterest()
        if area is not None and not area.isNull() and not area.isEmpty():
            area = QgsGeometry(area)
            area_crs = context.areaOfInterestCrs()
            if area_crs.isValid() and area_crs != self.crs:
                try:
                    area.transform(
                        QgsCoordinateTransform(
                            area_crs, self.crs, context.transformContext()
                        )
                    )
                except QgsCsException as e:
                    return [QgsGeocoderResult.errorResult(str(e))]
            bbox = area.boundingBox()

        key = (query.casefold(), bbox.toString(3) if bbox is not None else None)
        if key in self._cache:
            self.cache_hits += 1
            return self._cache[key]

        # Longer addresses are cut, the punctuation marks between spaces first
        words = query.split()
        if len(words) > MAX_SEARCH_WORDS:
            words = [word for word in words if _NON_WORD.sub("", word)]
        search_text = " ".join(words[:MAX_SEARCH_WORDS])

        if self._last_request is not None and self.delay_s > 0:
            elapsed = time.monotonic() - self._last_request
            if not sleep_cancellable(self.delay_s - elapsed, feedback):
                return [QgsGeocoderResult.errorResult("Request cancelled")]
        try:
            data = self.fetch_json(self.request(search_text, bbox), feedback)
        except GeocoderRequestError as e:
            results = [QgsGeocoderResult.errorResult(str(e))]
            if e.status is not None and 400 <= e.status < 500 and e.status != 429:
                # The service rejected this search and would do it again, it
                # says nothing about the next ones
                self.consecutive_errors = 0
                self._cache[key] = results
            elif feedback is None or not feedback.isCanceled():
                self.consecutive_errors += 1
            return results
        finally:
            self.requests += 1
            self._last_request = time.monotonic()
        self.consecutive_errors = 0

        # Only the returned locations are kept, the candidates count carried
        # by each of them still reflects the whole response
        results = self.json_to_results(data, query)[: self.max_results]
        self._cache[key] = results
        return results
