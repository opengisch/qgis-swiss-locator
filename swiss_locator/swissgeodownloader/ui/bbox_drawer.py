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

from qgis.PyQt.QtCore import QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFont, QPainter
from qgis.core import (
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsWkbTypes,
)
from qgis.gui import QgsRubberBand

from .qgis_utilities import transformBbox


class BboxPainter:
    """Paints the bounding boxes of the listed file into the map and labels
    them with their row number."""

    MAX_VISIBLE_SCALE = 100000
    MAX_BBOX_TO_DISPLAY = 8000

    def __init__(self, canvas, transformer: QgsCoordinateTransform):
        self.canvas = canvas
        self.transformer = transformer
        self.bboxItems = {}
        self.numberIsVisible = True
        self.meanBboxWidth = 0

    def paintBoxes(self, fileList):
        self.removeAll()
        # Limit max items to show in the map
        if len(fileList.values()) > self.MAX_BBOX_TO_DISPLAY:
            return
        for idx, file in enumerate(fileList.values()):
            if not file.bbox:
                continue
            coordinates = transformBbox(
                QgsRectangle(*tuple(file.bbox)), self.transformer
            )
            rectangle = QgsRectangle(*tuple(coordinates))
            # Bbox shape, labelled with the row number of the file in the list
            bbox = BboxMapItem(self.canvas, rectangle, file.id, str(idx + 1))
            self.bboxItems[file.id] = bbox

            self.meanBboxWidth += rectangle.width()

        if self.meanBboxWidth and len(fileList.values()):
            self.meanBboxWidth = self.meanBboxWidth / len(fileList.values())
        self.switchNumberVisibility()

    def switchNumberVisibility(self):
        # Check if the row numbers should be visible
        mapScale = self.canvas.scale()
        if self.meanBboxWidth:
            isVisible = round(mapScale) / max(round(self.meanBboxWidth), 1) <= 70
        else:
            isVisible = round(mapScale) <= self.MAX_VISIBLE_SCALE
        if self.numberIsVisible is not isVisible:
            self.numberIsVisible = isVisible
            for bbox in self.bboxItems.values():
                bbox.setNumberVisible(self.numberIsVisible)

    def removeAll(self):
        for item in self.bboxItems.values():
            item.reset()
            del item
        self.bboxItems = {}
        self.numberIsVisible = True
        self.meanBboxWidth = 0

    def setSelectState(self, fileId, selected: bool):
        if fileId in self.bboxItems:
            self.bboxItems[fileId].setSelected(selected)

    def fileIdsAt(self, point: QgsPointXY) -> list[str]:
        """Ids of the files whose bbox contains a point in map coordinates."""
        return [
            fileId for fileId, bbox in self.bboxItems.items() if bbox.isInside(point)
        ]

    def fileIdsIntersecting(self, rectangle: QgsRectangle) -> list[str]:
        """Ids of the files whose bbox intersects a rectangle in map
        coordinates."""
        return [
            fileId
            for fileId, bbox in self.bboxItems.items()
            if bbox.rectangle.intersects(rectangle)
        ]


class BboxMapItem(QgsRubberBand):
    """Creates a rectangle from a QgsRubberBand in the map, with a number in
    its centre. It is drawn on the map canvas only, not added to the project."""

    COLOR_SELECT = QColor(171, 0, 12, 30)
    COLOR_UNSELECT = QColor(171, 171, 171, 0)
    COLOR_BORDER = QColor(171, 0, 12)
    COLOR_BORDER_UNSELECTED = QColor(100, 100, 100)
    WIDTH_BORDER = 3
    COLOR_NUMBER = QColor(0, 102, 255)
    COLOR_NUMBER_BACKGROUND = QColor(255, 255, 255)

    def __init__(self, canvas, rectangle, bboxId, number: str = ""):
        self.canvas = canvas
        self.rectangle = rectangle
        self.bboxId = bboxId
        self.number = number
        self.numberVisible = True
        self.numberFont = QFont()
        self.numberFont.setPixelSize(20)
        self.numberFont.setBold(True)
        super().__init__(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)

        self.setToGeometry(QgsGeometry().fromRect(self.rectangle))
        self.setColor(self.COLOR_BORDER)
        self.setFillColor(self.COLOR_SELECT)
        self.setWidth(self.WIDTH_BORDER)
        self.selected = True
        self.xMin = self.rectangle.xMinimum()
        self.xMax = self.rectangle.xMaximum()
        self.yMin = self.rectangle.yMinimum()
        self.yMax = self.rectangle.yMaximum()
        self.show()

    def setNumberVisible(self, visible: bool):
        if visible != self.numberVisible:
            self.numberVisible = visible
            self.update()

    def paint(self, painter: QPainter):
        super().paint(painter)
        if not self.number or not self.numberVisible:
            return
        painter.save()
        painter.setFont(self.numberFont)
        metrics = painter.fontMetrics()
        label = QRectF(
            0, 0, metrics.horizontalAdvance(self.number) + 6, metrics.height()
        )
        label.moveCenter(self.toCanvasCoordinates(self.rectangle.center()) - self.pos())
        # Only where it fits: what is drawn out of the item is not repainted
        if self.boundingRect().contains(label):
            painter.fillRect(label, self.COLOR_NUMBER_BACKGROUND)
            painter.setPen(self.COLOR_NUMBER)
            painter.drawText(label, Qt.AlignmentFlag.AlignCenter, self.number)
        painter.restore()

    def isInside(self, point):
        return (
            self.xMin <= point.x() <= self.xMax and self.yMin <= point.y() <= self.yMax
        )

    def setSelected(self, selected: bool):
        if selected == self.selected:
            return
        if selected:
            self.setColor(self.COLOR_BORDER)
            self.setFillColor(self.COLOR_SELECT)
        else:
            self.setColor(self.COLOR_BORDER_UNSELECTED)
            self.setFillColor(self.COLOR_UNSELECT)
        self.selected = selected
        # Repaint the rubber band only, not the map layers
        self.update()
