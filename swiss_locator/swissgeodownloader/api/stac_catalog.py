"""
/***************************************************************************
 SwissGeoDownloader
                                 A QGIS plugin
 This plugin lets you comfortably download swiss geo data.
                             -------------------
        begin                : 2021-03-14
        copyright            : (C) 2025 by Patricia Moll
        email                : pimoll.dev@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from qgis.PyQt.QtCore import QUrl
from qgis.core import QgsTask, Qgis, QgsStacItem

from swiss_locator.swissgeodownloader.api.network_request import fetch
from swiss_locator.swissgeodownloader.api.response_objects import (
    CURRENT_VALUE,
    FILETYPE_STREAMED,
    SgdAsset,
    SgdStacCollection,
    assetFileName,
)
from swiss_locator.swissgeodownloader.api.stac_client import STACClient
from swiss_locator.swissgeodownloader.utils.filter_utils import (
    cleanupFilterItems,
    currentFileByBbox,
)
from swiss_locator.swissgeodownloader.utils.utilities import translate, log

# STAC APIs give bounding boxes in WGS84
API_EPSG = "EPSG:4326"


class ApiStacCatalog:
    """A STAC API whose files can be downloaded or streamed. Subclasses set
    the id, the name and the URL of the catalog and can add metadata to its
    collections."""

    CATALOG_ID = ""
    NAME = ""
    URL = ""

    def __init__(self, locale="en"):
        self.locale = locale
        self.stacClient: STACClient = STACClient(self.URL)

    def getCollections(self, task: QgsTask) -> dict[str, SgdStacCollection]:
        collectionList = {}
        try:
            collections = self.stacClient.fetchCollections(task)
        except Exception as e:
            msg = self.tr(
                "Error when loading available dataset - Unexpected API response"
            )
            task.exception = f"{msg}: {task.exception or str(e)}"
            raise Exception(task.exception)

        self.prepareMetadata(task)

        for stacCollection in collections:
            coll = SgdStacCollection(stacCollection, self.CATALOG_ID)

            # Get title and description in the current locale and add
            # missing metadata if necessary
            self.addMetadataToCollection(coll, task)

            # Check if important properties are available and log missing ones
            report = coll.reportCompleteness()
            if report:
                log(report, debugMsg=True)

            collectionList[coll.id()] = coll

        return collectionList

    def prepareMetadata(self, task: QgsTask):
        """Fetch what addMetadataToCollection() needs, once per catalog."""

    def addMetadataToCollection(self, collection: SgdStacCollection, task: QgsTask):
        """Complete the metadata of a collection, e.g. with translations."""

    def fileName(self, collectionId: str, itemId: str, assetId: str, href: str) -> str:
        """Name of the file of an asset, once downloaded."""
        return assetFileName(assetId, href)

    def analyseCollectionItems(
        self, task: QgsTask, collection: SgdStacCollection
    ) -> SgdStacCollection:
        """Analyse collection to figure out available options in gui"""
        # Get max. 40 features
        try:
            items: list[QgsStacItem] = self.stacClient.fetchItems(
                task, collection.id(), {"limit": 40}
            )
        except Exception as e:
            msg = self.tr(
                "Error when loading dataset details - Unexpected API response"
            )
            task.exception = f"{msg}: {task.exception or str(e)}"
            raise Exception(task.exception)

        estimate = {}
        itemCount = len(items)

        # Check if it makes sense to select by bbox or if the full file list
        #  should just be downloaded directly
        if itemCount <= 10:
            collection.setSelectByBBox(False)

        # Analyze size of an item to estimate download sizes later on
        if itemCount > 0:
            item = items[-1]

            # Get an estimate of file size
            for assetId, asset in item.assets().items():
                if task.isCanceled():
                    raise Exception("User canceled")

                # Don't request again if we have this estimate already
                if assetId in estimate.keys():
                    continue
                # Check Content-Length header: Make a HEAD request to get the file size
                try:
                    header = fetch(task, QUrl(asset.href()), method="head")
                except Exception:
                    # Some servers refuse HEAD requests, e.g. geo.bs.ch
                    header = None
                if header and header.hasRawHeader(b"Content-Length"):
                    estimate[asset.mediaType()] = int(
                        header.rawHeader(b"Content-Length")
                    )

        collection.setAnalysed(True)
        collection.setIsEmpty(itemCount == 0)
        collection.setAvgSize(estimate)
        return collection

    def getFileList(
        self, task: QgsTask, collectionId, bbox: list[float] | None
    ) -> dict:
        """Request a list of available files that are within a bounding box.
        Analyse the received list and extract file properties."""

        try:
            stacItemsResponse = self.stacClient.fetchItems(
                task, collectionId, {"bbox": bbox}, True
            )
        except Exception as e:
            msg = self.tr("Error when requesting file list - Unexpected API response")
            task.exception = f"{msg}: {task.exception or e}"
            raise Exception(task.exception)

        return self._processItems(stacItemsResponse, task, collectionId)

    def _processItems(
        self, stacItemResponse: list[QgsStacItem], task: QgsTask, collectionId: str
    ) -> dict:
        filterItems = {
            "filetype": [],
            "category": [],
            "resolution": [],
            "timestamp": [],
            "coordsys": [],
        }
        fileList = []

        for item in stacItemResponse:
            if task.isCanceled():
                raise Exception("User canceled")

            # Readout timestamp from the item itself
            try:
                timestamp = item.properties().get("datetime")
                endTimestamp = None
            except KeyError:
                # Try to get timestamp from 'start_datetime' and 'end_datetime'
                timestamp = item.properties().get("start_datetime")
                endTimestamp = item.properties().get("end_datetime")
                if not timestamp:
                    # Extract the mandatory timestamp 'created' instead
                    timestamp = item.properties().get("created")

            additionalAssetProperties = self.stacClient.assetProperties.get(
                item.id(), {}
            )
            # Save all files and their properties
            for assetId, asset in item.assets().items():
                if task.isCanceled():
                    raise Exception("User canceled")

                # Create file object
                file = SgdAsset(assetId, asset)
                file.id = self.fileName(collectionId, item.id(), assetId, file.href)
                file.properties = additionalAssetProperties.get(assetId, {})

                try:
                    file.setBbox(item.boundingBox())
                except AssertionError as e:
                    log(
                        f"File {file.id}: Bounding box not valid: {e} {item.boundingBox()}",
                        Qgis.MessageLevel.Warning,
                    )

                # Extract file properties, save them to the file object
                #  and add them to the filter list

                fileTypesPerAsset = []
                if file.filetype:
                    fileTypesPerAsset.append(file.filetype)
                    if file.isCloudOptimized():
                        fileTypesPerAsset.append(
                            f"{file.filetype}, {FILETYPE_STREAMED}"
                        )
                    filterItems["filetype"].extend(fileTypesPerAsset)

                if timestamp:
                    try:
                        file.setTimestamp(timestamp, endTimestamp)
                    except ValueError:
                        log(
                            f"File {file.id}: Timestamp not valid)",
                            Qgis.MessageLevel.Warning,
                        )
                    filterItems["timestamp"].append(file.timestampStr)

                # These are Swisstopo specific properties that don't follow
                #  the STAC specification
                if file.properties.get("geoadmin:variant"):
                    file.category = str(file.properties.get("geoadmin:variant"))
                    filterItems["category"].append(file.category)

                if file.properties.get("gsd"):
                    file.resolution = str(file.properties.get("gsd"))
                    filterItems["resolution"].append(file.resolution)

                # The projection extension can be on the asset or on the item
                epsg = file.properties.get("proj:epsg") or item.properties().get(
                    "proj:epsg"
                )
                if epsg:
                    file.coordsys = str(epsg)
                    filterItems["coordsys"].append(file.coordsys)

                fileList.append(file)
                # If one asset can support multiple file types (e.g. tif and
                #  COG), create a copy of the file for each file type
                if len(fileTypesPerAsset) > 1:
                    for fileType in fileTypesPerAsset[1:]:
                        copiedFile = file.copy()
                        copiedFile.filetype = fileType
                        fileList.append(copiedFile)

        # Sort file list by bbox coordinates (first item on top left corner)
        fileList.sort(key=lambda f: round(f.bbox[3], 2) if f.bbox else 0, reverse=True)
        fileList.sort(key=lambda f: round(f.bbox[0], 2) if f.bbox else 0)

        # Clean up filter items by removing duplicates and adding an 'ALL' entry
        filterItems = cleanupFilterItems(filterItems)

        # Extract most current file (timestamp) for every bbox on the map
        if len(filterItems["timestamp"]) >= 2:
            mostCurrentFileInBbox = currentFileByBbox(fileList)

            if len(mostCurrentFileInBbox.keys()) > 1:
                for savedBboxDicts in mostCurrentFileInBbox.values():
                    for file in savedBboxDicts.values():
                        file.isMostCurrent = True
                filterItems["timestamp"].insert(0, CURRENT_VALUE)

        return {"files": fileList, "filters": filterItems}

    def downloadFiles(self, task: QgsTask, fileList, outputDir):
        return self.stacClient.downloadFiles(task, fileList, outputDir)

    def tr(self, message):
        # The strings of this class are translated in its context, also when
        #  a subclass runs them
        return translate("ApiStacCatalog", message)
