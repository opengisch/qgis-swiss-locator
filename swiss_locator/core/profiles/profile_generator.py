import json

from qgis.PyQt.QtCore import QUrl, QUrlQuery
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
    QgsMessageLog,
    QgsNetworkAccessManager,
    QgsPoint,
)

from swiss_locator.core.profiles.profile_results import  SwissProfileResults
from swiss_locator.core.profiles.profile_url import profile_url


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
        def url_with_param(url, params) -> str:
            url = QUrl(url)
            q = QUrlQuery(url)
            for key, value in params.items():
                q.addQueryItem(key, value)
            url.setQuery(q)
            return url

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
            result = json.loads(str(content, 'utf-8'))

        return result

    def __parse_response_point(self, point):
        return point[self.X], point[self.Y], point[self.Z_DICT][self.Z], point[self.DISTANCE]

    def generateProfile(self, context):  # QgsProfileGenerationContext
        if self.__profile_curve is None:
            return False

        self.__transformed_curve = self.__profile_curve.clone()
        try:
            self.__transformed_curve.transform(self.__transformation)
        except QgsCsException as e:
            QgsMessageLog.logMessage("Error transforming profile line to EPSG:2056.",
                                     "Swiss locator",
                                     Qgis.Critical)
            return False

        self.__results = SwissProfileResults()
        self.__results.copyPropertiesFromGenerator(self)

        result = self.__get_profile_from_rest_api()

        if "error" in result:
            QgsMessageLog.logMessage(result["error"], "Swiss locator", Qgis.Critical)
            return False

        for point in result:
            if self.__feedback.isCanceled():
                return False

            x, y, z, d = self.__parse_response_point(point)
            point_z = QgsPoint(x, y, z)
            point_z.transform(self.__transformation, Qgis.TransformDirection.Reverse)

            self.__results.raw_points.append(point_z)
            self.__results.distance_to_height[d] = z
            if z < self.__results.min_z:
                self.__results.min_z = z

            if z > self.__results.max_z:
                self.__results.max_z = z

            self.__results.geometries.append(QgsGeometry(point_z))
            self.__results.cross_section_geometries = QgsGeometry(QgsPoint(d, z))

        return not self.__feedback.isCanceled()

    def takeResults(self):
        return self.__results


class SwissProfileSource(QgsAbstractProfileSource):
    def __init__(self):
        QgsAbstractProfileSource.__init__(self)

    def createProfileGenerator(self, request):
        return SwissProfileGenerator(request)
