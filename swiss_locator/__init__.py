# -*- coding: utf-8 -*-
"""
/***************************************************************************

                                 QgisLocator

                             -------------------
        begin                : 2018-05-03
        copyright            : (C) 2018 by Denis Rouzaud
        email                : denis@opengis.ch
        git sha              : $Format:%H$
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

DEBUG = False
PLUGIN_PATH = os.path.dirname(__file__)


def classFactory(iface):
    """Load plugin.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .swiss_locator_plugin import SwissLocatorPlugin

    return SwissLocatorPlugin(iface)
