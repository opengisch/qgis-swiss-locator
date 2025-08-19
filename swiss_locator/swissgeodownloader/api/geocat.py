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
import re
import xml.etree.ElementTree as ET

from qgis.core import QgsTask

from swiss_locator.swissgeodownloader.api.network_request import fetch
from swiss_locator.swissgeodownloader.utils.metadataHandler import (
    loadFromFile,
    saveToFile
)
from swiss_locator.swissgeodownloader.utils.utilities import translate, log

BASEURL = 'https://www.geocat.ch/geonetwork/srv/eng/csw'
XML_NAMESPACES = {'gmd': '{http://www.isotc211.org/2005/gmd}'}
REQUEST_PARAMS = {
    'service': 'CSW',
    'version': '2.0.2',
    'request': 'GetRecordById',
    'elementSetName': 'summary',
    'outputFormat': 'application/xml',
    'outputSchema': 'http://www.isotc211.org/2005/gmd',
}


class ApiGeoCat:
    
    def __init__(self, locale, fileName):
        """Request metadata from geocat.ch, the official geodata metadata
        service for switzerland."""
        self.locale = locale
        self.dataPath = fileName
        self.preSavedMetadata = {}
        self.loadPreSavedMetadata()
    
    def getMeta(self, task: QgsTask, collectionId: str, metadataUrl: str,
                locale: str):
        """Requests metadata for a collection Id. Since calling geocat several
        times on each plugin start is very slow, metadata is saved to a file
        and read from there. Only if there is no metadata for a specific
        collection in the file, geocat.ch is called."""
        metadata = {}
        
        # Check if metadata has been pre-saved and return this data
        if collectionId in self.preSavedMetadata \
                and locale in self.preSavedMetadata[collectionId]:
            return self.preSavedMetadata[collectionId][locale]
        
        geocatDsId = self.extractUuid(metadataUrl)
        if not geocatDsId:
            msg = translate('SGD',
                            'Error when trying to retrieve metadata - No dataset ID found')
            log(f'{msg}:\n{metadataUrl}')
            return metadata
        
        # Call geocat API
        rqParams = REQUEST_PARAMS
        rqParams['id'] = geocatDsId
        xml = fetch(task, BASEURL, params=rqParams, decoder='string')
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            msg = translate('SGD',
                            'Error when trying to retrieve metadata - Response cannot be parsed')
            log(msg)
            return metadata
        
        # Search for title and description in xml
        searchTerms = {
            'title': f"{XML_NAMESPACES['gmd']}title",
            'description': f"{XML_NAMESPACES['gmd']}abstract",
        }
        
        for mapsTo, searchTerm in searchTerms.items():
            xmlElements = [elem for elem in root.iter(tag=searchTerm)]
            for xmlElem in xmlElements:
                localizedStrings = [elem for elem in xmlElem.iter(
                        tag=f"{XML_NAMESPACES['gmd']}LocalisedCharacterString")]
                for localizedString in localizedStrings:
                    if localizedString.get('locale') == '#' + locale.upper():
                        metadata[mapsTo] = localizedString.text
                        break
                if metadata.get(mapsTo):
                    break
        
        # Save metadata to file so we don't have to call the API again
        self.updatePreSavedMetadata(metadata, collectionId, locale)
        
        return metadata
    
    def loadPreSavedMetadata(self):
        """Read pre-saved metadata from json file."""
        self.preSavedMetadata = loadFromFile(self.dataPath)
    
    def updatePreSavedMetadata(self, metadata, collectionId: str | None = None,
                               locale: str | None = None):
        """Update the pre-saved metadata with a completely new dictionary or
        only update partially by adding a new collection."""
        if collectionId and locale:
            # Make a partial update of the data in the file
            if collectionId not in self.preSavedMetadata:
                self.preSavedMetadata[collectionId] = {locale: metadata}
            else:
                self.preSavedMetadata[collectionId][locale] = metadata
            saveToFile(self.preSavedMetadata, self.dataPath)
        else:
            # Fully replace the data in the file
            saveToFile(metadata, self.dataPath)
    
    @staticmethod
    def extractUuid(url):
        if not url or not type(url) is str:
            return None
        uuidRegex = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        uuid = re.search(uuidRegex, url)
        return uuid.group(0) if uuid else None
