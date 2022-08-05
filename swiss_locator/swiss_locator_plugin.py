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

DEBUG = False

import os
from PyQt5.QtCore import QCoreApplication, QLocale, QSettings, QTranslator
from PyQt5.QtWidgets import QWidget
from qgis.core import Qgis
from qgis.gui import QgisInterface, QgsMessageBarItem
from swiss_locator.core.filters.swiss_locator_filter_feature import SwissLocatorFilterFeature
from swiss_locator.core.filters.swiss_locator_filter_layer import SwissLocatorFilterLayer
from swiss_locator.core.filters.swiss_locator_filter_location import SwissLocatorFilterLocation
from swiss_locator.core.filters.swiss_locator_filter_wmts import SwissLocatorFilterWMTS


class SwissLocatorPlugin:

    def __init__(self, iface: QgisInterface):
        self.iface = iface

        # initialize translation
        qgis_locale = QLocale(QSettings().value('locale/userLocale'))
        locale_path = os.path.join(os.path.dirname(__file__), 'i18n')
        self.translator = QTranslator()
        self.translator.load(qgis_locale, 'qgis-swiss-locator', '_', locale_path)
        QCoreApplication.installTranslator(self.translator)

        self.locator_filters = []

    def initGui(self):
        for _filter in (SwissLocatorFilterLocation, SwissLocatorFilterWMTS, SwissLocatorFilterLayer, SwissLocatorFilterFeature):
            self.locator_filters.append(_filter(self.iface))
            self.iface.registerLocatorFilter(self.locator_filters[-1])
            self.locator_filters[-1].message_emitted.connect(self.show_message)

    def unload(self):
        for locator_filter in self.locator_filters:
            self.iface.deregisterLocatorFilter(locator_filter)

    def show_message(self, title: str, msg: str, level: Qgis.MessageLevel, widget: QWidget = None):
        if widget:
            self.widget = widget
            self.item = QgsMessageBarItem(title, msg, self.widget, level, 7)
            self.iface.messageBar().pushItem(self.item)
        else:
            self.iface.messageBar().pushMessage(title, msg, level)
