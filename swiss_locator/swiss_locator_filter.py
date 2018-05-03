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
from qgis.PyQt.QtCore import pyqtSignal
from qgis.core import Qgis, QgsMessageLog, QgsLocatorFilter, QgsLocatorResult, QgsRectangle, \
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject

from .network_access_manager import NetworkAccessManager, RequestsException


class SwissLocatorFilter(QgsLocatorFilter):

    USER_AGENT = b'Mozilla/5.0 QGIS NominatimLocatorFilter'

    # some magic numbers to be able to zoom to more or less defined levels
    ADDRESS = 1000
    STREET = 1500
    ZIP = 3000
    PLACE = 30000
    CITY = 120000
    ISLAND = 250000
    COUNTRY = 4000000

    resultProblem = pyqtSignal(str)

    def __init__(self, iface):
        super().__init__(iface)

    def name(self):
        return self.__class__.__name__

    def clone(self):
        return SwissLocatorFilter(self.iface)

    def displayName(self):
        return self.tr('Swiss Geoadmin locations')

    def prefix(self):
        return 'ch'

    def fetchResults(self, search, context, feedback):

        if len(search) < 2:
            return

        url = 'https://api3.geo.admin.ch/rest/services/api/SearchServer?type={type}&searchText={search}'.format(
            type='locations', search=search)

        self.info('Search url {}'.format(url))
        nam = NetworkAccessManager()
        try:
            # see https://operations.osmfoundation.org/policies/nominatim/
            # "Provide a valid HTTP Referer or User-Agent identifying the application (QGIS geocoder)"
            headers = {b'User-Agent': self.USER_AGENT}
            # use BLOCKING request, as fetchResults already has it's own thread!
            (response, content) = nam.request(url, headers=headers, blocking=True)
            self.info(response)
            #self.info(response.status_code)
            if response.status_code == 200:  # other codes are handled by NetworkAccessManager
                content_string = content.decode('utf-8')
                locations = json.loads(content_string)
                for loc in locations:
                    result = QgsLocatorResult()
                    result.filter = self
                    result.displayString = '{} ({})'.format(loc['display_name'], loc['type'])
                    # use the json full item as userData, so all info is in it:
                    result.userData = loc
                    self.resultFetched.emit(result)

        except RequestsException as err:
            # Handle exception..
            # only this one seems to work
            self.info(err)
            # THIS: results in a floating window with a warning in it, wrong thread/parent?
            #self.iface.messageBar().pushWarning("NominatimLocatorFilter Error", '{}'.format(err))
            # THIS: emitting the signal here does not work either?
            self.resultProblem.emit('{}'.format(err))

    def triggerResult(self, result):
        self.info("UserClick: {}".format(result.displayString))
        doc = result.userData
        extent = doc['boundingbox']
        # "boundingbox": ["52.641015", "52.641115", "5.6737302", "5.6738302"]
        rect = QgsRectangle(float(extent[2]), float(extent[0]), float(extent[3]), float(extent[1]))
        dest_crs = QgsProject.instance().crs()
        results_crs = QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.PostgisCrsId)
        transform = QgsCoordinateTransform(results_crs, dest_crs, QgsProject.instance())
        r = transform.transformBoundingBox(rect)
        self.iface.mapCanvas().setExtent(r, False)
        # map the result types to generic GeocoderLocator types to determine the zoom
        # BUT only if the extent < 100 meter (as for other objects it is probably ok)
        # mmm, some objects return 'type':'province', but extent is point
        scale_denominator = self.ZIP  # defaulting to something
        # TODO add other types?
        if doc['type'] in ['house', 'information']:
            scale_denominator = self.ADDRESS
        elif doc['type'] in ['way', 'motorway_junction', 'cycleway']:
            scale_denominator = self.STREET
        elif doc['type'] in ['postcode']:
            scale_denominator = self.ZIP
        elif doc['type'] in ['city']:
            scale_denominator = self.CITY
        elif doc['type'] in ['island']:
            scale_denominator = self.ISLAND
        elif doc['type'] in ['administrative']:  # ?? can also be a city etc...
            scale_denominator = self.COUNTRY

        self.iface.mapCanvas().zoomScale(scale_denominator)
        self.iface.mapCanvas().refresh()

    def info(self, msg=""):
        QgsMessageLog.logMessage('{} {}'.format(self.__class__.__name__, msg), 'QgsLocatorFilter', Qgis.Info)