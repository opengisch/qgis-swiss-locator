import json
import math

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
from qgis.core import (
    Qgis,
    QgsAbstractProfileGenerator,
    QgsAbstractProfileSource,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsFeedback,
    QgsGeometry,
    QgsGeometryUtils,
    QgsMessageLog,
    QgsNetworkAccessManager,
    QgsPoint,
)

from swiss_locator.core.profiles.profile_results import SwissProfileResults
from swiss_locator.core.profiles.profile_url import (
    MAX_POINTS,
    MAX_VERTICES,
    SPACING,
    profile_url,
)
from swiss_locator.utils.utils import url_with_param

# Lines needing more requests than this at SPACING, over 100 km, get points
# further apart instead
MAX_REQUESTS = 10

# Lengths closer than this (in m) are the same
TOLERANCE = 0.001


def line_length(coordinates: list) -> float:
    return sum(math.dist(a, b) for a, b in zip(coordinates, coordinates[1:]))


def spacing_for(length: float) -> float:
    """The distance between the points of the profile of a line."""
    return max(SPACING, length / (MAX_REQUESTS * (MAX_POINTS - 1)))


def points_for_piece(piece_length: float, spacing: float) -> int:
    """The number of points to ask the profile service for along a piece of
    line: it spreads them along its segments, besides keeping its vertices."""
    return min(MAX_POINTS, max(2, math.ceil(piece_length / spacing) + 1))


def split_line(
    coordinates: list,
    max_vertices: int = MAX_VERTICES,
    max_length: float = math.inf,
) -> list:
    """Cut a line into pieces the profile service accepts: of at most
    max_vertices vertices and max_length long. Each piece starts where the
    previous one ends, so no part of the line is left out."""
    pieces = []
    piece = [coordinates[0]]
    length = 0.0
    for vertex in coordinates[1:]:
        start = piece[-1]
        segment = math.dist(start, vertex)
        while length + segment > max_length + TOLERANCE:
            if max_length - length > TOLERANCE:
                ratio = (max_length - length) / segment
                start = [
                    round(start[0] + (vertex[0] - start[0]) * ratio, 3),
                    round(start[1] + (vertex[1] - start[1]) * ratio, 3),
                ]
                piece.append(start)
            pieces.append(piece)
            piece = [start]
            length = 0.0
            segment = math.dist(start, vertex)
        piece.append(vertex)
        length += segment
        if len(piece) == max_vertices:
            pieces.append(piece)
            piece = [vertex]
            length = 0.0
    if len(piece) > 1 or not pieces:
        pieces.append(piece)
    return pieces


