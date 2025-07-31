import json

from PyQt5.QtCore import QUrl
from PyQt5.QtNetwork import QNetworkRequest
from qgis.core import (
    QgsApplication, QgsFeedback, QgsLocatorResult,
    QgsStacCollection
)
from qgis.gui import QgisInterface

from swiss_locator.core.filters.filter_type import FilterType
from swiss_locator.core.filters.map_geo_admin_stac import (
    collectionsToSearchStrings,
    fetchStacCollections,
    map_geo_admin_stac_items_url
)
from swiss_locator.core.filters.swiss_locator_filter import SwissLocatorFilter
from swiss_locator.core.results import STACResult
from swiss_locator.utils.utils import url_with_param

FILE_TYPE_ICONS = {
    'default': "/mActionAddLayer.svg",
    'zip': "/mIconZip.svg",
    'tiff': "/mActionAddRasterLayer.svg",
    'geotiff': "/mActionAddRasterLayer.svg",
    "ascii": "/mActionAddRasterLayer.svg",
    "xyz": "/mActionAddRasterLayer.svg",
    "grid": "/mActionAddRasterLayer.svg",
    'shapefile': "/mActionAddBasicShape.svg",
    'csv': "/mActionAddDelimitedTextLayer.svg",
    "jpeg": "/mActionAddImage.svg",
    "interlis": "/mActionAddLayer.svg",
    "filegdb": "/mActionAddOracleLayer.svg",
    "streamed": "/mActionAddRasterLayer.svg",
    "geopackage": "/mActionAddGeoPackageLayer.svg",
    "json": "/mActionAddOgrLayer.svg",
    "geojson": "/mActionAddOgrLayer.svg",
    "pdf": "/mActionTextInsideRect.svg",
    "xml": "/mActionAddHtml.svg",
    "netcdf": "/mActionAddLayer.svg",
    "kml": "mActionAddHtml.svg",
    "kmz": "/mIconZip.svg",
    "filter": "/mIndicatorFilter.svg",
        
    }


class SwissLocatorFilterSTAC(SwissLocatorFilter):
    HEADERS = {b"User-Agent": b"Mozilla/5.0 QGIS Swiss Geoportal Stac Filter"}
    
    def __init__(self, iface: QgisInterface = None, crs: str = None,
                 data=None):
        super().__init__(FilterType.STAC, iface, crs)
        self.minimum_search_length = 4
        self.maximum_assets_per_collection = 3
        
        if data:
            self.collections = data[0]
            self.collectionSearchStrings = data[1]
            self.collectionIds = data[2]
            return
        # Since the swisstopo STAC catalog does not provide a useful
        # search API to query collections, the collections are fetched
        # initially and titles are placed in a searchable list
        # TODO: make calls async, non-blocking
        self.collections: dict[str, QgsStacCollection] = fetchStacCollections(
                self.lang)
        self.collectionSearchStrings, self.collectionIds = collectionsToSearchStrings(
                self.collections)
    
    def clone(self):
        # TODO: What to do when language changes?
        return SwissLocatorFilterSTAC(crs=self.crs, data=(self.collections,
            self.collectionSearchStrings,
            self.collectionIds))
    
    def displayName(self):
        return self.tr("Swiss Geoportal STAC file download")
    
    def prefix(self):
        return "chstac"
    
    def perform_local_search(self, search: str):
        # TODO: ranks, order results!
        indexes = [i for (i, s) in enumerate(self.collectionSearchStrings) if
            search.lower() in s]
        return [self.collectionIds[idx] for idx in indexes]
    
    def perform_fetch_results(self, search: str, feedback: QgsFeedback):
        # Remove the opendata swiss link, keep the map_geo_admin one
        limit = self.settings.filters[self.type.value]["limit"].value()
        
        matchingCollections = self.perform_local_search(search)[:limit]
        requests = []
        # For each collection, request a handful of items so we get a sense of the collection
        for collectionId in matchingCollections:
            url, params = map_geo_admin_stac_items_url(collectionId, 5)
            requests.append(
                    self.request_for_url(url, params, self.HEADERS))
        
        self.fetch_requests(requests, feedback, slot=self.handle_content,
                            data=matchingCollections)
    
    def handle_content(self, content, feedback: QgsFeedback, data):
        response = json.loads(content)
        matchingCollections = data  # TODO: This should contain the order or result ranks
        
        if len(response.get("features", [])) == 0:
            return
        
        firstItem = response["features"][0]
        collection = self.collections[firstItem["collection"]]
        stacResults = []
        
        # TODO: What is the necessary check to know if we want to show assets or not
        if len(response["features"]) == 1:
            # This collection contains only one item, we analyse it's assets
            for (assetId, asset) in firstItem["assets"].items():
                assetResult = STACResult(
                        collection.id(),
                        collection.title(),
                        assetId,
                        asset.get("description"),
                        asset.get("type"),
                        asset.get("href"),
                        )
                stacResults.append(assetResult)
        else:
            # Save the collection as a locator result, no use in list many assets
            collectionResult = STACResult(collection.id(), collection.title(),
                                          '', collection.description(),
                                          '', '')
            stacResults.append(collectionResult)
        
        # TODO: Add specific logic to decide if this result should list assets or only link to the filter ui
        for idx, stacResult in enumerate(stacResults):
            
            if stacResult.is_downloadable_file:
                # If assets can be downloaded directly, add them to the results
                self.createLocatorResult(stacResult.collection_name,
                                         stacResult.asset_id,
                                         stacResult.media_type,
                                         stacResult.as_definition(),
                                         stacResult.simple_file_type)
                if idx >= self.maximum_assets_per_collection - 1:
                    break
            else:
                # If there are too many assets, only list the collection and
                # show an option to open up the filter dialog
                self.createLocatorResult(stacResult.collection_name,
                                         f'[click] to filter individual files for {stacResult.collection_name}...',
                                         '',
                                         stacResult.as_definition(),
                                         'filter')
    
    def createLocatorResult(self, group, title, description, userData, icon):
        result = QgsLocatorResult()
        result.filter = self
        result.group = group
        result.displayString = title
        result.description = description
        result.userData = userData
        result.icon = QgsApplication.getThemeIcon(
                self.getMatchingQgisIcon(icon))
        self.result_found = True
        self.resultFetched.emit(result)
    
    @staticmethod
    def getMatchingQgisIcon(file_type):
        parts = file_type.replace('.', ' ').replace('+', ' ').split()
        
        for part in parts:
            if FILE_TYPE_ICONS.get(part):
                return FILE_TYPE_ICONS.get(part)
        
        return FILE_TYPE_ICONS.get('default')
    
    def fetch_asset(self, asset: STACResult):
        # Try to get more info
        url = asset.href
        url = url_with_param(url, {})
        request = QNetworkRequest(QUrl(url))
        # TODO: Download file with QgsFileDownloader, using self.event_loop
        self.fetch_request(request, QgsFeedback(), self.parse_asset_response)
    
    def parse_asset_response(self):
        # TODO: Download file
        pass
