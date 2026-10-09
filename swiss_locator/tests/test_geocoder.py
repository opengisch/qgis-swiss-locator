"""
Unit tests for the geo.admin.ch geocoder.

These tests do NOT require network access: the network entry point of the
geocoder is replaced by canned SearchServer responses.
"""

import copy
from unittest.mock import patch

from qgis.PyQt.QtCore import QUrlQuery
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import (
    QgsBlockingNetworkRequest,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsFeedback,
    QgsGeocoderContext,
    QgsGeometry,
    QgsRectangle,
)
from qgis.testing import start_app, unittest

from swiss_locator.core.constants import SEARCH_URL
from swiss_locator.core.geocoder import swiss_geocoder
from swiss_locator.core.geocoder.swiss_geocoder import (
    MAX_API_LIMIT,
    QUALITY_EXACT,
    QUALITY_FUZZY,
    GeocoderRequestError,
    SwissGeocoder,
    match_quality,
    normalize_text,
    tokens,
)

start_app()


# Live response of the SearchServer for "Seftigenstrasse 264 3084 Wabern"
WABERN_DETAIL = "seftigenstrasse 264 3084 wabern 355 koeniz ch be"
WABERN_LABEL = "Seftigenstrasse 264 <b>3084 Wabern</b>"
WABERN_EASTING = 2600968.668
WABERN_NORTHING = 1197426.954
WABERN_RESULT = {
    "attrs": {
        "detail": WABERN_DETAIL,
        "featureId": "1272199_0",
        "geom_quadindex": "021300220302203002031",
        "geom_st_box2d": "BOX(2600968.6680000015 1197426.954,2600968.6680000015 1197426.954)",
        "label": WABERN_LABEL,
        "lat": 46.92793655395508,
        "lon": 7.451352119445801,
        "num": 264,
        "objectclass": "",
        "origin": "address",
        "rank": 7,
        "x": 1197427.0,
        "y": 2600968.75,
        "zoomlevel": 10,
    },
    "id": 1726423,
    "weight": 100,
}
WABERN_RESPONSE = {"results": [WABERN_RESULT]}
EMPTY_RESPONSE = {"results": []}


def make_result(label: str, detail: str, easting: float, northing: float, **extra):
    """Builds a SearchServer result item for a single location."""
    item = copy.deepcopy(WABERN_RESULT)
    item["attrs"].update(
        {
            "label": label,
            "detail": detail,
            "geom_st_box2d": f"BOX({easting} {northing},{easting} {northing})",
            "x": round(northing),
            "y": round(easting),
        }
    )
    item["attrs"].update(extra)
    return item


def query_items(request: QNetworkRequest) -> dict:
    return dict(QUrlQuery(request.url()).queryItems())


def context() -> QgsGeocoderContext:
    return QgsGeocoderContext(QgsCoordinateTransformContext())


# ---------------------------------------------------------------------------
# Text normalisation and match quality
# ---------------------------------------------------------------------------


class TestNormalizeAndQuality(unittest.TestCase):
    def test_strips_tags_case_and_punctuation(self):
        self.assertEqual(
            normalize_text("Rue du <b>Stand</b> 15, 1204 Genève"),
            "rue du stand 15 1204 geneve",
        )

    def test_transliterates_umlauts(self):
        self.assertEqual(
            normalize_text("Zürich Köniz Füllinsdorf"), "zuerich koeniz fuellinsdorf"
        )

    def test_transliterates_decomposed_umlauts(self):
        # "u" followed by a combining diaeresis, as produced e.g. by macOS
        self.assertEqual(normalize_text("Zu\u0308rich"), "zuerich")
        self.assertEqual(normalize_text("Zu\u0308rich"), normalize_text("Zürich"))

    def test_strips_accents(self):
        self.assertEqual(normalize_text("Genève Délémont"), "geneve delemont")

    def test_empty(self):
        self.assertEqual(normalize_text(None), "")
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(tokens("  "), set())

    def test_exact_full_address(self):
        self.assertEqual(
            match_quality(
                "Seftigenstrasse 264, 3084 Wabern", WABERN_DETAIL, WABERN_LABEL
            ),
            QUALITY_EXACT,
        )

    def test_exact_without_zip(self):
        self.assertEqual(
            match_quality("Seftigenstrasse 264 Wabern", WABERN_DETAIL, WABERN_LABEL),
            QUALITY_EXACT,
        )

    def test_exact_with_diacritics_in_query(self):
        self.assertEqual(
            match_quality("Seftigenstrasse 264 Köniz", WABERN_DETAIL, WABERN_LABEL),
            QUALITY_EXACT,
        )

    def test_fuzzy_on_typo(self):
        self.assertEqual(
            match_quality("Seftigenstrase 264 Wabern", WABERN_DETAIL, WABERN_LABEL),
            QUALITY_FUZZY,
        )

    def test_fuzzy_on_extra_token(self):
        self.assertEqual(
            match_quality(
                "Seftigenstrasse 264 Wabern Hinterhaus", WABERN_DETAIL, WABERN_LABEL
            ),
            QUALITY_FUZZY,
        )

    def test_empty_query_is_never_exact(self):
        self.assertEqual(match_quality("", WABERN_DETAIL, WABERN_LABEL), QUALITY_FUZZY)
        self.assertEqual(
            match_quality(" , ", WABERN_DETAIL, WABERN_LABEL), QUALITY_FUZZY
        )


