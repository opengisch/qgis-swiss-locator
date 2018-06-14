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
from PyQt5.QtCore import QUrl, QUrlQuery, pyqtSlot, pyqtSignal
from PyQt5.QtWidgets import QDialog
from PyQt5.uic import loadUiType

from qgis.core import Qgis, QgsMessageLog, QgsLocatorFilter, QgsLocatorResult, QgsRectangle, \
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsGeometry, QgsWkbTypes, QgsPointXY, \
    QgsLocatorContext, QgsFeedback, QgsRasterLayer
from qgis.gui import QgsRubberBand, QgsMapCanvas

from .qgissettingmanager.setting_dialog import SettingDialog, UpdateMode
from .network_access_manager import NetworkAccessManager, RequestsException, RequestsExceptionUserAbort
from .settings import Settings
from .swiss_locator_plugin import DEBUG
from .utils.html_stripper import strip_tags
from .gui.maptip import MapTip

DialogUi, _ = loadUiType(os.path.join(os.path.dirname(__file__), 'ui/config.ui'))


AVAILABLE_CRS = ('2056', '21781')
AVAILABLE_LANGUAGES = {'German': 'de',
                       'SwissGerman': 'de',
                       'French': 'fr',
                       'Italian': 'it',
                       'Romansh': 'rm',
                       'English': 'en'}


class ConfigDialog(QDialog, DialogUi, SettingDialog):
    def __init__(self, parent=None):
        settings = Settings()
        QDialog.__init__(self, parent)
        SettingDialog.__init__(self, setting_manager=settings, mode=UpdateMode.DialogAccept)
        self.setupUi(self)
        self.lang.addItem(self.tr('use the application locale, defaults to English'), '')
        for key, val in AVAILABLE_LANGUAGES.items():
            self.lang.addItem(key, val)
        self.crs.addItem(self.tr('Use map CRS if possible, defaults to CH1903+'), 'project')
        self.crs.addItem('CH 1903+ (EPSG:2056)', '2056')
        self.crs.addItem('CH 1903 (EPSG:21781)', '21781')
        self.settings = settings
        self.init_widgets()


class InvalidBox(Exception):
    pass


class WMSLayer:
    pass


class NoResult:
    pass


