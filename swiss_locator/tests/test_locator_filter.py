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

from qgis.testing import start_app, unittest
from qgis.testing.mocked import get_iface

from qgis.core import QgsLocator, QgsLocatorContext

from swiss_locator.core.filters.swiss_locator_filter_wmts import SwissLocatorFilterWMTS

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

        loc.fetchResults("pixelkarte", context)

        spy.wait(1000)

        self.assertEqual(got_hit._results_[0], "National Map")