# ---------------------------------------------------------------------------
# Request building
# ---------------------------------------------------------------------------


class TestSwissGeocoderRequest(unittest.TestCase):
    def test_default_request(self):
        request = SwissGeocoder().request("Bern")
        self.assertTrue(request.url().toString().startswith(SEARCH_URL))
        params = query_items(request)
        self.assertEqual(params["type"], "locations")
        self.assertEqual(params["searchText"], "Bern")
        self.assertEqual(params["origins"], "address")
        self.assertEqual(params["sr"], "2056")
        self.assertEqual(params["lang"], "en")
        self.assertEqual(params["limit"], "10")
        self.assertNotIn("bbox", params)

    def test_user_agent_header(self):
        request = SwissGeocoder().request("Bern")
        self.assertTrue(request.hasRawHeader(b"User-Agent"))

    def test_origins_language_and_sr(self):
        geocoder = SwissGeocoder(origins=("address", "zipcode"), sr="21781", lang="fr")
        params = query_items(geocoder.request("Bern"))
        self.assertEqual(params["origins"], "address,zipcode")
        self.assertEqual(params["sr"], "21781")
        self.assertEqual(params["lang"], "fr")
        self.assertEqual(geocoder.crs.authid(), "EPSG:21781")

    def test_limit_is_clamped(self):
        self.assertEqual(SwissGeocoder(limit=500).limit, MAX_API_LIMIT)
        self.assertEqual(SwissGeocoder(limit=0).limit, 1)
        self.assertEqual(
            query_items(SwissGeocoder(limit=500).request("Bern"))["limit"], "50"
        )

    def test_bbox(self):
        request = SwissGeocoder().request(
            "Bern", QgsRectangle(2598000, 1195000.5, 2602000.123456, 1200000)
        )
        self.assertEqual(
            query_items(request)["bbox"],
            "2598000.000,1195000.500,2602000.123,1200000.000",
        )

    def test_invalid_sr(self):
        with self.assertRaises(ValueError):
            SwissGeocoder(sr="4326")

    def test_invalid_origin(self):
        with self.assertRaises(ValueError):
            SwissGeocoder(origins=("address", "unknown"))


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


