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

from swiss_locator.swissgeodownloader import _AVAILABLE_LOCALES
from swiss_locator.swissgeodownloader.api.geocat import ApiGeoCat
from swiss_locator.swissgeodownloader.api.network_request import fetch
from swiss_locator.swissgeodownloader.api.response_objects import (
    CURRENT_VALUE,
    FILETYPE_STREAMED,
    SgdAsset,
    SgdStacCollection
)
from swiss_locator.swissgeodownloader.api.stac_client import STACClient
from swiss_locator.swissgeodownloader.utils.filter_utils import (
    cleanupFilterItems,
    currentFileByBbox
)
from swiss_locator.swissgeodownloader.utils.utilities import translate, log

BASEURL = 'https://data.geo.admin.ch/api/stac/v1'
API_EPSG = 'EPSG:4326'
API_METADATA_URL = 'https://api3.geo.admin.ch/rest/services/api/MapServer'


class ApiDataGeoAdmin:
    
    def __init__(self, locale='en'):
        self.locale = locale
        self.stacClient: STACClient = STACClient(BASEURL)
        self.ownMetadata = {}
        self.geocatClient = ApiGeoCat(locale,
                                      'datageoadmin_geocat_metadata.json')
    
    def getCollections(self, task: QgsTask) -> dict[str, SgdStacCollection]:
        collectionList = {}
        try:
            collections = self.stacClient.fetchCollections(task)
        except Exception as e:
            msg = self.tr(
                    'Error when loading available dataset - Unexpected API response')
            task.exception = f"{msg}: {task.exception or str(e)}"
            raise Exception(task.exception)
        
        # Geoadmin metadata: Fetches translated collection titles and descriptions
        self.ownMetadata = self.getOwnMetadata(task)
        
        for stacCollection in collections:
            coll = SgdStacCollection(stacCollection)
            
            # Get title and description in the current locale and add
            # missing metadata if necessary
            self.addMetadataToCollection(coll, task)
            
            # Check if important properties are available and log missing ones
            report = coll.reportCompleteness()
            if report:
                log(report, debugMsg=True)
            
            collectionList[coll.id()] = coll
        
        return collectionList
    
    def addMetadataToCollection(self, collection: SgdStacCollection,
                                task: QgsTask):
        if collection.id() in self.ownMetadata:
            metadata = self.ownMetadata[collection.id()]
            
            collection.setTitle(metadata.get('title'))
            collection.setDescription(metadata.get('description'))
            return
        
        # Get external metadata from geocat.ch
        gcMetadata = self.geocatClient.getMeta(task, collection.id(),
                                               collection.metadataLink(),
                                               self.locale)
        if not gcMetadata:
            return
        
        collection.setTitle(gcMetadata.get('title') or collection.title())
        collection.setDescription(
                gcMetadata.get('description') or collection.description())
    
    def getOwnMetadata(self, task: QgsTask):
        """ Calls geoadmin API and retrieves translated titles and
        descriptions."""
        metadata = {}
        
        params = {
            'lang': self.locale
        }
        faqData: dict = fetch(task, API_METADATA_URL, params)
        if not faqData or not isinstance(faqData, dict) \
                or 'layers' not in faqData:
            return metadata
        
        for layer in faqData['layers']:
            if task.isCanceled():
                raise Exception('User canceled')
            
            description = ''
            if 'layerBodId' not in layer:
                continue
            layerId = layer.get('layerBodId')
            title = layer.get('fullName', '')
            if 'attributes' in layer and 'inspireAbstract' in layer[
                'attributes']:
                description = layer['attributes']['inspireAbstract']
            
            metadata[layerId] = {
                'title': title,
                'description': description
            }
        return metadata
    
    def analyseCollectionItems(self, task: QgsTask,
                               collection: SgdStacCollection) -> SgdStacCollection:
        """Analyse collection to figure out available options in gui"""
        # Get max. 40 features
        try:
            items: list[QgsStacItem] = self.stacClient.fetchItems(
                    task, collection.id(), {'limit': 40})
        except Exception as e:
            msg = self.tr(
                    'Error when loading dataset details - Unexpected API response')
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
            for (assetId, asset) in item.assets().items():
                if task.isCanceled():
                    raise Exception('User canceled')
                
                # Don't request again if we have this estimate already
                if assetId in estimate.keys():
                    continue
                # Check Content-Length header: Make a HEAD request to get the file size
                header = fetch(task, QUrl(asset.href()), method='head')
                if header and header.hasRawHeader(b'Content-Length'):
                    estimate[asset.mediaType()] = int(
                            header.rawHeader(b'Content-Length'))
        
        collection.setAnalysed(True)
        collection.setIsEmpty(itemCount == 0)
        collection.setAvgSize(estimate)
        return collection
    
    def getFileList(self, task: QgsTask, collectionId,
                    bbox: list[float] | None) -> dict:
        """Request a list of available files that are within a bounding box.
        Analyse the received list and extract file properties."""
        
        try:
            stacItemsResponse = self.stacClient.fetchItems(
                    task, collectionId, {'bbox': bbox}, True)
        except Exception as e:
            msg = self.tr(
                    'Error when requesting file list - Unexpected API response')
            task.exception = f"{msg}: {task.exception or e}"
            raise Exception(task.exception)
        
        return self._processItems(stacItemsResponse, task)
    
    def _processItems(self, stacItemResponse: list[QgsStacItem],
                      task: QgsTask) -> dict:
        filterItems = {
            'filetype': [],
            'category': [],
            'resolution': [],
            'timestamp': [],
            'coordsys': [],
        }
        fileList = []
        
        for item in stacItemResponse:
            if task.isCanceled():
                raise Exception('User canceled')
            
            # Readout timestamp from the item itself
            try:
                timestamp = item.properties().get('datetime')
                endTimestamp = None
            except KeyError:
                # Try to get timestamp from 'start_datetime' and 'end_datetime'
                timestamp = item.properties().get('start_datetime')
                endTimestamp = item.properties().get('end_datetime')
                if not timestamp:
                    # Extract the mandatory timestamp 'created' instead
                    timestamp = item.properties().get('created')
            
            additionalAssetProperties = self.stacClient.assetProperties.get(
                    item.id(), {})
            # Save all files and their properties
            for (assetId, asset) in item.assets().items():
                if task.isCanceled():
                    raise Exception('User canceled')
                
                # Create file object
                file = SgdAsset(assetId, asset)
                file.properties = additionalAssetProperties.get(assetId, {})
                
                try:
                    file.setBbox(item.boundingBox())
                except AssertionError as e:
                    log(f"File {file.id}: Bounding box not valid: {e} {item.boundingBox()}",
                        Qgis.MessageLevel.Warning)
                
                # Extract file properties, save them to the file object
                #  and add them to the filter list
                
                fileTypesPerAsset = []
                if file.filetype:
                    fileTypesPerAsset.append(file.filetype)
                    if file.isCloudOptimized():
                        fileTypesPerAsset.append(
                                f'{file.filetype}, {FILETYPE_STREAMED}')
                    filterItems['filetype'].extend(fileTypesPerAsset)
                
                if timestamp:
                    try:
                        file.setTimestamp(timestamp, endTimestamp)
                    except ValueError:
                        log(f"File {file.id}: Timestamp not valid)",
                            Qgis.MessageLevel.Warning)
                    filterItems['timestamp'].append(file.timestampStr)
                
                # These are Swisstopo specific properties that don't follow
                #  the STAC specification
                if file.properties.get('geoadmin:variant'):
                    file.category = str(
                            file.properties.get('geoadmin:variant'))
                    filterItems['category'].append(file.category)
                
                if file.properties.get('gsd'):
                    file.resolution = str(file.properties.get('gsd'))
                    filterItems['resolution'].append(file.resolution)
                
                if file.properties.get('proj:epsg'):
                    file.coordsys = str(file.properties.get('proj:epsg'))
                    filterItems['coordsys'].append(file.coordsys)
                
                fileList.append(file)
                # If one asset can support multiple file types (e.g. tif and
                #  COG), create a copy of the file for each file type
                if len(fileTypesPerAsset) > 1:
                    for fileType in fileTypesPerAsset[1:]:
                        copiedFile = file.copy()
                        copiedFile.filetype = fileType
                        fileList.append(copiedFile)
        
        # Sort file list by bbox coordinates (first item on top left corner)
        fileList.sort(key=lambda f: round(f.bbox[3], 2) if f.bbox else 0,
                      reverse=True)
        fileList.sort(key=lambda f: round(f.bbox[0], 2) if f.bbox else 0)
        
        # Clean up filter items by removing duplicates and adding an 'ALL' entry
        filterItems = cleanupFilterItems(filterItems)
        
        # Extract most current file (timestamp) for every bbox on the map
        if len(filterItems['timestamp']) >= 2:
            mostCurrentFileInBbox = currentFileByBbox(fileList)
            
            if len(mostCurrentFileInBbox.keys()) > 1:
                for savedBboxDicts in mostCurrentFileInBbox.values():
                    for file in savedBboxDicts.values():
                        file.isMostCurrent = True
                filterItems['timestamp'].insert(0, CURRENT_VALUE)
        
        return {'files': fileList, 'filters': filterItems}
    
    def downloadFiles(self, task: QgsTask, fileList, outputDir):
        return self.stacClient.downloadFiles(task, fileList, outputDir)
    
    def refreshAllMetadata(self, task: QgsTask):
        """Fetches metadata for all collections and saves it to a json file."""
        collections = self.getCollections(task)
        
        md_geocat = {}
        for collectionId, collection in collections.items():
            # Request metadata in all languages
            metadata = {}
            for locale in _AVAILABLE_LOCALES:
                localizedMetadata = self.geocatClient.getMeta(
                        task, collectionId, collection.metadataLink(), locale,
                        False)
                if localizedMetadata:
                    metadata[locale] = localizedMetadata
            md_geocat[collectionId] = metadata
        
        self.geocatClient.updatePreSavedMetadata(md_geocat)
    
    def catalogPropertiesCrawler(self, task: QgsTask):
        """Crawls through all item / asset properties of the catalog and
        returns them."""
        collections = self.getCollections(task)
        items = {}
        for collectionId, collection in collections.items():
            items[collectionId] = {}
            items[collectionId]["title"] = collection.title()
            bbox = [7.8693964, 46.7961371, 7.9098771, 46.817595]
            fileList = self.getFileList(task, collectionId, bbox)
            if fileList:
                items[collectionId]["assets"] = len(fileList["files"])
                items[collectionId]["filters"] = {
                    k: v for k, v in fileList["filters"].items() if v
                }
        return items
    
    def tr(self, message):
        return translate(message, type(self).__name__)
