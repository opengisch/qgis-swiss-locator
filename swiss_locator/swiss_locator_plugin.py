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
from .swiss_locator_filter import SwissLocatorFilter, FilterType


class SwissLocatorPlugin:

    def __init__(self, iface: QgisInterface):
        self.iface = iface

        # initialize translation
        qgis_locale = QLocale(QSettings().value('locale/userLocale'))
        locale_path = os.path.join(os.path.dirname(__file__), 'i18n')
        self.translator = QTranslator()
        self.translator.load(qgis_locale, 'geomapfish_locator', '_', locale_path)
        QCoreApplication.installTranslator(self.translator)

        locale_lang = QLocale.languageToString(QLocale(QSettings().value('locale/userLocale')).language())

        self.locator_filters = {}
        for filter_type in FilterType:
            self.locator_filters[filter_type]= SwissLocatorFilter(filter_type, locale_lang, iface)
            self.iface.registerLocatorFilter(self.locator_filters[filter_type])
            self.locator_filters[filter_type].message_emitted.connect(self.iface.messageBar().pushMessage)

    def initGui(self):
        pass

    def unload(self):
        for locator_filter in self.filters.values():
            self.iface.deregisterLocatorFilter(locator_filter)
