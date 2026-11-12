"""
/***************************************************************************

 QGIS Swiss Locator Plugin
 Copyright (C) 2026 Denis Rouzaud

 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/

Contract between the data generators (scripts/) and the plugin.

Every published file is a JSON document wrapping the actual data:

    {"version": 1, "generated": "2026-11-12T00:00:00Z", "data": ...}

Standard library only: this module is imported by the CI scripts, outside QGIS.
"""

import os
from datetime import datetime, UTC
from typing import Any

from swiss_locator.core.constants import PAGES_URL

# Bump it on any incompatible change of a file's structure. The version is part
# of the URL, so released plugins keep reading the format they understand.
# When bumping it, keep publishing the previous version for them.
FORMAT_VERSION = 1

# Location of the files, relative to the root of the GitHub Pages site
DATA_PATH = f"data/v{FORMAT_VERSION}"
BASE_URL = f"{PAGES_URL}/{DATA_PATH}"

# Copies shipped in the plugin package (downloaded at packaging), or generated
# locally to test the plugin from the sources (git-ignored)
BUNDLED_DIR = os.path.join(os.path.dirname(__file__), "bundled")

# Searchable map.geo.admin.ch layers: {layer_id: {lang: label}}
MAP_GEO_ADMIN_LAYERS = "map_geo_admin_searchable_layers.json"

# Layers of the WMS services referenced by opendata.swiss:
# {"services": [{"url": str, "version": str, "title": str, "harvested": str,
#                "layers": [[name, title], ...]}]}
OPENDATA_SWISS_WMS_LAYERS = "opendata_swiss_wms_layers.json"

DATA_FILES = (MAP_GEO_ADMIN_LAYERS, OPENDATA_SWISS_WMS_LAYERS)

# Summary of the last generation, for humans and monitoring
MANIFEST = "index.json"

# ISO 8601 in UTC: timestamps compare chronologically as strings
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class InvalidDataFile(ValueError):
    """A document does not follow the format above."""


def utc_now() -> str:
    return datetime.now(UTC).strftime(TIMESTAMP_FORMAT)


def url(file_name: str) -> str:
    return f"{BASE_URL}/{file_name}"


def wrap(data: Any, generated: str | None = None) -> dict:
    return {
        "version": FORMAT_VERSION,
        "generated": generated or utc_now(),
        "data": data,
    }


def unwrap(document: Any) -> tuple[str, Any]:
    """Validate a document and return its generation timestamp and its data."""
    if not isinstance(document, dict):
        raise InvalidDataFile("document is not a JSON object")
    if document.get("version") != FORMAT_VERSION:
        raise InvalidDataFile(
            f"unsupported format version {document.get('version')!r}, "
            f"expected {FORMAT_VERSION}"
        )
    generated = document.get("generated")
    if not isinstance(generated, str) or not generated:
        raise InvalidDataFile("missing generation timestamp")
    if "data" not in document:
        raise InvalidDataFile("missing data")
    return generated, document["data"]
