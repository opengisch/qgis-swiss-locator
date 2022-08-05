# -*- coding: utf-8 -*-
# -----------------------------------------------------------
#
# QGIS Swiss Locator Plugin
# Copyright (C) 2022 Denis Rouzaud
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

import json
from qgis.core import QgsGeometry, QgsRectangle


class WMSLayerResult:
    def __init__(self, layer, title, url, tile_matrix_set: str = None, _format: str = 'image/png', style: str = None):
        self.title = title
        self.layer = layer
        self.url = url
        self.tile_matrix_set = tile_matrix_set
        self.format = _format
        self.style = style

    @staticmethod
    def from_dict(dict_data: dict):
        return WMSLayerResult(
            dict_data['layer'],
            dict_data['title'],
            dict_data['url'],
            tile_matrix_set=dict_data.get('tile_matrix_set'),
            _format=dict_data.get('format'),
            style=dict_data.get('style')
        )

    def as_definition(self):
        definition = {
            'type': 'WMSLayerResult',
            'title': self.title,
            'layer': self.layer,
            'url': self.url,
            'tile_matrix_set': self.tile_matrix_set,
            'format': self.format,
            'style': self.style,
        }
        return json.dumps(definition)


class LocationResult:
    def __init__(self, point, bbox, layer, feature_id, html_label):
        self.point = point
        self.bbox = bbox
        self.layer = layer
        self.feature_id = feature_id
        self.html_label = html_label

    @staticmethod
    def from_dict(dict_data: dict):
        return LocationResult(QgsGeometry.fromWkt(dict_data['point']).asPoint(), QgsRectangle.fromWkt(dict_data['bbox']), dict_data['layer'], dict_data['feature_id'],
                              dict_data['html_label'])

    def as_definition(self):
        definition = {
            'type': 'LocationResult',
            'point': self.point.asWkt(),
            'bbox': self.bbox.asWktPolygon(),
            'layer': self.layer,
            'feature_id': self.feature_id,
            'html_label': self.html_label,
        }
        return json.dumps(definition)


class FeatureResult:
    def __init__(self, point, layer, feature_id):
        self.point = point
        self.layer = layer
        self.feature_id = feature_id

    @staticmethod
    def from_dict(dict_data: dict):
        return FeatureResult(QgsGeometry.fromWkt(dict_data['point']).asPoint(), dict_data['layer'], dict_data['feature_id'])

    def as_definition(self):
        definition = {
            'type': 'FeatureResult',
            'point': self.point.asWkt(),
            'layer': self.layer,
            'feature_id': self.feature_id,
        }
        return json.dumps(definition)


class NoResult:
    def __init__(self):
        pass

    @staticmethod
    def as_definition():
        definition = {'type': 'NoResult'}
        return json.dumps(definition)