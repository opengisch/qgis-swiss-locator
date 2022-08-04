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


from qgis.core import QgsLocatorFilter
from swiss_locator.qgissettingmanager import SettingManager, Scope, Bool, String, Stringlist, Integer, Enum

pluginName = "swiss_locator_plugin"


class Settings(SettingManager):
    def __init__(self):
        SettingManager.__init__(self, pluginName)

        # lang of the service
        # possible values are de, fr, it , rm, en
        # if left empty or NULL, try to use locale and defaults to en
        self.add_setting(String("lang", Scope.Global, ''))
        self.add_setting(String("crs", Scope.Global, 'project', allowed_values=('2056', '21781', 'project')))
        self.add_setting(Bool("show_map_tip", Scope.Global, False))

        self.add_setting(Enum('locations_priority', Scope.Global, QgsLocatorFilter.Highest))
        self.add_setting(Integer('locations_limit', Scope.Global, 8))
        self.add_setting(Enum('wmts_priority', Scope.Global, QgsLocatorFilter.Highest))
        self.add_setting(Integer('wmts_limit', Scope.Global, 8))
        self.add_setting(Enum('featuresearch_priority', Scope.Global, QgsLocatorFilter.Medium))
        self.add_setting(Integer('featuresearch_limit', Scope.Global, 8))
        self.add_setting(Enum('layers_priority', Scope.Global, QgsLocatorFilter.High))
        self.add_setting(Integer('layers_limit', Scope.Global, 5))

        self.add_setting(Bool("feature_search_restrict", Scope.Global, False))
        self.add_setting(Stringlist("feature_search_layers_list", Scope.Global, None))

        self.add_setting(Bool("layers_include_opendataswiss", Scope.Global, True))

