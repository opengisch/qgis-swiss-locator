"""
Basic / unit tests for Swiss Locator.

These tests do not require the full QGIS locator pipeline.
They verify URL construction, API responses, and data helpers.
"""

import json
from urllib.parse import urlencode
from urllib.request import urlopen, Request

from qgis._core import QgsStacExtent
from qgis.core import QgsStacCollection
from qgis.testing import start_app, unittest

from swiss_locator.core.filters.map_geo_admin_stac import (
    collections_to_searchable_strings,
)
from swiss_locator.core.filters.opendata_swiss import opendata_swiss_url

start_app()


class TestOpendataSwissUrl(unittest.TestCase):
    """Tests for the opendata.swiss URL / query-parameter builder."""

    def test_opendata_swiss_url(self):
        url, params = opendata_swiss_url("wasser")
        self.assertEqual(url, "https://opendata.swiss/api/3/action/package_search")
        self.assertIn("wasser", params["q"])
        self.assertIn("title:wasser*", params["q"])
        self.assertIn("res_format", params["fq"])

    def test_opendata_swiss_search(self):
        """Test that the opendata.swiss API returns WMS/WMTS results."""
        url, params = opendata_swiss_url("wasser")
        full_url = f"{url}?{urlencode(params)}"
        req = Request(
            full_url, headers={"User-Agent": "Mozilla/5.0 QGIS Swiss Locator Test"}
        )
        response = urlopen(req, timeout=10)
        data = json.loads(response.read().decode("utf-8"))

        self.assertTrue(data["success"])
        results = data["result"]["results"]
        self.assertGreater(len(results), 0, "Expected at least one result for 'wasser'")

        first = results[0]
        self.assertIn("title", first)
        self.assertIn("resources", first)

    def test_opendata_swiss_search_partial_word(self):
        """Test that partial words like 'asia' find 'Asiatische' datasets."""
        url, params = opendata_swiss_url("asia")
        full_url = f"{url}?{urlencode(params)}"
        req = Request(
            full_url, headers={"User-Agent": "Mozilla/5.0 QGIS Swiss Locator Test"}
        )
        response = urlopen(req, timeout=10)
        data = json.loads(response.read().decode("utf-8"))

        self.assertTrue(data["success"])
        results = data["result"]["results"]
        self.assertGreater(len(results), 0, "Expected results for 'asia'")

        titles = [r["title"].get("de", "") for r in results]
        self.assertTrue(
            any("asiat" in t.lower() for t in titles if t),
            f"Expected 'Asiatische' in titles, got: {titles}",
        )


class TestStacHelpers(unittest.TestCase):
    """Tests for STAC collection helpers (no network needed)."""

    @classmethod
    def setUpClass(cls):
        cls.test_strings = (
            ("ch.swisstopo.swissalti3d", "swissALTI3D"),
            ("ch.bakom.mobilnetz-2g", "2G - GSM / EDGE Verfügbarkeit"),
            (
                "ch.bafu.wald-wasserverfuegbarkeit_boden",
                "Wasserverfügbarkeit im Boden (Standortwasserbilanz)",
            ),
        )
        cls.collections = {}
        for key, title in cls.test_strings:
            cls.collections[key] = QgsStacCollection(
                key, None, None, [], None, QgsStacExtent()
            )
            cls.collections[key].setTitle(title)

    def test_collections_to_searchable_strings(self):
        search_strings, search_ids = collections_to_searchable_strings(self.collections)

        self.assertEqual(
            search_strings,
            [
                "swissalti3d ch.swisstopo.swissalti3d",
                "2g - gsm / edge verfügbarkeit ch.bakom.mobilnetz-2g",
                "wasserverfügbarkeit im boden (standortwasserbilanz) ch.bafu.wald-wasserverfuegbarkeit_boden",
            ],
        )


if __name__ == "__main__":
    unittest.main()
