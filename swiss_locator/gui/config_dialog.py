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
from qgis.PyQt.QtCore import Qt, pyqtSlot
from qgis.PyQt.QtWidgets import QDialog, QTableWidgetItem, QAbstractItemView, QComboBox
from qgis.PyQt.uic import loadUiType
from qgis.core import QgsLocatorFilter, metaEnumFromType
from qgis.gui import (
    QgsSettingsEditorWidgetWrapper,
    QgsSettingsStringComboBoxWrapper,
    QgsSettingsBoolCheckBoxWrapper,
)

from ..core.settings import Settings
from ..core.language import get_language
from ..map_geo_admin.layers import searchable_layers
from .qtwebkit_conf import with_qt_web_kit
from ..core.filters.filter_type import FilterType
from ..core.parameters import AVAILABLE_LANGUAGES

DialogUi, _ = loadUiType(os.path.join(os.path.dirname(__file__), "../ui/config.ui"))


class ConfigDialog(QDialog, DialogUi):
    def accept(self):
        for wrapper in self.wrappers:
            wrapper.setSettingFromWidget()

        layers_list = []
        for r in range(self.feature_search_layers_list.rowCount()):
            item = self.feature_search_layers_list.item(r, 0)
            if item.checkState() == Qt.CheckState.Checked:
                layers_list.append(item.text())
        self.settings.feature_search_layers_list.setValue(layers_list)
        super().accept()

    def __init__(self, parent=None):
        self.settings = Settings()
        QDialog.__init__(self, parent)
        self.setupUi(self)
        self.wrappers: [QgsSettingsEditorWidgetWrapper] = []

        self.lang.addItem(
            self.tr("use the application locale, defaults to English"), ""
        )
        for key, val in AVAILABLE_LANGUAGES.items():
            self.lang.addItem(key, val)

        self.wrappers.append(
            QgsSettingsStringComboBoxWrapper(
                self.lang,
                self.settings.lang,
                QgsSettingsStringComboBoxWrapper.Mode.Data,
            )
        )

        self.wrappers.append(
            QgsSettingsBoolCheckBoxWrapper(
                self.layers_include_opendataswiss,
                self.settings.layers_include_opendataswiss,
            )
        )
        self.wrappers.append(
            QgsSettingsBoolCheckBoxWrapper(
                self.feature_search_restrict, self.settings.feature_search_restrict
            )
        )

        me = metaEnumFromType(QgsLocatorFilter.Priority)
        for filter_type in FilterType:
            cb = self.findChild(QComboBox, "{}_priority".format(filter_type.value))
            if cb is not None:  # Some filters might not have a config dialog
                cb.addItem(
                    self.tr("Highest"), me.valueToKey(QgsLocatorFilter.Priority.Highest)
                )
                cb.addItem(
                    self.tr("High"), me.valueToKey(QgsLocatorFilter.Priority.High)
                )
                cb.addItem(
                    self.tr("Medium"), me.valueToKey(QgsLocatorFilter.Priority.Medium)
                )
                cb.addItem(self.tr("Low"), me.valueToKey(QgsLocatorFilter.Priority.Low))
                cb.addItem(
                    self.tr("Lowest"), me.valueToKey(QgsLocatorFilter.Priority.Lowest)
                )

                self.wrappers.append(
                    QgsSettingsStringComboBoxWrapper(
                        cb,
                        self.settings.filters[filter_type.value]["priority"],
                        QgsSettingsStringComboBoxWrapper.Mode.Data,
                    )
                )

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
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.feature_search_layers_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        r = 0
        layers_list = self.settings.feature_search_layers_list.value()
        for layer, description in layers.items():
            item = QTableWidgetItem(layer)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            checked = layer in layers_list
            item.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
            self.feature_search_layers_list.setItem(r, 0, item)
            self.feature_search_layers_list.setItem(r, 1, QTableWidgetItem(description))
            r += 1
        self.feature_search_layers_list.horizontalHeader().setStretchLastSection(True)
        self.feature_search_layers_list.resizeColumnsToContents()

        if not with_qt_web_kit():
            self.show_map_tip.setEnabled(False)
            self.show_map_tip.setToolTip(
                self.tr("You need to install QtWebKit to use map tips.")
            )
        else:
            self.wrappers.append(
                QgsSettingsBoolCheckBoxWrapper(
                    self.show_map_tip, self.settings.show_map_tip
                )
            )

    def select_all(self, select: bool = True):
        for r in range(self.feature_search_layers_list.rowCount()):
            item = self.feature_search_layers_list.item(r, 0)
            item.setCheckState(
                Qt.CheckState.Checked if select else Qt.CheckState.Unchecked
            )

    @pyqtSlot(str)
    def filter_rows(self, text: str):
        if text:
            items = self.feature_search_layers_list.findItems(
                text, Qt.MatchFlag.MatchContains
            )
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
