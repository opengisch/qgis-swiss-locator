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
from qgis.PyQt.QtCore import QUrl

from qgis.core import QgsNetworkContentFetcher, QgsPointXY, QgsGeometry, QgsWkbTypes
from qgis.gui import QgisInterface

from swiss_locator.core.filters.swiss_locator_filter import (
    SwissLocatorFilter,
)
from swiss_locator.core.filters.filter_type import FilterType


class SwissLocatorFilterLocation(SwissLocatorFilter):
    def __init__(self, iface: QgisInterface = None, crs: str = None):
        super().__init__(FilterType.Location, iface, crs)

    def clone(self):
        return SwissLocatorFilterLocation(crs=self.crs)

    def displayName(self):
        return self.tr("Swiss Geoportal locations")

    def prefix(self):
        return "chs"

    def fetch_feature(self, layer, feature_id):
        # Try to get more info
        url_detail = "https://api3.geo.admin.ch/rest/services/api/MapServer/{layer}/{feature_id}".format(
            layer=layer, feature_id=feature_id
        )
        params = {"lang": self.lang, "sr": self.crs}
        url_detail = self.url_with_param(url_detail, params)
        self.dbg_info(url_detail)
        self.nam_fetch_feature = QgsNetworkContentFetcher()
        self.nam_fetch_feature.finished.connect(self.parse_feature_response)
        self.nam_fetch_feature.fetchContent(QUrl(url_detail))

    def parse_feature_response(self, response):
        data = json.loads(self.nam_fetch_feature.contentAsString())
        self.dbg_info(data)

        if "feature" not in data or "geometry" not in data["feature"]:
            return

        if "rings" in data["feature"]["geometry"]:
            rings = data["feature"]["geometry"]["rings"]
            self.dbg_info(rings)
            for r in range(0, len(rings)):
                for p in range(0, len(rings[r])):
                    rings[r][p] = QgsPointXY(rings[r][p][0], rings[r][p][1])
            geometry = QgsGeometry.fromPolygonXY(rings)
            geometry.transform(self.transform_ch)

            self.feature_rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            self.feature_rubber_band.addGeometry(geometry, None)

    def group_info(self, group: str) -> (str, str):
        groups = {
            "zipcode": {
                "name": self.tr("ZIP code"),
                "layer": "ch.swisstopo-vd.ortschaftenverzeichnis_plz",
            },
            "gg25": {
                "name": self.tr("Municipal boundaries"),
                "layer": "ch.swisstopo.swissboundaries3d-gemeinde-flaeche.fill",
            },
            "district": {
                "name": self.tr("District"),
                "layer": "ch.swisstopo.swissboundaries3d-bezirk-flaeche.fill",
            },
            "kantone": {
                "name": self.tr("Cantons"),
                "layer": "ch.swisstopo.swissboundaries3d-kanton-flaeche.fill",
            },
            "gazetteer": {
                "name": self.tr("Index"),
                "layer": "ch.swisstopo.swissnames3d",
            },  # there is also: ch.bav.haltestellen-oev ?
            "address": {
                "name": self.tr("Address"),
                "layer": "ch.bfs.gebaeude_wohnungs_register",
            },
            "parcel": {"name": self.tr("Parcel"), "layer": None},
        }
        if group not in groups:
            self.info("Could not find group {} in dictionary".format(group))
            return None, None
        return groups[group]["name"], groups[group]["layer"]
