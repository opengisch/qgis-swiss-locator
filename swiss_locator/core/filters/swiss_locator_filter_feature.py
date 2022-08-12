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
    QgsFeedback,
    QgsLocatorResult,
    QgsPointXY,
)
from qgis.gui import QgisInterface

from swiss_locator.core.filters.swiss_locator_filter import (
    SwissLocatorFilter,
)
from swiss_locator.core.filters.filter_type import FilterType
from swiss_locator.core.results import FeatureResult
from swiss_locator.core.filters.map_geo_admin import map_geo_admin_url


class SwissLocatorFilterFeature(SwissLocatorFilter):
    def __init__(self, iface: QgisInterface = None, crs: str = None):
        super().__init__(FilterType.Feature, iface, crs)
        self.minimum_search_length = 4

    def clone(self):
        return SwissLocatorFilterFeature(crs=self.crs)

    def displayName(self):
        return self.tr("Swiss Geoportal features")

    def prefix(self):
        return "chf"

    def perform_fetch_results(self, search: str, feedback: QgsFeedback):
        # Feature search is split in several requests
        # otherwise URL is too long
        urls = []
        try:
            limit = self.settings.value(f"{FilterType.Feature.value}_limit")
            layers = list(self.searchable_layers.keys())
            assert len(layers) > 0
            step = 20
            for i_layer in range(0, len(layers), step):
                last = min(i_layer + step - 1, len(layers) - 1)
                url, params = map_geo_admin_url(
                    search, self.type.value, self.crs, self.lang, limit
                )
                params["features"] = ",".join(layers[i_layer:last])
                urls.append(self.url_with_param(url, params).url())
        except IOError:
            self.info(
                "Layers data file not found. Please report an issue.",
                Qgis.Critical,
            )
        self.fetch_urls(urls, feedback)

    def handle_reply(self, url):
        self.dbg_info(f"feature handle reply {url}")
        content = self.access_managers[url].contentAsString()
        try:
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
        except json.decoder.JSONDecodeError:
            self.info(f"cannot load data from {url}. Are you online?")
            self.dbg_info(content)

        # clean nam
        if url in self.access_managers:
            self.dbg_info("cleaning nam")
            # self.access_managers[url] = None

        # quit loop if every nam has completed
        for url, nam in self.access_managers.items():
            if nam is not None:
                self.dbg_info(f"{url} nams still running, stay in loop")
                return
            self.dbg_info(f"{url} no nam left, exit loop")
            self.event_loop.quit()
