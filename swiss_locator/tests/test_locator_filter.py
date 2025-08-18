# -*- coding: utf-8 -*-
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
"""

from qgis.PyQt.QtTest import QSignalSpy
from qgis._core import QgsStacExtent
from qgis.core import QgsStacCollection, QgsLocator, QgsLocatorContext
from qgis.testing import start_app, unittest
from qgis.testing.mocked import get_iface

from swiss_locator.core.filters.map_geo_admin_stac import \
    collections_to_searchable_strings
from swiss_locator.core.filters.swiss_locator_filter_stac import \
    SwissLocatorFilterSTAC
from swiss_locator.core.filters.swiss_locator_filter_wmts import \
    SwissLocatorFilterWMTS

start_app()


class TestSwissLocatorFilters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.iface = get_iface()

    def setUp(self):
        pass

    def testSwissLocatorFilterWMTS(self):
        def got_hit(result):
            print(result)
            print(result.displayString)
            got_hit._results_.append(result.displayString)

        got_hit._results_ = []

        context = QgsLocatorContext()

        loc = QgsLocator()
        _filter = SwissLocatorFilterWMTS(get_iface())
        loc.registerFilter(_filter)

        loc.foundResult.connect(got_hit)

        spy = QSignalSpy(loc.foundResult)

        loc.fetchResults("pixelkarte-farbe", context)

        spy.wait(1000)

        self.assertTrue(got_hit._results_[0].startswith("National Map"))


class TestLocatorFilterSTAC(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.test_strings = (
            ('ch.swisstopo.swissalti3d', 'swissALTI3D'),
            ('ch.bakom.mobilnetz-2g', '2G - GSM / EDGE Verfügbarkeit'),
            ('ch.bafu.wald-wasserverfuegbarkeit_boden',
                'Wasserverfügbarkeit im Boden (Standortwasserbilanz)'),
        )
        cls.collections = {}
        for key, title in cls.test_strings:
            cls.collections[key] = QgsStacCollection(key, None, None, [], None,
                                                     QgsStacExtent())
            cls.collections[key].setTitle(title)
    
    def setUp(self):
        pass
    
    def test_collections_to_searchable_strings(self):
        search_strings, search_ids = collections_to_searchable_strings(
                self.collections)
        
        self.assertEqual(search_strings, [
            'swissalti3d ch.swisstopo.swissalti3d',
            '2g - gsm / edge verfügbarkeit ch.bakom.mobilnetz-2g',
            'wasserverfügbarkeit im boden (standortwasserbilanz) ch.bafu.wald-wasserverfuegbarkeit_boden'
        ])
    
    def test_local_search(self):
        search_strings, search_ids = collections_to_searchable_strings(
                self.collections)
        
        loc = QgsLocator()
        _filter = SwissLocatorFilterSTAC(get_iface(), None,
                                         [self.collections, search_strings,
                                             search_ids])
        loc.registerFilter(_filter)
        
        search_res_1 = _filter.perform_local_search('gsm')
        search_res_2 = _filter.perform_local_search('verfügbarkeit')
        
        self.assertEqual(search_res_1, ['ch.bakom.mobilnetz-2g'])
        self.assertEqual(search_res_2,
                         ['ch.bafu.wald-wasserverfuegbarkeit_boden',
                             'ch.bakom.mobilnetz-2g'])
