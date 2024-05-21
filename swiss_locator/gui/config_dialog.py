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

import os
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtWidgets import QDialog, QTableWidgetItem, QAbstractItemView, QComboBox
from qgis.PyQt.uic import loadUiType
from qgis.core import QgsLocatorFilter

from ..qgissettingmanager.setting_dialog import SettingDialog, UpdateMode
from ..core.settings import Settings
from ..core.language import get_language
from ..map_geo_admin.layers import searchable_layers
from .qtwebkit_conf import with_qt_web_kit

DialogUi, _ = loadUiType(os.path.join(os.path.dirname(__file__), "../ui/config.ui"))


class ConfigDialog(QDialog, DialogUi, SettingDialog):
    def __init__(self, parent=None):
        settings = Settings()
        QDialog.__init__(self, parent)
        SettingDialog.__init__(
            self, setting_manager=settings, mode=UpdateMode.DialogAccept
        )
        self.setupUi(self)

        self.lang.addItem(
            self.tr("use the application locale, defaults to English"), ""
        )
        from ..core.filters.filter_type import FilterType
        from ..core.parameters import AVAILABLE_LANGUAGES

        for key, val in AVAILABLE_LANGUAGES.items():
            self.lang.addItem(key, val)
        for filter_type in FilterType:
            cb = self.findChild(QComboBox, "{}_priority".format(filter_type.value))
            if cb is not None:  # Some filters might not have a config dialog
                cb.addItem(self.tr("Highest"), QgsLocatorFilter.Highest)
                cb.addItem(self.tr("High"), QgsLocatorFilter.High)
                cb.addItem(self.tr("Medium"), QgsLocatorFilter.Medium)
                cb.addItem(self.tr("Low"), QgsLocatorFilter.Low)
                cb.addItem(self.tr("Lowest"), QgsLocatorFilter.Lowest)

        self.crs.addItem(
            self.tr("Use map CRS if possible, defaults to CH1903+"), "project"
        )
        self.crs.addItem("CH 1903+ (EPSG:2056)", "2056")
        self.crs.addItem("CH 1903 (EPSG:21781)", "21781")

        self.search_line_edit.textChanged.connect(self.filter_rows)
        self.select_all_button.pressed.connect(self.select_all)
        self.unselect_all_button.pressed.connect(lambda: self.select_all(False))

        lang = get_language()
        layers = searchable_layers(lang)
        self.feature_search_layers_list.setRowCount(len(layers))
        self.feature_search_layers_list.setColumnCount(2)
        self.feature_search_layers_list.setHorizontalHeaderLabels(
            (self.tr("Layer"), self.tr("Description"))
        )
        self.feature_search_layers_list.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.feature_search_layers_list.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        r = 0
        for layer, description in layers.items():
            item = QTableWidgetItem(layer)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            # item.setCheckState(Qt.Unchecked)
            self.feature_search_layers_list.setItem(r, 0, item)
            self.feature_search_layers_list.setItem(r, 1, QTableWidgetItem(description))
            r += 1
        self.feature_search_layers_list.horizontalHeader().setStretchLastSection(True)
        self.feature_search_layers_list.resizeColumnsToContents()

        self.settings = settings
        self.init_widgets()

        if not with_qt_web_kit():
            map_tip = self.setting_widget("show_map_tip")
            map_tip.widget.setEnabled(False)
            map_tip.widget.setToolTip(self.tr("You need to install QtWebKit to use map tips."))

    def select_all(self, select: bool = True):
        for r in range(self.feature_search_layers_list.rowCount()):
            item = self.feature_search_layers_list.item(r, 0)
            item.setCheckState(Qt.Checked if select else Qt.Unchecked)

    @pyqtSlot(str)
    def filter_rows(self, text: str):
        if text:
            items = self.feature_search_layers_list.findItems(text, Qt.MatchContains)
            print(text)
            print(len(items))
            shown_rows = []
            for item in items:
                shown_rows.append(item.row())
            shown_rows = list(set(shown_rows))
            for r in range(self.feature_search_layers_list.rowCount()):
                self.feature_search_layers_list.setRowHidden(r, r not in shown_rows)
        else:
            for r in range(self.feature_search_layers_list.rowCount()):
                self.feature_search_layers_list.setRowHidden(r, False)
