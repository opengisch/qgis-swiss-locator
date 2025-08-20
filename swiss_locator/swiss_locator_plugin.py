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

import os

from qgis.PyQt.QtCore import (
    QCoreApplication,
    QLocale,
    QSettings,
    QTranslator,
    Qt
)
from qgis.PyQt.QtWidgets import QWidget
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsMessageLog,
    NULL,
    QgsSettingsTree
)
from qgis.gui import QgsDockWidget, QgisInterface, QgsMessageBarItem

from swiss_locator.core.filters.swiss_locator_filter_feature import (
    SwissLocatorFilterFeature,
)
from swiss_locator.core.filters.swiss_locator_filter_layer import (
    SwissLocatorFilterLayer,
)
from swiss_locator.core.filters.swiss_locator_filter_location import (
    SwissLocatorFilterLocation,
)
from swiss_locator.core.filters.swiss_locator_filter_stac import (
    SwissLocatorFilterSTAC
)
from swiss_locator.core.filters.swiss_locator_filter_vector_tiles import (
    SwissLocatorFilterVectorTiles,
)
from swiss_locator.core.filters.swiss_locator_filter_wmts import (
    SwissLocatorFilterWMTS
)
from swiss_locator.core.language import get_language
from swiss_locator.swissgeodownloader.ui.sgd_dockwidget import \
    SwissGeoDownloaderDockWidget

try:
    from swiss_locator.core.profiles.profile_generator import SwissProfileSource
except ImportError:
    # Should fail only for QGIS < 3.26, where profiles weren't available
    SwissProfileSource = None

from swiss_locator.core.settings import PLUGIN_NAME


class SwissLocatorPlugin:
    def __init__(self, iface: QgisInterface):
        self.iface = iface

        # initialize translation
        qgis_locale = QLocale(
            str(QSettings().value("locale/userLocale")).replace(str(NULL), "en_CH")
        )
        locale_path = os.path.join(os.path.dirname(__file__), "i18n")
        self.translator = QTranslator()
        self.translator.load(qgis_locale, "swiss_locator", "_", locale_path)
        QCoreApplication.installTranslator(self.translator)

        self.locator_filters = []
        self.stac_filter_widget: QgsDockWidget | None = None

        if Qgis.QGIS_VERSION_INT >= 33700:
            # Only on QGIS 3.37+ we'll be able to register profile sources
            self.profile_source = SwissProfileSource()

    def initGui(self):
        for _filter in (
            SwissLocatorFilterLocation,
            SwissLocatorFilterWMTS,
            SwissLocatorFilterLayer,
            SwissLocatorFilterVectorTiles,
            SwissLocatorFilterFeature,
            SwissLocatorFilterSTAC
        ):
            self.locator_filters.append(_filter(self.iface))
            self.iface.registerLocatorFilter(self.locator_filters[-1])
            self.locator_filters[-1].message_emitted.connect(self.show_message)
            if isinstance(self.locator_filters[-1], SwissLocatorFilterSTAC):
                self.locator_filters[-1].show_filter_widget.connect(
                        self.open_stac_filter_widget)

        if Qgis.QGIS_VERSION_INT >= 33700:
            QgsApplication.profileSourceRegistry().registerProfileSource(
                self.profile_source
            )
            QgsMessageLog.logMessage(
                "Swiss profile source has been registered!",
                "Swiss locator",
                Qgis.MessageLevel.Info,
            )

    def unload(self):
        for locator_filter in self.locator_filters:
            locator_filter.message_emitted.disconnect(self.show_message)
            if isinstance(locator_filter, SwissLocatorFilterSTAC):
                locator_filter.show_filter_widget.disconnect(
                        self.open_stac_filter_widget)
            self.iface.deregisterLocatorFilter(locator_filter)

        if Qgis.QGIS_VERSION_INT >= 33700:
            QgsApplication.profileSourceRegistry().unregisterProfileSource(
                self.profile_source
            )
            QgsMessageLog.logMessage(
                "Swiss profile source has been unregistered!",
                "Swiss locator",
                Qgis.MessageLevel.Info,
            )
        
        if self.stac_filter_widget:
            self.stac_filter_widget.cleanCanvas()
            self.stac_filter_widget.closingPlugin.disconnect(
                    self.close_stac_filter_widget)
            self.stac_filter_widget.deleteLater()

        QgsSettingsTree.unregisterPluginTreeNode(PLUGIN_NAME)

    def show_message(
        self, title: str, msg: str, level: Qgis.MessageLevel, widget: QWidget = None
    ):
        if widget:
            self.widget = widget
            self.item = QgsMessageBarItem(title, msg, self.widget, level, 7)
            self.iface.messageBar().pushItem(self.item)
        else:
            self.iface.messageBar().pushMessage(title, msg, level)
    
    def open_stac_filter_widget(self, collectionId):
        if not self.stac_filter_widget:
            self.stac_filter_widget = SwissGeoDownloaderDockWidget(
                    self.iface, get_language())
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,
                                     self.stac_filter_widget)
            # Connect signals to provide canvas cleanup on closing the widget
            self.stac_filter_widget.closingPlugin.connect(
                    self.close_stac_filter_widget)
            self.stac_filter_widget.show()
        
        if not self.stac_filter_widget.isUserVisible():
            self.stac_filter_widget.setUserVisible(True)
        self.stac_filter_widget.setCurrentCollection(collectionId)
    
    def close_stac_filter_widget(self):
        if self.stac_filter_widget:
            self.stac_filter_widget.cleanCanvas()
