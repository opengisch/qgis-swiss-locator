import json
import os
from copy import deepcopy

from qgis.PyQt.QtCore import pyqtSignal
from qgis.core import (
    QgsTask,
    QgsProject,
    QgsMapLayer,
    Qgis,
    QgsApplication,
    QgsFeedback,
    QgsLocatorResult,
)
from qgis.gui import QgisInterface

from swiss_locator.core.constants import USER_AGENT
from swiss_locator.core.filters.filter_type import FilterType
from swiss_locator.core.filters.map_geo_admin_stac import (
    collections_to_searchable_strings,
    stac_items_url,
)
from swiss_locator.core.filters.swiss_locator_filter import SwissLocatorFilter
from swiss_locator.core.results import STACResult
from swiss_locator.swissgeodownloader.api.api_caller_task import DownloadFilesTask
from swiss_locator.swissgeodownloader.api.catalogs import (
    STAC_CATALOGS,
    ApiBaselStadt,
    ApiViageo,
)
from swiss_locator.swissgeodownloader.api.datageoadmin import ApiDataGeoAdmin
from swiss_locator.swissgeodownloader.api.response_objects import SgdStacCollection
from swiss_locator.swissgeodownloader.api.stac_catalog import ApiStacCatalog
from swiss_locator.swissgeodownloader.utils.qgis_layer_creator_task import (
    createQgisLayersInTask,
)
from swiss_locator.utils.utils import get_save_location

FILE_TYPE_ICONS = {
    "default": "/mActionAddLayer.svg",
    "zip": "/mIconZip.svg",
    "tiff": "/mActionAddRasterLayer.svg",
    "geotiff": "/mActionAddRasterLayer.svg",
    "ascii": "/mActionAddRasterLayer.svg",
    "xyz": "/mActionAddRasterLayer.svg",
    "grid": "/mActionAddRasterLayer.svg",
    "shapefile": "/mActionAddBasicShape.svg",
    "shp": "/mActionAddBasicShape.svg",
    "flatgeobuf": "/mActionAddOgrLayer.svg",
    "csv": "/mActionAddDelimitedTextLayer.svg",
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
    "laszip": "/mIconPointCloudLayer.svg",
    "filter": "/mIndicatorFilter.svg",
}


