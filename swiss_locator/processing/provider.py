"""
/***************************************************************************

                            QGIS Swiss Locator Plugin
 
                             -------------------
        begin                : 2026-10-08
        copyright            : (C) 2026 by Tristan Carel
        email                : tristan.carel@protonmail.com
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

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from swiss_locator import PLUGIN_PATH
from swiss_locator.processing.geocode_addresses_algorithm import (
    GeocodeAddressesAlgorithm,
)

ICON_PATH = os.path.join(PLUGIN_PATH, "icons", "swiss_locator.png")


class SwissLocatorProcessingProvider(QgsProcessingProvider):
    """Processing provider exposing the geo.admin.ch based algorithms."""

    def id(self) -> str:
        return "swiss_locator"

    def name(self) -> str:
        return "Swiss Locator"

    def longName(self) -> str:
        return "Swiss Locator (geo.admin.ch)"

    def icon(self) -> QIcon:
        return QIcon(ICON_PATH)

    def svgIconPath(self) -> str:
        return ICON_PATH

    def loadAlgorithms(self):
        self.addAlgorithm(GeocodeAddressesAlgorithm())
