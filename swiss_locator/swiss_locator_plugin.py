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
    QTimer,
    QTranslator,
    Qt,
)
from qgis.PyQt.QtWidgets import QApplication, QDialog, QWidget
from qgis.core import Qgis, QgsApplication, QgsMessageLog, NULL, QgsSettingsTree
from qgis.gui import QgsDockWidget, QgisInterface, QgsMessageBarItem

from swiss_locator.core.filters.filter_type import FilterType
from swiss_locator.core.filters.opendata_swiss import WMS_LAYERS_INDEX
from swiss_locator.core.filters.swiss_locator_filter import SwissLocatorFilter
from swiss_locator.core.filters.swiss_locator_filter_feature import (
    SwissLocatorFilterFeature,
)
from swiss_locator.core.filters.swiss_locator_filter_layer import (
    SwissLocatorFilterLayer,
)
from swiss_locator.core.filters.swiss_locator_filter_location import (
    SwissLocatorFilterLocation,
)
from swiss_locator.core.filters.swiss_locator_filter_stac import SwissLocatorFilterSTAC
from swiss_locator.core.filters.swiss_locator_filter_vector_tiles import (
    SwissLocatorFilterVectorTiles,
)
from swiss_locator.core.filters.swiss_locator_filter_wmts import SwissLocatorFilterWMTS
from swiss_locator.core.language import get_language
from swiss_locator.core.settings import PLUGIN_NAME, Settings
from swiss_locator.gui.config_dialog import ConfigDialog
from swiss_locator.gui.welcome_dialog import WelcomeDialog, turn_on_default_catalogs
from swiss_locator.map_geo_admin.layers import SEARCHABLE_LAYERS
from swiss_locator.processing.provider import SwissLocatorProcessingProvider
from swiss_locator.swissgeodownloader.api.catalogs import STAC_CATALOGS
from swiss_locator.swissgeodownloader.api.datageoadmin import ApiDataGeoAdmin
from swiss_locator.swissgeodownloader.ui.sgd_dockwidget import (
    SwissGeoDownloaderDockWidget,
)

try:
    from swiss_locator.core.profiles.profile_generator import SwissProfileSource
