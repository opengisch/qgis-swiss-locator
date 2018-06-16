# -*- coding: utf-8 -*-
"""
/***************************************************************************

                                 QgisLocator

                             -------------------
        begin                : 2018-05-03
        copyright            : (C) 2018 by Denis Rouzaud
        email                : denis@opengis.ch
        git sha              : $Format:%H$
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
import sys, traceback

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtCore import QUrl, QUrlQuery, pyqtSlot, pyqtSignal, QEventLoop

from qgis.core import Qgis, QgsMessageLog, QgsLocatorFilter, QgsLocatorResult, QgsRectangle, \
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsGeometry, QgsWkbTypes, QgsPointXY, \
    QgsLocatorContext, QgsFeedback, QgsRasterLayer
from qgis.gui import QgsRubberBand, QgisInterface

from .core.network_access_manager import NetworkAccessManager, RequestsException, RequestsExceptionUserAbort
from .core.settings import Settings
from .gui.config_dialog import ConfigDialog
from .gui.maptip import MapTip
from .swiss_locator_plugin import DEBUG
from .utils.html_stripper import strip_tags
from .map_geo_admin.layers import searchable_layers


AVAILABLE_CRS = ('2056', '21781')
AVAILABLE_LANGUAGES = {'German': 'de',
                       'SwissGerman': 'de',
                       'French': 'fr',
                       'Italian': 'it',
                       'Romansh': 'rm',
                       'English': 'en'}


class InvalidBox(Exception):
    pass


class WMSLayerResult:
    def __init__(self, layer):
        self.layer = layer


class LocationResult:
    def __init__(self, point, bbox, layer, feature_id, html_label):
        self.point = point
        self.bbox = bbox
        self.layer = layer
        self.feature_id = feature_id
        self.html_label = html_label


class FeatureResult:
    def __init__(self, point, layer, feature_id):
        self.point = point
        self.layer = layer
        self.feature_id = feature_id


class NoResult:
    pass


class SwissLocatorFilter(QgsLocatorFilter):

    HEADERS = {b'User-Agent': b'Mozilla/5.0 QGIS Swiss MapGeoAdmin Locator Filter'}

    message_emitted = pyqtSignal(str, Qgis.MessageLevel)

    def __init__(self, locale_lang: str, iface: QgisInterface = None, crs: str = None):
        """"
        :param locale_lang: the language of the locale.
        :param iface: QGIS interface, given when on the main thread (which will display/trigger results), None otherwise
        :param crs: if iface is not given, it shall be provided, see clone()
        """
        super().__init__()
        self.rubber_band = None
        self.feature_rubber_band = None
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

        if crs:
            self.crs = crs

        self.locale_lang = locale_lang
        lang = self.settings.value('lang')
        if not lang:
            if locale_lang in AVAILABLE_LANGUAGES:
                self.lang = AVAILABLE_LANGUAGES[locale_lang]
            else:
                self.lang = 'en'
        else:
            self.lang = lang
        self.searchable_layers = searchable_layers(self.lang)

        if iface is not None:
            # happens only in main thread
            self.iface = iface
            self.map_canvas = iface.mapCanvas()
            self.map_canvas.destinationCrsChanged.connect(self.create_transforms)

            self.rubber_band = QgsRubberBand(self.map_canvas, QgsWkbTypes.PointGeometry)
            self.rubber_band.setColor(QColor(255, 255, 50, 200))
            self.rubber_band.setIcon(self.rubber_band.ICON_CIRCLE)
            self.rubber_band.setIconSize(15)
            self.rubber_band.setWidth(4)
            self.rubber_band.setBrushStyle(Qt.NoBrush)

            self.feature_rubber_band = QgsRubberBand(self.map_canvas, QgsWkbTypes.PolygonGeometry)
            self.feature_rubber_band.setColor(QColor(255, 50, 50, 200))
            self.feature_rubber_band.setFillColor(QColor(255, 255, 50, 160))
            self.feature_rubber_band.setBrushStyle(Qt.SolidPattern)
            self.feature_rubber_band.setLineStyle(Qt.SolidLine)
            self.feature_rubber_band.setWidth(4)

            self.create_transforms()

    def name(self):
        return self.__class__.__name__

    def clone(self):
        return SwissLocatorFilter(self.locale_lang, crs=self.crs)

    def displayName(self):
        return self.tr('Swiss Geoadmin locations')

    def prefix(self):
        return 'swi'

    def hasConfigWidget(self):
        return True

    def openConfigWidget(self, parent=None):
        ConfigDialog(parent).exec_()

    def create_transforms(self):
        # this should happen in the main thread
        self.crs = self.settings.value('crs')
        if self.crs == 'project':
            map_crs = self.map_canvas.mapSettings().destinationCrs()
            if map_crs.isValid():
                self.crs = map_crs.authid().split(':')[1]
            if self.crs not in AVAILABLE_CRS:
                self.crs = '2056'
        assert self.crs in AVAILABLE_CRS
        src_crs_ch = QgsCoordinateReferenceSystem('EPSG:{}'.format(self.crs))
        assert src_crs_ch.isValid()
        dst_crs = self.map_canvas.mapSettings().destinationCrs()
        self.transform_ch = QgsCoordinateTransform(src_crs_ch, dst_crs, QgsProject.instance())

        src_crs_4326 = QgsCoordinateReferenceSystem('EPSG:4326')
        self.transform_4326 = QgsCoordinateTransform(src_crs_4326, dst_crs, QgsProject.instance())

    def group_info(self, group: str) -> (str, str):
        groups = {'zipcode': {'name': self.tr('ZIP code'),
                              'layer': 'ch.swisstopo-vd.ortschaftenverzeichnis_plz'},
                  'gg25': {'name': self.tr('Municipal boundaries'),
                           'layer': 'ch.swisstopo.swissboundaries3d-gemeinde-flaeche.fill'},
                  'district': {'name': self.tr('District'),
                               'layer': 'ch.swisstopo.swissboundaries3d-bezirk-flaeche.fill'},
                  'kantone': {'name': self.tr('Cantons'),
                              'layer': 'ch.swisstopo.swissboundaries3d-kanton-flaeche.fill'},
                  'gazetteer': {'name': self.tr('Index'),
                                'layer': 'ch.swisstopo.swissnames3d'},  # there is also: ch.bav.haltestellen-oev ?
                  'address': {'name': self.tr('Address'), 'layer': 'ch.bfs.gebaeude_wohnungs_register'},
                  'parcel': {'name': self.tr('Parcel'), 'layer': None}
                  }
        if group not in groups:
            self.info('Could not find group {} in dictionary'.format(group))
            return None, None
        return groups[group]['name'], groups[group]['layer']

    @staticmethod
    def rank2priority(rank) -> float:
        """
        Translate the rank from GeoAdmin to the priority of the result
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
        coords = re.findall(r'\b(\d+(?:\.\d+)?)\b', box)
        if len(coords) != 4:
            raise InvalidBox('Could not parse: {}'.format(box))
        return QgsRectangle(float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3]))

    @staticmethod
    def url_with_param(url, params) -> str:
        url = QUrl(url)
        q = QUrlQuery(url)
        for key, value in params.items():
            q.addQueryItem(key, value)
        url.setQuery(q)
        return url.url()

    @pyqtSlot()
    def clear_results(self):
        self.rubber_band.reset(QgsWkbTypes.PointGeometry)
        self.feature_rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        if self.map_tip is not None:
            del self.map_tip
            self.map_tip = None
        if self.current_timer is not None:
            self.current_timer.stop()
            self.current_timer.deleteLater()
            self.current_timer = None

    def fetchResults(self, search: str, context: QgsLocatorContext, feedback: QgsFeedback):
        try:
            self.dbg_info("start Swiss locator search...")

            if len(search) < 2:
                return

            self.result_found = False

            # create the URLs to fetch
            self.access_managers = {}
            for search_type in ('locations', 'featuresearch', 'layers'):
                url = 'https://api3.geo.admin.ch/rest/services/api/SearchServer'
                params = {
                    'type': search_type,
                    'searchText': str(search),
                    'returnGeometry': 'true',
                    'lang': self.lang,
                    'sr': self.crs,
                    # bbox Must be provided if the searchText is not.
                    # A comma separated list of 4 coordinates representing
                    # the bounding box on which features should be filtered (SRID: 21781).
                }
                if search_type == 'featuresearch':
                    try:
                        layers = list(self.searchable_layers.keys())
                        assert len(layers) > 0
                        # split features search in several requests otherwise URL is too long
                        step = 30
                        for l in range(0, len(layers), step):
                            last = min(l + step - 1, len(layers) - 1)
                            params['features'] = ','.join(layers[l:last])
                            self.access_managers[self.url_with_param(url, params)] = None
                    except IOError:
                        self.info('Layers data file not found. Please report an issue.', Qgis.Critical)

                else:
                    self.access_managers[self.url_with_param(url, params)] = None

            # init event loop
            # wait for all requests to end
            self.event_loop = QEventLoop()

            def reply_finished(response):
                self.handle_response(response)
                if response.url in self.access_managers:
                    del self.access_managers[response.url]
                if len(self.access_managers) == 0:
                    self.event_loop.quit()

            # init the network access managers, create the URL
            for url in self.access_managers:
                try:
                    self.dbg_info(url)
                    nam = NetworkAccessManager()
                    self.access_managers[url] = nam
                    feedback.canceled.connect(nam.abort)
                    nam.finished.connect(reply_finished)
                    nam.request(url, headers=self.HEADERS, blocking=False)

                except RequestsExceptionUserAbort:
                    pass
                except RequestsException as err:
                    self.info(str(err))

            # Let the requests end and catch all exceptions (and clean up requests)
            if len(self.access_managers) > 0:
                try:
                    self.event_loop.exec_(QEventLoop.ExcludeUserInputEvents)
                except RequestsExceptionUserAbort:
                    pass
                except RequestsException as err:
                    self.info(str(err))

            if not self.result_found:
                result = QgsLocatorResult()
                result.filter = self
                result.displayString = self.tr('No result found.')
                result.userData = NoResult
                self.resultFetched.emit(result)

        except Exception as e:
            self.info(e, Qgis.Critical)
            exc_type, exc_obj, exc_traceback = sys.exc_info()
            filename = os.path.split(exc_traceback.tb_frame.f_code.co_filename)[1]
            self.info('{} {} {}'.format(exc_type, filename, exc_traceback.tb_lineno), Qgis.Critical)
            self.info(traceback.print_exception(exc_type, exc_obj, exc_traceback), Qgis.Critical)

    def handle_response(self, response):
        try:
            if response.status_code != 200:
                self.info("Error with status code: {}".format(response.status_code))
                return

            data = json.loads(response.content.decode('utf-8'))
            # self.dbg_info(data)

            for loc in data['results']:
                self.dbg_info("keys: {}".format(loc['attrs'].keys()))
                if loc['attrs']['origin'] == 'layer':
                    # available keys: ﻿['origin', 'lang', 'layer', 'staging', 'title', 'topics', 'detail', 'label', 'id']
                    for key, val in loc['attrs'].items():
                        self.dbg_info('{}: {}'.format(key, val))
                    result = QgsLocatorResult()
                    result.filter = self
                    result.displayString = strip_tags(loc['attrs']['label'])
                    result.description = loc['attrs']['layer']
                    result.userData = WMSLayerResult(layer=loc['attrs']['layer'])
                    if Qgis.QGIS_VERSION_INT >= 30100:
                        result.group = self.tr('WMS Layers')
                    self.result_found = True
                    self.resultFetched.emit(result)

                elif loc['attrs']['origin'] == 'feature':
                    for key, val in loc['attrs'].items():
                        self.dbg_info('{}: {}'.format(key, val))
                    result = QgsLocatorResult()
                    result.filter = self
                    layer = loc['attrs']['layer']
                    point = QgsPointXY(loc['attrs']['lon'], loc['attrs']['lat'])
                    if layer in self.searchable_layers:
                        layer_display = self.searchable_layers[layer]
                    else:
                        self.info(self.tr('Layer {} is not in the list of searchable layers.'
                                          ' Please report issue.'.format(layer)), Qgis.Warning)
                        layer_display = layer
                    if Qgis.QGIS_VERSION_INT >= 30100:
                        result.group = layer_display
                        result.displayString = loc['attrs']['detail']
                    else:
                        result.displayString = '{}, {}'.format(layer_display, loc['attrs']['detail'])
                    result.userData = FeatureResult(point=point,
                                                    layer=layer,
                                                    feature_id=loc['attrs']['feature_id'])
                    self.result_found = True
                    self.resultFetched.emit(result)

                else:  # locations
                    for key, val in loc['attrs'].items():
                        self.dbg_info('{}: {}'.format(key, val))
                    group_name, group_layer = self.group_info(loc['attrs']['origin'])
                    if 'layerBodId' in loc['attrs']:
                        self.dbg_info("layer: {}".format(loc['attrs']['layerBodId']))
                    if 'featureId' in loc['attrs']:
                        self.dbg_info("feature: {}".format(loc['attrs']['featureId']))

                    result = QgsLocatorResult()
                    result.filter = self
                    result.displayString = strip_tags(loc['attrs']['label'])
                    # result.description = loc['attrs']['detail']
                    # if 'featureId' in loc['attrs']:
                    #     result.description = loc['attrs']['featureId']
                    if Qgis.QGIS_VERSION_INT >= 30100:
                        result.group = group_name
                    result.userData = LocationResult(point=QgsPointXY(loc['attrs']['y'], loc['attrs']['x']),
                                                     bbox=self.box2geometry(loc['attrs']['geom_st_box2d']),
                                                     layer=group_layer,
                                                     feature_id=loc['attrs']['featureId'] if 'featureId' in loc['attrs']
                                                     else None,
                                                     html_label=loc['attrs']['label'])
                    self.result_found = True
                    self.resultFetched.emit(result)

        except Exception as e:
            self.info(str(e), Qgis.Critical)
            exc_type, exc_obj, exc_traceback = sys.exc_info()
            filename = os.path.split(exc_traceback.tb_frame.f_code.co_filename)[1]
            self.info('{} {} {}'.format(exc_type, filename, exc_traceback.tb_lineno), Qgis.Critical)
            self.info(traceback.print_exception(exc_type, exc_obj, exc_traceback), Qgis.Critical)

    def triggerResult(self, result: QgsLocatorResult):
        # this should be run in the main thread, i.e. mapCanvas should not be None
        
        # remove any map tip
        self.clear_results()
            
        if type(result.userData) == NoResult:
            pass
        # WMS
        elif type(result.userData) == WMSLayerResult:
            url_with_params = 'contextualWMSLegend=0' \
                              '&crs=EPSG:{crs}' \
                              '&dpiMode=7' \
                              '&featureCount=10' \
                              '&format=image/jpeg' \
                              '&layers={layer}' \
                              '&styles=' \
                              '&url=http://wms.geo.admin.ch/?VERSION%3D2.0.0'\
                .format(crs=self.crs, layer=result.userData.layer)
            wms_layer = QgsRasterLayer(url_with_params, result.displayString, 'wms')
            if not wms_layer.isValid():
                msg = self.tr('Cannot load WMS layer: {} ({})'.format(result.displayString, result.description))
                level = Qgis.Warning
                self.info(msg, level, True)
            QgsProject.instance().addMapLayer(wms_layer)
        # Feature
        elif type(result.userData) == FeatureResult:
            point = QgsGeometry.fromPointXY(result.userData.point)
            point.transform(self.transform_4326)
            self.highlight(point)
            if self.settings.value('show_map_tip'):
                self.show_map_tip(result.userData.layer, result.userData.feature_id, point)
        # Location
        else:
            point = QgsGeometry.fromPointXY(result.userData.point)
            bbox = QgsGeometry.fromRect(result.userData.bbox)
            layer = result.userData.layer
            feature_id = result.userData.feature_id
            if not point or not bbox:
                return

            point.transform(self.transform_ch)
            bbox.transform(self.transform_ch)

            self.highlight(point, bbox)

            if layer and feature_id:
                self.fetch_feature(layer, feature_id)

                if self.settings.value('show_map_tip'):
                    self.show_map_tip(layer, feature_id, point, alternative_text=result.userData.html_label)
            else:
                self.current_timer = QTimer()
                self.current_timer.timeout.connect(self.clear_results)
                self.current_timer.setSingleShot(True)
                self.current_timer.start(5000)
                
    def highlight(self, point, bbox=None):
        if bbox is None:
            bbox = point
        self.rubber_band.reset(QgsWkbTypes.PointGeometry)
        self.rubber_band.addGeometry(point, None)
        rect = bbox.boundingBox()
        rect.scale(1.1)
        self.map_canvas.setExtent(rect)
        self.map_canvas.refresh()
        
    def fetch_feature(self, layer, feature_id):
        # Try to get more info
        nam = NetworkAccessManager()
        url_detail = 'https://api3.geo.admin.ch/rest/services/api/MapServer/{layer}/{feature_id}' \
            .format(layer=layer, feature_id=feature_id)
        params = {
            'lang': self.lang,
            'sr': self.crs
        }
        url_detail = self.url_with_param(url_detail, params)
        self.dbg_info(url_detail)

        try:
            (response, content) = nam.request(url_detail, headers=self.HEADERS, blocking=True)
            if response.status_code != 200:
                self.info("Error with status code: {}".format(response.status_code))
            else:
                self.parse_feature_response(content.decode('utf-8'))
        except RequestsExceptionUserAbort:
            pass
        except RequestsException as err:
            self.info(str(err))

    def parse_feature_response(self, content):
        data = json.loads(content)
        self.dbg_info(data)

        if 'feature' not in data or 'geometry' not in data['feature']:
            return

        if 'rings' in data['feature']['geometry']:
            rings = data['feature']['geometry']['rings']
            self.dbg_info(rings)
            for r in range(0, len(rings)):
                for p in range(0, len(rings[r])):
                    rings[r][p] = QgsPointXY(rings[r][p][0], rings[r][p][1])
            geometry = QgsGeometry.fromPolygonXY(rings)
            geometry.transform(self.transform_ch)

            self.feature_rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            self.feature_rubber_band.addGeometry(geometry, None)

    def show_map_tip(self, layer, feature_id, point, alternative_text=None):
        if layer and feature_id:
            url_html = 'https://api3.geo.admin.ch/rest/services/api/MapServer/{layer}/{feature_id}/htmlPopup' \
                .format(layer=layer, feature_id=feature_id)
            params = {
                'lang': self.lang,
                'sr': self.crs
            }
            url_html = self.url_with_param(url_html, params)
            self.dbg_info(url_html)

            try:
                nam = NetworkAccessManager()
                (response, content) = nam.request(url_html, headers=self.HEADERS, blocking=True)
                if response.status_code != 200:
                    self.info("Error with status code: {}".format(response.status_code))
                else:
                    self.dbg_info(content.decode('utf-8'))
                    self.map_tip = MapTip(self.iface, content.decode('utf-8'), point.asPoint())
                    self.map_tip.closed.connect(self.clear_results)
            except RequestsExceptionUserAbort:
                pass
            except RequestsException as err:
                self.info(str(err))

        if self.map_tip is None and alternative_text is not None:
            self.map_tip = MapTip(self.iface, alternative_text, point.asPoint())
            self.map_tip.closed.connect(self.clear_results)

    def info(self, msg="", level=Qgis.Info, emit_message: bool = False):
        if Qgis.QGIS_VERSION_INT >= 30100:
            self.logMessage(str(msg), level)
        else:
            QgsMessageLog.logMessage('{} {}'.format(self.__class__.__name__, str(msg)), 'Locator bar', level)
        if emit_message:
            self.message_emitted.emit(msg, level)

    def dbg_info(self, msg=""):
        if DEBUG:
            self.info(msg)

    @staticmethod
    def break_camelcase(identifier):
        matches = re.finditer('.+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)', identifier)
        return ' '.join([m.group(0) for m in matches])
