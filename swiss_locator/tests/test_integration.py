"""
Integration tests for Swiss Locator filters.

These tests exercise the full QGIS QgsLocator pipeline: filter registration,
network requests, signal emission, and result collection.  They require a
running X server (or xvfb) and network access.
"""

import json

from qgis.PyQt.QtTest import QSignalSpy
from qgis.core import QgsLocator, QgsLocatorContext
from qgis.testing import start_app, unittest
from qgis.testing.mocked import get_iface

from swiss_locator.core.filters.swiss_locator_filter_layer import (
    SwissLocatorFilterLayer,
)
from swiss_locator.core.filters.swiss_locator_filter_location import (
    SwissLocatorFilterLocation,
)
from swiss_locator.core.filters.swiss_locator_filter_feature import (
    SwissLocatorFilterFeature,
)
from swiss_locator.core.filters.swiss_locator_filter_vector_tiles import (
    SwissLocatorFilterVectorTiles,
)
from swiss_locator.core.filters.swiss_locator_filter_wmts import (
    SwissLocatorFilterWMTS,
)

start_app()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_filter(filter_instance, search, timeout=30000):
    """Run a filter through QgsLocator and return collected results.

    Each result is a dict with keys: displayString, description, group, userData.
    """
    results = []

    def got_hit(result):
        results.append(
            {
                "displayString": result.displayString,
                "description": result.description,
                "group": result.group,
                "userData": result.userData,
            }
        )

    loc = QgsLocator()
    loc.registerFilter(filter_instance)
    loc.foundResult.connect(got_hit)

    spy = QSignalSpy(loc.finished)
    loc.fetchResults(search, QgsLocatorContext())
    spy.wait(timeout)

    return results


def _user_data_type(result_dict):
    """Extract the 'type' field from a result's JSON userData."""
    try:
        return json.loads(result_dict["userData"]).get("type", "")
    except (json.JSONDecodeError, TypeError):
        return ""


# ---------------------------------------------------------------------------
# Location filter
# ---------------------------------------------------------------------------


class TestLocatorFilterLocation(unittest.TestCase):
    """Integration tests for the Location filter (geo.admin.ch search)."""

    def _search(self, text, timeout=30000):
        return _run_filter(SwissLocatorFilterLocation(get_iface()), text, timeout)

    def test_location_bern(self):
        """'Bern' should return location results."""
        results = self._search("Bern")
        real = [r for r in results if _user_data_type(r) == "LocationResult"]
        self.assertGreater(
            len(real), 0, f"Expected LocationResult for 'Bern', got: {results}"
        )

    def test_location_zurich(self):
        """'Zürich' should return location results."""
        results = self._search("Zürich")
        real = [r for r in results if _user_data_type(r) == "LocationResult"]
        self.assertGreater(len(real), 0, "Expected LocationResult for 'Zürich'")

    def test_location_result_has_bbox(self):
        """Location results should contain a valid bbox in userData."""
        results = self._search("Lausanne")
        real = [r for r in results if _user_data_type(r) == "LocationResult"]
        self.assertGreater(len(real), 0)
        data = json.loads(real[0]["userData"])
        self.assertIn("bbox", data)
        self.assertIn("point", data)

    def test_location_short_query_returns_nothing(self):
        """A single character should not trigger any results (minimum_search_length=2)."""
        results = self._search("B")
        self.assertEqual(len(results), 0)

    def test_location_no_result(self):
        """Gibberish should return 'No result found.'."""
        results = self._search("xyzzy98765qqq")
        self.assertTrue(
            any("No result" in r["displayString"] for r in results),
            f"Expected 'No result found.' for gibberish, got: {results}",
        )


# ---------------------------------------------------------------------------
# Feature filter
# ---------------------------------------------------------------------------


