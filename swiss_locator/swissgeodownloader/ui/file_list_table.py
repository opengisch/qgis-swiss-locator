"""
/***************************************************************************
 SwissGeoDownloader
                                 A QGIS plugin
 This plugin lets you comfortably download swiss geo data.
                             -------------------
        begin                : 2021-03-14
        copyright            : (C) 2025 by Patricia Moll
        email                : pimoll.dev@gmail.com
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

from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtGui import QFont, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QSizePolicy,
    QTableView,
)
from qgis.core import QgsApplication

from swiss_locator.swissgeodownloader.api.response_objects import SgdAsset


class FileListTable(QObject):
    # Ids of the files whose check state changed, and their new state
    sig_selectionChanged = pyqtSignal(list, bool)

    def __init__(self, parent, layout):
        super().__init__()
        self.parent = parent

        # Buttons above the table, the dock widget adds its own ones here
        self.buttonLayout = QHBoxLayout()
        self.toggleAllBtn = QPushButton(self.parent)
        self.toggleAllBtn.clicked.connect(self.onToggleAllClicked)
        self.buttonLayout.addWidget(self.toggleAllBtn)
        self.buttonLayout.addStretch()
        layout.addLayout(self.buttonLayout)

        self.tbl = QTableView(self.parent)
        sizePolicy = QSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding
        )
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.tbl.sizePolicy().hasHeightForWidth())
        self.tbl.setSizePolicy(sizePolicy)
        self.tbl.setMinimumHeight(160)
        self.tbl.setMaximumHeight(1200)
        self.tbl.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        self.tbl.setAutoScroll(True)

        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setObjectName("FileListTable")
        self.tbl.horizontalHeader().setVisible(False)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.verticalHeader().setVisible(True)
        self.tbl.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.tbl.verticalHeader().setDefaultSectionSize(24)
        layout.addWidget(self.tbl)

        self.model = QStandardItemModel(0, 0, self.tbl)
        self.tbl.setModel(self.model)
        # Only a click on the checkbox toggles a file, not a click on the row
        self.model.itemChanged.connect(self.onItemChanged)

        self.items: dict[str, QStandardItem] = {}
        # Set while check states are changed by code, to emit a single signal
        self.settingCheckStates = False
        self.updateToggleAllBtn()

    def fill(self, fileList: list[SgdAsset]):
        self.clear()
        for file in fileList:
            item = QStandardItem(file.id)
            item.setCheckable(True)
            item.setCheckState(Qt.CheckState.Checked)
            item.setEditable(False)
            self.model.appendRow(item)
            self.items[file.id] = item

        self.tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.updateToggleAllBtn()

    def onItemChanged(self, item: QStandardItem):
        if self.settingCheckStates or not item.isCheckable():
            return
        self.updateToggleAllBtn()
        self.sig_selectionChanged.emit(
            [item.text()], item.checkState() == Qt.CheckState.Checked
        )

    def allChecked(self) -> bool:
        return all(
            item.checkState() == Qt.CheckState.Checked for item in self.items.values()
        )

    def setChecked(self, fileIds: list[str], checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        changed = [
            fileId
            for fileId in fileIds
            if fileId in self.items and self.items[fileId].checkState() != state
        ]
        if not changed:
            return
        self.settingCheckStates = True
        try:
            for fileId in changed:
                self.items[fileId].setCheckState(state)
        finally:
            self.settingCheckStates = False
        self.updateToggleAllBtn()
        self.sig_selectionChanged.emit(changed, checked)

    def onToggleAllClicked(self):
        self.setChecked(list(self.items), not self.allChecked())

    def updateToggleAllBtn(self):
        self.toggleAllBtn.setEnabled(bool(self.items))
        if self.items and self.allChecked():
            self.toggleAllBtn.setText(self.tr("Deselect all"))
            self.toggleAllBtn.setIcon(
                QgsApplication.getThemeIcon("/mActionDeselectAll.svg")
            )
        else:
            self.toggleAllBtn.setText(self.tr("Select all"))
            self.toggleAllBtn.setIcon(
                QgsApplication.getThemeIcon("/mActionSelectAll.svg")
            )

    def showFile(self, fileId: str):
        """Selects the row of a file and scrolls it to the top: the bottom of
        the table is often hidden by the scroll area of the dock widget."""
        if fileId in self.items:
            index = self.items[fileId].index()
            self.tbl.selectRow(index.row())
            self.tbl.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtTop)

    def onEmptyList(self, message):
        self.clear()
        item = QStandardItem(message)
        item.setEditable(False)
        italicFont = QFont()
        italicFont.setItalic(True)
        item.setFont(italicFont)

        self.model.appendRow(item)
        self.tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def clear(self):
        self.model.clear()
        self.items = {}
        self.updateToggleAllBtn()
