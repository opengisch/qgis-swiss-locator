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
    def __init__(
        self,
        layer,
        title,
        url,
        tile_matrix_set: str = None,
        _format: str = "image/png",
        style: str = None,
        tile_dimensions: str = None,
    ):
        self.title = title
        self.layer = layer
        self.url = url
        self.tile_matrix_set = tile_matrix_set
        self.format = _format
        self.style = style
        self.tile_dimensions = tile_dimensions

    @staticmethod
    def from_dict(dict_data: dict):
        return WMSLayerResult(
            dict_data["layer"],
            dict_data["title"],
            dict_data["url"],
            tile_matrix_set=dict_data.get("tile_matrix_set"),
            _format=dict_data.get("format"),
            style=dict_data.get("style"),
            tile_dimensions=dict_data.get("tile_dimensions"),
        )

    def as_definition(self):
        definition = {
            "type": "WMSLayerResult",
            "title": self.title,
            "layer": self.layer,
            "url": self.url,
            "tile_matrix_set": self.tile_matrix_set,
            "format": self.format,
            "style": self.style,
            "tile_dimensions": self.tile_dimensions,
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
        return LocationResult(
            QgsGeometry.fromWkt(dict_data["point"]).asPoint(),
            QgsRectangle.fromWkt(dict_data["bbox"]),
            dict_data["layer"],
            dict_data["feature_id"],
            dict_data["html_label"],
        )

    def as_definition(self):
        definition = {
            "type": "LocationResult",
            "point": self.point.asWkt(),
            "bbox": self.bbox.asWktPolygon(),
            "layer": self.layer,
            "feature_id": self.feature_id,
            "html_label": self.html_label,
        }
        return json.dumps(definition)


class FeatureResult:
    def __init__(self, point, layer, feature_id):
        self.point = point
        self.layer = layer
        self.feature_id = feature_id

    @staticmethod
    def from_dict(dict_data: dict):
        return FeatureResult(
            QgsGeometry.fromWkt(dict_data["point"]).asPoint(),
            dict_data["layer"],
            dict_data["feature_id"],
        )

    def as_definition(self):
        definition = {
            "type": "FeatureResult",
            "point": self.point.asWkt(),
            "layer": self.layer,
            "feature_id": self.feature_id,
        }
        return json.dumps(definition)


class VectorTilesLayerResult:
    def __init__(
        self,
        layer,
        title,
        url: str = None,
        style: str = None,
    ):
        self.title = title
        self.layer = layer
        self.url = url
        self.style = style

    @staticmethod
    def from_dict(dict_data: dict):
        return VectorTilesLayerResult(
            dict_data["layer"],
            dict_data["title"],
            dict_data["url"],
            style=dict_data.get("style"),
        )

    def as_definition(self):
        definition = {
            "type": "VectorTilesLayerResult",
            "title": self.title,
            "layer": self.layer,
            "url": self.url,
            "style": self.style,
        }
        return json.dumps(definition)


class STACResult:
    STREAMED_SOURCE_PREFIX = "/vsicurl/"
    
    def __init__(self, collection_id: str, collection_name: str, asset_id: str,
                 description: str, media_type: str, href: str, path: str = ''):
        self.collection_id = collection_id
        self.collection_name = collection_name
        self.asset_id = asset_id
        self.description = description
        self.media_type = media_type
        self.href = href
        self.path = path
        # Necessary for Swiss Geo Downloader compatibility
        self.id = asset_id
    
    def as_definition(self):
        definition = {
            "type": "STACResult",
            "collection_id": self.collection_id,
            "collection_name": self.collection_name,
            "asset_id": self.asset_id,
            "description": self.description,
            "media_type": self.media_type,
            "href": self.href,
            "path": self.path,
        }
        return json.dumps(definition)
    
    @staticmethod
    def from_dict(dict_data: dict):
        return STACResult(
                dict_data["collection_id"],
                dict_data["collection_name"],
                dict_data["asset_id"],
                dict_data["description"],
                dict_data["media_type"],
                dict_data["href"],
                dict_data["path"],
        )
    
    @property
    def is_downloadable(self):
        return self.asset_id and self.href
    
    @property
    def is_streamable(self):
        return "profile=cloud-optimized" in self.media_type and self.asset_id and self.href
    
    @property
    def is_streamed(self):
        return self.is_streamable and self.path.startswith(
                self.STREAMED_SOURCE_PREFIX)
    
    @property
    def isStreamable(self):
        # Necessary for Swiss Geo Downloader compatibility
        return self.is_streamed
    
    @property
    def simple_file_type(self):
        try:
            main_type = self.media_type.split(';')[0]
        except IndexError:
            return self.media_type
        try:
            return main_type.split('/')[
                -1] + (" (streamed)" if self.is_streamed else "")
        except IndexError:
            return main_type


class NoResult:
    def __init__(self):
        pass

    @staticmethod
    def as_definition():
        definition = {"type": "NoResult"}
        return json.dumps(definition)
