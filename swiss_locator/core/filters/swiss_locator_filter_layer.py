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
import re
from urllib.parse import urlparse, parse_qs
import xml.etree.ElementTree as etree


from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from qgis.core import (
    QgsLocatorResult,
    QgsFeedback,
    QgsApplication,
)
from qgis.gui import QgisInterface

from swiss_locator.core.filters.swiss_locator_filter import SwissLocatorFilter
from swiss_locator.core.filters.filter_type import FilterType
from swiss_locator.core.filters.map_geo_admin import map_geo_admin_url
from swiss_locator.core.filters.opendata_swiss import opendata_swiss_url
from swiss_locator.core.results import WMSLayerResult


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
        urls = [
            map_geo_admin_url(search, self.type.value, self.crs, self.lang, limit),
            opendata_swiss_url(search),
        ]
        requests = []
        for (url, params) in urls:
            requests.append(self.request_for_url(url, params, self.HEADERS))
        self.fetch_requests(requests, feedback, slot=self.handle_content, data=search)

    def handle_content(self, content, feedback: QgsFeedback, search: str):
        data = json.loads(content)
        self.dbg_info(data)

        if self.is_opendata_swiss_response(data):
            visited_capabilities = []

            for loc in data["result"]["results"]:
                display_name = loc["title"].get(self.lang, "")
                self.info(display_name)
                if not display_name:
                    # Fallback to german
                    display_name = loc["title"]["de"]

                for res in loc["resources"]:

                    url = res["url"]
                    url_components = urlparse(url)
                    wms_url = f"{url_components.scheme}://{url_components.netloc}/{url_components.path}?"

                    result = QgsLocatorResult()
                    result.filter = self
                    result.group = "opendata.swiss"
                    result.icon = QgsApplication.getThemeIcon("/mActionAddWmsLayer.svg")

                    if re.match(r"https?:\/\/wmt?s.geo.admin.ch", url):
                        # skip swisstopo since it's handled in other filter
                        self.dbg_info(
                            "skip swisstopo get capabilities since it"
                            "'s handled in other filter"
                        )
                        continue

                    if "wms" in url.lower():
                        if "media_type" in res and res["media_type"] == "Layers":
                            result.displayString = display_name
                            result.description = url

                            if res["title"]["de"] == "GetMap":
                                layers = parse_qs(url_components.query)["LAYERS"]
                                self.info(layers)
                                result.userData = WMSLayerResult(
                                    layer=layers[0],
                                    title=display_name,
                                    url=wms_url,
                                ).as_definition()
                                self.result_found = True
                                self.resultFetched.emit(result)

                        elif (
                            "request=getcapabilities" in url.lower()
                            and url_components.netloc not in visited_capabilities
                        ):
                            self.dbg_info(f"get_cap: {url_components.netloc} {url}")
                            visited_capabilities.append(url_components.netloc)
                            self.fetch_request(
                                QNetworkRequest(QUrl(url)),
                                feedback,
                                slot=self.handle_capabilities_response,
                                data=(search, wms_url),
                            )

        else:
            for loc in data["results"]:
                self.dbg_info("keys: {}".format(loc["attrs"].keys()))

                result = QgsLocatorResult()
                result.filter = self
                result.group = self.tr("Swiss Geoportal")
                if loc["attrs"]["origin"] == "layer":
                    # available keys: ['origin', 'lang', 'layer', 'staging', 'title', 'topics', 'detail', 'label', 'id']
                    for key, val in loc["attrs"].items():
                        self.dbg_info(f"{key}: {val}")
                    result.displayString = loc["attrs"]["title"]
                    result.description = loc["attrs"]["layer"]
                    result.userData = WMSLayerResult(
                        layer=loc["attrs"]["layer"],
                        title=loc["attrs"]["title"],
                        url="http://wms.geo.admin.ch/?VERSION%3D2.0.0",
                    ).as_definition()
                    result.icon = QgsApplication.getThemeIcon("/mActionAddWmsLayer.svg")
                    self.result_found = True
                    self.resultFetched.emit(result)

    def handle_capabilities_response(self, content, feedback: QgsFeedback, data):
        search = data[0]
        wms_url = data[1]
        capabilities = etree.fromstring(content)

        # Get xml namespace
        match = re.match(r"\{.*\}", capabilities.tag)
        namespace = match.group(0) if match else ""

        # Search for layers containing the search term in the name or title
        for layer in capabilities.findall(".//{}Layer".format(namespace)):
            layername = self.find_text(layer, "{}Name".format(namespace))
            layertitle = self.find_text(layer, "{}Title".format(namespace))
            if layername and (
                search in layername.lower() or search in layertitle.lower()
            ):
                if not layertitle:
                    layertitle = layername

                result = QgsLocatorResult()
                result.filter = self
                result.group = "opendata.swiss"
                result.icon = QgsApplication.getThemeIcon("/mActionAddWmsLayer.svg")
                result.displayString = layertitle
                result.description = layername
                result.userData = WMSLayerResult(
                    layer=layername,
                    title=layertitle,
                    url=wms_url,
                ).as_definition()
                self.result_found = True
                self.resultFetched.emit(result)
