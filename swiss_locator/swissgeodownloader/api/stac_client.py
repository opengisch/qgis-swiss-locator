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

import os

from qgis.core import (
    QgsTask,
    QgsBox3D,
    QgsGeometry,
    QgsStacAsset,
    QgsStacCollection,
    QgsStacCollectionList,
    QgsStacController,
    QgsStacItem,
    QgsStacItemCollection
)

from swiss_locator.swissgeodownloader.api.network_request import (
    fetch,
    createUrl,
    fetchFile
)
from swiss_locator.swissgeodownloader.api.responseObjects import SgdAsset


class STACClient:
    CACHE: dict[str, list[QgsStacCollection]] = {}
    
    def __init__(self, url):
        self.url = url
        self.controller = QgsStacController()
        self.assetProperties = {}
    
    def fetchCollections(self, task: QgsTask,
                         params: dict = None) -> list[QgsStacCollection]:
        """Get a list of all available collections."""
        
        initUrl = createUrl(f"{self.url}/collections", params)
        
        if self.CACHE.get(initUrl):
            return self.CACHE.get(initUrl)
        
        errorMsg = ""
        collections = []
        url = initUrl
        
        while url:
            if task.isCanceled():
                raise Exception('User canceled')
            
            response: QgsStacCollectionList = self.controller.fetchCollections(
                    url, errorMsg
            )
            
            if errorMsg or not response:
                task.exception = errorMsg
                raise Exception(task.exception)
            
            collections += response.takeCollections()
            url = None
            if (
                    not params
                    or not params.get("limit")
                    or len(collections) < params["limit"]
            ):
                url = response.nextUrl() if not response.nextUrl().isEmpty() else None
        
        if len(collections) > 0:
            self.CACHE[initUrl] = collections
        
        return collections
    
    def fetchItems(
            self,
            task: QgsTask,
            collectionId: str,
            params: dict = None,
            requestAdditionalProperties: bool = False,
    ) -> list[QgsStacItem]:
        """Fetch items from a collection."""
        
        url = createUrl(f"{self.url}/collections/{collectionId}/items", params)
        errorMsg = ""
        items: list[QgsStacItem] = []
        self.assetProperties = {}
        
        while url:
            if task.isCanceled():
                raise Exception('User canceled')
            
            if requestAdditionalProperties:
                rawStacItemResponse: dict = fetch(task, url)
                
                requestedItems = self._parseItems(task, rawStacItemResponse)
                url = next(
                        (link["href"] for link in rawStacItemResponse["links"]
                            if link["rel"] == "next"), None)
            
            else:
                response: QgsStacItemCollection = self.controller.fetchItemCollection(
                        url, errorMsg
                )
                if errorMsg or not response:
                    task.exception = errorMsg
                    raise Exception(task.exception)
                
                requestedItems = response.takeItems()
                url = response.nextUrl() if not response.nextUrl().isEmpty() else None
            
            items += requestedItems
            
            if params and params.get("limit") and len(items) >= params[
                "limit"]:
                url = None
        
        return items
    
    def _parseItems(self, task: QgsTask,
                    rawStacItemResponse: dict) -> list[QgsStacItem]:
        """Parse the raw json response from the stac api into a list of items
        and assets. This is necessary because the STAC controller does not parse
         additional properties of the asset."""
        parsedItems = []
        for rawItem in rawStacItemResponse["features"]:
            
            if task.isCanceled():
                raise Exception('User canceled')
            
            bbox = None
            if len(rawItem["bbox"]) == 4:
                bbox = QgsBox3D(*rawItem["bbox"][:2], None,
                                *rawItem["bbox"][2:], None)
            elif len(rawItem["bbox"]) == 6:
                bbox = QgsBox3D(*rawItem["bbox"])
            
            item = QgsStacItem(
                    rawItem.get("id"),
                    rawItem.get("version"),
                    QgsGeometry(),  # Geometry currently isn't used
                    rawItem.get("properties", {}),
                    [],  # Links currently aren't used
                    {},
                    bbox,
            )
            assets = {}
            self.assetProperties[item.id()] = {}
            for assetId in rawItem.get("assets"):
                rawAsset = rawItem["assets"][assetId]
                asset = QgsStacAsset(
                        rawAsset.get("href"),
                        rawAsset.get("title"),
                        rawAsset.get("description"),
                        rawAsset.get("type"),
                        [],
                )
                assets[assetId] = asset
                
                # Collect any additional properties of the asset and save them
                #   separately
                for k in ["href", "title", "description", "type"]:
                    rawAsset.pop(k, None)
                self.assetProperties[item.id()][assetId] = rawAsset
            
            item.setAssets(assets)
            parsedItems.append(item)
        return parsedItems
    
    @staticmethod
    def downloadFiles(task: QgsTask, fileList: list[SgdAsset],
                      outputDir: str) -> bool:
        task.setProgress(0)
        partProgress = 100 / len(fileList)
        
        for file in fileList:
            savePath = os.path.join(outputDir, file.id)
            fetchFile(task, file.href, file.id, savePath, partProgress)
            if task.isCanceled():
                raise Exception('User canceled')
            task.setProgress(task.progress() + partProgress)
        return True
