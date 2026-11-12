"""Unit tests of the dataset generators, on fake responses."""

import unittest

from datetime import UTC, datetime, timedelta

from scripts import summary
from scripts.datasets import DATASETS, map_geo_admin, opendata_swiss
from scripts.datasets.opendata_swiss import HarvestError
from scripts.http_client import HttpError
from swiss_locator.remote_data import spec
from swiss_locator.utils import safe_xml

CAPABILITIES_1_3_0 = b"""<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms">
  <Service><Name>WMS</Name><Title> Geoportal Kanton Zug </Title></Service>
  <Capability>
    <Layer>
      <Title>Root without name</Title>
      <Layer><Name>zg_wald</Name><Title>Wald</Title></Layer>
      <Layer>
        <Name>zg_naturschutz</Name><Title>Naturschutz</Title>
        <Layer><Name>zg_naturschutz_objekte</Name></Layer>
      </Layer>
      <Layer><Name>zg_wald</Name><Title>Duplicate</Title></Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>
"""

CAPABILITIES_1_1_1 = b"""<?xml version="1.0"?>
<WMT_MS_Capabilities version="1.1.1">
  <Service><Title>Old server</Title></Service>
  <Capability><Layer><Name>a</Name><Title>A</Title></Layer></Capability>
</WMT_MS_Capabilities>
"""

EXCEPTION = b"""<?xml version="1.0"?>
<ServiceExceptionReport version="1.3.0"><ServiceException>Oops</ServiceException>
</ServiceExceptionReport>
"""


class TestDatasets(unittest.TestCase):
    def test_one_dataset_per_published_file(self):
        self.assertEqual(
            sorted(dataset.file_name for dataset in DATASETS),
            sorted(spec.DATA_FILES),
        )


class TestMapGeoAdmin(unittest.TestCase):
    def fake_get_json(self, configs, search_errors=None):
        """Answer the layers configuration by language, and the feature search
        by layer: an HttpError of search_errors, or no result."""
        search_errors = search_errors or {}

        def get_json(url, params):
            if url == map_geo_admin.LAYERS_CONFIG_URL:
                return configs.get(params["lang"], {})
            self.assertEqual(url, map_geo_admin.SEARCH_URL)
            self.assertEqual(params["type"], "featuresearch")
            error = search_errors.get(params["features"])
            if error:
                raise error
            return {"results": []}

        return get_json

    def test_build(self):
        configs = {
            "de": {
                "ch.b": {"label": "B de", "searchable": True},
                "ch.a": {"label": "A de", "searchable": True},
                "ch.hidden": {"label": "Hidden", "searchable": False},
            },
            "fr": {"ch.a": {"label": "A fr", "searchable": True}},
            "en": {"ch.a": {"searchable": True}},
        }

        layers = map_geo_admin.build(None, self.fake_get_json(configs))
        self.assertEqual(list(layers), ["ch.a", "ch.b"])
        self.assertEqual(layers["ch.a"]["de"], "A de")
        self.assertEqual(layers["ch.a"]["fr"], "A fr")
        # no label: the layer id
        self.assertEqual(layers["ch.a"]["en"], "ch.a")
        self.assertEqual(layers["ch.b"], {"de": "B de"})

    def test_layer_without_search_index_is_left_out(self):
        configs = {"de": {"ch.a": {"searchable": True}, "ch.b": {"searchable": True}}}
        errors = {"ch.b": HttpError("HTTP error 404", status=404)}
        layers = map_geo_admin.build({"ch.b": {}}, self.fake_get_json(configs, errors))
        self.assertEqual(list(layers), ["ch.a"])

    def test_unchecked_layer_is_kept_if_published(self):
        configs = {"de": {"ch.a": {"searchable": True}, "ch.b": {"searchable": True}}}
        errors = {
            "ch.a": HttpError("HTTP error 503", status=503),
            "ch.b": HttpError("unreachable"),
        }
        with self.assertLogs(map_geo_admin.log, "WARNING"):
            layers = map_geo_admin.build(
                {"ch.a": {"de": "A"}}, self.fake_get_json(configs, errors)
            )
        self.assertEqual(list(layers), ["ch.a"])


