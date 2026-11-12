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

from qgis.core import (
    QgsLocatorResult,
    QgsFeedback,
    QgsApplication,
)
from qgis.gui import QgisInterface

from swiss_locator.core.constants import WMS_BASE_URL
from swiss_locator.core.filters.swiss_locator_filter import SwissLocatorFilter
from swiss_locator.core.filters.filter_type import FilterType
from swiss_locator.core.filters.map_geo_admin import map_geo_admin_url
from swiss_locator.core.filters.opendata_swiss import (
    WMS_LAYERS_INDEX,
    opendata_swiss_url,
)
from swiss_locator.core.results import WMSLayerResult
from swiss_locator.utils import wms


class SwissLocatorFilterLayer(SwissLocatorFilter):
    def __init__(self, iface: QgisInterface = None, crs: str = None):
        super().__init__(FilterType.Layers, iface, crs)
        # (service URL, layer name) of the opendata.swiss results of a search
        self.emitted_layers = set()

    def clone(self):
        return SwissLocatorFilterLayer(crs=self.crs)

    def displayName(self):
        return self.tr("Swiss Geoportal / opendata.swiss Layers layers")

    def prefix(self):
        return "chl"

    def perform_fetch_results(self, search: str, feedback: QgsFeedback):
        limit = self.settings.filters[self.type.value]["limit"].value()
        self.emitted_layers = set()
        urls = [map_geo_admin_url(search, self.type.value, self.crs, self.lang, limit)]

        if self.settings.layers_include_opendataswiss.value():
            # Layers of the services referenced by opendata.swiss come from the
            # index published by the plugin: available before the online searches.
            self.emit_indexed_layers(search, limit)
            # Datasets pointing to a single layer of a service (GetMap links)
            urls.append(opendata_swiss_url(search))

        requests = [
            self.request_for_url(url, params, self.HEADERS) for url, params in urls
        ]
        self.fetch_requests(requests, feedback, slot=self.handle_content)

    def emit_indexed_layers(self, search: str, limit: int):
        index = WMS_LAYERS_INDEX.data()
        if index is None:
            return
        for layer, score in index.search(search, limit):
            description = layer.name
            if layer.service_title:
                description += f" – {layer.service_title}"
            self.emit_opendata_swiss_layer(
                layer.name,
                layer.title,
                layer.service_url,
                layer.version,
                description,
                score,
            )

    def handle_content(self, content: str, feedback: QgsFeedback):
        data = json.loads(content)
        self.dbg_info(data)

        if self.is_opendata_swiss_response(data):
            self.handle_opendata_swiss_content(data)
        else:
            self.handle_geo_admin_content(data)

    def handle_opendata_swiss_content(self, data: dict):
        for dataset in data["result"]["results"]:
            title = dataset["title"].get(self.lang) or dataset["title"].get("de", "")
            for resource in dataset["resources"]:
                url = resource.get("url") or ""
                if (
                    wms.is_geo_admin(url)
                    or "wms" not in url.lower()
                    or resource.get("media_type") != "Layers"
                    or (resource.get("title") or {}).get("de") != "GetMap"
                ):
                    continue
                layer = wms.query_parameter(url, "LAYERS")
                service_url = wms.service_url(url)
                if not layer or not service_url:
                    continue
                version = wms.query_parameter(url, "VERSION") or wms.DEFAULT_VERSION
                self.emit_opendata_swiss_layer(layer, title, service_url, version, url)

    def emit_opendata_swiss_layer(
        self,
        layer: str,
        title: str,
        service_url: str,
        version: str,
        description: str,
        score: float | None = None,
    ):
        key = (service_url, layer)
        if key in self.emitted_layers:
            return
        self.emitted_layers.add(key)

        result = QgsLocatorResult()
        result.filter = self
        result.group = "opendata.swiss"
        result.icon = QgsApplication.getThemeIcon("/mActionAddWmsLayer.svg")
        result.displayString = title
        result.description = description
        if score is not None:
            result.score = score
        result.userData = WMSLayerResult(
            layer=layer,
            title=title,
            url=wms.provider_url(service_url, version),
        ).as_definition()
        self.result_found = True
        self.resultFetched.emit(result)

    def handle_geo_admin_content(self, data: dict):
        for loc in data["results"]:
            self.dbg_info("keys: {}".format(loc["attrs"].keys()))
            if loc["attrs"]["origin"] != "layer":
                continue
            # available keys: ['origin', 'lang', 'layer', 'staging', 'title', 'topics', 'detail', 'label', 'id']
            for key, val in loc["attrs"].items():
                self.dbg_info(f"{key}: {val}")
            result = QgsLocatorResult()
            result.filter = self
            result.group = self.tr("Swiss Geoportal")
            result.displayString = loc["attrs"]["title"]
            result.description = loc["attrs"]["layer"]
            result.userData = WMSLayerResult(
                layer=loc["attrs"]["layer"],
                title=loc["attrs"]["title"],
                url=wms.provider_url(f"{WMS_BASE_URL}/"),
            ).as_definition()
            result.icon = QgsApplication.getThemeIcon("/mActionAddWmsLayer.svg")
            self.result_found = True
            self.resultFetched.emit(result)
