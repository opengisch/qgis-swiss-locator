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

from qgis.core import QgsTask

from swiss_locator.core.constants import STAC_BASE_URL
from swiss_locator.swissgeodownloader import _AVAILABLE_LOCALES
from swiss_locator.swissgeodownloader.api.geocat import ApiGeoCat
from swiss_locator.swissgeodownloader.api.network_request import fetch
from swiss_locator.swissgeodownloader.api.response_objects import SgdStacCollection
from swiss_locator.swissgeodownloader.api.stac_catalog import ApiStacCatalog

API_METADATA_URL = "https://api3.geo.admin.ch/rest/services/api/MapServer"


class ApiDataGeoAdmin(ApiStacCatalog):
    """Federal geodata of data.geo.admin.ch, with titles and descriptions
    translated by the geo.admin API and geocat.ch"""

    CATALOG_ID = "geoadmin"
    NAME = "data.geo.admin.ch"
    URL = STAC_BASE_URL

    def __init__(self, locale="en"):
        super().__init__(locale)
        self.ownMetadata = {}
        self.geocatClient = ApiGeoCat(locale, "datageoadmin_geocat_metadata.json")

    def prepareMetadata(self, task: QgsTask):
        # Geoadmin metadata: Fetches translated collection titles and descriptions
        self.ownMetadata = self.getOwnMetadata(task)

    def addMetadataToCollection(self, collection: SgdStacCollection, task: QgsTask):
        if collection.id() in self.ownMetadata:
            metadata = self.ownMetadata[collection.id()]

            collection.setTitle(metadata.get("title"))
            collection.setDescription(metadata.get("description"))
            return

        # Get external metadata from geocat.ch
        gcMetadata = self.geocatClient.getMeta(
            task, collection.id(), collection.metadataLink(), self.locale
        )
        if not gcMetadata:
            return

        collection.setTitle(gcMetadata.get("title") or collection.title())
        collection.setDescription(
            gcMetadata.get("description") or collection.description()
        )

    def getOwnMetadata(self, task: QgsTask):
        """Calls geoadmin API and retrieves translated titles and
        descriptions."""
        metadata = {}

        params = {"lang": self.locale}
        faqData: dict = fetch(task, API_METADATA_URL, params)
        if not faqData or not isinstance(faqData, dict) or "layers" not in faqData:
            return metadata

        for layer in faqData["layers"]:
            if task.isCanceled():
                raise Exception("User canceled")

            description = ""
            if "layerBodId" not in layer:
                continue
            layerId = layer.get("layerBodId")
            title = layer.get("fullName", "")
            if "attributes" in layer and "inspireAbstract" in layer["attributes"]:
                description = layer["attributes"]["inspireAbstract"]

            metadata[layerId] = {"title": title, "description": description}
        return metadata

    def refreshAllMetadata(self, task: QgsTask):
        """Fetches metadata for all collections and saves it to a json file."""
        collections = self.getCollections(task)

        md_geocat = {}
        for collectionId, collection in collections.items():
            # Request metadata in all languages
            metadata = {}
            for locale in _AVAILABLE_LOCALES:
                localizedMetadata = self.geocatClient.getMeta(
                    task, collectionId, collection.metadataLink(), locale, False
                )
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