class TestOpendataSwiss(unittest.TestCase):
    def test_datasets_are_paginated(self):
        calls = []

        def get_json(url, params):
            calls.append(params["start"])
            page = params["start"] // opendata_swiss.PAGE_SIZE
            results = [{"name": f"page {page}"}] if page < 3 else []
            return {
                "result": {"count": 3 * opendata_swiss.PAGE_SIZE, "results": results}
            }

        names = [d["name"] for d in opendata_swiss.datasets(get_json)]
        self.assertEqual(names, ["page 0", "page 1", "page 2"])
        self.assertEqual(len(calls), 3)

    def test_service_urls(self):
        datasets = [
            {
                "resources": [
                    {
                        "url": "https://geo.zg.ch/wms?SERVICE=WMS&REQUEST=GetCapabilities"
                    },
                    {"url": "http://geo.zg.ch/wms?request=GetMap&LAYERS=a"},
                    {"url": "https://mapserver.ch/cgi?map=x.map", "format": "WMS"},
                    {"url": "https://wms.geo.admin.ch/?LAYERS=ch.a"},
                    {"url": "https://map.geo.admin.ch/?topic=ech", "format": "WMS"},
                    {
                        "url": "https://zh.ch/wms?Service=WMS&amp;Request=GetCapabilities"
                    },
                    {"url": "https://geo.zg.ch/wfs"},
                    {"url": "ftp://geo.zg.ch/wms"},
                    {"format": "WMS"},
                ]
            },
            {"resources": None},
            {},
        ]
        self.assertEqual(
            opendata_swiss.service_urls(datasets),
            [
                "https://geo.zg.ch/wms",
                "https://mapserver.ch/cgi?map=x.map",
                "https://zh.ch/wms",
            ],
        )

    def test_parse_capabilities_1_3_0(self):
        service = opendata_swiss.parse_capabilities(
            "https://geo.zg.ch/wms", safe_xml.fromstring(CAPABILITIES_1_3_0)
        )
        self.assertEqual(
            service,
            {
                "url": "https://geo.zg.ch/wms",
                "version": "1.3.0",
                "title": "Geoportal Kanton Zug",
                "layers": [
                    ["zg_naturschutz", "Naturschutz"],
                    ["zg_naturschutz_objekte", "zg_naturschutz_objekte"],
                    ["zg_wald", "Wald"],
                ],
            },
        )

    def test_parse_capabilities_1_1_1(self):
        service = opendata_swiss.parse_capabilities(
            "https://old.ch/wms", safe_xml.fromstring(CAPABILITIES_1_1_1)
        )
        self.assertEqual(service["version"], "1.1.1")
        self.assertEqual(service["layers"], [["a", "A"]])

    def test_harvest_failures(self):
        def get_error(url):
            raise HttpError("HTTP error 503", status=503)

        for get, reason in (
            (get_error, "HTTP error 503"),
            (lambda url: b"<html>not xml", HarvestError.NOT_CAPABILITIES),
            (lambda url: EXCEPTION, HarvestError.NOT_CAPABILITIES),
            (
                lambda url: b"<WMS_Capabilities><Capability/></WMS_Capabilities>",
                HarvestError.NO_LAYER,
            ),
        ):
            with self.subTest(reason=reason):
                self.assertEqual(
                    opendata_swiss._try_harvest("https://a.ch/wms", get),
                    (None, reason),
                )

    def test_harvest_retries_lowercase_path(self):
        def get(url):
            if "/ows/Naturschutz" in url:
                raise HttpError("HTTP error 404", status=404)
            return CAPABILITIES_1_3_0

        service = opendata_swiss.harvest("https://geo.zg.ch/ows/Naturschutz", get)
        self.assertEqual(service["url"], "https://geo.zg.ch/ows/naturschutz")


def ckan(*urls):
    """Fake opendata.swiss API, with one dataset referencing the URLs."""

    def get_json(url, params):
        resources = [{"url": url} for url in urls]
        return {"result": {"count": 1, "results": [{"resources": resources}]}}

    return get_json


def servers(*down):
    """Fake servers, all serving the same capabilities but the ones down."""

    def get(url):
        if url.startswith(down):
            raise HttpError("unreachable", "connection refused")
        return CAPABILITIES_1_3_0

    return get


def published_service(url, age_days):
    harvested = datetime.now(UTC) - timedelta(days=age_days)
    return {
        "url": url,
        "version": "1.3.0",
        "title": "Published",
        "harvested": harvested.strftime(spec.TIMESTAMP_FORMAT),
        "layers": [["published_layer", "Published layer"]],
    }


class TestOpendataSwissBuild(unittest.TestCase):
    def test_build(self):
        data = opendata_swiss.build(
            None,
            ckan("https://geo.zg.ch/wms", "https://down.ch/wms"),
            servers("https://down.ch"),
        )
        self.assertEqual(
            [s["url"] for s in data["services"]], ["https://geo.zg.ch/wms"]
        )
        self.assertEqual(opendata_swiss.count(data), 3)
        self.assertTrue(data["services"][0]["harvested"])

    def test_offline_service_keeps_published_layers(self):
        previous = {
            "services": [
                published_service("https://down.ch/wms", age_days=10),
                published_service("https://down.ch/old", age_days=60),
                published_service("https://geo.zg.ch/wms", age_days=10),
            ]
        }
        data = opendata_swiss.build(
            previous,
            ckan("https://down.ch/wms", "https://down.ch/old", "https://geo.zg.ch/wms"),
            servers("https://down.ch"),
        )
        services = {s["url"]: s for s in data["services"]}
        # offline for 10 days: kept as published
        self.assertEqual(services["https://down.ch/wms"], previous["services"][0])
        # offline for 60 days: dropped
        self.assertNotIn("https://down.ch/old", services)
        # online: harvested again
        self.assertEqual(len(services["https://geo.zg.ch/wms"]["layers"]), 3)

    def test_offline_service_found_by_lowercase_url(self):
        previous = {"services": [published_service("https://down.ch/wms/wald", 1)]}
        data = opendata_swiss.build(
            previous, ckan("https://down.ch/wms/Wald"), servers("https://down.ch")
        )
        self.assertEqual(data["services"], previous["services"])

    def test_unreadable_previous_is_ignored(self):
        data = opendata_swiss.build(
            {"services": [{"url": "u"}]}, ckan("https://geo.zg.ch/wms"), servers()
        )
        self.assertEqual(len(data["services"]), 1)

    def test_summary(self):
        with self.assertLogs(summary, "INFO") as logs:
            opendata_swiss.build(
                None,
                ckan("https://geo.zg.ch/wms", "https://down.ch/wms"),
                servers("https://down.ch"),
            )
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            [
                "2 services: 1 harvested, 0 kept from the published version, 1 failed",
                "  failed, unreachable: 1",
            ],
        )


if __name__ == "__main__":
    unittest.main()
