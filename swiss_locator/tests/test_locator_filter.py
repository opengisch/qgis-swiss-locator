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

    def test_local_search(self):
        search_strings, search_ids = collections_to_searchable_strings(self.collections)

        loc = QgsLocator()
        _filter = SwissLocatorFilterSTAC(
            get_iface(), None, [self.collections, search_strings, search_ids]
        )
        loc.registerFilter(_filter)

        search_res_1 = _filter.perform_local_search("gsm")
        search_res_2 = _filter.perform_local_search("verfügbarkeit")

        self.assertEqual(search_res_1, ["ch.bakom.mobilnetz-2g"])
        self.assertEqual(
            search_res_2,
            ["ch.bafu.wald-wasserverfuegbarkeit_boden", "ch.bakom.mobilnetz-2g"],
        )