class TestSwissGeocoderParse(unittest.TestCase):
    def setUp(self):
        self.geocoder = SwissGeocoder()

    def test_single_result(self):
        results = self.geocoder.json_to_results(
            WABERN_RESPONSE, "Seftigenstrasse 264 3084 Wabern"
        )
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertTrue(result.isValid())
        self.assertEqual(result.crs().authid(), "EPSG:2056")
        self.assertEqual(result.identifier(), "1272199_0")
        self.assertEqual(result.description(), "Seftigenstrasse 264 3084 Wabern")
        self.assertEqual(result.group(), "address")
        # The point comes from the full precision box, with easting first
        point = result.geometry().asPoint()
        self.assertAlmostEqual(point.x(), WABERN_EASTING, places=3)
        self.assertAlmostEqual(point.y(), WABERN_NORTHING, places=3)

    def test_additional_attributes(self):
        result = self.geocoder.json_to_results(
            WABERN_RESPONSE, "Seftigenstrasse 264 Wabern"
        )[0]
        attributes = result.additionalAttributes()
        self.assertEqual(set(attributes.keys()), set(SwissGeocoder.FIELD_NAMES))
        self.assertEqual(attributes["geocode_quality"], QUALITY_EXACT)
        self.assertEqual(attributes["geocode_label"], "Seftigenstrasse 264 3084 Wabern")
        self.assertEqual(attributes["geocode_detail"], WABERN_DETAIL)
        self.assertEqual(attributes["geocode_origin"], "address")
        self.assertEqual(attributes["geocode_feature_id"], "1272199_0")
        self.assertEqual(attributes["geocode_rank"], 7)
        self.assertEqual(attributes["geocode_weight"], 100)

    def test_appended_fields_match_attributes(self):
        fields = self.geocoder.appendedFields()
        self.assertEqual(tuple(fields.names()), SwissGeocoder.FIELD_NAMES)

    def test_point_from_xy_when_box_is_not_degenerate(self):
        item = make_result("Wabern", "wabern", 2600000, 1197000)
        item["attrs"]["geom_st_box2d"] = "BOX(2599000 1196000,2601000 1198000)"
        item["attrs"]["x"] = 1197000.0  # northing
        item["attrs"]["y"] = 2600000.0  # easting
        result = self.geocoder.json_to_results({"results": [item]}, "Wabern")[0]
        point = result.geometry().asPoint()
        self.assertEqual((point.x(), point.y()), (2600000.0, 1197000.0))
        self.assertEqual(result.viewport().width(), 2000)

    def test_missing_feature_id_falls_back_to_id(self):
        item = copy.deepcopy(WABERN_RESULT)
        del item["attrs"]["featureId"]
        result = self.geocoder.json_to_results({"results": [item]}, "Wabern")[0]
        self.assertEqual(result.identifier(), "1726423")
        self.assertIsNone(result.additionalAttributes()["geocode_feature_id"])

    def test_empty_and_malformed_responses(self):
        self.assertEqual(self.geocoder.json_to_results(EMPTY_RESPONSE, "Bern"), [])
        self.assertEqual(self.geocoder.json_to_results({}, "Bern"), [])
        self.assertEqual(
            self.geocoder.json_to_results({"results": [{"attrs": {}}]}, "Bern"), []
        )

    def test_exact_results_come_first(self):
        response = {
            "results": [
                make_result(
                    "Seftigenstrasse 186 <b>3084 Wabern</b>",
                    "seftigenstrasse 186 3084 wabern",
                    2600555,
                    1197797,
                ),
                make_result(
                    WABERN_LABEL, WABERN_DETAIL, WABERN_EASTING, WABERN_NORTHING
                ),
                make_result(
                    "Seftigenstrasse 188 <b>3084 Wabern</b>",
                    "seftigenstrasse 188 3084 wabern",
                    2600540,
                    1197800,
                ),
            ]
        }
        results = self.geocoder.json_to_results(response, "Seftigenstrasse 264 Wabern")
        self.assertEqual(
            [r.description() for r in results],
            [
                "Seftigenstrasse 264 3084 Wabern",
                "Seftigenstrasse 186 3084 Wabern",
                "Seftigenstrasse 188 3084 Wabern",
            ],
        )
        self.assertEqual(
            [r.additionalAttributes()["geocode_quality"] for r in results],
            [QUALITY_EXACT, QUALITY_FUZZY, QUALITY_FUZZY],
        )


# ---------------------------------------------------------------------------
# geocodeString with a canned network layer
# ---------------------------------------------------------------------------


