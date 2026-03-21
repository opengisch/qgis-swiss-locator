"""
Unit tests for base filter utilities, URL builders, html_stripper,
and constants module.

These tests do NOT require network access or the full QGIS locator pipeline.
"""

from qgis.core import QgsRectangle
from qgis.testing import start_app, unittest

from swiss_locator.core.constants import (
    API_BASE_URL,
    MAP_GEO_ADMIN_URL,
    MAP_SERVER_URL,
    OPENDATA_SWISS_URL,
    PROFILE_URL,
    SEARCH_URL,
    STAC_BASE_URL,
    USER_AGENT,
    VECTOR_TILES_BASE_URL,
    WMS_BASE_URL,
    WMTS_BASE_URL,
)
from swiss_locator.core.filters.map_geo_admin import map_geo_admin_url
from swiss_locator.core.filters.map_geo_admin_stac import (
    map_geo_admin_stac_items_url,
)
from swiss_locator.core.filters.opendata_swiss import opendata_swiss_url
from swiss_locator.core.filters.swiss_locator_filter import (
    InvalidBox,
    SwissLocatorFilter,
)
from swiss_locator.core.profiles.profile_url import profile_url
from swiss_locator.utils.html_stripper import strip_tags

start_app()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants(unittest.TestCase):
    """Verify that constants are well-formed URLs."""

    def test_api_base_url(self):
        self.assertTrue(API_BASE_URL.startswith("https://"))

    def test_search_url_derives_from_base(self):
        self.assertTrue(SEARCH_URL.startswith(API_BASE_URL))

    def test_map_server_url_derives_from_base(self):
        self.assertTrue(MAP_SERVER_URL.startswith(API_BASE_URL))

    def test_profile_url_derives_from_base(self):
        self.assertTrue(PROFILE_URL.startswith(API_BASE_URL))

    def test_all_urls_are_strings(self):
        for url in (
            SEARCH_URL,
            MAP_SERVER_URL,
            PROFILE_URL,
            WMTS_BASE_URL,
            WMS_BASE_URL,
            STAC_BASE_URL,
            VECTOR_TILES_BASE_URL,
            OPENDATA_SWISS_URL,
            MAP_GEO_ADMIN_URL,
        ):
            self.assertIsInstance(url, str)

    def test_user_agent_is_bytes(self):
        self.assertIsInstance(USER_AGENT, bytes)


# ---------------------------------------------------------------------------
# box2geometry
# ---------------------------------------------------------------------------


class TestBox2Geometry(unittest.TestCase):
    """Test SwissLocatorFilter.box2geometry static method."""

    def test_valid_box(self):
        rect = SwissLocatorFilter.box2geometry("BOX(2599000 1199000,2601000 1201000)")
        self.assertIsInstance(rect, QgsRectangle)
        self.assertAlmostEqual(rect.xMinimum(), 2599000.0)
        self.assertAlmostEqual(rect.yMinimum(), 1199000.0)
        self.assertAlmostEqual(rect.xMaximum(), 2601000.0)
        self.assertAlmostEqual(rect.yMaximum(), 1201000.0)

    def test_valid_box_with_decimals(self):
        rect = SwissLocatorFilter.box2geometry("BOX(7.123 46.456,8.789 47.012)")
        self.assertAlmostEqual(rect.xMinimum(), 7.123, places=3)
        self.assertAlmostEqual(rect.yMaximum(), 47.012, places=3)

    def test_invalid_box_raises(self):
        with self.assertRaises(InvalidBox):
            SwissLocatorFilter.box2geometry("not a box")

    def test_incomplete_box_raises(self):
        with self.assertRaises(InvalidBox):
            SwissLocatorFilter.box2geometry("BOX(100 200)")


# ---------------------------------------------------------------------------
# rank2priority
# ---------------------------------------------------------------------------


