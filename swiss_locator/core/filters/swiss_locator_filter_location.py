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

import traceback
import json
import sys
import os

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtNetwork import QNetworkRequest

from qgis.core import (
    Qgis,
    QgsLocatorResult,
    QgsNetworkContentFetcher,
    QgsPointXY,
    QgsGeometry,
    QgsWkbTypes,
    QgsFeedback,
    QgsBlockingNetworkRequest,
)
from qgis.gui import QgisInterface

from swiss_locator.core.filters.swiss_locator_filter import SwissLocatorFilter
from swiss_locator.core.filters.filter_type import FilterType
from swiss_locator.core.filters.map_geo_admin import map_geo_admin_url
from swiss_locator.core.results import (
    LocationResult,
    NoResult,
)
from swiss_locator.utils.html_stripper import strip_tags


class SwissLocatorFilterLocation(SwissLocatorFilter):
    def __init__(self, iface: QgisInterface = None, crs: str = None):
        super().__init__(FilterType.Location, iface, crs)

    def clone(self):
        return SwissLocatorFilterLocation(crs=self.crs)

    def displayName(self):
        return self.tr("Swiss Geoportal locations")

    def prefix(self):
        return "chs"

    def perform_fetch_results(self, search: str, feedback: QgsFeedback):
        limit = self.settings.value(f"{FilterType.Location.value}_limit")
        url, params = map_geo_admin_url(
            search, self.type.value, self.crs, self.lang, limit
        )
        request = self.request_for_url(url, params, self.HEADERS)
        nam = QgsBlockingNetworkRequest()
        feedback.canceled.connect(nam.abort)
        try:
            nam.get(request)
            reply = nam.reply()
            self.handle_reply(reply, search, feedback)
        except Exception as err:
            self.info(err)

        if not self.result_found:
            result = QgsLocatorResult()
            result.filter = self
            result.displayString = self.tr("No result found.")
            result.userData = NoResult().as_definition()
            self.resultFetched.emit(result)

    def handle_reply(self, reply, search: str, feedback: QgsFeedback):
        try:
            if reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) != 200:
                self.info(
                    "Error in main response with status code: {} from {}".format(
                        reply.attribute(QNetworkRequest.HttpStatusCodeAttribute),
                        reply.request().url(),
                    )
                )

            else:
                data = json.loads(reply.content().data().decode("utf8"))
                for loc in data["results"]:
                    result = QgsLocatorResult()
                    result.filter = self
                    result.group = self.tr("Swiss Geoportal")
                    for key, val in loc["attrs"].items():
                        self.dbg_info(f"{key}: {val}")
                    group_name, group_layer = self.group_info(loc["attrs"]["origin"])
                    if "layerBodId" in loc["attrs"]:
                        self.dbg_info("layer: {}".format(loc["attrs"]["layerBodId"]))
                    if "featureId" in loc["attrs"]:
                        self.dbg_info("feature: {}".format(loc["attrs"]["featureId"]))

                    result.displayString = strip_tags(loc["attrs"]["label"])
                    # result.description = loc['attrs']['detail']
                    # if 'featureId' in loc['attrs']:
                    #     result.description = loc['attrs']['featureId']
                    result.group = group_name
                    result.userData = LocationResult(
                        point=QgsPointXY(loc["attrs"]["y"], loc["attrs"]["x"]),
                        bbox=self.box2geometry(loc["attrs"]["geom_st_box2d"]),
                        layer=group_layer,
                        feature_id=loc["attrs"]["featureId"]
                        if "featureId" in loc["attrs"]
                        else None,
                        html_label=loc["attrs"]["label"],
                    ).as_definition()
                    result.icon = QIcon(
                        ":/plugins/swiss_locator/icons/swiss_locator.png"
                    )
                    self.result_found = True
                    self.resultFetched.emit(result)

        except Exception as e:
            self.info(str(e), Qgis.Critical)
            exc_type, exc_obj, exc_traceback = sys.exc_info()
            filename = os.path.split(exc_traceback.tb_frame.f_code.co_filename)[1]
            self.info(
                f"{exc_type} {filename} {exc_traceback.tb_lineno}",
                Qgis.Critical,
            )
            self.info(
                traceback.print_exception(exc_type, exc_obj, exc_traceback),
                Qgis.Critical,
            )

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