class TestSwissGeocoderGeocodeString(unittest.TestCase):
    def setUp(self):
        self.geocoder = SwissGeocoder()
        self.requests = []

    def fake_fetch(self, response):
        def fetch(request, feedback=None):
            self.requests.append(request)
            if isinstance(response, Exception):
                raise response
            return response

        return fetch

    def test_empty_string_sends_no_request(self):
        with patch.object(
            SwissGeocoder, "fetch_json", side_effect=self.fake_fetch(WABERN_RESPONSE)
        ):
            self.assertEqual(self.geocoder.geocodeString("", context()), [])
            self.assertEqual(self.geocoder.geocodeString("  \t ", context()), [])
            self.assertEqual(self.geocoder.geocodeString(None, context()), [])
        self.assertEqual(self.requests, [])

    def test_whitespace_is_collapsed(self):
        with patch.object(
            SwissGeocoder, "fetch_json", side_effect=self.fake_fetch(WABERN_RESPONSE)
        ):
            results = self.geocoder.geocodeString(
                "  Seftigenstrasse   264\n3084 Wabern ", context()
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(
            query_items(self.requests[0])["searchText"],
            "Seftigenstrasse 264 3084 Wabern",
        )

    def test_request_error_gives_error_result(self):
        error = GeocoderRequestError("Service unavailable (HTTP 503)", 503)
        with patch.object(
            SwissGeocoder, "fetch_json", side_effect=self.fake_fetch(error)
        ):
            results = self.geocoder.geocodeString("Bern", context())
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].isValid())
        self.assertEqual(results[0].error(), "Service unavailable (HTTP 503)")

    def test_area_of_interest_is_transformed_to_bbox(self):
        ctx = context()
        ctx.setAreaOfInterest(
            QgsGeometry.fromRect(QgsRectangle(7.43, 46.91, 7.47, 46.94))
        )
        ctx.setAreaOfInterestCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        with patch.object(
            SwissGeocoder, "fetch_json", side_effect=self.fake_fetch(WABERN_RESPONSE)
        ):
            self.geocoder.geocodeString("Bahnhofstrasse 1", ctx)
        bbox = [float(v) for v in query_items(self.requests[0])["bbox"].split(",")]
        # Roughly the Wabern area in LV95
        self.assertAlmostEqual(bbox[0], 2599300, delta=500)
        self.assertAlmostEqual(bbox[1], 1195400, delta=500)
        self.assertAlmostEqual(bbox[2], 2602400, delta=500)
        self.assertAlmostEqual(bbox[3], 1198800, delta=500)


# ---------------------------------------------------------------------------
# Options: all origins, extent, truncation and cache
# ---------------------------------------------------------------------------


