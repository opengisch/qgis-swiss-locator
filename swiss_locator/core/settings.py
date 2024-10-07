# -*- coding: utf-8 -*-
# -----------------------------------------------------------
#
# QGIS Swiss Locator Plugin
# Copyright (C) 2018 Denis Rouzaud
#
# -----------------------------------------------------------
#
# licensed under the terms of GNU GPL 2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# ---------------------------------------------------------------------

from qgis.core import (
    metaEnumFromType,
    QgsLocatorFilter,
    QgsSettingsTree,
    QgsSettingsEntryBool,
    QgsSettingsEntryString,
    QgsSettingsEntryInteger,
    QgsSettingsEntryStringList,
)
from swiss_locator.core.filters.filter_type import FilterType

PLUGIN_NAME = "swiss_locator_plugin"


class Settings(object):
    instance = None

    def __new__(cls):
        if cls.instance is None:
            cls.instance = super(Settings, cls).__new__(cls)

            settings_node = QgsSettingsTree.createPluginTreeNode(pluginName=PLUGIN_NAME)

            cls.lang = QgsSettingsEntryString("lang", settings_node, "lang")
            cls.show_map_tip = QgsSettingsEntryBool(
                "show_map_tip", settings_node, False
            )
            cls.feature_search_restrict = QgsSettingsEntryBool(
                "feature_search_restrict", settings_node, False
            )
            cls.layers_include_opendataswiss = QgsSettingsEntryBool(
                "layers_include_opendataswiss", settings_node, True
            )
            cls.feature_search_layers_list = QgsSettingsEntryStringList(
                "feature_search_layers_list", settings_node, []
            )

            me = metaEnumFromType(QgsLocatorFilter.Priority)

            cls.filters = {
                FilterType.Location.value: {
                    "priority": QgsSettingsEntryString(
                        f"{FilterType.Location.value}_priority",
                        settings_node,
                        me.valueToKey(QgsLocatorFilter.Priority.Highest),
                    ),
                    "limit": QgsSettingsEntryInteger(
                        f"{FilterType.Location.value}_limit", settings_node, 8
                    ),
                },
                FilterType.WMTS.value: {
                    "priority": QgsSettingsEntryString(
                        f"{FilterType.WMTS.value}_priority",
                        settings_node,
                        me.valueToKey(QgsLocatorFilter.Priority.Medium),
                    ),
                    "limit": QgsSettingsEntryInteger(
                        f"{FilterType.WMTS.value}_limit", settings_node, 8
                    ),
                },
                FilterType.VectorTiles.value: {
                    "priority": QgsSettingsEntryString(
                        f"{FilterType.VectorTiles.value}_priority",
                        settings_node,
                        me.valueToKey(QgsLocatorFilter.Priority.Highest),
                    ),
                    "limit": QgsSettingsEntryInteger(
                        f"{FilterType.VectorTiles.value}_limit", settings_node, 8
                    ),
                },
                FilterType.Feature.value: {
                    "priority": QgsSettingsEntryString(
                        f"{FilterType.Feature.value}_priority",
                        settings_node,
                        me.valueToKey(QgsLocatorFilter.Priority.High),
                    ),
                    "limit": QgsSettingsEntryInteger(
                        f"{FilterType.Feature.value}_limit", settings_node, 8
                    ),
                },
                FilterType.Layers.value: {
                    "priority": QgsSettingsEntryString(
                        f"{FilterType.Layers.value}_priority",
                        settings_node,
                        me.valueToKey(QgsLocatorFilter.Priority.High),
                    ),
                    "limit": QgsSettingsEntryInteger(
                        f"{FilterType.Layers.value}_limit", settings_node, 5
                    ),
                },
            }

        return cls.instance
