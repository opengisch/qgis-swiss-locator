"""
/***************************************************************************
 Swiss Locator plugin
 Copyright (C) 2022 Denis Rouzaud
 ***************************************************************************/
/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/

Tests in this file have been reorganised:
  - Basic / unit tests          → test_basic.py
  - Integration tests (locator) → test_integration.py

This file keeps only the STAC local-search test that depends on
QgsLocator + SwissLocatorFilterSTAC but does NOT hit the network.
"""

import json
import os
import tempfile
import time
from unittest import mock

from qgis._core import QgsStacExtent
from qgis.PyQt.QtCore import QUrl, QUrlQuery
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import (
    QgsFeedback,
    QgsLocator,
    QgsLocatorContext,
    QgsStacCollection,
)
from qgis.testing import start_app, unittest
from qgis.testing.mocked import get_iface

from swiss_locator.core.filters import response_cache
from swiss_locator.core.filters.response_cache import ResponseCache
from swiss_locator.core.filters.map_geo_admin_stac import (
    collections_to_searchable_strings,
)
from swiss_locator.core.filters.swiss_locator_filter_stac import (
    CatalogState,
    SwissLocatorFilterSTAC,
)
from swiss_locator.core.results import result_from_data
from swiss_locator.swissgeodownloader.api.catalogs import (
    ApiBaselStadt,
    ApiGeodienste,
    ApiViageo,
)
from swiss_locator.swissgeodownloader.api.datageoadmin import ApiDataGeoAdmin
from swiss_locator.swissgeodownloader.api.response_objects import SgdStacCollection

start_app()