class TestSwissGeocoderOptions(unittest.TestCase):
    AMBIGUOUS = {
        "results": [
            make_result(
                "Bahnhofstrasse 1 <b>4125 Riehen</b>",
                "bahnhofstrasse 1 4125 riehen",
                2616082.606,
                1270433.993,
            ),
            make_result(
                "Bahnhofstrasse 1 <b>7477 Filisur</b>",
                "bahnhofstrasse 1 7477 filisur",
                2771830.615,
                1171628.225,
            ),
            make_result(
                "Bahnhofstrasse 1 <b>7304 Maienfeld</b>",
                "bahnhofstrasse 1 7304 maienfeld",
                2759018.821,
                1208081.156,
            ),
        ]
    }

    def setUp(self):
        self.requests = []

    def fetch(self, request, feedback=None):
        self.requests.append(request)
        return self.AMBIGUOUS

    def geocode(self, geocoder, query, ctx=None):
        with patch.object(SwissGeocoder, "fetch_json", side_effect=self.fetch):
            return geocoder.geocodeString(query, ctx or context())

    def test_all_origins(self):
        request = SwissGeocoder(origins=None).request("Bern")
        self.assertNotIn("origins", query_items(request))

    def test_configure_resets_counters_and_validates(self):
        geocoder = SwissGeocoder()
        self.geocode(geocoder, "Bahnhofstrasse 1")
        self.assertEqual(geocoder.requests, 1)
        geocoder.configure(origins=("zipcode",), sr="21781", lang="it", limit=3)
        self.assertEqual(geocoder.requests, 0)
        self.assertEqual(geocoder.crs.authid(), "EPSG:21781")
        params = query_items(geocoder.request("Bern"))
        self.assertEqual(params["origins"], "zipcode")
        self.assertEqual(params["limit"], "3")
        with self.assertRaises(ValueError):
            geocoder.configure(sr="4326")

    def test_bbox_option(self):
        geocoder = SwissGeocoder(bbox=QgsRectangle(2598000, 1195000, 2602000, 1200000))
        self.geocode(geocoder, "Bahnhofstrasse 1")
        self.assertEqual(
            query_items(self.requests[0])["bbox"],
            "2598000.000,1195000.000,2602000.000,1200000.000",
        )

    def test_area_of_interest_overrides_bbox_option(self):
        geocoder = SwissGeocoder(bbox=QgsRectangle(2598000, 1195000, 2602000, 1200000))
        ctx = context()
        ctx.setAreaOfInterest(
            QgsGeometry.fromRect(QgsRectangle(2700000, 1100000, 2710000, 1110000))
        )
        ctx.setAreaOfInterestCrs(QgsCoordinateReferenceSystem("EPSG:2056"))
        self.geocode(geocoder, "Bahnhofstrasse 1", ctx)
        self.assertEqual(
            query_items(self.requests[0])["bbox"],
            "2700000.000,1100000.000,2710000.000,1110000.000",
        )

    def test_max_results_keeps_the_candidates_count(self):
        geocoder = SwissGeocoder(max_results=1)
        results = self.geocode(geocoder, "Bahnhofstrasse 1, 7477 Filisur")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].description(), "Bahnhofstrasse 1 7477 Filisur")
        self.assertEqual(results[0].additionalAttributes()["geocode_candidates"], 3)

    def test_identical_queries_are_requested_once(self):
        geocoder = SwissGeocoder()
        first = self.geocode(geocoder, "Bahnhofstrasse 1")
        second = self.geocode(geocoder, "  bahnhofstrasse  1 ")
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(
            [r.description() for r in first], [r.description() for r in second]
        )
        self.assertEqual(geocoder.requests, 1)
        self.assertEqual(geocoder.cache_hits, 1)

    def test_consecutive_errors_counter(self):
        geocoder = SwissGeocoder()
        error = GeocoderRequestError("Service unavailable (HTTP 503)", 503)
        with patch.object(SwissGeocoder, "fetch_json", side_effect=error):
            geocoder.geocodeString("Bern", context())
            geocoder.geocodeString("Thun", context())
        self.assertEqual(geocoder.consecutive_errors, 2)
        self.geocode(geocoder, "Bahnhofstrasse 1")
        self.assertEqual(geocoder.consecutive_errors, 0)
        self.assertEqual(geocoder.requests, 3)

    def test_pause_between_requests(self):
        geocoder = SwissGeocoder(delay_s=0.05)
        with patch.object(swiss_geocoder, "sleep_cancellable") as sleep:
            self.geocode(geocoder, "Bern")
            self.geocode(geocoder, "Thun")
        # No pause before the first request, one before the second
        self.assertEqual(sleep.call_count, 1)
        self.assertLessEqual(sleep.call_args[0][0], 0.05)

    def test_cancelled_pause_sends_no_request(self):
        geocoder = SwissGeocoder(delay_s=0.05)
        self.geocode(geocoder, "Bern")
        feedback = QgsFeedback()
        feedback.cancel()
        with patch.object(SwissGeocoder, "fetch_json", side_effect=self.fetch):
            results = geocoder.geocodeString("Thun", context(), feedback)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].isValid())
        self.assertEqual(results[0].error(), "Request cancelled")


# ---------------------------------------------------------------------------
# Network layer: retries, client errors and cancellation
# ---------------------------------------------------------------------------


class FakeReply:
    def __init__(self, status, content=b"", retry_after=b""):
        self._status = status
        self._content = content
        self._retry_after = retry_after

    def attribute(self, _):
        return self._status

    def content(self):
        return self._content

    def errorString(self):
        return f"error {self._status}"

    def rawHeader(self, _):
        return self._retry_after


class FakeBlockingRequest:
    """
    Replaces QgsBlockingNetworkRequest with a scripted sequence of
    (error code, reply) pairs shared by all instances.
    """

    ErrorCode = QgsBlockingNetworkRequest.ErrorCode
    script = []
    calls = 0
    feedback_to_cancel = None

    def __init__(self):
        self._reply = None

    def get(self, request, forceRefresh=False, feedback=None):
        type(self).calls += 1
        if self.feedback_to_cancel is not None:
            self.feedback_to_cancel.cancel()
        code, self._reply = self.script.pop(0)
        return code

    def reply(self):
        return self._reply

    def errorMessage(self):
        return self._reply.errorString()