except ImportError:
    # Should fail only for QGIS < 3.26, where profiles weren't available
    SwissProfileSource = None


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

        self.settings = Settings()
        self.locator_filters: list[SwissLocatorFilter] = []
        self.stac_filter_widget: QgsDockWidget | None = None
        self.welcome_dialog: WelcomeDialog | None = None
        # The modal dialog the welcome dialog waits for to close
        self.welcome_dialog_blocker: QDialog | None = None
        self.provider: SwissLocatorProcessingProvider | None = None

        if Qgis.QGIS_VERSION_INT >= 33700:
            # Only on QGIS 3.37+ we'll be able to register profile sources
            self.profile_source = SwissProfileSource()

    def initProcessing(self):
        # Called by QGIS before initGui() (hasProcessingProvider=yes in the
        # metadata) and by qgis_process, hence the guard against a double
        # registration
        if self.provider is None:
            self.provider = SwissLocatorProcessingProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()

        # Update the data published by the plugin on GitHub Pages, in the background
        for remote_data_file in (SEARCHABLE_LAYERS, WMS_LAYERS_INDEX):
            remote_data_file.refresh()

        for _filter in (
            SwissLocatorFilterLocation,
            SwissLocatorFilterWMTS,
            SwissLocatorFilterLayer,
            SwissLocatorFilterVectorTiles,
            SwissLocatorFilterFeature,
        ):
            self.register_filter(_filter(self.iface))
        turn_on_default_catalogs()
        self.update_stac_filters()

        if Qgis.QGIS_VERSION_INT >= 33700:
            QgsApplication.profileSourceRegistry().registerProfileSource(
                self.profile_source
            )
            QgsMessageLog.logMessage(
                "Swiss profile source has been registered!",
                "Swiss locator",
                Qgis.MessageLevel.Info,
            )

        if WelcomeDialog.is_due():
            if self.iface.mainWindow().isVisible():
                # Enabled or upgraded from the plugin manager
                self.show_welcome_dialog()
            else:
                # Loaded at the launch of QGIS: once its window shows
                self.iface.initializationCompleted.connect(self.show_welcome_dialog)

    def unload(self):
        try:
            self.iface.initializationCompleted.disconnect(self.show_welcome_dialog)
        except TypeError:
            # Not connected
            pass
        if self.welcome_dialog_blocker:
            self.welcome_dialog_blocker.finished.disconnect(
                self.welcome_dialog_unblocked
            )
            self.welcome_dialog_blocker = None
        if self.welcome_dialog:
            self.welcome_dialog.finished.disconnect(self.welcome_dialog_finished)
            self.welcome_dialog.deleteLater()
            self.welcome_dialog = None

        for locator_filter in list(self.locator_filters):
            self.deregister_filter(locator_filter)

        if Qgis.QGIS_VERSION_INT >= 33700:
            if Qgis.QGIS_VERSION_INT >= 39900:  # Change to 40000 from QGIS 4.0 onwards
                QgsApplication.profileSourceRegistry().unregisterProfileSource(
                    "swiss-profile"
                )
            else:  # Legacy, remove for QGIS v4.0
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
                self.close_stac_filter_widget
            )
            self.stac_filter_widget.deleteLater()

        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

        QgsSettingsTree.unregisterPluginTreeNode(PLUGIN_NAME)

    def register_filter(self, locator_filter: SwissLocatorFilter):
        self.iface.registerLocatorFilter(locator_filter)
        locator_filter.message_emitted.connect(self.show_message)
        locator_filter.config_changed.connect(self.config_changed)
        if isinstance(locator_filter, SwissLocatorFilterSTAC):
            locator_filter.show_filter_widget.connect(self.open_stac_filter_widget)
        self.locator_filters.append(locator_filter)

    def deregister_filter(self, locator_filter: SwissLocatorFilter):
        locator_filter.message_emitted.disconnect(self.show_message)
        locator_filter.config_changed.disconnect(self.config_changed)
        if isinstance(locator_filter, SwissLocatorFilterSTAC):
            locator_filter.show_filter_widget.disconnect(self.open_stac_filter_widget)
        self.locator_filters.remove(locator_filter)
        # Deletes the filter
        self.iface.deregisterLocatorFilter(locator_filter)

    def update_stac_filters(self):
        """One filter per STAC catalog, so the results are grouped by source:
        data.geo.admin.ch and the local catalogs chosen in the settings"""
        catalog_ids = [
            ApiDataGeoAdmin.CATALOG_ID,
            *self.settings.stac_local_catalogs.value(),
        ]
        registered = set()
        for locator_filter in list(self.locator_filters):
            if isinstance(locator_filter, SwissLocatorFilterSTAC):
                if locator_filter.catalog.CATALOG_ID in catalog_ids:
                    registered.add(locator_filter.catalog.CATALOG_ID)
                else:
                    self.deregister_filter(locator_filter)
        for catalog_id in STAC_CATALOGS:
            if catalog_id in catalog_ids and catalog_id not in registered:
                self.register_filter(
                    SwissLocatorFilterSTAC(self.iface, catalog_id=catalog_id)
                )

    def config_changed(self):
        """The configuration of the plugin was saved. It opens from the options
        of QGIS, whose locator page holds the filters until it closes: update
        the filters of the catalogs then."""
        options = QApplication.activeModalWidget()
        if isinstance(options, QDialog):
            options.finished.connect(
                lambda: QTimer.singleShot(0, self.update_stac_filters)
            )
        else:
            self.update_stac_filters()

    def show_welcome_dialog(self):
        if self.welcome_dialog or self.welcome_dialog_blocker:
            return
        blocker = QApplication.activeModalWidget()
        if isinstance(blocker, QDialog):
            # The plugin manager, modal, when the plugin is enabled or upgraded
            # from it: opened now, the dialog would block it, hidden behind it
            self.welcome_dialog_blocker = blocker
            blocker.finished.connect(self.welcome_dialog_unblocked)
            return
        self.welcome_dialog = WelcomeDialog(self.iface.mainWindow())
        self.welcome_dialog.finished.connect(self.welcome_dialog_finished)
        self.welcome_dialog.open()

    def welcome_dialog_unblocked(self):
        self.welcome_dialog_blocker.finished.disconnect(self.welcome_dialog_unblocked)
        self.welcome_dialog_blocker = None
        QTimer.singleShot(0, self.show_welcome_dialog)

    def welcome_dialog_finished(self):
        open_settings = self.welcome_dialog.open_settings
        self.welcome_dialog.deleteLater()
        self.welcome_dialog = None
        self.update_stac_filters()
        if open_settings:
            QTimer.singleShot(0, self.open_config_dialog)

    def open_config_dialog(self):
        dialog = ConfigDialog(self.iface.mainWindow())
        dialog.set_current_tab(FilterType.STAC)
        if dialog.exec():
            self.update_stac_filters()

    def show_message(
        self, title: str, msg: str, level: Qgis.MessageLevel, widget: QWidget = None
    ):
        if widget:
            self.widget = widget
            self.item = QgsMessageBarItem(title, msg, self.widget, level, 7)
            self.iface.messageBar().pushItem(self.item)
        else:
            self.iface.messageBar().pushMessage(title, msg, level)

    def open_stac_filter_widget(self, catalogId, collectionId):
        if not self.stac_filter_widget:
            self.stac_filter_widget = SwissGeoDownloaderDockWidget(
                self.iface, get_language()
            )
            self.iface.addDockWidget(
                Qt.DockWidgetArea.RightDockWidgetArea, self.stac_filter_widget
            )
            # Connect signals to provide canvas cleanup on closing the widget
            self.stac_filter_widget.closingPlugin.connect(self.close_stac_filter_widget)
            self.stac_filter_widget.show()

            # Hide some filter widget Ui elements for use with swiss-locator
            self.stac_filter_widget.guiGroupDataset.setCollapsed(True)
            self.stac_filter_widget.guiInfoBtn.setVisible(False)
            self.stac_filter_widget.guiRefreshDatasetsBtn.setVisible(False)
            title = QCoreApplication.translate(
                "SGD", "Swiss Locator: Filter files to download"
            )
            self.stac_filter_widget.setWindowTitle(title)

        if not self.stac_filter_widget.isUserVisible():
            self.stac_filter_widget.setUserVisible(True)
        self.stac_filter_widget.setCurrentCollection(catalogId, collectionId)

    def close_stac_filter_widget(self):
        if self.stac_filter_widget:
            self.stac_filter_widget.cleanCanvas()