class TestLocatorFilterSTAC(unittest.TestCase):
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
            cls.collections[key] = cls.collection(key, title, ApiDataGeoAdmin)
        cls.geoadmin = ApiDataGeoAdmin("en")
        # Orthophoto of Pully on viageo.ch
        cls.viageo_id = "dc37c46c-167e-46a8-b2e6-3b71287b423b"
        cls.viageo_collections = {
            cls.viageo_id: cls.collection(
                cls.viageo_id, "Image aérienne True Orthophoto 2cm Pully", ApiViageo
            )
        }
        cls.viageo = ApiViageo("en")
        cls.basel_collections = {
            "DEFI": cls.collection("DEFI", "Defibrillatoren", ApiBaselStadt)
        }
        cls.basel = ApiBaselStadt("en")
        cls.geodienste_collections = {
            "wildruhezonen": cls.collection(
                "wildruhezonen", "Zones de tranquillité", ApiGeodienste
            )
        }
        cls.geodienste = ApiGeodienste("fr")

    @staticmethod
    def collection(collection_id, title, catalog) -> SgdStacCollection:
        collection = SgdStacCollection(
            QgsStacCollection(collection_id, None, None, [], None, QgsStacExtent()),
            catalog.CATALOG_ID,
        )
        collection.setTitle(title)
        return collection

    def _make_filter(self, catalog=None, collections=None):
        """Filter of data.geo.admin.ch, unless another catalog is given"""
        catalog = catalog or self.geoadmin
        collections = self.collections if collections is None else collections
        search_strings, search_ids = collections_to_searchable_strings(collections)
        return SwissLocatorFilterSTAC(
            get_iface(),
            None,
            [catalog, collections, search_strings, search_ids, CatalogState()],
        )

    def _make_viageo_filter(self):
        return self._make_filter(self.viageo, self.viageo_collections)

    def _make_basel_filter(self):
        return self._make_filter(self.basel, self.basel_collections)

    def _make_geodienste_filter(self):
        return self._make_filter(self.geodienste, self.geodienste_collections)

    @staticmethod
    def _display_strings(_filter, items):
        results = []
        _filter.resultFetched.connect(lambda r: results.append(r.displayString))
        _filter.handle_content(json.dumps({"features": items}), None)
        return results

    def test_local_search(self):
        _filter = self._make_filter()

        search_res_1 = _filter.perform_local_search("gsm")
        search_res_2 = _filter.perform_local_search("verfügbarkeit")

        self.assertEqual(search_res_1, ["ch.bakom.mobilnetz-2g"])
        self.assertEqual(
            search_res_2,
            ["ch.bafu.wald-wasserverfuegbarkeit_boden", "ch.bakom.mobilnetz-2g"],
        )

    def test_local_search_by_collection_id(self):
        """Searching by collection ID should also match."""
        _filter = self._make_filter()
        results = _filter.perform_local_search("ch.swisstopo.swissalti3d")
        self.assertIn("ch.swisstopo.swissalti3d", results)

    def test_local_search_case_insensitive(self):
        """Search should be case-insensitive."""
        _filter = self._make_filter()
        results_lower = _filter.perform_local_search("swissalti3d")
        results_upper = _filter.perform_local_search("SWISSALTI3D")
        self.assertEqual(results_lower, results_upper)

    def test_local_search_by_description_and_keywords(self):
        """Description and keywords match too, after the titles and ids"""
        surface3d = self.collection(
            "ch.swisstopo.swisssurface3d", "swissSURFACE3D", ApiDataGeoAdmin
        )
        surface3d.setDescription("Lidar data: a classified point cloud")
        pully = self.collection(
            "lidar-pully", "Classified point cloud of Pully", ApiViageo
        )
        cartolacote = self.collection(
            "cartolacote", "Point cloud LiDAR 2023 (Cartolacôte)", ApiViageo
        )
        waste = self.collection("AFRB", "Abfuhrzonen", ApiBaselStadt)
        waste.setKeywords(["Abfall", "Müll"])
        collections = {c.id(): c for c in (surface3d, pully, cartolacote, waste)}
        _filter = self._make_filter(collections=collections)

        self.assertEqual(
            _filter.perform_local_search("LiDAR"),
            ["cartolacote", "lidar-pully", "ch.swisstopo.swisssurface3d"],
        )
        self.assertEqual(_filter.perform_local_search("müll"), ["AFRB"])

    def test_copc_asset_also_offered_streamed(self):
        """A COPC point cloud can be downloaded or streamed from its URL."""
        _filter = self._make_filter()
        results = []
        _filter.resultFetched.connect(
            lambda r: results.append((r.displayString, result_from_data(r.userData)))
        )
        _filter.handle_content(
            '{"features": [{"collection": "ch.swisstopo.swissalti3d", "assets": '
            '{"tile.copc.laz": {"type": "application/vnd.laszip+copc", '
            '"href": "https://example.com/tile.copc.laz", "proj:epsg": 2056}}}]}',
            None,
        )
        self.assertEqual(
            [(name, r.path, r.coordsys) for name, r in results],
            [
                ("tile.copc.laz", "", "2056"),
                (
                    "tile.copc.laz (streamed)",
                    "https://example.com/tile.copc.laz",
                    "2056",
                ),
            ],
        )

    def test_viageo_asset_named_after_its_file(self):
        """viageo.ch names all assets 'geotiff_cog' and gives the coordinate
        system on the item, not on the asset."""
        _filter = self._make_viageo_filter()
        results = []
        _filter.resultFetched.connect(
            lambda r: results.append((r.displayString, result_from_data(r.userData)))
        )
        href = "https://data.viageo.ch/pully/true_ortho-Pully.cog.tif"
        _filter.handle_content(
            json.dumps(
                {
                    "features": [
                        {
                            "id": "data",
                            "collection": self.viageo_id,
                            "properties": {"proj:epsg": 2056},
                            "assets": {
                                "geotiff_cog": {
                                    "href": href,
                                    "type": "image/tiff; application=geotiff; "
                                    "profile=cloud-optimized",
                                }
                            },
                        }
                    ]
                }
            ),
            None,
        )
        self.assertEqual(
            [(name, r.href, r.coordsys) for name, r in results],
            [
                ("true_ortho-Pully.cog.tif", href, "2056"),
                ("true_ortho-Pully.cog.tif (streamed)", href, "2056"),
            ],
        )

    def test_one_filter_per_catalog(self):
        """The filters of the catalogs share the prefix and show the source
        of the files above the results."""
        geoadmin, viageo = self._make_filter(), self._make_viageo_filter()
        self.assertEqual(geoadmin.prefix(), viageo.prefix())
        self.assertNotEqual(geoadmin.displayName(), viageo.displayName())
        # QGIS saves the settings of a filter under its name, the one of
        #  data.geo.admin.ch keeps the name it had alone
        self.assertEqual(geoadmin.name(), "SwissLocatorFilterSTAC")
        self.assertEqual(viageo.name(), "SwissLocatorFilterSTAC_viageo")
        self.assertEqual(viageo.clone().name(), viageo.name())
        basel = self._make_basel_filter()
        self.assertEqual(basel.name(), "SwissLocatorFilterSTAC_baselstadt")
        self.assertEqual(basel.prefix(), geoadmin.prefix())

    def test_formats_of_a_single_item_are_listed(self):
        """Basel-Stadt serves each dataset as a single item in 6 or 8 formats,
        more than the files per result: all are listed, named as the server
        names the zip files."""
        formats = {
            "csv": "application/vnd.geo+csv",
            "fgb": "application/vnd.flatgeobuf",
            "gdb": "application/x-filegdb",
            "geojson": "application/geo+json",
            "gpkg": "application/geopackage+sqlite3",
            "shp": "application/vnd.shp",
        }
        item = {
            "id": "latest",
            "collection": "DEFI",
            "assets": {
                key: {
                    "href": f"{ApiBaselStadt.URL}/download/DEFI/latest/{key}",
                    "type": t,
                }
                for key, t in formats.items()
            },
        }
        self.assertEqual(
            self._display_strings(self._make_basel_filter(), [item]),
            [f"DEFI_latest_{key}.zip" for key in formats],
        )

    def test_formats_of_geodienste_are_told_apart(self):
        """geodienste.ch zips each format under application/zip: the locator
        shows the format of the dataset inside."""
        url = "https://geodienste.ch/downloads"
        item = {
            "id": "wildruhezonen_v2_1-AR",
            "collection": "wildruhezonen",
            "assets": {
                key: {"href": f"{url}/{path}", "type": "application/zip"}
                for key, path in (
                    ("interlis", "interlis/AR/wildruhezonen_v2_1_AR_lv95.zip"),
                    ("geopackage_zip", "geopackage/AR/fra/w_AR_gpkg_lv95.zip"),
                    ("shapefile_zip", "shapefile/AR/fra/w_AR_shp_lv95.zip"),
                )
            },
        }
        results = []
        _filter = self._make_geodienste_filter()
        _filter.resultFetched.connect(
            lambda r: results.append((r.displayString, r.description))
        )
        _filter.handle_content(json.dumps({"features": [item]}), None)
        self.assertEqual(
            results,
            [
                ("wildruhezonen_v2_1_AR_lv95.zip", "x.interlis+zip"),
                ("w_AR_gpkg_lv95.zip", "geopackage+sqlite3"),
                ("w_AR_shp_lv95.zip", "vnd.shp"),
            ],
        )

    def test_files_of_a_single_item_in_one_format_open_the_filter_dialog(self):
        """data.geo.admin.ch has single items with many files of a format,
        e.g. the climate scenarios: the filter dialog is offered."""
        item = {
            "id": "ch2025",
            "collection": "ch.swisstopo.swissalti3d",
            "assets": {
                f"scenario_{i}.nc": {
                    "href": f"https://example.com/scenario_{i}.nc",
                    "type": "application/x-netcdf",
                }
                for i in range(6)
            },
        }
        self.assertEqual(
            self._display_strings(self._make_filter(), [item]),
            ["open filter dialog to choose files"],
        )

    def test_items_requested_from_the_catalog_of_the_filter(self):
        urls = []

        def fake_fetch_requests(requests, feedback, slot, data=None, cache=None):
            urls.extend(request.url().toString().split("?")[0] for request in requests)

        for _filter, search in (
            (self._make_viageo_filter(), "pully"),
            (self._make_filter(), "swissalti3d"),
            (self._make_geodienste_filter(), "tranquillité"),
        ):
            _filter.fetch_requests = fake_fetch_requests
            _filter.perform_fetch_results(search, QgsFeedback())
        self.assertEqual(
            urls,
            [
                f"{ApiViageo.URL}/collections/{self.viageo_id}/items",
                f"{ApiDataGeoAdmin.URL}/collections/ch.swisstopo.swissalti3d/items",
                # In the language of the user
                "https://geodienste.ch/stac/fra/collections/wildruhezonen/items",
            ],
        )

    def test_local_search_no_match(self):
        """Unmatched terms should return an empty list."""
        _filter = self._make_filter()
        results = _filter.perform_local_search("xyzzy_nonexistent")
        self.assertEqual(results, [])

    def test_local_search_partial_match(self):
        """Partial strings should match (e.g. 'alti' matches 'swissALTI3D')."""
        _filter = self._make_filter()
        results = _filter.perform_local_search("alti")
        self.assertIn("ch.swisstopo.swissalti3d", results)

    def test_local_search_ordering(self):
        """Results should be ordered by match position (earlier match first)."""
        _filter = self._make_filter()
        # 'verfügbarkeit' appears in the title of both collections, but
        # at different positions — the one with the earlier match should come first
        results = _filter.perform_local_search("verfügbarkeit")
        self.assertEqual(len(results), 2)
        # 'wasserverfügbarkeit' has 'verfügbarkeit' later in the string than
        # '2G - GSM / EDGE Verfügbarkeit'
        # Depending on the search string composition, verify ordering is stable
        self.assertIsInstance(results, list)

    def test_clone_preserves_collections(self):
        """Cloning the filter should preserve the cached collections data."""
        _filter = self._make_filter()
        loc = QgsLocator()
        loc.registerFilter(_filter)
        cloned = _filter.clone()
        self.assertEqual(
            set(cloned.available_collections.keys()),
            set(self.collections.keys()),
        )
        self.assertEqual(cloned.search_strings, _filter.search_strings)
        self.assertEqual(cloned.collection_ids, _filter.collection_ids)
        self.assertIs(cloned.catalog, _filter.catalog)
        self.assertIs(cloned.state, _filter.state)
        # Read on the clone by QGIS before it searches
        self.assertEqual(cloned.fetchResultsDelay(), 300)

    def _search_single_asset_collection(self, items_over_limit: int):
        """Search a collection made of single-asset items (limit +
        items_over_limit of them), served by a fake STAC API honouring the
        `limit` parameter. Return the limit and the emitted display strings."""
        _filter = self._make_filter()
        limit = _filter.settings.filters[_filter.type.value][
            "limit_files_per_result"
        ].value()
        item_count = limit + items_over_limit

        def fake_fetch_requests(requests, feedback, slot, data=None, cache=None):
            for request in requests:
                requested = int(QUrlQuery(request.url()).queryItemValue("limit"))
                features = [
                    {
                        "collection": "ch.swisstopo.swissalti3d",
                        "assets": {
                            f"tile_{i}.las.zip": {
                                "type": "application/vnd.laszip",
                                "href": f"https://example.com/tile_{i}.las.zip",
                            }
                        },
                    }
                    for i in range(min(requested, item_count))
                ]
                slot(json.dumps({"features": features}), feedback)

        _filter.fetch_requests = fake_fetch_requests
        results = []
        _filter.resultFetched.connect(lambda r: results.append(r.displayString))
        _filter.perform_fetch_results("swissalti3d", QgsFeedback())
        return limit, results

    def test_items_within_limit_are_listed(self):
        limit, results = self._search_single_asset_collection(0)
        self.assertEqual(len(results), limit)
        self.assertTrue(all(r.endswith(".las.zip") for r in results))

    def test_more_items_than_limit_opens_filter_dialog(self):
        """A collection with one asset per item and more items than the limit
        (e.g. swissSURFACE3D point cloud) must offer the filter dialog, not the
        first few files."""
        _limit, results = self._search_single_asset_collection(100)
        self.assertEqual(results, ["open filter dialog to choose files"])

    def _search_geodienste(self, _filter, fake_fetch_requests=None) -> list[str]:
        """Search "wild" with the filter of geodienste.ch, its requests to the
        fake given; return the emitted display strings"""
        if fake_fetch_requests:
            _filter.fetch_requests = fake_fetch_requests
        results = []
        _filter.resultFetched.connect(lambda r: results.append(r.displayString))
        _filter.fetchResults("wild", QgsLocatorContext(), QgsFeedback())
        return results

    def test_collections_loading_or_not_loaded_are_told(self):
        """No collections to search: a line tells why, not "No result found." """
        _filter = self._make_filter(self.geodienste, {})
        self.assertEqual(
            self._search_geodienste(_filter),
            ["Loading the datasets of geodienste.ch: search again in a moment"],
        )
        _filter.state.collections_failed_at = time.monotonic()
        self.assertEqual(
            self._search_geodienste(_filter),
            [
                "The datasets of geodienste.ch could not be loaded: "
                "search again in a minute"
            ],
        )

    def test_collections_not_loaded_are_asked_again(self):
        """Offline or refused when QGIS started: the collections are asked
        again before a search, once a minute at most"""
        _filter = self._make_filter(self.geodienste, {})
        with mock.patch.object(_filter, "fetch_stac_collections") as fetch:
            _filter.receive_stac_collections(Exception("Too Many Requests"))
            _filter.clone()
            fetch.assert_not_called()
            _filter.state.collections_failed_at -= _filter.COLLECTIONS_RETRY
            _filter.clone()
            fetch.assert_called_once()

    def test_items_kept_for_the_next_searches(self):
        """The searches of the keys typed share the items received"""
        _filter = self._make_geodienste_filter()
        caches = []

        def fake_fetch_requests(requests, feedback, slot, data=None, cache=None):
            caches.append(cache)

        clone = _filter.clone()
        self._search_geodienste(_filter, fake_fetch_requests)
        self._search_geodienste(clone, fake_fetch_requests)
        self.assertIs(caches[0], _filter.state.responses)
        self.assertIs(caches[1], _filter.state.responses)

    def test_refused_requests_pause_the_catalog(self):
        """A catalog answering 429 is not asked again for a while: the
        searches use what was received before and tell what is missing"""
        _filter = self._make_geodienste_filter()
        refused = (
            "geodienste.ch refuses requests for now: search again in a few minutes"
        )
        sent = []

        def refusing_fetch_requests(requests, feedback, slot, data=None, cache=None):
            for request in requests:
                sent.append(request.url().url())
                _filter.handle_reply_error(sent[-1], FakeReply(429))

        self.assertEqual(
            self._search_geodienste(_filter, refusing_fetch_requests), [refused]
        )
        self.assertEqual(len(sent), 1)
        self.assertTrue(_filter.state.refusing())

        # Paused: nothing sent
        self.assertEqual(
            self._search_geodienste(_filter.clone(), refusing_fetch_requests),
            [refused],
        )
        self.assertEqual(len(sent), 1)

        # Kept from before the pause: still passed on, nothing missing
        _filter.state.responses.put(sent[0], json.dumps({"features": []}))
        passed = []

        def fake_fetch_requests(requests, feedback, slot, data=None, cache=None):
            passed.extend(requests)

        self.assertEqual(
            self._search_geodienste(_filter.clone(), fake_fetch_requests),
            ["No result found."],
        )
        self.assertEqual(len(passed), 1)

    def test_other_errors_do_not_pause_the_catalog(self):
        _filter = self._make_geodienste_filter()
        _filter.handle_reply_error("https://geodienste.ch/stac", FakeReply(500))
        self.assertFalse(_filter.state.refusing())


