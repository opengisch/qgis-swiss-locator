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
from qgis.PyQt.QtNetwork import QNetworkReply

from qgis.core import (
    QgsLocatorResult,
    QgsFeedback,
    QgsBlockingNetworkRequest,
)
from qgis.gui import QgisInterface

from swiss_locator.core.filters.swiss_locator_filter import SwissLocatorFilter
from swiss_locator.core.filters.filter_type import FilterType
from swiss_locator.core.filters.map_geo_admin import map_geo_admin_url
from swiss_locator.core.filters.opendata_swiss import opendata_swiss_url
from swiss_locator.core.results import NoResult


class SwissLocatorFilterLayer(SwissLocatorFilter):
    def __init__(self, iface: QgisInterface = None, crs: str = None):
        super().__init__(FilterType.Layers, iface, crs)

    def clone(self):
        return SwissLocatorFilterLayer(crs=self.crs)

    def displayName(self):
        return self.tr("Swiss Geoportal / opendata.swiss Layers layers")

    def prefix(self):
        return "chl"

    def perform_fetch_results(self, search: str, feedback: QgsFeedback):
        limit = self.settings.value(f"{FilterType.Location.value}_limit")
        urls = list()
        urls.append(
            map_geo_admin_url(search, self.type.value, self.crs, self.lang, limit)
        )
        urls.append(opendata_swiss_url(search))
        for (url, params) in urls:
            request = self.request_for_url(url, params, self.HEADERS)
            nam = QgsBlockingNetworkRequest()
            feedback.canceled.connect(nam.abort)
            try:
                nam.get(request)
                reply = nam.reply()
                self.handle_reply(reply)
            except Exception as err:
                self.info(err)

        if not self.result_found:
            result = QgsLocatorResult()
            result.filter = self
            result.displayString = self.tr("No result found.")
            result.userData = NoResult().as_definition()
            self.resultFetched.emit(result)

    def handle_reply(self, reply: QNetworkReply):
        pass
