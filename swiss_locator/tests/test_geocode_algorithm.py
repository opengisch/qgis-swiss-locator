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
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingUtils,
    QgsVectorLayer,
)
from qgis.testing import start_app, unittest

from swiss_locator.core.geocoder.swiss_geocoder import (
    MAX_CONSECUTIVE_ERRORS,
    QUALITY_EXACT,
    GeocoderRequestError,
    SwissGeocoder,
)
from swiss_locator.processing.geocode_addresses_algorithm import (
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


def address_table(rows, geometry="None") -> QgsVectorLayer:
    """
    Builds a table with an address and a remark column.
    :param rows: (address, remark) tuples, or (address, remark, QgsPointXY)
        when the layer has a geometry
    :param geometry: the memory provider geometry definition, e.g. "Point?crs=EPSG:4326"
    """
    layer = QgsVectorLayer(
        f"{geometry}{'&' if '?' in geometry else '?'}field=address:string&field=remark:string",
        "addresses",
        "memory",
    )
    for row in rows:
        feature = QgsFeature(layer.fields())
        feature.setAttributes(list(row[:2]))
        if len(row) > 2:
            feature.setGeometry(QgsGeometry.fromPointXY(row[2]))
        layer.dataProvider().addFeature(feature)
    return layer


DEFAULT_ROWS = (
    ("Seftigenstrasse 264, 3084 Wabern", "first"),
    ("seftigenstrasse 264, 3084 wabern", "same address, other case"),
    (None, "no address"),
    ("Xyzzy 1, 9999 Nowhere", "unknown"),
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


class CollectingFeedback(QgsProcessingFeedback):
    """Keeps the warnings and errors reported by the algorithm."""

    def __init__(self):
        super().__init__()
        self.infos = []
        self.warnings = []
        self.errors = []

    def pushInfo(self, message):
        self.infos.append(message)

    def pushWarning(self, message):
        self.warnings.append(message)

    def reportError(self, message, fatalError=False):
        self.errors.append(message)


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
    def run_algorithm(self, service, rows=DEFAULT_ROWS, layer=None, **parameters):
        """Runs the algorithm with the canned service and returns (results, ok, layer)."""
        algorithm = GeocodeAddressesAlgorithm()
        algorithm.initAlgorithm({})
        params = {
            "INPUT": layer if layer is not None else address_table(rows),
            "FIELD": "address",
            "REQUEST_DELAY": 0,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        params.update(parameters)
        # The temporary output layer is owned by the context, keep it alive
        self.context = QgsProcessingContext()
        self.feedback = CollectingFeedback()
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

    def test_parameters(self):
        algorithm = GeocodeAddressesAlgorithm()
        algorithm.initAlgorithm({})
        names = [p.name() for p in algorithm.parameterDefinitions()]
        self.assertEqual(
            names,
            [
                "INPUT",
                "FIELD",
                "ORIGINS",
                "CRS",
                "EXTENT",
                "LANGUAGE",
                "REQUEST_DELAY",
                "OUTPUT",
            ],
        )

    def test_output_layer_definition(self):
        results, ok, layer = self.run_algorithm(FakeService())
        self.assertTrue(ok)
        self.assertEqual(layer.crs().authid(), "EPSG:2056")
        self.assertEqual(layer.wkbType(), 1)  # Point
        self.assertEqual(
            tuple(layer.fields().names()),
            ("address", "remark") + SwissGeocoder.FIELD_NAMES,
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

    def test_matched_row(self):
        results, ok, layer = self.run_algorithm(FakeService())
        attributes, geometry = self.rows(layer)[0]
        self.assertEqual(attributes["remark"], "first")
        self.assertEqual(attributes["geocode_quality"], QUALITY_EXACT)
        self.assertEqual(attributes["geocode_candidates"], 1)
        self.assertEqual(attributes["geocode_label"], "Seftigenstrasse 264 3084 Wabern")
        self.assertEqual(attributes["geocode_detail"], WABERN_DETAIL)
        self.assertEqual(attributes["geocode_origin"], "address")
        self.assertEqual(attributes["geocode_feature_id"], "1272199_0")
        self.assertEqual(attributes["geocode_rank"], 7)
        self.assertEqual(attributes["geocode_weight"], 100)
        self.assertAlmostEqual(geometry.asPoint().x(), WABERN_EASTING, places=3)
        self.assertAlmostEqual(geometry.asPoint().y(), WABERN_NORTHING, places=3)

    def test_identical_addresses_are_requested_once(self):
        service = FakeService()
        self.run_algorithm(service)
        self.assertEqual(
            service.queries,
            ["Seftigenstrasse 264, 3084 Wabern", "Xyzzy 1, 9999 Nowhere"],
        )
        self.assertIn(
            "Requests sent: 2, identical addresses reused: 1.", self.feedback.infos
        )

    def test_unmatched_and_empty_rows_are_kept(self):
        results, ok, layer = self.run_algorithm(FakeService())
        rows = self.rows(layer)
        self.assertEqual(len(rows), 4)
        self.assertEqual(
            [r[0]["remark"] for r in rows],
            ["first", "same address, other case", "no address", "unknown"],
        )
        for attributes, geometry in rows[2:]:
            self.assertTrue(geometry.isNull())
            for name in SwissGeocoder.FIELD_NAMES:
                self.assertIsNone(attributes[name], name)
        # One warning for the empty address, one for the unknown one
        self.assertEqual(len(self.feedback.warnings), 2)
        self.assertEqual(self.feedback.errors, [])

    def test_lv03(self):
        service = FakeService()
        results, ok, layer = self.run_algorithm(service, CRS=1)
        self.assertEqual(service.params[0]["sr"], "21781")
        self.assertEqual(layer.crs().authid(), "EPSG:21781")

    def test_input_layer_crs_is_kept(self):
        rows = (("Seftigenstrasse 264, 3084 Wabern", "first", QgsPointXY(7, 46)),)
        layer = address_table(rows, geometry="Point?crs=EPSG:4326")
        results, ok, layer = self.run_algorithm(FakeService(), layer=layer)
        self.assertEqual(layer.crs().authid(), "EPSG:4326")
        point = self.rows(layer)[0][1].asPoint()
        self.assertAlmostEqual(point.x(), 7.4514, places=3)
        self.assertAlmostEqual(point.y(), 46.9279, places=3)

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

    def test_best_candidate_is_written(self):
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
        rows = (("Bahnhofstrasse 1, 7477 Filisur", ""),)
        results, ok, layer = self.run_algorithm(service, rows=rows)
        output = self.rows(layer)
        self.assertEqual(len(output), 1)
        attributes, geometry = output[0]
        # The exact match comes first even if the service ranked it second
        self.assertEqual(attributes["geocode_label"], "Bahnhofstrasse 1 7477 Filisur")
        self.assertEqual(attributes["geocode_quality"], QUALITY_EXACT)
        self.assertEqual(attributes["geocode_candidates"], 3)

    def test_request_error_row(self):
        service = FakeService(
            error=GeocoderRequestError("Service unavailable (HTTP 503)", 503)
        )
        rows = (("Seftigenstrasse 264, 3084 Wabern", ""),)
        results, ok, layer = self.run_algorithm(service, rows=rows)
        self.assertTrue(ok)
        attributes, geometry = self.rows(layer)[0]
        self.assertTrue(geometry.isNull())
        self.assertIsNone(attributes["geocode_label"])
        self.assertEqual(len(self.feedback.errors), 1)
        self.assertIn("Service unavailable (HTTP 503)", self.feedback.errors[0])

    def test_consecutive_errors_abort(self):
        service = FakeService(
            error=GeocoderRequestError("Service unavailable (HTTP 503)", 503)
        )
        rows = tuple(
            (f"Street {i}, 3000 Bern", "") for i in range(MAX_CONSECUTIVE_ERRORS + 3)
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
                tuple((f"Street {i}, 3000 Bern", "") for i in range(5))
            ),
            "FIELD": "address",
            "REQUEST_DELAY": 0,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        with patch.object(SwissGeocoder, "fetch_json", side_effect=service):
            results, ok = algorithm.run(params, QgsProcessingContext(), feedback)
        self.assertEqual(len(service.queries), 1)

    def test_empty_address_sends_no_request(self):
        service = FakeService()
        results, ok, layer = self.run_algorithm(service, rows=((None, ""), ("", "")))
        self.assertEqual(service.queries, [])
        self.assertEqual(len(self.rows(layer)), 2)


if __name__ == "__main__":
    unittest.main()
