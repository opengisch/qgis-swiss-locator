# -*- coding: utf-8 -*-
"""
/***************************************************************************

 QGIS Swiss Locator Plugin
 Copyright (C) 2018 Denis Rouzaud

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
import os
import re
import sys
import traceback

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QLabel, QWidget, QTabWidget
from PyQt5.QtCore import QUrl, QUrlQuery, pyqtSignal, QEventLoop
from PyQt5.QtNetwork import QNetworkRequest, QNetworkReply, QNetworkAccessManager

from qgis.core import (
    Qgis,
    QgsLocatorFilter,
    QgsLocatorResult,
    QgsRectangle,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsGeometry,
    QgsWkbTypes,
    QgsLocatorContext,
    QgsFeedback,
    QgsRasterLayer,
)
from qgis.gui import QgsRubberBand, QgisInterface

from swiss_locator import DEBUG
from swiss_locator.core.filters.filter_type import FilterType
from swiss_locator.core.parameters import AVAILABLE_CRS
from swiss_locator.core.results import (
    WMSLayerResult,
    LocationResult,
    FeatureResult,
    NoResult,
)
from swiss_locator.core.settings import Settings
from swiss_locator.core.language import get_language
from swiss_locator.gui.config_dialog import ConfigDialog
from swiss_locator.gui.maptip import MapTip
from swiss_locator.map_geo_admin.layers import searchable_layers

from urllib.parse import urlparse, parse_qs

import xml.etree.ElementTree as ET


def result_from_data(result: QgsLocatorResult):
    # see https://github.com/qgis/QGIS/pull/40452
    if hasattr(result, "getUserData"):
        definition = result.getUserData()
    else:
        definition = result.userData
    dict_data = json.loads(definition)
    if dict_data["type"] == "WMSLayerResult":
        return WMSLayerResult.from_dict(dict_data)
    if dict_data["type"] == "LocationResult":
        return LocationResult.from_dict(dict_data)
    if dict_data["type"] == "FeatureResult":
        return FeatureResult.from_dict(dict_data)
    return NoResult()


class InvalidBox(Exception):
    pass


class SwissLocatorFilter(QgsLocatorFilter):

    HEADERS = {b"User-Agent": b"Mozilla/5.0 QGIS Swiss Geoportal Locator Filter"}

    message_emitted = pyqtSignal(str, str, Qgis.MessageLevel, QWidget)

    def __init__(
        self, filter_type: FilterType, iface: QgisInterface = None, crs: str = None
    ):
        """ "
        :param filter_type: the type of filter
        :param locale_lang: the language of the locale.
        :param iface: QGIS interface, given when on the main thread (which will display/trigger results), None otherwise
        :param crs: if iface is not given, it shall be provided, see clone()
        """
        super().__init__()
        self.type = filter_type
        self.rubber_band = None
        self.feature_rubber_band = None
        self.iface = iface
        self.map_canvas = None
        self.settings = Settings()
        self.transform_ch = None
        self.transform_4326 = None
        self.map_tip = None
        self.current_timer = None
        self.crs = None
        self.event_loop = None
        self.result_found = False
        self.access_managers = {}
        self.nam_map_tip = None
        self.nam_fetch_feature = None
        self.minimum_search_length = 2

        self.nam = QNetworkAccessManager()
        self.network_replies = dict()

        if crs:
            self.crs = crs

        self.lang = get_language()

        self.searchable_layers = searchable_layers(self.lang, restrict=True)

        if iface is not None:
            # happens only in main thread
            self.map_canvas = iface.mapCanvas()
            self.map_canvas.destinationCrsChanged.connect(self.create_transforms)

            self.rubber_band = QgsRubberBand(self.map_canvas, QgsWkbTypes.PointGeometry)
            self.rubber_band.setColor(QColor(255, 255, 50, 200))
            self.rubber_band.setIcon(self.rubber_band.ICON_CIRCLE)
            self.rubber_band.setIconSize(15)
            self.rubber_band.setWidth(4)
            self.rubber_band.setBrushStyle(Qt.NoBrush)

            self.feature_rubber_band = QgsRubberBand(
                self.map_canvas, QgsWkbTypes.PolygonGeometry
            )
            self.feature_rubber_band.setColor(QColor(255, 50, 50, 200))
            self.feature_rubber_band.setFillColor(QColor(255, 255, 50, 160))
            self.feature_rubber_band.setBrushStyle(Qt.SolidPattern)
            self.feature_rubber_band.setLineStyle(Qt.SolidLine)
            self.feature_rubber_band.setWidth(4)

            self.create_transforms()

    def name(self):
        return self.__class__.__name__

    def priority(self):
        return self.settings.value("{type}_priority".format(type=self.type.value))

    def displayName(self):
        # this should be re-implemented
        raise NameError(
            "Filter type is not valid. This method should be reimplemented."
        )

    def prefix(self):
        # this should be re-implemented
        raise NameError(
            "Filter type is not valid. This method should be reimplemented."
        )

    def clearPreviousResults(self):
        self.rubber_band.reset(QgsWkbTypes.PointGeometry)
        self.feature_rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        if self.map_tip is not None:
            del self.map_tip
            self.map_tip = None
        if self.current_timer is not None:
            self.current_timer.stop()
            self.current_timer.deleteLater()
            self.current_timer = None

    def hasConfigWidget(self):
        return True

    def openConfigWidget(self, parent=None):
        dlg = ConfigDialog(parent)
        wid = dlg.findChild(QTabWidget, "tabWidget", Qt.FindDirectChildrenOnly)
        tab = wid.findChild(QWidget, self.type.value)
        wid.setCurrentWidget(tab)
        dlg.exec_()

    def create_transforms(self):
        # this should happen in the main thread
        self.crs = self.settings.value("crs")
        if self.crs == "project":
            map_crs = self.map_canvas.mapSettings().destinationCrs()
            if map_crs.isValid():
                self.crs = map_crs.authid().split(":")[1]
            if self.crs not in AVAILABLE_CRS:
                self.crs = "2056"
        assert self.crs in AVAILABLE_CRS
        src_crs_ch = QgsCoordinateReferenceSystem("EPSG:{}".format(self.crs))
        assert src_crs_ch.isValid()
        dst_crs = self.map_canvas.mapSettings().destinationCrs()
        self.transform_ch = QgsCoordinateTransform(
            src_crs_ch, dst_crs, QgsProject.instance()
        )

        src_crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
        self.transform_4326 = QgsCoordinateTransform(
            src_crs_4326, dst_crs, QgsProject.instance()
        )

    @staticmethod
    def rank2priority(rank) -> float:
        """
        Translate the rank from geoportal to the priority of the result
        see https://api3.geo.admin.ch/services/sdiservices.html#search
        :param rank: an integer from 1 to 7
        :return: the priority as a float from 0 to 1, 1 being a perfect match
        """
        return float(-rank / 7 + 1)

    @staticmethod
    def box2geometry(box: str) -> QgsRectangle:
        """
        Creates a rectangle from a Box definition as string
        :param box: the box as a string
        :return: the rectangle
        """
        coords = re.findall(r"\b(\d+(?:\.\d+)?)\b", box)
        if len(coords) != 4:
            raise InvalidBox("Could not parse: {}".format(box))
        return QgsRectangle(
            float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3])
        )

    @staticmethod
    def url_with_param(url, params) -> str:
        url = QUrl(url)
        q = QUrlQuery(url)
        for key, value in params.items():
            q.addQueryItem(key, value)
        url.setQuery(q)
        return url

    @staticmethod
    def request_for_url(url, params, headers) -> QNetworkRequest:
        url = SwissLocatorFilter.url_with_param(url, params)
        request = QNetworkRequest(url)
        for k, v in list(headers.items()):
            request.setRawHeader(k, v)
        return request

    def handle_reply(self, url: str, slot, data=None):
        try:
            self.dbg_info(f"feature handle reply {url}")
            reply = self.network_replies[url]

            if reply.error() != QNetworkReply.NoError:
                self.info(f"could not load url: {reply.errorString()}")
            else:
                content = reply.readAll().data().decode("utf-8")
                if data:
                    slot(content, data)
                else:
                    slot(content)

            # clean nam
            reply.deleteLater()
            self.network_replies.pop(url)

            # quit loop if every nam has completed
            if len(self.network_replies) == 0:
                self.dbg_info(f"{url} no nam left, exit loop")
                self.event_loop.quit()

        except json.decoder.JSONDecodeError:
            self.info(f"cannot load data from {url}. Are you online?")
            self.dbg_info(content)

    def fetch_request(self, request: QNetworkRequest, feedback: QgsFeedback, slot, data=None):
        return self.fetch_requests([request], feedback, slot, data)

    def fetch_requests(
        self, requests: [QNetworkRequest], feedback: QgsFeedback, slot, data=None
    ):
        # init event loop
        # wait for all requests to end
        self.event_loop = QEventLoop()
        feedback.canceled.connect(self.event_loop.quit)

        for request in requests:
            url = request.url().url()
            self.info(f"fetching {url}")
            reply = self.nam.get(request)
            reply.finished.connect(lambda _url=url: self.handle_reply(_url, slot, data))
            feedback.canceled.connect(reply.abort)
            self.network_replies[url] = reply

        # Let the requests end and catch all exceptions (and clean up requests)
        if len(self.network_replies) > 0:
            self.event_loop.exec_(QEventLoop.ExcludeUserInputEvents)

    def fetchResults(
        self, search: str, context: QgsLocatorContext, feedback: QgsFeedback
    ):
        try:
            if len(search) < self.minimum_search_length:
                return

            self.result_found = False

            self.perform_fetch_results(search, feedback)

            if not self.result_found:
                result = QgsLocatorResult()
                result.filter = self
                result.displayString = self.tr("No result found.")
                result.userData = NoResult().as_definition()
                self.resultFetched.emit(result)

        except Exception as e:
            self.info(e, Qgis.Critical)
            exc_type, exc_obj, exc_traceback = sys.exc_info()
            filename = os.path.split(exc_traceback.tb_frame.f_code.co_filename)[1]
            self.info(
                "{} {} {}".format(exc_type, filename, exc_traceback.tb_lineno),
                Qgis.Critical,
            )
            self.info(
                traceback.print_exception(exc_type, exc_obj, exc_traceback),
                Qgis.Critical,
            )

    def handle_reply2(self, reply, search: str, feedback: QgsFeedback):
        raise NameError
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
                self.dbg_info(data)

                if self.is_opendata_swiss_response(data):
                    visited_capabilities = []

                    # opendata might search on other servers
                    # and might perform several getCapabilities requests
                    self.access_managers = {}

                    # init event loop
                    # wait for all requests (for get_capabilities) to end
                    self.event_loop = QEventLoop()
                    feedback.canceled.connect(self.event_loop.quit)

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
                            result.icon = QgsApplication.getThemeIcon(
                                "/mActionAddWmsLayer.svg"
                            )

                            if re.match(r"https?:\/\/wmt?s.geo.admin.ch", url):
                                # skip swisstopo since it's handled in other filter
                                self.dbg_info(
                                    "skip swisstopo get capabilities since it"
                                    "s handled in other filter"
                                )
                                continue

                            if "wms" in url.lower():
                                if res["media_type"] == "Layers":
                                    result.displayString = display_name
                                    result.description = url

                                    if res["title"]["de"] == "GetMap":
                                        layers = parse_qs(url_components.query)[
                                            "LAYERS"
                                        ]
                                        result.userData = WMSLayerResult(
                                            layer=layers[0],
                                            title=display_name,
                                            url=wms_url,
                                        ).as_definition()
                                        self.result_found = True
                                        self.resultFetched.emit(result)

                                elif (
                                    "request=getcapabilities" in url.lower()
                                    and url_components.netloc
                                    not in visited_capabilities
                                ):
                                    self.info("get_cap")
                                    visited_capabilities.append(url_components.netloc)

                                    # Retrieve Capabilities xml
                                    nam = QNetworkAccessManager()
                                    nam.fetchContent(QUrl(url))
                                    nam.finished.connect(
                                        lambda: self.parse_capabilities_result(
                                            nam.reply(), search, result, wms_url
                                        )
                                    )
                                    self.access_managers[url] = nam
                                    feedback.canceled.connect(nam.cancel)

                                    # Let the requests end and catch all exceptions (and clean up requests)
                                    if len(self.access_managers) > 0:
                                        try:
                                            self.event_loop.exec_(
                                                QEventLoop.ExcludeUserInputEvents
                                            )
                                        except Exception as err:
                                            self.info(str(err))

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
                            result.icon = QgsApplication.getThemeIcon(
                                "/mActionAddWmsLayer.svg"
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

    def triggerResult(self, result: QgsLocatorResult):
        # this should be run in the main thread, i.e. mapCanvas should not be None

        # remove any map tip
        self.clearPreviousResults()

        # user_data = NoResult
        try:
            swiss_result = result_from_data(result)
        except SystemError:
            self.message_emitted.emit(
                self.displayName(),
                self.tr(
                    "QGIS Swiss Locator encountered an error. Please <b>update to QGIS 3.16.2</b> or newer."
                ),
                Qgis.Warning,
                None,
            )
            return

        if type(swiss_result) == NoResult:
            return

        # Layers
        if type(swiss_result) == WMSLayerResult:
            params = dict()
            params["contextualWMSLegend"] = 0
            params["crs"] = f"EPSG:{self.crs}"
            params["dpiMode"] = 7
            params["featureCount"] = 10
            params["format"] = swiss_result.format
            params["layers"] = swiss_result.layer
            params["styles"] = swiss_result.style or ""
            if swiss_result.tile_matrix_set:
                params["tileMatrixSet"] = f"{swiss_result.tile_matrix_set}"
            if swiss_result.tile_dimensions:
                params["tileDimensions"] = swiss_result.tile_dimensions
            params["url"] = f"{swiss_result.url}"

            url_with_params = "&".join([f"{k}={v}" for (k, v) in params.items()])

            self.info(f"Loading layer: {url_with_params}")
            wms_layer = QgsRasterLayer(url_with_params, result.displayString, "wms")
            label = QLabel()
            label.setTextFormat(Qt.RichText)
            label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            label.setOpenExternalLinks(True)

            if "geo.admin.ch" in swiss_result.url.lower():
                label.setText(
                    '<a href="https://map.geo.admin.ch/'
                    '?lang={}&bgLayer=ch.swisstopo.pixelkarte-farbe&layers={}">'
                    "Open layer in map.geo.admin.ch</a>".format(
                        self.lang, swiss_result.layer
                    )
                )

            if not wms_layer.isValid():
                msg = self.tr(
                    "Cannot load Layers layer: {} ({})".format(
                        swiss_result.title, swiss_result.layer
                    )
                )
                level = Qgis.Warning
                self.info(msg, level)
            else:
                msg = self.tr(
                    "Layers layer added to the map: {} ({})".format(
                        swiss_result.title, swiss_result.layer
                    )
                )
                level = Qgis.Info

                QgsProject.instance().addMapLayer(wms_layer)

            self.message_emitted.emit(self.displayName(), msg, level, label)

        # Feature
        elif type(swiss_result) == FeatureResult:
            point = QgsGeometry.fromPointXY(swiss_result.point)
            point.transform(self.transform_4326)
            self.highlight(point)
            if self.settings.value("show_map_tip"):
                self.show_map_tip(swiss_result.layer, swiss_result.feature_id, point)

        # Location
        else:
            point = QgsGeometry.fromPointXY(swiss_result.point)
            if swiss_result.bbox.isNull():
                bbox = None
            else:
                bbox = QgsGeometry.fromRect(swiss_result.bbox)
                bbox.transform(self.transform_ch)
            layer = swiss_result.layer
            feature_id = swiss_result.feature_id
            if not point:
                return

            point.transform(self.transform_ch)

            self.highlight(point, bbox)

            if layer and feature_id:
                self.fetch_feature(layer, feature_id)

                if self.settings.value("show_map_tip"):
                    self.show_map_tip(layer, feature_id, point)
            else:
                self.current_timer = QTimer()
                self.current_timer.timeout.connect(self.clearPreviousResults)
                self.current_timer.setSingleShot(True)
                self.current_timer.start(5000)

    def show_map_tip(self, layer, feature_id, point):
        if layer and feature_id:
            url = "https://api3.geo.admin.ch/rest/services/api/MapServer/{layer}/{feature_id}/htmlPopup".format(
                layer=layer, feature_id=feature_id
            )
            params = {"lang": self.lang, "sr": self.crs}
            url = self.url_with_param(url, params)
            self.dbg_info(url)
            request = QNetworkRequest(QUrl(url))
            self.fetch_request(request, QgsFeedback(), self.parse_map_tip_response, data=point)

    def parse_map_tip_response(self, content, point):
        self.map_tip = MapTip(self.iface, content, point.asPoint())
        self.map_tip.closed.connect(self.clearPreviousResults)

    def highlight(self, point, bbox=None):
        if bbox is None:
            bbox = point
        self.rubber_band.reset(QgsWkbTypes.PointGeometry)
        self.rubber_band.addGeometry(point, None)
        rect = bbox.boundingBox()
        rect.scale(1.1)
        self.map_canvas.setExtent(rect)
        self.map_canvas.refresh()

    def info(self, msg="", level=Qgis.Info):
        self.logMessage(str(msg), level)

    def dbg_info(self, msg=""):
        if DEBUG:
            self.info(msg)

    @staticmethod
    def break_camelcase(identifier):
        matches = re.finditer(
            ".+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)", identifier
        )
        return " ".join([m.group(0) for m in matches])

    def is_opendata_swiss_response(self, json):
        return "opendata.swiss" in json.get("help", [])

    def find_text(self, xmlElement, match):
        node = xmlElement.find(match)
        return node.text if node is not None else ""

    def parse_capabilities_result(self, reply, search, result, wms_url):
        if reply.content().url() in self.access_managers:
            self.info("url in access manager")
            self.access_managers[reply.content().url()] = None
        else:
            self.info("url not in")

        capabilities = ET.fromstring(reply.content().data().decode("utf-8"))

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

                result.displayString = layertitle
                result.description = layername
                result.userData = WMSLayerResult(
                    layer=layername,
                    title=layertitle,
                    url=wms_url,
                ).as_definition()
                self.result_found = True
                self.resultFetched.emit(result)

        for _nam in self.access_managers.values():
            if _nam is not None:
                return
            self.event_loop.quit()