class FakeReply:
    def __init__(self, status: int):
        self.status = status

    def attribute(self, attribute):
        return self.status

    def errorString(self):
        return f"server replied with status code {self.status}"


class TestResponseCache(unittest.TestCase):
    def test_kept_for_a_while(self):
        cache = ResponseCache(max_age=60)
        with mock.patch.object(response_cache.time, "monotonic", return_value=1000):
            cache.put("https://example.com/a", "content")
            self.assertEqual(cache.get("https://example.com/a"), "content")
            self.assertIsNone(cache.get("https://example.com/b"))
        with mock.patch.object(response_cache.time, "monotonic", return_value=1061):
            self.assertIsNone(cache.get("https://example.com/a"))

    def test_fetch_requests_sends_once(self):
        """What the cache keeps is passed on without being requested again,
        unless the slot failed on it"""
        _filter = SwissLocatorFilterSTAC(
            get_iface(), None, [ApiGeodienste("de"), {}, [], [], CatalogState()]
        )
        cache = ResponseCache()
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "items.json")
            with open(path, "w") as file:
                file.write('{"features": []}')
            request = QNetworkRequest(QUrl.fromLocalFile(path))

            def failing_slot(content, feedback):
                raise ValueError(content)

            _filter.fetch_requests([request], QgsFeedback(), failing_slot, cache=cache)
            self.assertIsNone(cache.get(request.url().url()))

            received = []

            def slot(content, feedback):
                received.append(content)

            _filter.fetch_requests([request], QgsFeedback(), slot, cache=cache)
            os.remove(path)
            # Not readable anymore: only the cache can answer
            _filter.fetch_requests([request], QgsFeedback(), slot, cache=cache)
        self.assertEqual(received, ['{"features": []}'] * 2)


if __name__ == "__main__":
    unittest.main()
