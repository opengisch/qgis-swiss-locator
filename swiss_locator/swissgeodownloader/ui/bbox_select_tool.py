from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QApplication
from qgis.core import (
    QgsApplication,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsWkbTypes,
)
from qgis.gui import QgsMapMouseEvent, QgsMapTool, QgsRubberBand


class BboxSelectTool(QgsMapTool):
    """Map tool to select files by clicking their bbox or dragging a
    rectangle over them."""

    sig_clicked = pyqtSignal(QgsPointXY)
    # Dragged rectangle, and whether the files in it are to be deselected
    sig_rectangle = pyqtSignal(QgsRectangle, bool)

    def __init__(self, canvas):
        super().__init__(canvas)
        self.setCursor(QgsApplication.getThemeCursor(QgsApplication.Cursor.Select))
        self.rubberBand = QgsRubberBand(
            canvas, QgsWkbTypes.GeometryType.PolygonGeometry
        )
        self.rubberBand.setColor(QColor(0, 102, 255))
        self.rubberBand.setFillColor(QColor(0, 102, 255, 40))
        self.rubberBand.setWidth(1)
        self.startPos = None
        self.startPoint = None
        self.dragging = False

    def canvasPressEvent(self, e: QgsMapMouseEvent):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        self.startPos = e.pos()
        self.startPoint = e.mapPoint()
        self.dragging = False

    def canvasMoveEvent(self, e: QgsMapMouseEvent):
        if self.startPos is None:
            return
        if not self.dragging:
            distance = (e.pos() - self.startPos).manhattanLength()
            if distance < QApplication.startDragDistance():
                return
            self.dragging = True
        self.rubberBand.setToGeometry(
            QgsGeometry.fromRect(QgsRectangle(self.startPoint, e.mapPoint()))
        )

    def canvasReleaseEvent(self, e: QgsMapMouseEvent):
        if e.button() != Qt.MouseButton.LeftButton or self.startPos is None:
            return
        if self.dragging:
            rectangle = QgsRectangle(self.startPoint, e.mapPoint())
            # Ctrl on Windows and Linux, Cmd on macOS, as in QGIS select tool
            deselect = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.resetDrag()
            self.sig_rectangle.emit(rectangle, deselect)
        else:
            self.resetDrag()
            self.sig_clicked.emit(e.mapPoint())

    def deactivate(self):
        self.resetDrag()
        super().deactivate()

    def resetDrag(self):
        self.startPos = None
        self.startPoint = None
        self.dragging = False
        self.rubberBand.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
