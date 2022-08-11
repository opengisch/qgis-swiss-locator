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

import json

from PyQt5.QtGui import QIcon

from qgis.core import (
    Qgis,
    QgsLocatorResult,
    QgsPointXY,
)
from qgis.gui import QgisInterface

from swiss_locator.core.filters.swiss_locator_filter import (
    SwissLocatorFilter,
    FilterType,
)
from swiss_locator.core.results import FeatureResult


class SwissLocatorFilterFeature(SwissLocatorFilter):
    def __init__(self, iface: QgisInterface = None, crs: str = None):
        super().__init__(FilterType.Feature, iface, crs)

    def clone(self):
        return SwissLocatorFilterFeature(crs=self.crs)

    def displayName(self):
        return self.tr("Swiss Geoportal features")

    def prefix(self):
        return "chf"

    def handle_reply(self, url):
        self.dbg_info("feature handle reply")
        self.dbg_info(f"{len(self.access_managers)} nams running")
        content = self.access_managers[url].contentAsString()
        data = json.loads(content)
        for loc in data["results"]:
            self.dbg_info("keys: {}".format(loc["attrs"].keys()))
            result = QgsLocatorResult()
            result.filter = self
            result.group = self.tr("Swiss Geoportal")
            for key, val in loc["attrs"].items():
                self.dbg_info(f"{key}: {val}")
            layer = loc["attrs"]["layer"]
            point = QgsPointXY(loc["attrs"]["lon"], loc["attrs"]["lat"])
            if layer in self.searchable_layers:
                layer_display = self.searchable_layers[layer]
            else:
                self.info(
                    self.tr(
                        f"Layer {layer} is not in the list of searchable layers."
                        " Please report issue."
                    ),
                    Qgis.Warning,
                )
                layer_display = layer
            result.group = layer_display
            result.displayString = loc["attrs"]["detail"]
            result.userData = FeatureResult(
                point=point,
                layer=layer,
                feature_id=loc["attrs"]["feature_id"],
            ).as_definition()
            result.icon = QIcon(":/plugins/swiss_locator/icons/swiss_locator.png")
            self.result_found = True
            self.resultFetched.emit(result)

        # clean nam
        if url in self.access_managers:
            self.access_managers[url] = None

        # quit loop if every nam has completed
        for nam in self.access_managers.values():
            if nam is not None:
                self.dbg_info("nams still running, stay in loop")
                return
            self.dbg_info("no nam left, exit loop")
            self.event_loop.quit()
