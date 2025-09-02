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
import json
import os

from swiss_locator.swissgeodownloader import PLUGIN_DIR
from swiss_locator.swissgeodownloader.utils.utilities import log

SETTING_PREFIX = 'PluginSwissGeoDownloader'
SAVE_DIRECTORY = os.path.join(PLUGIN_DIR, 'api')


def saveToFile(metadata, filename):
    try:
        jsonData = json.dumps(metadata, indent=2, sort_keys=True,
                              ensure_ascii=False)
    except Exception:
        log('Converting metadata to json data not successful')
        return
    
    metafile = os.path.join(SAVE_DIRECTORY, filename)
    try:
        with open(metafile, 'w', encoding='utf8') as f:
            f.write(jsonData)
    except PermissionError:
        log('Saving metadata to json file not successful')


def loadFromFile(filename):
    filepath = os.path.join(SAVE_DIRECTORY, filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            log('Loading metadata from file not possible')
            return {}
    else:
        log('Metadata file not found')
    return {}
