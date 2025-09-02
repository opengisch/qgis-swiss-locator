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

from qgis.PyQt.QtCore import QPointF, QSizeF
from qgis.PyQt.QtGui import QColor, QTextDocument
from qgis.core import (QgsAnnotationManager, QgsCoordinateTransform,
                       QgsGeometry, QgsPointXY, QgsRectangle,
                       QgsTextAnnotation, QgsWkbTypes)
from qgis.gui import QgsRubberBand

from .qgis_utilities import transformBbox


class BboxPainter:
    """Paints the bounding boxes of the listed file into the map and labels
    them with their row number."""
    
    MAX_VISIBLE_SCALE = 100000
    MAX_BBOX_TO_DISPLAY = 8000
    
    def __init__(self, canvas, transformer: QgsCoordinateTransform,
                 annotationManager: QgsAnnotationManager):
        self.canvas = canvas
        self.transformer = transformer
        self.annotationManager = annotationManager
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
            coordinates = transformBbox(QgsRectangle(*tuple(file.bbox)),
                                        self.transformer)
            rectangle = QgsRectangle(*tuple(coordinates))
            # Bbox shape
            bbox = BboxMapItem(self.canvas, rectangle, file.id)
            self.bboxItems[file.id] = bbox

            self.meanBboxWidth += rectangle.width()
            
            # Row number as annotation
            html = ('<div style="font-size: 20px; color: rgb(0,102,255); '
                    'text-align: center; background-color: rgb(255,255,255)">'
                    '<strong>' + str(idx+1) + '</strong></div>')
            a = QgsTextAnnotation()
            c = QTextDocument()
            c.setHtml(html)
            a.setDocument(c)
            a.setMarkerSymbol(None)
            a.setFillSymbol(None)
            labelPos = QgsPointXY(rectangle.center())
            a.setMapPosition(labelPos)
            numberLen = len(str(idx+1))-1
            # Dimensions for white background box depending on number length
            sizes = [[6, 3], [9, 4], [14, 7], [18, 9]]
            a.setFrameSizeMm(QSizeF(sizes[numberLen][0], 14))
            a.setFrameOffsetFromReferencePointMm(QPointF(-sizes[numberLen][1], -4))
            a.setMapPositionCrs(self.transformer.destinationCrs())
            # Add annotation to annotation manager so it can be removed
            self.annotationManager.addAnnotation(a)
        
        if self.meanBboxWidth and len(fileList.values()):
            self.meanBboxWidth = self.meanBboxWidth / len(fileList.values())
        self.switchNumberVisibility()
    
    def switchNumberVisibility(self):
        # Check if annotation numbering should be visible
        mapScale = self.canvas.scale()
        if self.meanBboxWidth:
            isVisible = round(mapScale) / max(round(self.meanBboxWidth), 1) <= 70
        else:
            isVisible = round(mapScale) <= self.MAX_VISIBLE_SCALE
        if self.numberIsVisible is not isVisible:
            self.numberIsVisible = isVisible
            # Switch visibility of all annotations
            for ann in self.annotationManager.annotations():
                ann.setVisible(self.numberIsVisible)
    
    def removeAll(self):
        for item in self.bboxItems.values():
            item.reset()
            del item
        self.bboxItems = {}
        for ann in self.annotationManager.annotations():
            self.annotationManager.removeAnnotation(ann)
        self.numberIsVisible = True
        self.meanBboxWidth = 0
    
    def switchSelectState(self, fileId):
        if fileId in self.bboxItems:
            bbox = self.bboxItems[fileId]
            bbox.switchSelectState()


class BboxMapItem(QgsRubberBand):
    """Creates a rectangle from a QgsRubberBand in the map."""
    
    COLOR_SELECT = QColor(171, 0, 12, 30)
    COLOR_UNSELECT = QColor(171, 171, 171, 0)
    COLOR_BORDER = QColor(171, 0, 12)
    COLOR_BORDER_UNSELECTED = QColor(100, 100, 100)
    WIDTH_BORDER = 3
    
    def __init__(self, canvas, rectangle, bboxId):
        self.canvas = canvas
        self.rectangle = rectangle
        self.bboxId = bboxId
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
    
    def isInside(self, point):
        return self.xMin <= point.x() <= self.xMax and \
                self.yMin <= point.y() <= self.yMax

    def switchSelectState(self):
        if self.selected:
            # Unselect
            self.setColor(self.COLOR_BORDER_UNSELECTED)
            self.setFillColor(self.COLOR_UNSELECT)
        else:
            # Select
            self.setColor(self.COLOR_BORDER)
            self.setFillColor(self.COLOR_SELECT)
        self.selected = not self.selected
        self.canvas.refresh()

