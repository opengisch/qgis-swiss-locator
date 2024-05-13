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
                "style": "https://vectortiles.geo.admin.ch/styles/ch.swisstopo.lightbasemap.vt/style.json"
            },
            "imagery base map": {
                "title": "Imagery base map", "description": "",
                "url": "https://vectortiles.geo.admin.ch/tiles/ch.swisstopo.base.vt/v1.0.0/{z}/{x}/{y}.pbf",
                "style": "https://vectortiles.geo.admin.ch/styles/ch.swisstopo.imagerybasemap.vt/style.json"
            },
            "leichte-basiskarte": {
                "title": "leichte-basiskarte", "description": "",
                "url": "https://vectortiles.geo.admin.ch/tiles/ch.swisstopo.leichte-basiskarte.vt/v3.0.1/{z}/{x}/{y}.pbf",
                "style": "https://vectortiles.geo.admin.ch/styles/ch.swisstopo.leichte-basiskarte.vt/style.json"
            },
            "leichte-basiskarte-imagery": {
                "title": "leichte-basiskarte-imagery", "description": "",
                "url": "https://vectortiles.geo.admin.ch/tiles/ch.swisstopo.leichte-basiskarte.vt/v3.0.1/{z}/{x}/{y}.pbf",
                "style": "https://vectortiles.geo.admin.ch/styles/ch.swisstopo.leichte-basiskarte-imagery.vt/style.json"
            },
        }

        for keyword in list(data.keys()):
            results = {}
            score = 1
            if search.lower() in keyword:
                result = QgsLocatorResult()
                result.filter = self
                result.icon = QgsApplication.getThemeIcon("/mActionAddVectorTileLayer.svg")

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
