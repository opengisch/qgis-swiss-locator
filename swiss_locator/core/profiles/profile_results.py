from qgis.PyQt.QtCore import QRectF, Qt, QPointF
from qgis.PyQt.QtGui import QPainterPath, QPolygonF
from qgis.core import (
    Qgis,
    QgsAbstractProfileResults,
    QgsDoubleRange,
    QgsMarkerSymbol,
    QgsProfileRenderContext,
)


class SwissProfileResults(QgsAbstractProfileResults):
    def __init__(self):
        QgsAbstractProfileResults.__init__(self)

        self.__profile_curve = None
        self.raw_points = []  # QgsPointSequence
        self.__symbology = None

        self.distance_to_height = {}
        self.geometries = []
        self.cross_section_geometries = []
        self.min_z = 4500
        self.max_z = -100

        self.marker_symbol = QgsMarkerSymbol.createSimple(
            {'name': 'square', 'size': 2, 'color': '#00ff00',
             'outline_style': 'no'})

    def asFeatures(self, profile_export_type, feedback):
        result = []

        if type == Qgis.ProfileExportType.Features3D:
            for geom in self.geometries:
                feature = QgsAbstractProfileResults.Feature()
                feature.geometry = geom
                result.append(feature)

        elif type == Qgis.ProfileExportType.Profile2D:
            for geom in self.cross_section_geometries:
                feature = QgsAbstractProfileResults.Feature()
                feature.geometry = geom
                result.append(feature)

        return result

    def asGeometries(self):
        return self.geometries

    def zRange(self):
        return QgsDoubleRange(self.min_z, self.max_z)

    def type(self):
        return "swiss-web-service"

    def renderResults(self, context: QgsProfileRenderContext):
        painter = context.renderContext().painter()
        if not painter:
            return

        painter.setBrush(Qt.NoBrush)
        painter.setPen(Qt.NoPen)

        minDistance = context.distanceRange().lower()
        maxDistance = context.distanceRange().upper()
        minZ = context.elevationRange().lower()
        maxZ = context.elevationRange().upper()

        visibleRegion = QRectF(minDistance, minZ, maxDistance - minDistance, maxZ - minZ)
        clipPath = QPainterPath()
        clipPath.addPolygon(context.worldTransform().map(QPolygonF(visibleRegion)))
        painter.setClipPath(clipPath, Qt.ClipOperation.IntersectClip)

        self.marker_symbol.startRender(context.renderContext())

        for k, v in self.distance_to_height.items():
            if not v:
                continue

            self.marker_symbol.renderPoint(context.worldTransform().map(QPointF(k, v)), None, context.renderContext())

        self.marker_symbol.stopRender(context.renderContext())