def api_error_message(content) -> str | None:
    """The reason the profile service gives for refusing a request, or None
    if the reply does not give one."""
    try:
        return json.loads(bytes(content).decode("utf-8"))["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return None


class SwissProfileGenerator(QgsAbstractProfileGenerator):
    X = "easting"
    Y = "northing"
    DISTANCE = "dist"
    Z_DICT = "alts"
    Z = "DTM2"

    def __init__(self, request):
        QgsAbstractProfileGenerator.__init__(self)
        self.__request = request
        self.__profile_curve = (
            request.profileCurve().clone() if request.profileCurve() else None
        )
        self.__transformed_curve = None
        self.__transformation = QgsCoordinateTransform(
            request.crs(),  # Profile curve's CRS
            QgsCoordinateReferenceSystem("EPSG:2056"),
            request.transformContext(),
        )
        self.__results = None  # SwissProfileResults()
        self.__feedback = QgsFeedback()

    def sourceId(self):
        return "swiss-profile"

    def __get_profile_from_rest_api(self):
        """The points of the profile of the whole line, with their distances
        from its start, or a dict with an error."""
        line = self.__transformed_curve.curveToLine()
        coordinates = [[round(p.x(), 3), round(p.y(), 3)] for p in line.points()]
        spacing = spacing_for(line_length(coordinates))
        pieces = split_line(coordinates, MAX_VERTICES, (MAX_POINTS - 1) * spacing)

        result = []
        offset = 0
        for index, piece in enumerate(pieces):
            if self.__feedback.isCanceled():
                return []
            piece_length = line_length(piece)
            points = self.__get_piece_profile(
                piece, points_for_piece(piece_length, spacing)
            )
            if "error" in points:
                return points
            for point in points:
                # The start of a piece is the end of the previous one
                if index > 0 and point[self.DISTANCE] == 0:
                    continue
                result.append({**point, self.DISTANCE: point[self.DISTANCE] + offset})
            offset += piece_length
        return result

    def __get_piece_profile(self, coordinates, nb_points):
        geojson = json.dumps({"type": "LineString", "coordinates": coordinates})
        base_url, base_params = profile_url(nb_points)
        url = url_with_param(base_url, base_params)

        network_access_manager = QgsNetworkAccessManager.instance()

        req = QNetworkRequest(QUrl(url))
        req.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json"
        )
        reply = network_access_manager.blockingPost(
            req, geojson.encode("utf-8"), feedback=self.__feedback
        )

        if reply.error() == QNetworkReply.NetworkError.NoError:
            content = reply.content()
            try:
                result = json.loads(str(content, "utf-8"))
            except json.decoder.JSONDecodeError as e:
                result = {
                    "error": "Unable to parse results from Profile service. "
                    f"Details: {e.msg}"
                }
        else:
            details = reply.errorString()
            api_message = api_error_message(reply.content())
            if api_message:
                details += f": {api_message}"
            result = {
                "error": "Error from the profile server. Details: "
                + details
                + f" (status code: {reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)}, error code: {reply.error()})"
            }

        return result

    def __parse_response_point(self, point):
        return (
            point[self.X],
            point[self.Y],
            point[self.Z_DICT][self.Z],
            point[self.DISTANCE],
        )

    def feedback(self):
        return self.__feedback

    def generateProfile(self, context):  # QgsProfileGenerationContext
        if self.__profile_curve is None:
            return False

        self.__transformed_curve = self.__profile_curve.clone()
        try:
            self.__transformed_curve.transform(self.__transformation)
        except QgsCsException as e:
            QgsMessageLog.logMessage(
                f"Error transforming profile line to EPSG 2056. Details: {e}",
                "Swiss locator",
                Qgis.MessageLevel.Critical,
            )
            return False

        self.__results = SwissProfileResults()
        self.__results.copyPropertiesFromGenerator(self)

        result = self.__get_profile_from_rest_api()

        if "error" in result:
            QgsMessageLog.logMessage(
                result["error"], "Swiss locator", Qgis.MessageLevel.Critical
            )
            return False

        cartesian_d = 0
        for point in result:
            if self.__feedback.isCanceled():
                return False

            # Note: d is ellipsoidal from the API
            x, y, z, d = self.__parse_response_point(point)
            point_z = QgsPoint(x, y, z)
            point_z.transform(self.__transformation, Qgis.TransformDirection.Reverse)

            self.__results.ellipsoidal_distance_to_height[d] = z
            self.__results.ellipsoidal_cross_section_geometries.append(
                QgsGeometry(QgsPoint(d, z))
            )

            try:
                if d != 0:
                    # QGIS elevation profile won't calculate distances
                    # using 3d, so let's stick to 2d to avoid getting
                    # displaced markers or lines in the profile canvas
                    cartesian_d += QgsGeometryUtils.distance2D(
                        point_z, self.__results.raw_points[-1]
                    )
            except IndexError as e:
                QgsMessageLog.logMessage(
                    f"\nError in SwissLocator Elevation Profile. Details: {e}",
                    "Swiss locator",
                    Qgis.MessageLevel.Critical,
                )
                return False

            self.__results.raw_points.append(point_z)
            self.__results.cartesian_distance_to_height[cartesian_d] = z
            self.__results.cartesian_cross_section_geometries.append(
                QgsGeometry(QgsPoint(cartesian_d, z))
            )

            if z < self.__results.min_z:
                self.__results.min_z = z

            if z > self.__results.max_z:
                self.__results.max_z = z

            self.__results.geometries.append(QgsGeometry(point_z))

        return not self.__feedback.isCanceled()

    def takeResults(self):
        return self.__results


class SwissProfileSource(QgsAbstractProfileSource):
    def __init__(self):
        QgsAbstractProfileSource.__init__(self)

    def profileSourceId(self):
        return "swiss-profile"

    def profileSourceName(self):
        return "Swiss Profile"

    def createProfileGenerator(self, request):
        return SwissProfileGenerator(request)