class TestLocatorFilterFeature(unittest.TestCase):
    """Integration tests for the Feature filter (geo.admin.ch feature search)."""

    def _search(self, text, timeout=30000):
        return _run_filter(SwissLocatorFilterFeature(get_iface()), text, timeout)

    def test_feature_search(self):
        """'Bern' (4+ chars) should find features."""
        results = self._search("Bern")
        real = [r for r in results if _user_data_type(r) == "FeatureResult"]
        self.assertGreater(
            len(real), 0, f"Expected FeatureResult for 'Bern', got: {results}"
        )

    def test_feature_result_has_point(self):
        """Feature results should contain a point in userData."""
        results = self._search("Zürich")
        real = [r for r in results if _user_data_type(r) == "FeatureResult"]
        if len(real) > 0:
            data = json.loads(real[0]["userData"])
            self.assertIn("point", data)
            self.assertIn("layer", data)
            self.assertIn("feature_id", data)

    def test_feature_short_query_returns_nothing(self):
        """Queries shorter than 4 chars should not trigger results."""
        results = self._search("Be")
        self.assertEqual(len(results), 0)

    def test_feature_no_result(self):
        """Gibberish should produce 'No result found.'."""
        results = self._search("xyzzy98765qqq")
        self.assertTrue(
            any("No result" in r["displayString"] for r in results),
            f"Expected 'No result found.', got: {results}",
        )


# ---------------------------------------------------------------------------
# WMTS filter
# ---------------------------------------------------------------------------


class TestLocatorFilterWMTS(unittest.TestCase):
    """Integration test for the WMTS locator filter."""

    def _search(self, text, timeout=30000):
        return _run_filter(SwissLocatorFilterWMTS(get_iface()), text, timeout)

    def test_wmts_pixelkarte(self):
        results = self._search("pixelkarte-farbe")
        self.assertGreater(
            len(results), 0, "Expected WMTS results for 'pixelkarte-farbe'"
        )
        self.assertTrue(results[0]["displayString"].startswith("National Map"))

    def test_wmts_result_type(self):
        """WMTS results should have WMSLayerResult as userData type."""
        results = self._search("pixelkarte-farbe")
        real = [r for r in results if _user_data_type(r) == "WMSLayerResult"]
        self.assertGreater(len(real), 0)

    def test_wmts_result_has_tile_matrix_set(self):
        """WMTS results should include a tile_matrix_set."""
        results = self._search("pixelkarte-farbe")
        real = [r for r in results if _user_data_type(r) == "WMSLayerResult"]
        self.assertGreater(len(real), 0)
        data = json.loads(real[0]["userData"])
        self.assertIsNotNone(data.get("tile_matrix_set"))

    def test_wmts_swissimage(self):
        """'swissimage' should return WMTS results."""
        results = self._search("swissimage")
        real = [r for r in results if _user_data_type(r) == "WMSLayerResult"]
        self.assertGreater(len(real), 0, "Expected WMTS results for 'swissimage'")

    def test_wmts_no_result(self):
        """Gibberish should produce no real results."""
        results = self._search("xyzzy98765qqq")
        real = [r for r in results if _user_data_type(r) == "WMSLayerResult"]
        self.assertEqual(len(real), 0)


# ---------------------------------------------------------------------------
# Vector Tiles filter
# ---------------------------------------------------------------------------


