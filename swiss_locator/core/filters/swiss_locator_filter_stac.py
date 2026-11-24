import json
import os
import time
from copy import deepcopy

from qgis.PyQt import sip
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
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
from swiss_locator.core.filters.response_cache import ResponseCache
from swiss_locator.core.filters.swiss_locator_filter import SwissLocatorFilter
from swiss_locator.core.results import NoResult, STACResult
from swiss_locator.swissgeodownloader.api.api_caller_task import DownloadFilesTask
from swiss_locator.swissgeodownloader.api.catalogs import (
    STAC_CATALOGS,
    ApiBaselStadt,
    ApiGeodienste,
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


class CatalogState:
    """What the filter of a catalog shares with its clones, which search in
    other threads"""

    # Seconds without requests to a catalog that refused them as too many
    PAUSE = 300

    def __init__(self):
        # The first files of each collection, asked for at each key typed
        self.responses = ResponseCache()
        # When the collections could not be loaded, None while they load
        self.collections_failed_at: float | None = None
        self.refused_until = 0.0

    def refuse(self):
        self.refused_until = time.monotonic() + self.PAUSE

    def refusing(self) -> bool:
        return time.monotonic() < self.refused_until


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
    # Seconds before collections that could not be loaded are asked again
    COLLECTIONS_RETRY = 60

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
        # A key typed meanwhile cancels the search before it requests anything
        self.setFetchResultsDelay(300)

        if not data:
            self.state = CatalogState()
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
                self.state,
            ) = data

    def fetch_stac_collections(self):
        description = self.tr("Fetching the STAC collections of {}").format(
            self.catalog.NAME
        )
        self.info(description)
        self.state.collections_failed_at = None
        self.stac_fetch_task = QgsTask.fromFunction(
            description,
            self.catalog.getCollections,
            on_finished=self.receive_stac_collections,
        )
        QgsApplication.taskManager().addTask(self.stac_fetch_task)

    def receive_stac_collections(
        self, exception=None, stac_collections: dict[str, SgdStacCollection] = None
    ):
        if sip.isdeleted(self):
            # Deregistered meanwhile: its catalog is no longer searched
            return
        if exception or not stac_collections:
            self.info(
                self.tr("Not able to download the STAC collections of {}").format(
                    self.catalog.NAME
                )
                + f": {str(exception)}",
                Qgis.MessageLevel.Critical,
            )
            self.state.collections_failed_at = time.monotonic()
            return
        self.available_collections = stac_collections
        self.search_strings, self.collection_ids = collections_to_searchable_strings(
            self.available_collections
        )

    def clone(self):
        # Called before each search, in the main thread: the collections that
        #  could not be loaded, e.g. offline when QGIS started, are asked again
        failed_at = self.state.collections_failed_at
        if (
            failed_at is not None
            and time.monotonic() - failed_at >= self.COLLECTIONS_RETRY
        ):
            self.fetch_stac_collections()
        return SwissLocatorFilterSTAC(
            crs=self.crs,
            data=(
                self.catalog,
                self.available_collections,
                self.search_strings,
                self.collection_ids,
                self.state,
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
            ApiGeodienste.CATALOG_ID: self.tr("geodienste.ch STAC file download"),
        }
        return display_names[self.catalog.CATALOG_ID]

    def prefix(self):
        return "chd"

    def perform_local_search(self, search_term: str):
        """Search the STAC collections by title and id, then by description
        and keywords, and return the IDs of the matching collections. Those
        matching by title or id come first, each group ordered by the match
        position.
        """
        search_term = search_term.lower()
        matches = []
        for idx, (title_and_id, details) in enumerate(self.search_strings):
            pos = title_and_id.find(search_term)
            if pos >= 0:
                matches.append((0, pos, idx))
                continue
            pos = details.find(search_term)
            if pos >= 0:
                matches.append((1, pos, idx))
        return [self.collection_ids[idx] for _, _, idx in sorted(matches)]

    def perform_fetch_results(self, search: str, feedback: QgsFeedback):
        if not self.available_collections:
            # Nothing to search: tell why rather than finding nothing
            if self.state.collections_failed_at is None:
                message = self.tr(
                    "Loading the datasets of {}: search again in a moment"
                )
            else:
                message = self.tr(
                    "The datasets of {} could not be loaded: search again in a minute"
                )
            self.tell(message.format(self.catalog.NAME))
            return

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

        refusing = self.state.refusing()
        missing = False
        if refusing:
            # Only what is kept from before
            kept = [
                request
                for request in requests
                if self.state.responses.get(request.url().url()) is not None
            ]
            missing = len(kept) < len(requests)
            requests = kept

        self.fetch_requests(
            requests, feedback, self.handle_content, cache=self.state.responses
        )

        # Refused before this search or during it
        if missing or (not refusing and self.state.refusing()):
            self.tell(
                self.tr(
                    "{} refuses requests for now: search again in a few minutes"
                ).format(self.catalog.NAME)
            )

    def handle_reply_error(self, url: str, reply: QNetworkReply):
        super().handle_reply_error(url, reply)
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status == 429:
            # Too many requests: geodienste.ch blocks whoever insists for hours
            self.state.refuse()

    def tell(self, message: str):
        """A line among the results telling why some are missing"""
        result = QgsLocatorResult()
        result.filter = self
        result.displayString = message
        result.userData = NoResult().as_definition()
        self.result_found = True
        self.resultFetched.emit(result)

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
            self.catalog.mediaType(asset_id, asset.get("type"))
            for item in response["features"]
            for asset_id, asset in item["assets"].items()
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
                        self.catalog.mediaType(asset_id, asset.get("type")),
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
