"""
Unit tests for result serialization round-trips and the registry pattern.

These tests verify that every result type can be serialized via
as_definition() and deserialized back via result_from_data() without
data loss.  They do NOT require network access.
"""

import json

from qgis.core import QgsPointXY, QgsRectangle
from qgis.testing import start_app, unittest

from swiss_locator.core.results import (
    RESULT_REGISTRY,
    ResultBase,
    WMSLayerResult,
    LocationResult,
    FeatureResult,
    VectorTilesLayerResult,
    STACResult,
    NoResult,
    result_from_data,
)

start_app()


class TestResultRegistry(unittest.TestCase):
    """Verify the auto-registry populated by ResultBase.__init_subclass__."""

    def test_all_types_registered(self):
        expected = {
            "WMSLayerResult",
            "LocationResult",
            "FeatureResult",
            "VectorTilesLayerResult",
            "STACResult",
            "NoResult",
        }
        self.assertEqual(set(RESULT_REGISTRY.keys()), expected)

    def test_registry_maps_to_correct_classes(self):
        self.assertIs(RESULT_REGISTRY["WMSLayerResult"], WMSLayerResult)
        self.assertIs(RESULT_REGISTRY["LocationResult"], LocationResult)
        self.assertIs(RESULT_REGISTRY["FeatureResult"], FeatureResult)
        self.assertIs(RESULT_REGISTRY["VectorTilesLayerResult"], VectorTilesLayerResult)
        self.assertIs(RESULT_REGISTRY["STACResult"], STACResult)
        self.assertIs(RESULT_REGISTRY["NoResult"], NoResult)

    def test_all_registered_classes_inherit_from_base(self):
        for cls in RESULT_REGISTRY.values():
            self.assertTrue(
                issubclass(cls, ResultBase),
                f"{cls.__name__} should inherit from ResultBase",
            )


class TestResultFromData(unittest.TestCase):
    """Test the top-level result_from_data dispatcher."""

    def test_unknown_type_returns_no_result(self):
        definition = json.dumps({"type": "UnknownType"})
        result = result_from_data(definition)
        self.assertIsInstance(result, NoResult)

    def test_missing_type_returns_no_result(self):
        definition = json.dumps({"foo": "bar"})
        result = result_from_data(definition)
        self.assertIsInstance(result, NoResult)


class TestWMSLayerResultRoundTrip(unittest.TestCase):
    """Serialize → deserialize WMSLayerResult and check all fields."""

    def test_full_round_trip(self):
        original = WMSLayerResult(
            layer="ch.swisstopo.pixelkarte-farbe",
            title="Pixelkarte",
            url="https://wms.geo.admin.ch/?VERSION=2.0.0",
            tile_matrix_set="EPSG:2056",
            _format="image/jpeg",
            style="default",
            tile_dimensions="Time=current",
        )
        definition = original.as_definition()
        restored = result_from_data(definition)

        self.assertIsInstance(restored, WMSLayerResult)
        self.assertEqual(restored.layer, original.layer)
        self.assertEqual(restored.title, original.title)
        self.assertEqual(restored.url, original.url)
        self.assertEqual(restored.tile_matrix_set, original.tile_matrix_set)
        self.assertEqual(restored.format, original.format)
        self.assertEqual(restored.style, original.style)
        self.assertEqual(restored.tile_dimensions, original.tile_dimensions)

    def test_minimal_round_trip(self):
        """Optional fields left as None should survive the round-trip."""
        original = WMSLayerResult(
            layer="ch.test",
            title="Test",
            url="https://example.com",
        )
        definition = original.as_definition()
        restored = result_from_data(definition)

        self.assertIsInstance(restored, WMSLayerResult)
        self.assertIsNone(restored.tile_matrix_set)
        self.assertIsNone(restored.style)
        self.assertIsNone(restored.tile_dimensions)

    def test_definition_contains_type_key(self):
        wms = WMSLayerResult("layer", "title", "url")
        data = json.loads(wms.as_definition())
        self.assertEqual(data["type"], "WMSLayerResult")


class TestLocationResultRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        point = QgsPointXY(2600000, 1200000)
        bbox = QgsRectangle(2599000, 1199000, 2601000, 1201000)
        original = LocationResult(
            point=point,
            bbox=bbox,
            layer="ch.swisstopo.swissboundaries3d-gemeinde-flaeche.fill",
            feature_id="123",
            html_label="<b>Bern</b>",
        )
        definition = original.as_definition()
        restored = result_from_data(definition)

        self.assertIsInstance(restored, LocationResult)
        self.assertAlmostEqual(restored.point.x(), point.x(), places=1)
        self.assertAlmostEqual(restored.point.y(), point.y(), places=1)
        self.assertAlmostEqual(restored.bbox.xMinimum(), bbox.xMinimum(), places=1)
        self.assertAlmostEqual(restored.bbox.yMaximum(), bbox.yMaximum(), places=1)
        self.assertEqual(restored.layer, original.layer)
        self.assertEqual(restored.feature_id, original.feature_id)
        self.assertEqual(restored.html_label, original.html_label)

    def test_none_feature_id(self):
        original = LocationResult(
            point=QgsPointXY(8.0, 47.0),
            bbox=QgsRectangle(7.0, 46.0, 9.0, 48.0),
            layer="ch.test",
            feature_id=None,
            html_label="label",
        )
        definition = original.as_definition()
        restored = result_from_data(definition)
        self.assertIsNone(restored.feature_id)


class TestFeatureResultRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        point = QgsPointXY(8.5, 47.3)
        original = FeatureResult(
            point=point,
            layer="ch.bfs.gebaeude_wohnungs_register",
            feature_id="456",
        )
        definition = original.as_definition()
        restored = result_from_data(definition)

        self.assertIsInstance(restored, FeatureResult)
        self.assertAlmostEqual(restored.point.x(), point.x(), places=5)
        self.assertAlmostEqual(restored.point.y(), point.y(), places=5)
        self.assertEqual(restored.layer, original.layer)
        self.assertEqual(restored.feature_id, original.feature_id)


class TestVectorTilesLayerResultRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        original = VectorTilesLayerResult(
            layer="Base map",
            title="Base map",
            url="https://vectortiles.geo.admin.ch/tiles/ch.swisstopo.base.vt/v1.0.0/{z}/{x}/{y}.pbf",
            style="https://vectortiles.geo.admin.ch/styles/ch.swisstopo.basemap.vt/style.json",
        )
        definition = original.as_definition()
        restored = result_from_data(definition)

        self.assertIsInstance(restored, VectorTilesLayerResult)
        self.assertEqual(restored.layer, original.layer)
        self.assertEqual(restored.title, original.title)
        self.assertEqual(restored.url, original.url)
        self.assertEqual(restored.style, original.style)

    def test_minimal_round_trip(self):
        original = VectorTilesLayerResult(layer="test", title="Test")
        restored = result_from_data(original.as_definition())
        self.assertIsNone(restored.url)
        self.assertIsNone(restored.style)


class TestSTACResultRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        original = STACResult(
            collection_id="ch.swisstopo.swissalti3d",
            collection_name="swissALTI3D",
            asset_id="swissalti3d_2020_2600-1200",
            description="Digital elevation model",
            media_type="image/tiff; profile=cloud-optimized",
            href="https://data.geo.admin.ch/ch.swisstopo.swissalti3d/test.tif",
            path="/vsicurl/https://data.geo.admin.ch/test.tif",
        )
        definition = original.as_definition()
        restored = result_from_data(definition)

        self.assertIsInstance(restored, STACResult)
        self.assertEqual(restored.collection_id, original.collection_id)
        self.assertEqual(restored.collection_name, original.collection_name)
        self.assertEqual(restored.asset_id, original.asset_id)
        self.assertEqual(restored.description, original.description)
        self.assertEqual(restored.media_type, original.media_type)
        self.assertEqual(restored.href, original.href)
        self.assertEqual(restored.path, original.path)

    def test_default_path(self):
        original = STACResult("coll_id", "coll_name", "asset", "desc", "type", "href")
        self.assertEqual(original.path, "")
        restored = result_from_data(original.as_definition())
        self.assertEqual(restored.path, "")


class TestSTACResultProperties(unittest.TestCase):
    """Test computed properties on STACResult."""

    def test_is_downloadable(self):
        r = STACResult("c", "n", "asset", "d", "type", "http://example.com")
        self.assertTrue(r.is_downloadable)

    def test_not_downloadable_no_href(self):
        r = STACResult("c", "n", "asset", "d", "type", "")
        self.assertFalse(r.is_downloadable)

    def test_not_downloadable_no_asset_id(self):
        r = STACResult("c", "n", "", "d", "type", "http://example.com")
        self.assertFalse(r.is_downloadable)

    def test_is_streamable(self):
        r = STACResult(
            "c",
            "n",
            "asset",
            "d",
            "image/tiff; profile=cloud-optimized",
            "http://example.com",
        )
        self.assertTrue(r.is_streamable)

    def test_not_streamable_wrong_media_type(self):
        r = STACResult("c", "n", "asset", "d", "image/tiff", "http://example.com")
        self.assertFalse(r.is_streamable)

    def test_is_streamed(self):
        r = STACResult(
            "c",
            "n",
            "asset",
            "d",
            "image/tiff; profile=cloud-optimized",
            "http://example.com",
            path="/vsicurl/http://example.com",
        )
        self.assertTrue(r.is_streamed)

    def test_not_streamed_without_prefix(self):
        r = STACResult(
            "c",
            "n",
            "asset",
            "d",
            "image/tiff; profile=cloud-optimized",
            "http://example.com",
            path="/tmp/local.tif",
        )
        self.assertFalse(r.is_streamed)

    def test_simple_file_type_with_semicolon(self):
        r = STACResult(
            "c", "n", "asset", "d", "image/tiff; profile=cloud-optimized", "href"
        )
        self.assertEqual(r.simple_file_type, "tiff")

    def test_simple_file_type_plain(self):
        r = STACResult("c", "n", "asset", "d", "application/zip", "href")
        self.assertEqual(r.simple_file_type, "zip")


class TestNoResult(unittest.TestCase):
    def test_round_trip(self):
        definition = NoResult.as_definition()
        restored = result_from_data(definition)
        self.assertIsInstance(restored, NoResult)

    def test_definition_contains_type(self):
        data = json.loads(NoResult.as_definition())
        self.assertEqual(data["type"], "NoResult")


if __name__ == "__main__":
    unittest.main()
