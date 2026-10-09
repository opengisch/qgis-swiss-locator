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
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import (
    Qgis,
    QgsCoordinateTransformContext,
    QgsGeocoderContext,
    QgsLocatorResult,
    QgsPointXY,
    QgsGeometry,
    QgsRectangle,
    QgsWkbTypes,
    QgsFeedback,
)
from qgis.gui import QgisInterface

from swiss_locator.core.constants import MAP_SERVER_URL
from swiss_locator.core.filters.filter_type import FilterType
from swiss_locator.core.filters.swiss_locator_filter import SwissLocatorFilter
from swiss_locator.core.geocoder.swiss_geocoder import (
    FIELD_PREFIX,
    HTML_LABEL_ATTRIBUTE,
    SwissGeocoder,
)
from swiss_locator.core.results import LocationResult
from swiss_locator.utils.utils import url_with_param, get_icon_path


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
        # Same request and parsing as the batch geocoding, all kinds of
        # locations, no retry so that the locator stays responsive
        geocoder = SwissGeocoder(
            origins=None,
            sr=self.crs,
            lang=self.lang,
            limit=self.settings.filters[self.type.value]["limit"].value(),
            retries=0,
        )
        results = geocoder.geocodeString(
            search, QgsGeocoderContext(QgsCoordinateTransformContext()), feedback
        )
        for geocoder_result in results:
            if not geocoder_result.isValid():
                self.info(
                    f"could not search locations: {geocoder_result.error()}",
                    Qgis.MessageLevel.Warning,
                )
                return
            attributes = geocoder_result.additionalAttributes()
            group_name, group_layer = self.group_info(geocoder_result.group())

            result = QgsLocatorResult()
            result.filter = self
            result.displayString = geocoder_result.description()
            result.group = group_name
            result.userData = LocationResult(
                point=geocoder_result.geometry().asPoint(),
                bbox=geocoder_result.viewport() or QgsRectangle(),
                layer=group_layer,
                feature_id=attributes.get(f"{FIELD_PREFIX}feature_id"),
                html_label=attributes.get(HTML_LABEL_ATTRIBUTE),
            ).as_definition()
            result.icon = QIcon(get_icon_path("swiss_locator.png"))
            self.result_found = True
            self.resultFetched.emit(result)

    def fetch_feature(self, layer, feature_id):
        # Try to get more info
        url = f"{MAP_SERVER_URL}/{layer}/{feature_id}"
        params = {"lang": self.lang, "sr": self.crs}
        url = url_with_param(url, params)
        request = QNetworkRequest(QUrl(url))
        self.fetch_request(request, QgsFeedback(), self.parse_feature_response)

    def parse_feature_response(self, content, feedback: QgsFeedback):
        data = json.loads(content)
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

            self.feature_rubber_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
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
            self.info(f"Could not find group {group} in dictionary")
            return None, None
        return groups[group]["name"], groups[group]["layer"]
