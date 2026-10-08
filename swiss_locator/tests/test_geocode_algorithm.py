"""
Unit tests for the Processing provider and the address geocoding algorithm.

These tests do NOT require network access: the network entry point of the
geocoder is replaced by canned SearchServer responses.
"""

from unittest.mock import patch

from qgis.PyQt.QtCore import QUrlQuery
from qgis.core import (
    QgsApplication,
    QgsFeature,
    QgsProcessing,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingUtils,
    QgsVectorLayer,
)
from qgis.testing import start_app, unittest

from swiss_locator.core.geocoder.swiss_geocoder import (
    QUALITY_EXACT,
    GeocoderRequestError,
    SwissGeocoder,
)
from swiss_locator.processing.geocode_addresses_algorithm import (
    MAX_CONSECUTIVE_ERRORS,
    GeocodeAddressesAlgorithm,
)
from swiss_locator.processing.provider import SwissLocatorProcessingProvider
from swiss_locator.tests.test_geocoder import (
    EMPTY_RESPONSE,
    WABERN_DETAIL,
    WABERN_EASTING,
    WABERN_NORTHING,
    WABERN_RESPONSE,
    make_result,
)

start_app()

ADDRESS_EXPRESSION = 'concat("street", \' \', "number", \', \', "zip", \' \', "city")'
APPENDED_FIELDS = (
    "geocode_query",
    "geocode_status",
    "geocode_candidates",
    "geocode_candidate",
    "geocode_quality",
    "geocode_label",
    "geocode_detail",
    "geocode_origin",
    "geocode_feature_id",
    "geocode_rank",
    "geocode_weight",
    "geocode_message",
)


def address_table(rows) -> QgsVectorLayer:
    """Builds a geometry-less table with street, number, zip and city columns."""
    layer = QgsVectorLayer(
        "None?field=street:string&field=number:string&field=zip:string&field=city:string",
        "addresses",
        "memory",
    )
    for row in rows:
        feature = QgsFeature(layer.fields())
        feature.setAttributes(list(row))
        layer.dataProvider().addFeature(feature)
    return layer


DEFAULT_ROWS = (
    ("Seftigenstrasse", "264", "3084", "Wabern"),
    ("seftigenstrasse", "264", "3084", "wabern"),
    (None, None, None, None),
    ("Xyzzy", "1", "9999", "Nowhere"),
)


class FakeService:
    """Canned SearchServer: Wabern addresses match, everything else does not."""

    def __init__(self, responses=None, error=None, cancel_feedback=None):
        self.queries = []
        self.params = []
        self.responses = responses or {}
        self.error = error
        self.cancel_feedback = cancel_feedback

    def __call__(self, request, feedback=None):
        params = dict(QUrlQuery(request.url()).queryItems())
        self.params.append(params)
        query = params["searchText"]
        self.queries.append(query)
        if self.cancel_feedback is not None:
            self.cancel_feedback.cancel()
        if self.error is not None:
            raise self.error
        for key, response in self.responses.items():
            if key in query.casefold():
                return response
        if "seftigenstrasse" in query.casefold():
            return WABERN_RESPONSE
        return EMPTY_RESPONSE


class TestProvider(unittest.TestCase):
    def test_provider(self):
        provider = SwissLocatorProcessingProvider()
        self.assertEqual(provider.id(), "swiss_locator")
        self.assertEqual(provider.name(), "Swiss Locator")
        self.assertFalse(provider.icon().isNull())

    def test_registration(self):
        provider = SwissLocatorProcessingProvider()
        registry = QgsApplication.processingRegistry()
        self.assertTrue(registry.addProvider(provider))
        try:
            algorithm = registry.algorithmById("swiss_locator:geocodeaddresses")
            self.assertIsNotNone(algorithm)
            self.assertEqual(
                algorithm.displayName(), "Geocode addresses (geo.admin.ch)"
            )
            self.assertFalse(algorithm.icon().isNull())
        finally:
            registry.removeProvider(provider)