class SwissLocatorFilter(QgsLocatorFilter):

    USER_AGENT = b'Mozilla/5.0 QGIS Swiss MapGeoAdmin Locator Filter'

    message_emitted = pyqtSignal(str, Qgis.MessageLevel)

    def __init__(self,  locale_lang: str, map_canvas: QgsMapCanvas = None, crs: str = None):
        """"
        :param locale_lang:
        :param map_canvas: given when on the main thread (which will display/trigger results), None otherwise
        """
        super().__init__()
        self.rubber_band = None
        self.feature_rubber_band = None
        self.map_canvas = None
        self.settings = Settings()
        self.transform = None
        self.map_tip = None
        self.current_timer = None
        self.crs = None

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

        if map_canvas is not None:
            # happens only in main thread
            self.map_canvas = map_canvas
            self.map_canvas.destinationCrsChanged.connect(self.create_transform)

            self.rubber_band = QgsRubberBand(map_canvas, QgsWkbTypes.PointGeometry)
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

            self.create_transform()

    def create_transform(self):
        # this should happen in the main thread
        self.crs = self.settings.value('crs')
        if self.crs == 'project':
            map_crs = self.map_canvas.mapSettings().destinationCrs()
            if map_crs.isValid():
                self.crs = map_crs.authid().split(':')[1]
            if self.crs not in AVAILABLE_CRS:
                self.crs = '2056'
        assert self.crs in AVAILABLE_CRS
        src_crs = QgsCoordinateReferenceSystem('EPSG:{}'.format(self.crs))
        assert src_crs.isValid()
        dst_crs = self.map_canvas.mapSettings().destinationCrs()
        self.transform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())

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

            nam = NetworkAccessManager()
            feedback.canceled.connect(nam.abort)

            result_found = False

            for search_type in ('locations', 'layers'):
                url = 'https://api3.geo.admin.ch/rest/services/api/SearchServer'
                params = {
                    'type': search_type,
                    'searchText': str(search),
                    'returnGeometry': 'true',
                    'lang': self.lang,
                    'sr': self.crs,
                    #'limit': '10' if search_type == 'locations' else '30'
                }
                # bbox Must be provided if the searchText is not.
                # A comma separated list of 4 coordinates representing
                # the bounding box on which features should be filtered (SRID: 21781).

                headers = {b'User-Agent': self.USER_AGENT}
                url = self.url_with_param(url, params)
                self.dbg_info(url)

                try:
                    (response, content) = nam.request(url, headers=headers, blocking=True)
                    result_found = self.handle_response(response, content) or result_found
                except RequestsExceptionUserAbort:
                    pass
                except RequestsException as err:
                    self.info(err)

            if not result_found:
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

    def handle_response(self, response, content) -> bool:
        try:
            if response.status_code != 200:
                self.info("Error with status code: {}".format(response.status_code))
                return

            data = json.loads(content.decode('utf-8'))
            # self.dbg_info(data)

            result_found = False

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
                    result.userData = WMSLayer
                    if Qgis.QGIS_VERSION_INT >= 30100:
                        result.group = self.tr('WMS Layers')
                    result_found = True
                    self.resultFetched.emit(result)

                else:  # locations
                    group_name, group_layer = self.group_info(loc['attrs']['origin'])
                    self.dbg_info("label: {}".format(loc['attrs']['label']))
                    self.dbg_info("detail: {}".format(loc['attrs']['detail']))
                    self.dbg_info("priority: {} (rank: {})".format(self.rank2priority(loc['attrs']['rank']), loc['attrs']['rank']))
                    self.dbg_info("category: {} ({})".format(group_name, loc['attrs']['origin']))
                    self.dbg_info("bbox: {}".format(loc['attrs']['geom_st_box2d']))
                    self.dbg_info("pos: {} {}".format(loc['attrs']['y'], loc['attrs']['x']))
                    self.dbg_info("geom_quadindex: {}".format(loc['attrs']['geom_quadindex']))
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
                    result.userData = {'point': QgsPointXY(loc['attrs']['y'], loc['attrs']['x']),
                                       'bbox': self.box2geometry(loc['attrs']['geom_st_box2d']),
                                       'layer': group_layer,
                                       'feature_id': loc['attrs']['featureId'] if 'featureId' in loc['attrs'] else None,
                                       'html_label': loc['attrs']['label']}
                    result_found = True
                    self.resultFetched.emit(result)

        except Exception as e:
            self.info(e, Qgis.Critical)
            exc_type, exc_obj, exc_traceback = sys.exc_info()
            filename = os.path.split(exc_traceback.tb_frame.f_code.co_filename)[1]
            self.info('{} {} {}'.format(exc_type, filename, exc_traceback.tb_lineno), Qgis.Critical)
            self.info(traceback.print_exception(exc_type, exc_obj, exc_traceback), Qgis.Critical)

    def triggerResult(self, result: QgsLocatorResult):
        # this should be run in the main thread, i.e. mapCanvas should not be None
        if result.userData == NoResult:
            pass
        elif result.userData == WMSLayer:
            urlWithParams = 'contextualWMSLegend=0' \
                            '&crs=EPSG:{crs}' \
                            '&dpiMode=7' \
                            '&featureCount=10' \
                            '&format=image/jpeg' \
                            '&layers={layer}' \
                            '&styles=' \
                            '&url=http://wms.geo.admin.ch/?VERSION%3D2.0.0'\
                .format(crs=self.crs, layer=result.description)
            wms_layer = QgsRasterLayer(urlWithParams, result.displayString, 'wms')
            if not wms_layer.isValid():
                msg = self.tr('Cannot load WMS layer: {} ({})'.format(result.displayString, result.description))
                level = Qgis.Warning
                self.info(msg, level, True)
            QgsProject.instance().addMapLayer(wms_layer)

        else:
            point = QgsGeometry.fromPointXY(result.userData['point'])
            bbox = QgsGeometry.fromRect(result.userData['bbox'])
            layer = result.userData['layer']
            feature_id = result.userData['feature_id']
            if not point or not bbox:
                return

            self.dbg_info('point: {}'.format(point.asWkt()))
            self.dbg_info('bbox: {}'.format(bbox.asWkt()))
            self.dbg_info('descr: {}'.format(result.description))
            self.dbg_info('layer: {}'.format(layer))
            self.dbg_info('feature_id: {}'.format(feature_id))

            point.transform(self.transform)
            bbox.transform(self.transform)

            self.rubber_band.reset(QgsWkbTypes.PointGeometry)
            self.rubber_band.addGeometry(point, None)

            rect = bbox.boundingBox()
            rect.scale(1.1)
            self.map_canvas.setExtent(rect)
            self.map_canvas.refresh()

            if self.map_tip is not None:
                del self.map_tip
                self.map_tip = None

            # Try to get more info
            headers = {b'User-Agent': self.USER_AGENT}
            nam = NetworkAccessManager()

            if layer and feature_id:
                url_detail = 'https://api3.geo.admin.ch/rest/services/api/MapServer/{layer}/{feature_id}' \
                    .format(layer=layer, feature_id=feature_id)
                params = {
                    'lang': self.lang,
                    'sr': self.crs
                }
                url_detail = self.url_with_param(url_detail, params)
                self.dbg_info(url_detail)

            try:
                (response, content) = nam.request(url_detail, headers=headers, blocking=True)
                if response.status_code != 200:
                    self.info("Error with status code: {}".format(response.status_code))
                else:
                    self.parse_feature_response(content.decode('utf-8'))
            except RequestsExceptionUserAbort:
                pass
            except RequestsException as err:
                self.info(err)

            if self.settings.value('more_info'):
                if layer and feature_id:
                    url_html = 'https://api3.geo.admin.ch/rest/services/api/MapServer/{layer}/{feature_id}/htmlPopup'\
                        .format(layer=layer, feature_id=feature_id)
                    params = {
                        'lang': self.lang,
                        'sr': self.crs
                    }
                    url_html = self.url_with_param(url_html, params)
                    self.dbg_info(url_html)

                    try:
                        (response, content) = nam.request(url_html, headers=headers, blocking=True)
                        if response.status_code != 200:
                            self.info("Error with status code: {}".format(response.status_code))
                        else:
                            self.dbg_info(content.decode('utf-8'))
                            self.map_tip = MapTip(self.map_canvas, content.decode('utf-8'), point.asPoint())
                            self.map_tip.closed.connect(self.clear_results)
                    except RequestsExceptionUserAbort:
                        pass
                    except RequestsException as err:
                        self.info(err)

                if self.map_tip is None:
                    self.map_tip = MapTip(self.map_canvas, result.userData['html_label'], point.asPoint())
                    self.map_tip.closed.connect(self.clear_results)
            else:
                self.current_timer = QTimer()
                self.current_timer.timeout.connect(self.clear_results)
                self.current_timer.setSingleShot(True)
                self.current_timer.start(5000)

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
            geometry.transform(self.transform)

            self.feature_rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            self.feature_rubber_band.addGeometry(geometry, None)

    def info(self, msg="", level=Qgis.Info, emit_message: bool = False):
        if Qgis.QGIS_VERSION_INT >= 30100:
            self.logMessage(msg, level)
        else:
            QgsMessageLog.logMessage('{} {}'.format(self.__class__.__name__, msg), 'QgsLocatorFilter', level)
        if emit_message:
            self.message_emitted.emit(msg, level)

    def dbg_info(self, msg=""):
        if DEBUG:
            self.info(msg)

    @staticmethod
    def break_camelcase(identifier):
        matches = re.finditer('.+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)', identifier)
        return ' '.join([m.group(0) for m in matches])
