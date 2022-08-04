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

from PyQt5.QtCore import QUrl

from qgis.gui import QgisInterface
from qgis.core import QgsApplication, QgsNetworkContentFetcherTask

from swiss_locator.core.filters.swiss_locator_filter import SwissLocatorFilter, FilterType


class SwissLocatorFilterWMTS(SwissLocatorFilter):
    def __init__(self, iface: QgisInterface = None, crs: str = None):
        super().__init__(FilterType.WMTS, iface, crs)

        self.info('hey')
        url = f'https://wmts.geo.admin.ch/EPSG/{self.crs}/1.0.0/WMTSCapabilities.xml?lang={self.lang}'
        self.swisstopo_capabilities_fetch_task = QgsNetworkContentFetcherTask(QUrl(url))
        QgsApplication.taskManager().addTask(self.swisstopo_capabilities_fetch_task)

        def parse_capabilities():
            self.info('kkk')
            #self.info(content.status)

            #capabilities = ET.parse(content.filePath())
            #self.info(capabilities)

    def clone(self):
        return SwissLocatorFilterWMTS(crs=self.crs)

    def displayName(self):
        return self.tr('Swiss Geoportal WMTS Layers')

    def prefix(self):
        return 'chw'