class TestGeocodeAddressesAlgorithm(unittest.TestCase):
    def run_algorithm(self, service, rows=DEFAULT_ROWS, **parameters):
        """Runs the algorithm with the canned service and returns (results, ok, layer)."""
        algorithm = GeocodeAddressesAlgorithm()
        algorithm.initAlgorithm({})
        params = {
            "INPUT": address_table(rows),
            "ADDRESS": ADDRESS_EXPRESSION,
            "REQUEST_DELAY": 0,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        params.update(parameters)
        # The temporary output layer is owned by the context, keep it alive
        self.context = QgsProcessingContext()
        self.feedback = QgsProcessingFeedback()
        with patch.object(SwissGeocoder, "fetch_json", side_effect=service):
            results, ok = algorithm.run(params, self.context, self.feedback)
        layer = (
            QgsProcessingUtils.mapLayerFromString(results["OUTPUT"], self.context)
            if ok
            else None
        )
        return results, ok, layer

    @staticmethod
    def rows(layer):
        return [
            (dict(zip(layer.fields().names(), f.attributes())), f.geometry())
            for f in layer.getFeatures()
        ]

    def test_output_layer_definition(self):
        service = FakeService()
        results, ok, layer = self.run_algorithm(service)
        self.assertTrue(ok)
        self.assertEqual(layer.crs().authid(), "EPSG:2056")
        self.assertEqual(layer.wkbType(), 1)  # Point
        self.assertEqual(
            tuple(layer.fields().names()),
            ("street", "number", "zip", "city") + APPENDED_FIELDS,
        )

    def test_default_request_parameters(self):
        service = FakeService()
        self.run_algorithm(service)
        params = service.params[0]
        self.assertEqual(params["origins"], "address")
        self.assertEqual(params["sr"], "2056")
        self.assertEqual(params["type"], "locations")
        # At least 10 candidates are requested to detect ambiguous addresses
        self.assertEqual(params["limit"], "10")

    def test_expression_and_matched_row(self):
        service = FakeService()
        results, ok, layer = self.run_algorithm(service)
        attributes, geometry = self.rows(layer)[0]
        self.assertEqual(
            attributes["geocode_query"], "Seftigenstrasse 264, 3084 Wabern"
        )
        self.assertEqual(attributes["geocode_status"], "matched")
        self.assertEqual(attributes["geocode_candidates"], 1)
        self.assertEqual(attributes["geocode_candidate"], 1)
        self.assertEqual(attributes["geocode_quality"], QUALITY_EXACT)
        self.assertEqual(attributes["geocode_label"], "Seftigenstrasse 264 3084 Wabern")
        self.assertEqual(attributes["geocode_detail"], WABERN_DETAIL)
        self.assertEqual(attributes["geocode_origin"], "address")
        self.assertEqual(attributes["geocode_feature_id"], "1272199_0")
        self.assertEqual(attributes["geocode_rank"], 7)
        self.assertEqual(attributes["geocode_weight"], 100)
        self.assertIsNone(attributes["geocode_message"])
        self.assertAlmostEqual(geometry.asPoint().x(), WABERN_EASTING, places=3)
        self.assertAlmostEqual(geometry.asPoint().y(), WABERN_NORTHING, places=3)

    def test_identical_addresses_are_requested_once(self):
        service = FakeService()
        results, ok, layer = self.run_algorithm(service)
        self.assertEqual(
            service.queries,
            ["Seftigenstrasse 264, 3084 Wabern", "Xyzzy 1, 9999 Nowhere"],
        )
        self.assertEqual(results["REQUEST_COUNT"], 2)
        self.assertEqual(results["GEOCODED_COUNT"], 2)
        self.assertEqual(results["UNMATCHED_COUNT"], 1)
        self.assertEqual(results["ERROR_COUNT"], 0)

    def test_unmatched_rows_are_kept_by_default(self):
        results, ok, layer = self.run_algorithm(FakeService())
        rows = self.rows(layer)
        self.assertEqual(len(rows), 4)
        self.assertEqual(
            [r[0]["geocode_status"] for r in rows],
            ["matched", "matched", "empty", "unmatched"],
        )
        empty, unmatched = rows[2], rows[3]
        self.assertTrue(empty[1].isNull())
        self.assertIsNone(empty[0]["geocode_candidates"])
        self.assertTrue(unmatched[1].isNull())
        self.assertEqual(unmatched[0]["geocode_candidates"], 0)
        self.assertIsNone(unmatched[0]["geocode_quality"])

    def test_unmatched_rows_can_be_dropped(self):
        results, ok, layer = self.run_algorithm(FakeService(), KEEP_UNMATCHED=False)
        rows = self.rows(layer)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r[0]["geocode_status"] == "matched" for r in rows))

    def test_target_crs(self):
        results, ok, layer = self.run_algorithm(FakeService(), TARGET_CRS="EPSG:4326")
        self.assertEqual(layer.crs().authid(), "EPSG:4326")
        point = self.rows(layer)[0][1].asPoint()
        self.assertAlmostEqual(point.x(), 7.4514, places=3)
        self.assertAlmostEqual(point.y(), 46.9279, places=3)

    def test_lv03_is_requested_from_the_service(self):
        service = FakeService()
        results, ok, layer = self.run_algorithm(service, TARGET_CRS="EPSG:21781")
        self.assertEqual(service.params[0]["sr"], "21781")
        self.assertEqual(layer.crs().authid(), "EPSG:21781")

    def test_origins_and_language(self):
        service = FakeService()
        self.run_algorithm(service, ORIGINS=[0, 2], LANGUAGE=2)
        self.assertEqual(service.params[0]["origins"], "address,zipcode")
        self.assertEqual(service.params[0]["lang"], "fr")

    def test_extent(self):
        service = FakeService()
        self.run_algorithm(
            service, EXTENT="2598000,2602000,1195000,1200000 [EPSG:2056]"
        )
        self.assertEqual(
            service.params[0]["bbox"], "2598000.000,1195000.000,2602000.000,1200000.000"
        )

    def test_several_candidates(self):
        ambiguous = {
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
        service = FakeService(responses={"bahnhofstrasse": ambiguous})
        rows = (("Bahnhofstrasse", "1", None, None),)
        results, ok, layer = self.run_algorithm(service, rows=rows, MAX_CANDIDATES=2)
        output = self.rows(layer)
        self.assertEqual(len(output), 2)
        self.assertEqual([r[0]["geocode_candidate"] for r in output], [1, 2])
        self.assertEqual([r[0]["geocode_candidates"] for r in output], [3, 3])
        self.assertEqual(
            [r[0]["geocode_label"] for r in output],
            ["Bahnhofstrasse 1 4125 Riehen", "Bahnhofstrasse 1 7477 Filisur"],
        )
        self.assertEqual(results["GEOCODED_COUNT"], 1)

    def test_request_error_row(self):
        service = FakeService(
            error=GeocoderRequestError("Service unavailable (HTTP 503)", 503)
        )
        rows = (("Seftigenstrasse", "264", "3084", "Wabern"),)
        results, ok, layer = self.run_algorithm(
            service, rows=rows, KEEP_UNMATCHED=False
        )
        self.assertTrue(ok)
        output = self.rows(layer)
        # Failed rows are written even when unmatched rows are dropped
        self.assertEqual(len(output), 1)
        attributes, geometry = output[0]
        self.assertEqual(attributes["geocode_status"], "error")
        self.assertEqual(
            attributes["geocode_message"], "Service unavailable (HTTP 503)"
        )
        self.assertTrue(geometry.isNull())
        self.assertEqual(results["ERROR_COUNT"], 1)

    def test_consecutive_errors_abort(self):
        service = FakeService(
            error=GeocoderRequestError("Service unavailable (HTTP 503)", 503)
        )
        rows = tuple(
            ("Street", str(i), "3000", "Bern")
            for i in range(MAX_CONSECUTIVE_ERRORS + 3)
        )
        results, ok, layer = self.run_algorithm(service, rows=rows)
        self.assertFalse(ok)
        self.assertEqual(len(service.queries), MAX_CONSECUTIVE_ERRORS)

    def test_cancel(self):
        feedback = QgsProcessingFeedback()
        service = FakeService(cancel_feedback=feedback)
        algorithm = GeocodeAddressesAlgorithm()
        algorithm.initAlgorithm({})
        params = {
            "INPUT": address_table(
                tuple(("Street", str(i), "3000", "Bern") for i in range(5))
            ),
            "ADDRESS": ADDRESS_EXPRESSION,
            "REQUEST_DELAY": 0,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        with patch.object(SwissGeocoder, "fetch_json", side_effect=service):
            results, ok = algorithm.run(params, QgsProcessingContext(), feedback)
        self.assertEqual(len(service.queries), 1)

    def test_invalid_expression(self):
        results, ok, layer = self.run_algorithm(
            FakeService(), ADDRESS='concat("street", '
        )
        self.assertFalse(ok)

    def test_punctuation_only_address_is_empty(self):
        service = FakeService()
        results, ok, layer = self.run_algorithm(
            service, rows=((None, None, None, None),)
        )
        self.assertEqual(service.queries, [])
        self.assertEqual(self.rows(layer)[0][0]["geocode_status"], "empty")


if __name__ == "__main__":
    unittest.main()
