from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from qgis.gui import QgisInterface
from qgis.core import (
    QgsApplication,
    QgsBlockingNetworkRequest,
    QgsFetchedContent,
    QgsLocatorResult,
    QgsFeedback,
)
from swiss_locator.core.filters.swiss_locator_filter import (
    SwissLocatorFilter,
)
from swiss_locator.core.filters.filter_type import FilterType
from swiss_locator.core.results import VectorTilesLayerResult

import xml.etree.ElementTree as ET
import urllib.parse


class SwissLocatorFilterVectorTiles(SwissLocatorFilter):
    def __init__(self, iface: QgisInterface = None, crs: str = None):
        super().__init__(FilterType.VectorTiles, iface, crs)

    def clone(self):
        return SwissLocatorFilterVectorTiles(crs=self.crs)

    def displayName(self):
        return self.tr("Swiss Geoportal Vector Tile Layers")

    def prefix(self):
        return "chb"

    def hasConfigWidget(self):
        return False

    def perform_fetch_results(self, search: str, feedback: QgsFeedback):
        data = {
            "base map": {
                "title": "Base map",
                "description": "",
                "url": "https://vectortiles.geo.admin.ch/tiles/ch.swisstopo.base.vt/v1.0.0/{z}/{x}/{y}.pbf",
                "style": "https://vectortiles.geo.admin.ch/styles/ch.swisstopo.basemap.vt/style.json"
            },
            "light base map": {
                "title": "Light base map", "description": "",
                "url": "https://vectortiles.geo.admin.ch/tiles/ch.swisstopo.base.vt/v1.0.0/{z}/{x}/{y}.pbf",
                "style": "https://vectortiles.geo.admin.ch/styles/ch.swisstopo.basemap.vt/style.json"
            },
            "imagery base map": {
                "title": "Imagery base map", "description": "",
                "url": "https://vectortiles.geo.admin.ch/tiles/ch.swisstopo.base.vt/v1.0.0/{z}/{x}/{y}.pbf",
                "style": "https://vectortiles.geo.admin.ch/styles/ch.swisstopo.basemap.vt/style.json"
            }
        }

        for keyword in list(data.keys()):
            results = {}
            score = 1
            if search in keyword:
                result = QgsLocatorResult()
                result.filter = self
                #result.icon = QgsApplication.getThemeIcon("/mActionAddWmsLayer.svg")

                result.displayString = data[keyword]["title"]
                result.description = data[keyword]["description"]
                result.userData = VectorTilesLayerResult(
                    layer=data[keyword]["title"],
                    title=data[keyword]["title"],
                    url=data[keyword]["url"],
                    style=data[keyword]["style"],
                ).as_definition()

                results[result] = score

            # sort the results with score
            #results = sorted([result for (result, score) in results.items()])

            for result in results:
                self.resultFetched.emit(result)
                self.result_found = True