class TestLocatorFilterVectorTiles(unittest.TestCase):
    """Integration tests for the Vector Tiles filter (local, no network)."""

    def _search(self, text, timeout=5000):
        return _run_filter(SwissLocatorFilterVectorTiles(get_iface()), text, timeout)

    def test_empty_search_returns_all(self):
        """Empty search (minimum_search_length=0) should return all 3 base maps."""
        results = self._search("")
        real = [r for r in results if _user_data_type(r) == "VectorTilesLayerResult"]
        self.assertEqual(len(real), 3, f"Expected 3 vector tile layers, got: {results}")

    def test_search_base_map(self):
        """'base map' should match at least the 'Base map' entry."""
        results = self._search("base map")
        real = [r for r in results if _user_data_type(r) == "VectorTilesLayerResult"]
        self.assertGreater(len(real), 0)
        titles = [r["displayString"] for r in real]
        self.assertIn("Base map", titles)

    def test_search_light(self):
        """'light' should match 'Light base map'."""
        results = self._search("light")
        real = [r for r in results if _user_data_type(r) == "VectorTilesLayerResult"]
        self.assertEqual(len(real), 1)
        self.assertEqual(real[0]["displayString"], "Light base map")

    def test_search_imagery(self):
        """'imagery' should match 'Imagery base map'."""
        results = self._search("imagery")
        real = [r for r in results if _user_data_type(r) == "VectorTilesLayerResult"]
        self.assertEqual(len(real), 1)
        self.assertEqual(real[0]["displayString"], "Imagery base map")

    def test_no_match(self):
        """A query that doesn't match any keyword returns no VectorTilesLayerResult."""
        results = self._search("xyzzy")
        real = [r for r in results if _user_data_type(r) == "VectorTilesLayerResult"]
        self.assertEqual(len(real), 0)

    def test_result_has_url_and_style(self):
        """Each VectorTiles result should carry url and style in userData."""
        results = self._search("")
        real = [r for r in results if _user_data_type(r) == "VectorTilesLayerResult"]
        for r in real:
            data = json.loads(r["userData"])
            self.assertTrue(data.get("url"), f"Missing url in {data}")
            self.assertTrue(data.get("style"), f"Missing style in {data}")


# ---------------------------------------------------------------------------
# Layer filter (geo.admin + opendata.swiss)
# ---------------------------------------------------------------------------


class TestLocatorFilterLayer(unittest.TestCase):
    """Integration test for the Layer locator filter (geo.admin + opendata.swiss)."""

    def _search(self, text, timeout=30000):
        return _run_filter(SwissLocatorFilterLayer(get_iface()), text, timeout)

    # -- geo.admin.ch results ------------------------------------------------

    def test_geoadmin_search(self):
        """Searching 'pixelkarte' should return geo.admin layers."""
        results = self._search("pixelkarte")
        geoadmin = [r for r in results if r["group"] == "Swiss Geoportal"]
        self.assertGreater(
            len(geoadmin),
            0,
            f"Expected geo.admin results for 'pixelkarte', got: {results}",
        )

    def test_geoadmin_result_type(self):
        """geo.admin layer results should be WMSLayerResult."""
        results = self._search("pixelkarte")
        geoadmin = [
            r
            for r in results
            if r["group"] == "Swiss Geoportal"
            and _user_data_type(r) == "WMSLayerResult"
        ]
        self.assertGreater(len(geoadmin), 0)

    # -- opendata.swiss results via GetCapabilities --------------------------

    def test_opendata_swiss_layer_asiat(self):
        """'asiat' should return opendata.swiss layers (Asiatische Hornisse)."""
        results = self._search("asiat")
        opendata = [r for r in results if r["group"] == "opendata.swiss"]
        self.assertGreater(
            len(opendata),
            0,
            f"Expected opendata.swiss results for 'asiat', got all: {results}",
        )

    def test_opendata_swiss_layer_asia(self):
        """'asia' (partial word) should also return opendata.swiss layers."""
        results = self._search("asia")
        opendata = [r for r in results if r["group"] == "opendata.swiss"]
        self.assertGreater(
            len(opendata),
            0,
            f"Expected opendata.swiss results for 'asia', got all: {results}",
        )

    def test_opendata_swiss_layer_wasser(self):
        """'wasser' should return opendata.swiss WMS layers."""
        results = self._search("wasser")
        opendata = [r for r in results if r["group"] == "opendata.swiss"]
        self.assertGreater(
            len(opendata),
            0,
            f"Expected opendata.swiss results for 'wasser', got all: {results}",
        )

    def test_no_result_for_gibberish(self):
        """A nonsense query should return 'No result found.'."""
        results = self._search("xyzzy12345zzz")
        self.assertTrue(
            any("No result" in r["displayString"] for r in results),
            f"Expected 'No result found.' for gibberish, got: {results}",
        )


if __name__ == "__main__":
    unittest.main()
