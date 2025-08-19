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
from swiss_locator.swissgeodownloader.api.responseObjects import (
    ALL_VALUE,
    SgdAsset
)


def cleanupFilterItems(filterItems: dict):
    """Cleanup filter values so no duplicates are present. Also add 'ALL'
    option."""
    # Remove duplicate entries in the filter list and sort
    for key, l in filterItems.items():
        sortedList = list(set(l))
        sortedList.sort()
        sortedList.reverse()
        filterItems[key] = sortedList
    
    # Add an 'ALL' option to the filter list
    for filterType in filterItems.keys():
        if len(filterItems[filterType]) >= 2:
            filterItems[filterType].append(ALL_VALUE)
    
    return filterItems


def currentFileByBbox(fileList: list[SgdAsset]):
    """ Searches for the most current file for each bbox and property
    combination. Creates a dictionary for each unique bbox that contains
    the most current file for each property combination.
    Example:
    '5.22|47.45|6.13|48.33': {
        '.tif|0.5': file,
        '.csv|0.5'; file,
    }
    """
    bboxList = {}
    for file in fileList:
        bboxKey = file.bboxKey
        propKey = file.propKey
        
        # Bbox already exists
        propertyDict = bboxList.get(bboxKey)
        if propertyDict:
            # See if property combination already exists
            if propKey not in propertyDict:
                bboxList[bboxKey][propKey] = file
            # Other files with same properties exist: Check if file
            #  timestamp is more current
            elif propertyDict[propKey].timestamp < file.timestamp:
                # Replace old file with new file
                bboxList[bboxKey][propKey] = file
        
        # Same bbox key does not exist yet, search for similar bbox by
        #  comparing coordinates
        else:
            foundSimilar = False
            # Go trough already saved bbox entries
            for savedBboxKey, propertyDict in bboxList.items():
                # If property combination matches, compare bbox
                if (propKey in propertyDict
                        and propertyDict[propKey].hasSimilarBboxAs(file.bbox)):
                    foundSimilar = True
                    # Compare timestamps and replace file if timestamp is
                    #  more current
                    if propertyDict[propKey].timestamp < file.timestamp:
                        bboxList[savedBboxKey][propKey] = file
                    break
            # Add new bbox entry
            if not foundSimilar:
                bboxList[bboxKey] = {propKey: file}
    
    return bboxList

