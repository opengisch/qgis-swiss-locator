import json
import os
from copy import deepcopy

from qgis.PyQt.QtCore import pyqtSignal
from qgis.core import (
    QgsTask,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
    Qgis,
    QgsApplication,
    QgsFeedback,
    QgsLocatorResult,
    QgsStacCollection
)
from qgis.gui import QgisInterface

from swiss_locator.core.filters.filter_type import FilterType
from swiss_locator.core.filters.map_geo_admin_stac import (
    collections_to_searchable_strings,
    map_geo_admin_stac_items_url
)
from swiss_locator.core.filters.swiss_locator_filter import (
    SwissLocatorFilter
)
from swiss_locator.core.results import STACResult
from swiss_locator.swissgeodownloader.api.api_caller_task import \
    DownloadFilesTask
from swiss_locator.swissgeodownloader.api.datageoadmin import ApiDataGeoAdmin
from swiss_locator.swissgeodownloader.utils.qgis_layer_creator_task import \
    createQgisLayersInTask
from swiss_locator.utils.utils import get_save_location

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
    """
    Handles filtering and downloading files from the Swiss Geoportal
    STAC data catalog.
    Since the catalog does not provide a search endpoint to query collection
    names or titles, the search functionality is implemented by initially
    fetching all collections and storing titles and ids in a searchable list.
    """
    HEADERS = {b"User-Agent": b"Mozilla/5.0 QGIS Swiss Geoportal Stac Filter"}
    
    show_filter_widget = pyqtSignal(str)
    
    def __init__(self, iface: QgisInterface = None, crs: str = None,
                 data=None):
        super().__init__(FilterType.STAC, iface, crs)
        
        self.stac_fetch_task: QgsTask | None = None
        self.stac_download_task: QgsTask | None = None
        self.stac_layer_create_task: QgsTask | None = None
        self.stac_api_data_geo_admin = ApiDataGeoAdmin(self.lang)
        self.available_collections: dict[str, QgsStacCollection] = {}
        self.search_strings = []
        self.collection_ids = []
        
        if not data:
            self.fetch_stac_collections()
        else:
            self.available_collections = data[0]
            self.search_strings = data[1]
            self.collection_ids = data[2]
    
    def fetch_stac_collections(self):
        self.info(self.tr('Fetching Swisstopo STAC collections'))
        self.stac_fetch_task = QgsTask.fromFunction(
                self.tr('Fetching Swisstopo STAC collections'),
                self.stac_api_data_geo_admin.getCollections,
                on_finished=self.receive_stac_collections)
        
        QgsApplication.taskManager().addTask(self.stac_fetch_task)
    
    def receive_stac_collections(self, exception=None,
                                 stac_collections: dict[
                                     str, QgsStacCollection] = None):
        if exception or not stac_collections:
            self.info(self.tr(
                    "Not able to download Swisstopo STAC collections") + f": {str(exception)}",
                      Qgis.MessageLevel.Critical)
            return
        self.available_collections = stac_collections
        self.search_strings, self.collection_ids = collections_to_searchable_strings(
                self.available_collections)
    
    def clone(self):
        return SwissLocatorFilterSTAC(crs=self.crs,
                                      data=(
                                          self.available_collections,
                                          self.search_strings,
                                          self.collection_ids))
    
    def displayName(self):
        return self.tr("Swiss Geoportal STAC file download")
    
    def prefix(self):
        return "chd"
    
    def perform_local_search(self, search_term: str):
        """ Perform search on a list of strings containing the STAC collection
        id and title, and return a sorted list of corresponding collection IDs
         for the found matches. Results are ordered by the match positions.
        """
        search_term = search_term.lower()
        matches = [(i, s.find(search_term)) for (i, s) in
            enumerate(self.search_strings)]
        valid_matches = [(i, pos) for (i, pos) in matches if pos >= 0]
        sorted_matches = sorted(valid_matches, key=lambda x: x[1])
        return [self.collection_ids[idx] for idx, _ in sorted_matches]
    
    def perform_fetch_results(self, search: str, feedback: QgsFeedback):
        result_limit = self.settings.filters[self.type.value]["limit"].value()
        files_per_result_limit = self.settings.filters[self.type.value][
            "limit_files_per_result"].value()
        
        matching_collections = self.perform_local_search(search)[:result_limit]
        
        # For each collection, request a few items to decide whether assets can
        # be downloaded directly from the locator or a filter dialog is necessary
        requests = []
        for collection_id in matching_collections:
            url, params = map_geo_admin_stac_items_url(collection_id,
                                                       files_per_result_limit)
            requests.append(
                    self.request_for_url(url, params, self.HEADERS))
        
        self.fetch_requests(requests, feedback, self.handle_content)
    
    def handle_content(self, content, feedback: QgsFeedback):
        response = json.loads(content)
        
        if len(response.get("features", [])) == 0:
            return
        
        try:
            stac_collection = self.available_collections[
                response["features"][0]["collection"]]
        except KeyError:
            return
        
        files_per_collection_limit = self.settings.filters[self.type.value][
            "limit_files_per_result"].value()
        file_count = sum([len(item["assets"].values()) for item in
                             response["features"]])
        
        if file_count <= files_per_collection_limit:
            results = []
            # Analyse response and create stac result objects
            for item in response["features"]:
                for (asset_id, asset) in item["assets"].items():
                    asset_result = STACResult(
                            stac_collection.id(),
                            stac_collection.title(),
                            asset_id,
                            asset.get("description"),
                            asset.get("type"),
                            asset.get("href"),
                    )
                    results.append(asset_result)
                    if asset_result.is_streamable:
                        # Create a second, streamable asset object
                        asset_as_stream = deepcopy(asset_result)
                        postfix = self.tr('streamed')
                        asset_as_stream.asset_id += f" ({postfix})"
                        asset_as_stream.path = STACResult.STREAMED_SOURCE_PREFIX + asset.get(
                                "href")
                        results.append(asset_as_stream)
            
            # Create locator entries
            for stac_result in results:
                if stac_result.is_downloadable:
                    self.create_locator_result(stac_result.collection_name,
                                               stac_result.asset_id,
                                               stac_result.simple_file_type,
                                               stac_result.as_definition(),
                                               stac_result.simple_file_type)
        
        else:
            # If the collection has too many items/assets, only the collection
            #  itself is listed in the locator and further filtering is done
            #  in a filter dialog
            result = STACResult(stac_collection.id(),
                                stac_collection.title(),
                                '', stac_collection.description(),
                                '', '')
            
            self.create_locator_result(
                    result.collection_name,
                    self.tr('open filter dialog to choose files'),
                    '', result.as_definition(), 'filter')
    
    def create_locator_result(self, group, title, description, user_data,
                              icon):
        result = QgsLocatorResult()
        result.filter = self
        result.group = group
        result.displayString = title
        result.description = description
        result.userData = user_data
        result.icon = QgsApplication.getThemeIcon(
                self.get_matching_result_icon(icon))
        self.result_found = True
        self.resultFetched.emit(result)
    
    @staticmethod
    def get_matching_result_icon(file_type):
        parts = file_type.replace('.', ' ').replace('+', ' ').split()
        
        if 'zip' in parts:
            return FILE_TYPE_ICONS.get('zip')
        
        for part in parts:
            if FILE_TYPE_ICONS.get(part):
                return FILE_TYPE_ICONS.get(part)
        
        return FILE_TYPE_ICONS.get('default')
    
    def download_asset(self, asset: STACResult):
        folder_path = get_save_location(self.tr("Choose download location"))
        if not folder_path:
            return
        
        file_path = os.path.join(folder_path, asset.asset_id)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Download the asset in a separate event loop
        asset.path = file_path
        self.info(f"fetching {asset.href}")
        
        def on_download_error():
            level = Qgis.MessageLevel.Warning
            msg = self.tr('Unable to download file {}').format(asset.asset_id)
            self.info(msg, level)
        
        self.stac_download_task = DownloadFilesTask(
                self.stac_api_data_geo_admin,
                self.iface.messageBar(),
                self.tr('download {}').format(asset.asset_id),
                fileList=[asset],
                outputDir=folder_path)
        # Listen for finished api call
        self.stac_download_task.taskCompleted.connect(
                lambda: self.add_asset_to_qgis(asset))
        self.stac_download_task.taskTerminated.connect(on_download_error)
        # Add task to task manager
        QgsApplication.taskManager().addTask(self.stac_download_task)
    
    def add_asset_to_qgis(self, asset: STACResult):
        if not os.path.exists(asset.path) and not asset.is_streamed:
            return
        
        if 'zip' in asset.path:
            msg = self.tr('Download completed: {}').format(asset.asset_id)
            level = Qgis.MessageLevel.Success
            self.message_emitted.emit(self.displayName(), msg, level, None)
            self.info(msg, level)
            return
        
        createQgisLayersInTask([asset], self.qgis_layer_created)
    
    def qgis_layer_created(
            self,
            layers: list[QgsRasterLayer | QgsVectorLayer] | None = None,
            _alreadyAdded: int = 0,
            exception=None):
        
        msg = ''
        level = Qgis.MessageLevel.Info
        if layers:
            layer = layers[0]
            QgsProject.instance().addMapLayer(layer)
            msg = self.tr('Added file {} to QGIS').format(layer.name())
        if exception:
            msg = self.tr('Unable to add layer to QGIS: {}').format(
                    exception)
            level = Qgis.MessageLevel.Warning
            self.message_emitted.emit(self.displayName(), msg, level, None)
        
        self.info(msg, level)
    
    def open_filter_widget(self, collection: STACResult):
        self.show_filter_widget.emit(collection.collection_id)
