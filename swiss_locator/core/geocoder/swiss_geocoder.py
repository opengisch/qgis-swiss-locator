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
#
# This module is used from Processing worker threads and from qgis_process,
# so it must stay free of any qgis.gui / QtWidgets import.

import json
import re
import time
import unicodedata

from qgis.PyQt.QtCore import QMetaType, QUrl, QUrlQuery
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
    QgsPointXY,
    QgsRectangle,
)

from swiss_locator.core.constants import USER_AGENT
from swiss_locator.core.filters.map_geo_admin import map_geo_admin_url
from swiss_locator.core.parameters import AVAILABLE_CRS
from swiss_locator.utils.html_stripper import strip_tags

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

# Retry policy for transient failures (network errors, HTTP 429 and 5xx)
MAX_RETRIES = 3
RETRY_BASE_DELAY_S = 1.0
RETRY_AFTER_CAP_S = 30.0

# All fields appended by the geocoder share this prefix so that they stay
# grouped in attribute tables and do not clash with common CSV column names.
FIELD_PREFIX = "geocode_"

QUALITY_EXACT = "exact"
QUALITY_FUZZY = "fuzzy"

# The "detail" attribute returned by the service transliterates umlauts the
# Swiss way (ö -> oe), so queries are normalised in the same manner before
# being compared.
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_NON_WORD = re.compile(r"[^\w]+")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


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
    Normalises a label or a query for comparison: HTML tags removed,
    case folded, umlauts transliterated, accents stripped and punctuation
    replaced by single spaces.
    """
    if not text:
        return ""
    text = strip_tags(text).casefold().translate(_UMLAUTS)
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
    """
    query_tokens = tokens(query)
    if not query_tokens:
        return QUALITY_FUZZY
    if query_tokens <= tokens(detail) | tokens(label):
        return QUALITY_EXACT
    return QUALITY_FUZZY


def parse_box2d(box: str | None) -> QgsRectangle | None:
    """
    Parses the "geom_st_box2d" attribute, e.g. "BOX(2600968.668 1197426.954,2600968.668 1197426.954)".
    :return: the rectangle or None if the value cannot be parsed
    """
    if not box:
        return None
    numbers = _NUMBER.findall(box)
    if len(numbers) != 4:
        return None
    xmin, ymin, xmax, ymax = (float(n) for n in numbers)
    return QgsRectangle(xmin, ymin, xmax, ymax)


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
        f"{FIELD_PREFIX}label",
        f"{FIELD_PREFIX}detail",
        f"{FIELD_PREFIX}origin",
        f"{FIELD_PREFIX}feature_id",
        f"{FIELD_PREFIX}rank",
        f"{FIELD_PREFIX}weight",
    )
    _INTEGER_FIELDS = (f"{FIELD_PREFIX}rank", f"{FIELD_PREFIX}weight")

    def __init__(
        self,
        origins: tuple[str, ...] = ("address",),
        sr: str = "2056",
        lang: str = "en",
        limit: int = 10,
    ):
        super().__init__()
        if sr not in AVAILABLE_CRS:
            raise ValueError(f"Unsupported spatial reference: {sr}")
        unknown = set(origins) - set(GEOCODE_ORIGINS)
        if unknown:
            raise ValueError(f"Unknown origins: {', '.join(sorted(unknown))}")
        self.origins = tuple(origins)
        self.sr = sr
        self.lang = lang
        self.limit = max(1, min(int(limit), MAX_API_LIMIT))
        self.crs = QgsCoordinateReferenceSystem(f"EPSG:{sr}")

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
        params["origins"] = ",".join(self.origins)
        if bbox is not None and not bbox.isNull():
            params["bbox"] = (
                f"{bbox.xMinimum():.3f},{bbox.yMinimum():.3f},{bbox.xMaximum():.3f},{bbox.yMaximum():.3f}"
            )
        qurl = QUrl(url)
        query = QUrlQuery()
        for key, value in params.items():
            query.addQueryItem(key, str(value))
        qurl.setQuery(query)
        request = QNetworkRequest(qurl)
        request.setRawHeader(b"User-Agent", USER_AGENT)
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
        for attempt in range(MAX_RETRIES + 1):
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

            if attempt == MAX_RETRIES:
                break
            delay = RETRY_BASE_DELAY_S * 2**attempt
            if retry_after is not None:
                delay = min(float(retry_after), RETRY_AFTER_CAP_S)
            if not sleep_cancellable(delay, feedback):
                raise GeocoderRequestError("Request cancelled")

        if status:
            message = f"{message} (HTTP {status})"
        raise GeocoderRequestError(message, status)

    def json_to_results(self, data: dict, query: str) -> list[QgsGeocoderResult]:
        """
        Converts a SearchServer response to geocoder results.
        Exact matches are listed first, the service order is kept otherwise.
        """
        results = []
        items = data.get("results", []) if isinstance(data, dict) else []
        for item in items:
            attrs = item.get("attrs", {})
            label = attrs.get("label") or ""
            detail = attrs.get("detail") or ""
            box = parse_box2d(attrs.get("geom_st_box2d"))
            if box is not None and box.width() == 0 and box.height() == 0:
                # Single location: the box carries the full precision coordinates
                point = QgsPointXY(box.xMinimum(), box.yMinimum())
            elif "x" in attrs and "y" in attrs:
                # In Swiss projections the service returns the northing as "x"
                # and the easting as "y"
                point = QgsPointXY(float(attrs["y"]), float(attrs["x"]))
            else:
                continue

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
                    f"{FIELD_PREFIX}quality": match_quality(query, detail, label),
                    f"{FIELD_PREFIX}label": strip_tags(label),
                    f"{FIELD_PREFIX}detail": detail,
                    f"{FIELD_PREFIX}origin": attrs.get("origin"),
                    f"{FIELD_PREFIX}feature_id": str(feature_id)
                    if feature_id is not None
                    else None,
                    f"{FIELD_PREFIX}rank": attrs.get("rank"),
                    f"{FIELD_PREFIX}weight": item.get("weight"),
                }
            )
            results.append(result)

        # sort() is stable: exact matches first, service order otherwise
        results.sort(
            key=lambda r: (
                r.additionalAttributes()[f"{FIELD_PREFIX}quality"] != QUALITY_EXACT
            )
        )
        return results

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

        bbox = None
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

        try:
            data = self.fetch_json(self.request(query, bbox), feedback)
        except GeocoderRequestError as e:
            return [QgsGeocoderResult.errorResult(str(e))]
        return self.json_to_results(data, query)
