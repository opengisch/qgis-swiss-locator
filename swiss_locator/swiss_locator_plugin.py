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

DEBUG = True

import os
from PyQt5.QtCore import QCoreApplication, QLocale, QSettings, QTranslator
from qgis.gui import QgisInterface
from .swiss_locator_filter import SwissLocatorFilter


class SwissLocatorPlugin:

    def __init__(self, iface: QgisInterface):
        self.iface = iface
        self.filter = SwissLocatorFilter(iface.mapCanvas())
        self.iface.registerLocatorFilter(self.filter)

        # initialize translation
        qgis_locale = QLocale(QSettings().value('locale/userLocale'))
        locale_path = os.path.join(os.path.dirname(__file__), 'i18n')
        self.translator = QTranslator()
        self.translator.load(qgis_locale, 'geomapfish_locator', '_', locale_path)
        QCoreApplication.installTranslator(self.translator)

    def initGui(self):
        pass

    def unload(self):
        self.iface.deregisterLocatorFilter(self.filter)
