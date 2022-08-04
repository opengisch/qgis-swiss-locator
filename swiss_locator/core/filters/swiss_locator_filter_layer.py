# -*- coding: utf-8 -*-
"""
/***************************************************************************

 QGIS Swiss Locator Plugin
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


from qgis.gui import QgisInterface

from swiss_locator.core.filters.swiss_locator_filter import SwissLocatorFilter, FilterType


class SwissLocatorFilterLayer(SwissLocatorFilter):
    def __init__(self, iface: QgisInterface = None, crs: str = None):
        super().__init__(FilterType.WMTS, iface, crs)

    def clone(self):
        return SwissLocatorFilterLayer(crs=self.crs)

    def displayName(self):
        return self.tr('Swiss Geoportal / opendata.swiss Layers layers')

    def prefix(self):
        return 'chl'