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

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from qgis.gui import QgisInterface
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsBlockingNetworkRequest,
    QgsFetchedContent,
    QgsLocatorResult,
    QgsFeedback,
)
from swiss_locator.core.filters.swiss_locator_filter import (
    SwissLocatorFilter,
)
from swiss_locator.core.filters.filter_type import FilterType
from swiss_locator.core.results import WMSLayerResult

import xml.etree.ElementTree as ET
import urllib.parse


class SwissLocatorFilterWMTS(SwissLocatorFilter):
    def __init__(self, iface: QgisInterface = None, crs: str = None, capabilities=None):
        super().__init__(FilterType.WMTS, iface, crs)

        self.capabilities = capabilities
        self.capabilities_url = f"https://wmts.geo.admin.ch/EPSG/{self.crs}/1.0.0/WMTSCapabilities.xml?lang={self.lang}"

        # do this on main thread only?
        if self.capabilities is None and iface is not None:

            self.content = QgsApplication.networkContentFetcherRegistry().fetch(
                self.capabilities_url
            )
            self.content.fetched.connect(self.handle_capabilities_response)

            self.info(self.content.status())

            if (
                self.content.status() == QgsFetchedContent.ContentStatus.Finished
                and self.content.filePath()
            ):
                file_path = self.content.filePath()
                self.info(
                    f"Swisstopo capabilities already downloaded. Reading from {file_path}"
                )
                self.capabilities = ET.parse(file_path).getroot()
            else:
                self.content.download()

    def clone(self):
        if self.capabilities is None:
            self.content.cancel()
            nam = QgsBlockingNetworkRequest()
            request = QNetworkRequest(QUrl(self.capabilities_url))
            nam.get(request, forceRefresh=True)
            reply = nam.reply()
            if (
                reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
                == 200
            ):  # other codes are handled by NetworkAccessManager
                self.capabilities = ET.fromstring(reply.content().data().decode("utf8"))
            else:
                self.info(
                    self.tr(
                        "The Swiss Locator filter for WMTS layers could not fetch capabilities."
                    )
                )

        return SwissLocatorFilterWMTS(crs=self.crs, capabilities=self.capabilities)

    def displayName(self):
        return self.tr("Swiss Geoportal WMTS Layers")

    def prefix(self):
        return "chw"

    def handle_capabilities_response(self):
        if (
            self.content.status() == QgsFetchedContent.ContentStatus.Finished
            and self.content.filePath()
        ):
            self.info(
                f"Swisstopo capabilities has been downloaded. Reading from {self.content.filePath()}"
            )
            self.capabilities = ET.parse(self.content.filePath()).getroot()
        else:
            self.info(
                "The Swiss Locator filter for WMTS layers could not fetch capabilities",
                Qgis.MessageLevel.Critical,
            )

    def perform_fetch_results(self, search: str, feedback: QgsFeedback):
        namespaces = {
            "wmts": "http://www.opengis.net/wmts/1.0",
            "ows": "http://www.opengis.net/ows/1.1",
        }

        if len(search) < 2:
            return

        if self.capabilities is None:
            self.info(
                self.tr(
                    "The Swiss Locator filter for WMTS layers could not fetch capabilities."
                )
            )
            return

        # Search for layers containing the search term in the name or title
        for layer in self.capabilities.findall(".//wmts:Layer", namespaces):
            layer_title = layer.find(".//ows:Title", namespaces).text
            layer_abstract = layer.find(".//ows:Abstract", namespaces).text
            layer_identifier = layer.find(".//ows:Identifier", namespaces).text
            temporal_wmts = False
            dimensions = dict()
            for dim in layer.findall(".//wmts:Dimension", namespaces):
                identifier = dim.find("./ows:Identifier", namespaces).text
                default = dim.find("./wmts:Default", namespaces).text
                dimension_values = dim.findall(".//wmts:Value", namespaces)
                if len(dimension_values) > 1 and identifier.lower() == "time":
                    temporal_wmts = True
                    continue  # Let the temporal controller take care of it
                dimensions[identifier] = default
            dimensions = "&".join([f"{k}={v}" for (k, v) in dimensions.items()])
            dimensions = urllib.parse.quote(dimensions)

            results = {}

            if layer_identifier:
                if search in layer_identifier.lower():
                    score = 1
                elif search in layer_title.lower():
                    score = 2
                elif search in layer_abstract.lower():
                    score = 3
                else:
                    continue

                tile_matrix_set = layer.find(".//wmts:TileMatrixSet", namespaces).text
                _format = layer.find(".//wmts:Format", namespaces).text
                style = layer.find(".//wmts:Style/ows:Identifier", namespaces).text

                result = QgsLocatorResult()
                result.filter = self
                result.icon = QgsApplication.getThemeIcon("/mIconTemporalRaster.svg") if temporal_wmts else QgsApplication.getThemeIcon("/mActionAddWmsLayer.svg")

                result.displayString = layer_title
                result.description = layer_abstract
                result.userData = WMSLayerResult(
                    layer=layer_identifier,
                    title=layer_title,
                    url=self.capabilities_url,
                    tile_matrix_set=tile_matrix_set,
                    _format=_format,
                    style=style,
                    tile_dimensions=dimensions,
                ).as_definition()

                results[result] = score

            # sort the results with score
            results = sorted([result for (result, score) in results.items()])

            limit = self.settings.filters[self.type.value]["limit"].value()
            for result in results[0:limit]:
                self.resultFetched.emit(result)
                self.result_found = True