class TestSwissGeocoderFetchRetry(unittest.TestCase):
    def setUp(self):
        FakeBlockingRequest.script = []
        FakeBlockingRequest.calls = 0
        FakeBlockingRequest.feedback_to_cancel = None
        patcher = patch.object(
            swiss_geocoder, "QgsBlockingNetworkRequest", FakeBlockingRequest
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        delay_patcher = patch.object(swiss_geocoder, "RETRY_BASE_DELAY_S", 0.001)
        delay_patcher.start()
        self.addCleanup(delay_patcher.stop)
        self.geocoder = SwissGeocoder()
        self.request = self.geocoder.request("Bern")

    def test_success(self):
        FakeBlockingRequest.script = [
            (
                QgsBlockingNetworkRequest.ErrorCode.NoError,
                FakeReply(200, b'{"results": []}'),
            )
        ]
        self.assertEqual(self.geocoder.fetch_json(self.request), {"results": []})
        self.assertEqual(FakeBlockingRequest.calls, 1)

    def test_retry_after_429_then_success(self):
        FakeBlockingRequest.script = [
            (
                QgsBlockingNetworkRequest.ErrorCode.ServerExceptionError,
                FakeReply(429, b"", b"0"),
            ),
            (
                QgsBlockingNetworkRequest.ErrorCode.NoError,
                FakeReply(200, b'{"results": []}'),
            ),
        ]
        self.assertEqual(self.geocoder.fetch_json(self.request), {"results": []})
        self.assertEqual(FakeBlockingRequest.calls, 2)

    def test_retry_after_network_error(self):
        FakeBlockingRequest.script = [
            (QgsBlockingNetworkRequest.ErrorCode.NetworkError, FakeReply(None)),
            (QgsBlockingNetworkRequest.ErrorCode.TimeoutError, FakeReply(None)),
            (
                QgsBlockingNetworkRequest.ErrorCode.NoError,
                FakeReply(200, b'{"results": []}'),
            ),
        ]
        self.assertEqual(self.geocoder.fetch_json(self.request), {"results": []})
        self.assertEqual(FakeBlockingRequest.calls, 3)

    def test_client_error_is_not_retried(self):
        body = b'{"error": {"code": 400, "message": "Please provide a search text"}, "success": false}'
        FakeBlockingRequest.script = [
            (
                QgsBlockingNetworkRequest.ErrorCode.ServerExceptionError,
                FakeReply(400, body),
            )
        ]
        with self.assertRaises(GeocoderRequestError) as cm:
            self.geocoder.fetch_json(self.request)
        self.assertEqual(cm.exception.status, 400)
        self.assertEqual(str(cm.exception), "Please provide a search text (HTTP 400)")
        self.assertEqual(FakeBlockingRequest.calls, 1)

    def test_no_retry(self):
        FakeBlockingRequest.script = [
            (QgsBlockingNetworkRequest.ErrorCode.ServerExceptionError, FakeReply(503))
        ] * 2
        with self.assertRaises(GeocoderRequestError):
            SwissGeocoder(retries=0).fetch_json(self.request)
        self.assertEqual(FakeBlockingRequest.calls, 1)

    def test_server_errors_exhaust_retries(self):
        FakeBlockingRequest.script = [
            (QgsBlockingNetworkRequest.ErrorCode.ServerExceptionError, FakeReply(503))
        ] * 4
        with self.assertRaises(GeocoderRequestError) as cm:
            self.geocoder.fetch_json(self.request)
        self.assertEqual(cm.exception.status, 503)
        self.assertEqual(FakeBlockingRequest.calls, 4)

    def test_invalid_json(self):
        FakeBlockingRequest.script = [
            (QgsBlockingNetworkRequest.ErrorCode.NoError, FakeReply(200, b"<html>"))
        ]
        with self.assertRaises(GeocoderRequestError):
            self.geocoder.fetch_json(self.request)
        self.assertEqual(FakeBlockingRequest.calls, 1)

    def test_cancel_stops_immediately(self):
        feedback = QgsFeedback()
        FakeBlockingRequest.feedback_to_cancel = feedback
        FakeBlockingRequest.script = [
            (QgsBlockingNetworkRequest.ErrorCode.NetworkError, FakeReply(None))
        ] * 4
        with self.assertRaises(GeocoderRequestError):
            self.geocoder.fetch_json(self.request, feedback)
        self.assertEqual(FakeBlockingRequest.calls, 1)


if __name__ == "__main__":
    unittest.main()
