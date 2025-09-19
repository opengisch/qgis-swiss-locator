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
from datetime import datetime

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import Qgis, QgsMessageLog

from swiss_locator.swissgeodownloader import DEBUG

MESSAGE_CATEGORY = 'Swiss Geo Downloader'


def translate(context, message):
    """Get the translation for a string using Qt translation API.
    We implement this ourselves since we do not inherit QObject.
    """
    return QCoreApplication.translate(context, message)


def formatCoordinate(number):
    """Format big numbers with thousand separator, swiss-style"""
    if number is None:
        return ''
    # Format big numbers with thousand separator
    elif number >= 1000:
        return f"{number:,.0f}".replace(',', "'")
    else:
        return f"{number:,.6f}"


def castToNum(formattedNum):
    """Casts formatted numbers back to floats"""
    if type(formattedNum) in [int, float]:
        return formattedNum
    try:
        num = float(formattedNum.replace("'", ''))
    except (ValueError, AttributeError):
        num = None
    return num


def filesizeFormatter(num, suffix='B'):
    """Formats data sizes to human readable units"""
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Yi', suffix)


def getDateFromIsoString(isoString, formatted=True):
    """Translate ISO date string to date or swiss date format"""
    if isoString[-1] == 'Z':
        isoString = isoString[:-1]
    dt = datetime.fromisoformat(isoString)
    if formatted:
        return dt.strftime('%Y-%m-%d')
    else:
        return dt


def log(msg, level=Qgis.MessageLevel.Info, debugMsg=False):
    if debugMsg:
        if not DEBUG:
            return
        msg = f'DEBUG {msg}'
    QgsMessageLog.logMessage(str(msg), MESSAGE_CATEGORY, level)
