from qgis.PyQt.QtCore import QRectF, Qt, QPointF
from qgis.PyQt.QtGui import QPainterPath, QPolygonF
from qgis.core import (
    Qgis,
    QgsAbstractProfileResults,
    QgsDoubleRange,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsProfilePoint,
    QgsProfileRenderContext,
    QgsProfileSnapResult
)

PROFILE_SYMBOLOGY = Qgis.ProfileSurfaceSymbology.FillBelow
INCLUDE_PROFILE_MARKERS = False


class SwissProfileResults(QgsAbstractProfileResults):
    def __init__(self):
        QgsAbstractProfileResults.__init__(self)

        self.__profile_curve = None
        self.raw_points = []  # QgsPointSequence
        self.cartesian_distance_to_height = {}
        self.ellipsoidal_distance_to_height = {}
        self.geometries = []
        self.cartesian_cross_section_geometries = []
        self.ellipsoidal_cross_section_geometries = []
        self.min_z = 4500
        self.max_z = -100

        self.marker_symbol = QgsMarkerSymbol.createSimple({
            'name': 'square',
            'size': 1,
            'color': '#aeaeae',
            'outline_style': 'no'
        })
        self.line_symbol = QgsLineSymbol.createSimple({'color': '#ff0000',
                                                       'width': 0.6})
        self.line_symbol.setOpacity(0.5)
        self.fill_symbol = QgsFillSymbol.createSimple({
            'color': '#ff0000',
            'style': 'solid',
            'outline_style': 'no'
        })
        self.fill_symbol.setOpacity(0.5)

    def asFeatures(self, type, feedback):
        result = []

        if type == Qgis.ProfileExportType.Features3D:
            for geom in self.geometries:
                feature = QgsAbstractProfileResults.Feature()
                feature.geometry = geom
                feature.layerIdentifier = self.type()
                result.append(feature)

        elif type == Qgis.ProfileExportType.Profile2D:
            for geom in self.cartesian_cross_section_geometries:
                feature = QgsAbstractProfileResults.Feature()
                feature.geometry = geom
                feature.layerIdentifier = self.type()
                result.append(feature)

        elif type == Qgis.ProfileExportType.DistanceVsElevationTable:
            for i, geom in enumerate(self.geometries):
                feature = QgsAbstractProfileResults.Feature()
                feature.geometry = geom
                feature.layerIdentifier = self.type()

                # Since we've got distance/elevation pairs as
                # x,y for cross-section geometries, and since
                # both point arrays have the same length:
                p = self.cartesian_cross_section_geometries[i].asPoint()
                feature.attributes = {"distance": p.x(), "elevation": p.y()}
                result.append(feature)

        return result

    def asGeometries(self):
        return self.geometries

    def sampledPoints(self):
        return self.raw_points

    def zRange(self):
        return QgsDoubleRange(self.min_z, self.max_z)

    def type(self):
        return "swiss-profile-web-service"

    def snapPoint(self, point, context):
        result = QgsProfileSnapResult()

        prev_distance = float('inf')
        prev_elevation = 0
        for k, v in self.cartesian_distance_to_height.items():
            # find segment which corresponds to the given distance along curve
            if k != 0 and prev_distance <= point.distance() <= k:
                dx = k - prev_distance
                dy = v - prev_elevation
                snapped_z = (dy / dx) * (point.distance() - prev_distance) + prev_elevation

                if abs(point.elevation() - snapped_z) > context.maximumSurfaceElevationDelta:
                    return QgsProfileSnapResult()

                result.snappedPoint = QgsProfilePoint(point.distance(), snapped_z)
                break

            prev_distance = k
            prev_elevation = v

        return result

    def renderResults(self, context: QgsProfileRenderContext):
        self.__render_continuous_surface(context)
        if INCLUDE_PROFILE_MARKERS:
            self.__render_markers(context)

    def __render_continuous_surface(self, context):
        painter = context.renderContext().painter()
        if not painter:
            return

        painter.setBrush(Qt.NoBrush)
        painter.setPen(Qt.NoPen)

        min_distance = context.distanceRange().lower()
        max_distance = context.distanceRange().upper()
        min_z = context.elevationRange().lower()
        max_z = context.elevationRange().upper()

        visible_region = QRectF(min_distance, min_z, max_distance - min_distance, max_z - min_z)
        clip_path = QPainterPath()
        clip_path.addPolygon(context.worldTransform().map(QPolygonF(visible_region)))
        painter.setClipPath(clip_path, Qt.ClipOperation.IntersectClip)

        if PROFILE_SYMBOLOGY == Qgis.ProfileSurfaceSymbology.Line:
            self.line_symbol.startRender(context.renderContext())
        elif PROFILE_SYMBOLOGY == Qgis.ProfileSurfaceSymbology.FillBelow:
            self.fill_symbol.startRender(context.renderContext())

        def check_line(
            current_line: QPolygonF,
            context: QgsProfileRenderContext,
            min_z: float,
            max_z: float,
            prev_distance: float,
            current_part_start_distance: float
        ):
            if len(current_line) > 1:
                if PROFILE_SYMBOLOGY == Qgis.ProfileSurfaceSymbology.Line:
                    self.line_symbol.renderPolyline(current_line, None, context.renderContext())
                elif PROFILE_SYMBOLOGY == Qgis.ProfileSurfaceSymbology.FillBelow:
                    current_line.append(context.worldTransform().map(QPointF(prev_distance, min_z)))
                    current_line.append(context.worldTransform().map(QPointF(current_part_start_distance, min_z)))
                    current_line.append(current_line.at(0))
                    self.fill_symbol.renderPolygon(current_line, None, None, context.renderContext())

        current_line = QPolygonF()
        prev_distance = None
        current_part_start_distance = 0
        for k, v in self.cartesian_distance_to_height.items():
            if not len(current_line):  # new part
                if not v:  # skip emptiness
                    continue

                current_part_start_distance = k

            if not v:
                check_line(current_line, context, min_z, max_z, prev_distance, current_part_start_distance)
                current_line.clear()
            else:
                current_line.append(context.worldTransform().map(QPointF(k, v)))
                prev_distance = k

        check_line(current_line, context, min_z, max_z, prev_distance, current_part_start_distance)

        if PROFILE_SYMBOLOGY == Qgis.ProfileSurfaceSymbology.Line:
            self.line_symbol.stopRender(context.renderContext())
        elif PROFILE_SYMBOLOGY == Qgis.ProfileSurfaceSymbology.FillBelow:
            self.fill_symbol.stopRender(context.renderContext())

    def __render_markers(self, context):
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

        for k, v in self.cartesian_distance_to_height.items():
            if not v:
                continue

            self.marker_symbol.renderPoint(context.worldTransform().map(QPointF(k, v)), None, context.renderContext())

        self.marker_symbol.stopRender(context.renderContext())