class SwissLocatorFilterSTAC(SwissLocatorFilter):
    """
    Handles filtering and downloading files from a STAC data catalog: the
    Swiss Geoportal (data.geo.admin.ch) or viageo.ch. Each catalog has its
    own filter, all with the same prefix, so the results are grouped by source.
    Since the catalogs do not provide a search endpoint to query collection
    names or titles, the search functionality is implemented by initially
    fetching all collections and storing titles and ids in a searchable list.
    """

    HEADERS = {b"User-Agent": USER_AGENT}

    # Catalog id, collection id
    show_filter_widget = pyqtSignal(str, str)

    def __init__(
        self,
        iface: QgisInterface = None,
        crs: str = None,
        data=None,
        catalog_id: str = ApiDataGeoAdmin.CATALOG_ID,
    ):
        super().__init__(FilterType.STAC, iface, crs)

        self.stac_fetch_task: QgsTask | None = None
        self.stac_download_task: QgsTask | None = None
        self.stac_layer_create_task: QgsTask | None = None
        self.available_collections: dict[str, SgdStacCollection] = {}
        self.search_strings = []
        self.collection_ids = []

        if not data:
            self.catalog: ApiStacCatalog = STAC_CATALOGS[catalog_id](self.lang)
            self.fetch_stac_collections()
        else:
            # Clones share the catalog, creating the one of data.geo.admin.ch
            #  reads the geocat metadata file
            (
                self.catalog,
                self.available_collections,
                self.search_strings,
                self.collection_ids,
            ) = data

    def fetch_stac_collections(self):
        description = self.tr("Fetching the STAC collections of {}").format(
            self.catalog.NAME
        )
        self.info(description)
        self.stac_fetch_task = QgsTask.fromFunction(
            description,
            self.catalog.getCollections,
            on_finished=self.receive_stac_collections,
        )
        QgsApplication.taskManager().addTask(self.stac_fetch_task)

    def receive_stac_collections(
        self, exception=None, stac_collections: dict[str, SgdStacCollection] = None
    ):
        if exception or not stac_collections:
            self.info(
                self.tr("Not able to download the STAC collections of {}").format(
                    self.catalog.NAME
                )
                + f": {str(exception)}",
                Qgis.MessageLevel.Critical,
            )
            return
        self.available_collections = stac_collections
        self.search_strings, self.collection_ids = collections_to_searchable_strings(
            self.available_collections
        )

    def clone(self):
        return SwissLocatorFilterSTAC(
            crs=self.crs,
            data=(
                self.catalog,
                self.available_collections,
                self.search_strings,
                self.collection_ids,
            ),
        )

    def name(self):
        # QGIS saves the settings of a filter (enabled, prefix) under its name:
        #  the filter of data.geo.admin.ch keeps the one it had on its own
        if self.catalog.CATALOG_ID == ApiDataGeoAdmin.CATALOG_ID:
            return super().name()
        return f"{super().name()}_{self.catalog.CATALOG_ID}"

    def displayName(self):
        # Shown above the results, it tells where the files come from
        display_names = {
            ApiDataGeoAdmin.CATALOG_ID: self.tr("Swiss Geoportal STAC file download"),
            ApiViageo.CATALOG_ID: self.tr("viageo.ch STAC file download"),
            ApiBaselStadt.CATALOG_ID: self.tr("Basel-Stadt STAC file download"),
        }
        return display_names[self.catalog.CATALOG_ID]

    def prefix(self):
        return "chd"

    def perform_local_search(self, search_term: str):
        """Perform search on a list of strings containing the STAC collection
        id and title, and return a sorted list of corresponding collection IDs
         for the found matches. Results are ordered by the match positions.
        """
        search_term = search_term.lower()
        matches = [
            (i, s.find(search_term)) for (i, s) in enumerate(self.search_strings)
        ]
        valid_matches = [(i, pos) for (i, pos) in matches if pos >= 0]
        sorted_matches = sorted(valid_matches, key=lambda x: x[1])
        return [self.collection_ids[idx] for idx, _ in sorted_matches]

    def perform_fetch_results(self, search: str, feedback: QgsFeedback):
        result_limit = self.settings.filters[self.type.value]["limit"].value()
        files_per_result_limit = self.settings.filters[self.type.value][
            "limit_files_per_result"
        ].value()

        matching_collections = self.perform_local_search(search)[:result_limit]

        # For each collection, request a few items to decide whether assets can
        # be downloaded directly from the locator or a filter dialog is necessary.
        # One more item than the limit is requested to know if there are more.
        requests = []
        for collection_id in matching_collections:
            url, params = stac_items_url(
                self.catalog.URL, collection_id, files_per_result_limit + 1
            )
            requests.append(self.request_for_url(url, params, self.HEADERS))

        self.fetch_requests(requests, feedback, self.handle_content)

    def handle_content(self, content, feedback: QgsFeedback):
        response = json.loads(content)

        if len(response.get("features", [])) == 0:
            return

        try:
            stac_collection = self.available_collections[
                response["features"][0]["collection"]
            ]
        except KeyError:
            return

        files_per_collection_limit = self.settings.filters[self.type.value][
            "limit_files_per_result"
        ].value()
        item_count = len(response["features"])
        file_count = sum(
            [len(item["assets"].values()) for item in response["features"]]
        )
        # The files of a single item, each in its own format, are the formats to
        #  choose from: all are listed (e.g. Basel-Stadt)
        media_types = {
            asset.get("type")
            for item in response["features"]
            for asset in item["assets"].values()
        }
        formats_of_one_item = item_count == 1 and len(media_types) == file_count

        if formats_of_one_item or (
            item_count <= files_per_collection_limit
            and file_count <= files_per_collection_limit
        ):
            results = []
            # Analyse response and create stac result objects
            for item in response["features"]:
                # The projection extension can be on the asset or on the item
                item_epsg = item.get("properties", {}).get("proj:epsg")
                for asset_id, asset in item["assets"].items():
                    asset_result = STACResult(
                        stac_collection.id(),
                        stac_collection.title(),
                        self.catalog.fileName(
                            stac_collection.id(),
                            item.get("id"),
                            asset_id,
                            asset.get("href"),
                        ),
                        asset.get("description"),
                        asset.get("type"),
                        asset.get("href"),
                        coordsys=str(asset.get("proj:epsg") or item_epsg or ""),
                    )
                    results.append(asset_result)
                    if asset_result.is_streamable:
                        # Create a second, streamable asset object
                        asset_as_stream = deepcopy(asset_result)
                        postfix = self.tr("streamed")
                        asset_as_stream.asset_id += f" ({postfix})"
                        asset_as_stream.path = asset_result.uri().uri
                        results.append(asset_as_stream)

            # Create locator entries
            for stac_result in results:
                if stac_result.is_downloadable:
                    self.create_locator_result(
                        stac_result.collection_name,
                        stac_result.asset_id,
                        stac_result.simple_file_type,
                        stac_result.as_definition(),
                        stac_result.simple_file_type,
                    )

        else:
            # If the collection has too many items/assets, only the collection
            #  itself is listed in the locator and further filtering is done
            #  in a filter dialog
            result = STACResult(
                stac_collection.id(),
                stac_collection.title(),
                "",
                stac_collection.description(),
                "",
                "",
            )

            self.create_locator_result(
                result.collection_name,
                self.tr("open filter dialog to choose files"),
                "",
                result.as_definition(),
                "filter",
            )

    def create_locator_result(self, group, title, description, user_data, icon):
        result = QgsLocatorResult()
        result.filter = self
        result.group = group
        result.displayString = title
        result.description = description
        result.userData = user_data
        result.icon = QgsApplication.getThemeIcon(self.get_matching_result_icon(icon))
        self.result_found = True
        self.resultFetched.emit(result)

    @staticmethod
    def get_matching_result_icon(file_type):
        parts = file_type.replace(".", " ").replace("+", " ").replace("-", " ").split()

        if "zip" in parts:
            return FILE_TYPE_ICONS.get("zip")

        for part in parts:
            if FILE_TYPE_ICONS.get(part):
                return FILE_TYPE_ICONS.get(part)

        return FILE_TYPE_ICONS.get("default")

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
            msg = self.tr("Unable to download file {}").format(asset.asset_id)
            self.info(msg, level)

        self.stac_download_task = DownloadFilesTask(
            self.catalog,
            self.iface.messageBar(),
            self.tr("download {}").format(asset.asset_id),
            fileList=[asset],
            outputDir=folder_path,
        )
        # Listen for finished api call
        self.stac_download_task.taskCompleted.connect(
            lambda: self.add_asset_to_qgis(asset)
        )
        self.stac_download_task.taskTerminated.connect(on_download_error)
        # Add task to task manager
        QgsApplication.taskManager().addTask(self.stac_download_task)

    def add_asset_to_qgis(self, asset: STACResult):
        if not os.path.exists(asset.path) and not asset.is_streamed:
            return

        createQgisLayersInTask(
            [asset],
            lambda layers=None, alreadyAdded=0, exception=None: self.qgis_layer_created(
                asset, layers, alreadyAdded, exception
            ),
        )

    def qgis_layer_created(
        self,
        asset: STACResult,
        layers: list[QgsMapLayer] | None = None,
        alreadyAdded: int = 0,
        exception=None,
    ):
        msg = ""
        level = Qgis.MessageLevel.Info
        if layers:
            # A zip file can contain several point clouds
            QgsProject.instance().addMapLayers(layers)
            msg = self.tr("Added file {} to QGIS").format(
                ", ".join(layer.name() for layer in layers)
            )
        elif not alreadyAdded and not asset.is_streamed:
            # Downloaded files QGIS cannot open directly, such as most zip files
            msg = self.tr("Download completed: {}").format(asset.asset_id)
            level = Qgis.MessageLevel.Success
            self.message_emitted.emit(self.displayName(), msg, level, None)
        if exception:
            msg = self.tr("Unable to add layer to QGIS: {}").format(exception)
            level = Qgis.MessageLevel.Warning
            self.message_emitted.emit(self.displayName(), msg, level, None)

        self.info(msg, level)

    def open_filter_widget(self, collection: STACResult):
        self.show_filter_widget.emit(self.catalog.CATALOG_ID, collection.collection_id)