class TestRank2Priority(unittest.TestCase):
    """Test SwissLocatorFilter.rank2priority static method."""

    def test_rank_1_is_highest(self):
        p = SwissLocatorFilter.rank2priority(1)
        self.assertAlmostEqual(p, 6 / 7)

    def test_rank_7_is_zero(self):
        p = SwissLocatorFilter.rank2priority(7)
        self.assertAlmostEqual(p, 0.0)

    def test_rank_0_is_one(self):
        p = SwissLocatorFilter.rank2priority(0)
        self.assertAlmostEqual(p, 1.0)

    def test_returns_float(self):
        self.assertIsInstance(SwissLocatorFilter.rank2priority(3), float)


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------


class TestMapGeoAdminUrl(unittest.TestCase):
    def test_returns_search_url(self):
        url, params = map_geo_admin_url("bern", "locations", "2056", "de", 10)
        self.assertEqual(url, SEARCH_URL)

    def test_params_contain_search_text(self):
        url, params = map_geo_admin_url("zürich", "locations", "2056", "de", 5)
        self.assertEqual(params["searchText"], "zürich")
        self.assertEqual(params["type"], "locations")
        self.assertEqual(params["lang"], "de")
        self.assertEqual(params["sr"], "2056")
        self.assertEqual(params["limit"], "5")

    def test_params_return_geometry(self):
        _, params = map_geo_admin_url("test", "layers", "21781", "fr", 20)
        self.assertEqual(params["returnGeometry"], "true")


class TestMapGeoAdminStacItemsUrl(unittest.TestCase):
    def test_url_contains_collection_id(self):
        url, params = map_geo_admin_stac_items_url("ch.swisstopo.swissalti3d", 10)
        self.assertIn("ch.swisstopo.swissalti3d", url)
        self.assertTrue(url.startswith(STAC_BASE_URL))

    def test_limit_param(self):
        _, params = map_geo_admin_stac_items_url("ch.test", 5)
        self.assertEqual(params["limit"], "5")


class TestOpendataSwissUrl(unittest.TestCase):
    def test_url(self):
        url, params = opendata_swiss_url("wasser")
        self.assertEqual(url, OPENDATA_SWISS_URL)

    def test_query_contains_search_and_wildcard(self):
        _, params = opendata_swiss_url("wasser")
        self.assertIn("wasser", params["q"])
        self.assertIn("title:wasser*", params["q"])

    def test_multi_word_search(self):
        _, params = opendata_swiss_url("erneuerbare energie")
        self.assertIn("title:erneuerbare*", params["q"])
        self.assertIn("title:energie*", params["q"])

    def test_filter_wms_wmts(self):
        _, params = opendata_swiss_url("test")
        self.assertIn("WMS", params["fq"])
        self.assertIn("WMTS", params["fq"])


class TestProfileUrl(unittest.TestCase):
    def test_url(self):
        url, params = profile_url('{"type":"LineString","coordinates":[[0,0],[1,1]]}')
        self.assertEqual(url, PROFILE_URL)

    def test_geom_param(self):
        geojson = (
            '{"type":"LineString","coordinates":[[2600000,1200000],[2601000,1201000]]}'
        )
        _, params = profile_url(geojson)
        self.assertEqual(params["geom"], geojson)


# ---------------------------------------------------------------------------
# html_stripper
# ---------------------------------------------------------------------------


class TestHtmlStripper(unittest.TestCase):
    def test_strips_bold(self):
        self.assertEqual(strip_tags("<b>Bern</b>"), "Bern")

    def test_strips_nested_tags(self):
        self.assertEqual(
            strip_tags("<div><span>Hello</span> <b>World</b></div>"),
            "Hello World",
        )

    def test_plain_text_unchanged(self):
        self.assertEqual(strip_tags("plain text"), "plain text")

    def test_empty_string(self):
        self.assertEqual(strip_tags(""), "")

    def test_entities_preserved(self):
        # HTML entities should be fed through as-is by the parser
        result = strip_tags("<b>A &amp; B</b>")
        self.assertIn("A", result)
        self.assertIn("B", result)


if __name__ == "__main__":
    unittest.main()
