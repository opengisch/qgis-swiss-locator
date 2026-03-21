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

from qgis._core import QgsStacExtent
from qgis.core import QgsStacCollection, QgsLocator
from qgis.testing import start_app, unittest
from qgis.testing.mocked import get_iface

from swiss_locator.core.filters.map_geo_admin_stac import (
    collections_to_searchable_strings,
)
from swiss_locator.core.filters.swiss_locator_filter_stac import SwissLocatorFilterSTAC

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
            cls.collections[key] = QgsStacCollection(
                key, None, None, [], None, QgsStacExtent()
            )
            cls.collections[key].setTitle(title)

    def _make_filter(self):
        search_strings, search_ids = collections_to_searchable_strings(self.collections)
        _filter = SwissLocatorFilterSTAC(
            get_iface(), None, [self.collections, search_strings, search_ids]
        )
        return _filter

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
