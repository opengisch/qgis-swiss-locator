"""
Unit tests for the WMS URL helpers and the opendata.swiss WMS layers index.
Does NOT require network access.
"""

from qgis.testing import start_app, unittest

from swiss_locator.core.filters.opendata_swiss import WmsLayerIndex
from swiss_locator.remote_data import spec
from swiss_locator.utils import wms

start_app()


class TestWmsUrls(unittest.TestCase):
    def test_service_url_drops_request_parameters(self):
        self.assertEqual(
            wms.service_url(
                "https://Example.CH/ows?service=WMS&Request=GetMap&LAYERS=a&bbox=1,2,3,4"
            ),
            "https://example.ch/ows",
        )

    def test_service_url_keeps_other_parameters(self):
        self.assertEqual(
            wms.service_url("https://example.ch/mapserv?map=/maps/a.map&VERSION=1.1.1"),
            "https://example.ch/mapserv?map=%2Fmaps%2Fa.map",
        )

    def test_html_escaped_separators(self):
        url = "https://zh.ch/wms?Service=WMS&amp;Request=GetMap&amp;Layers=a"
        self.assertEqual(wms.service_url(url), "https://zh.ch/wms")
        self.assertEqual(wms.query_parameter(url, "LAYERS"), "a")

    def test_service_url_rejects_non_http(self):
        for url in ("ftp://example.ch/wms", "not a url", ""):
            with self.subTest(url=url):
                self.assertIsNone(wms.service_url(url))

    def test_query_parameter_is_case_insensitive(self):
        url = "https://example.ch/wms?layers=a,b&Version=1.1.1"
        self.assertEqual(wms.query_parameter(url, "LAYERS"), "a,b")
        self.assertEqual(wms.query_parameter(url, "version"), "1.1.1")
        self.assertIsNone(wms.query_parameter(url, "STYLES"))

    def test_capabilities_url(self):
        self.assertEqual(
            wms.capabilities_url("https://example.ch/wms"),
            "https://example.ch/wms?SERVICE=WMS&REQUEST=GetCapabilities",
        )
        self.assertEqual(
            wms.capabilities_url("https://example.ch/wms?map=a"),
            "https://example.ch/wms?map=a&SERVICE=WMS&REQUEST=GetCapabilities",
        )

    def test_provider_url(self):
        # same URL as the one historically used for geo.admin.ch
        self.assertEqual(
            wms.provider_url("https://wms.geo.admin.ch/"),
            "https://wms.geo.admin.ch/?VERSION%3D1.3.0",
        )
        # no "&" left, it would end the url key of the provider URI
        self.assertEqual(
            wms.provider_url("https://example.ch/wms?map=%2Fa.map", "1.1.1"),
            "https://example.ch/wms?map%3D%252Fa.map%26VERSION%3D1.1.1",
        )

    def test_is_geo_admin(self):
        self.assertTrue(wms.is_geo_admin("https://wms.geo.admin.ch/?LAYERS=a"))
        self.assertTrue(wms.is_geo_admin("http://wmts.geo.admin.ch/1.0.0"))
        self.assertTrue(wms.is_geo_admin("https://map.geo.admin.ch/?topic=ech"))
        self.assertTrue(wms.is_geo_admin("https://www.geo.admin.ch/de/wms.html"))
        self.assertFalse(wms.is_geo_admin("https://geodienste.ch/wms"))
        self.assertFalse(wms.is_geo_admin("https://notgeo.admin.ch/wms"))
        self.assertFalse(wms.is_geo_admin("https://geo.admin.ch.example.com/wms"))


INDEX_DATA = {
    "services": [
        {
            "url": "https://services.geo.zg.ch/wms",
            "version": "1.3.0",
            "title": "Kanton Zug",
            "layers": [
                ["zg_naturschutz", "Naturschutzgebiete"],
                ["zg_naturschutz_objekte", "Naturschutzobjekte"],
                ["zg_wald", "Wald"],
            ],
        },
        {
            "url": "https://example.ch/mapserv?map=a",
            "title": "",
            "layers": [["naturschutz", ""], ["other", "Naturschutz Inventar"]],
        },
    ]
}


class TestWmsLayerIndex(unittest.TestCase):
    def setUp(self):
        self.index = WmsLayerIndex(INDEX_DATA)

    def names(self, text, limit=10):
        return [layer.name for layer, _ in self.index.search(text, limit)]

    def test_size(self):
        self.assertEqual(len(self.index), 5)

    def test_search_by_name(self):
        self.assertEqual(self.names("zg_naturschutz")[0], "zg_naturschutz")

    def test_search_is_case_insensitive(self):
        self.assertEqual(self.names("ZG_WALD"), ["zg_wald"])

    def test_ranking(self):
        """Exact match first, then title prefixes, sorted by title."""
        self.assertEqual(
            self.names("naturschutz"),
            ["naturschutz", "other", "zg_naturschutz", "zg_naturschutz_objekte"],
        )

    def test_name_prefix_before_name_substring(self):
        self.assertEqual(
            self.names("zg_natur"), ["zg_naturschutz", "zg_naturschutz_objekte"]
        )
        self.assertEqual(self.names("schutz_obj"), ["zg_naturschutz_objekte"])

    def test_scores_decrease(self):
        scores = [score for _, score in self.index.search("naturschutz", 10)]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(scores[0], 1)

    def test_words_match_service_title(self):
        self.assertEqual(self.names("wald zug"), ["zg_wald"])

    def test_limit(self):
        self.assertEqual(len(self.names("naturschutz", limit=2)), 2)

    def test_no_match(self):
        self.assertEqual(self.names("xyzzy"), [])
        self.assertEqual(self.names("   "), [])

    def test_defaults(self):
        """A layer without title is titled by its name, the version defaults."""
        layer = self.index.search("naturschutz", 1)[0][0]
        self.assertEqual(layer.title, "naturschutz")
        self.assertEqual(layer.version, wms.DEFAULT_VERSION)
        self.assertEqual(layer.service_url, "https://example.ch/mapserv?map=a")

    def test_invalid_data(self):
        for data in (
            {},
            {"services": [{"layers": [["name", "title"]]}]},
            {"services": [{"url": "u"}]},
            {"services": [{"url": "u", "layers": [["name"]]}]},
        ):
            with self.subTest(data=data):
                with self.assertRaises(spec.InvalidDataFile):
                    WmsLayerIndex(data)


if __name__ == "__main__":
    unittest.main()
