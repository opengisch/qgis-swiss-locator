import json

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest
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
from swiss_locator.core.profiles.profile_url import profile_url
from swiss_locator.utils.utils import url_with_param


class SwissProfileGenerator(QgsAbstractProfileGenerator):
    X = "easting"
    Y = "northing"
    DISTANCE = "dist"
    Z_DICT = "alts"
    Z = "DTM2"

    def __init__(self, request):
        QgsAbstractProfileGenerator.__init__(self)
        self.__request = request
        self.__profile_curve = request.profileCurve().clone() if request.profileCurve() else None
        self.__transformed_curve = None
        self.__transformation = QgsCoordinateTransform(request.crs(),  # Profile curve's CRS
                                                       QgsCoordinateReferenceSystem("EPSG:2056"),
                                                       request.transformContext())
        self.__results = None  # SwissProfileResults()
        self.__feedback = QgsFeedback()

    def sourceId(self):
        return "swiss-profile"

    def __get_profile_from_rest_api(self):
        result = {}
        geojson = self.__transformed_curve.asJson(3)
        base_url, base_params = profile_url(geojson)
        url = url_with_param(base_url, base_params)

        network_access_manager = QgsNetworkAccessManager.instance()

        req = QNetworkRequest(QUrl(url))
        reply = network_access_manager.blockingGet(req, feedback=self.__feedback)

        if reply.error():
            result = {"error": reply.errorString()}
        else:
            content = reply.content()
            try:
                result = json.loads(str(content, 'utf-8'))
            except json.decoder.JSONDecodeError as e:
                QgsMessageLog.logMessage(
                        "Unable to parse results from Profile service. Details: {}".format(
                            e.msg),
                        "Locator bar",
                        Qgis.MessageLevel.Critical
                )

        return result

    def __parse_response_point(self, point):
        return point[self.X], point[self.Y], point[self.Z_DICT][self.Z], point[self.DISTANCE]

    def feedback(self):
        return self.__feedback

    def generateProfile(self, context):  # QgsProfileGenerationContext
        if self.__profile_curve is None:
            return False

        self.__transformed_curve = self.__profile_curve.clone()
        try:
            self.__transformed_curve.transform(self.__transformation)
        except QgsCsException as e:
            QgsMessageLog.logMessage("Error transforming profile line to EPSG:2056.",
                                     "Locator bar",
                                     Qgis.MessageLevel.Critical)
            return False

        self.__results = SwissProfileResults()
        self.__results.copyPropertiesFromGenerator(self)

        result = self.__get_profile_from_rest_api()

        if "error" in result:
            QgsMessageLog.logMessage(result["error"], "Locator bar",
                                     Qgis.MessageLevel.Critical)
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
            self.__results.ellipsoidal_cross_section_geometries.append(QgsGeometry(QgsPoint(d, z)))

            if d != 0:
                # QGIS elevation profile won't calculate distances
                # using 3d, so let's stick to 2d to avoid getting
                # displaced markers or lines in the profile canvas
                cartesian_d += QgsGeometryUtils.distance2D(point_z, self.__results.raw_points[-1])

            self.__results.raw_points.append(point_z)
            self.__results.cartesian_distance_to_height[cartesian_d] = z
            self.__results.cartesian_cross_section_geometries.append(QgsGeometry(QgsPoint(cartesian_d, z)))

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

    def createProfileGenerator(self, request):
        return SwissProfileGenerator(request)
