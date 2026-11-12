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

WMS URL helpers.

Standard library only: shared by the plugin and the opendata.swiss harvester
in scripts/, so that both identify a service by the same URL.
"""

import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

# Parameters of WMS requests. Any other query parameter of a URL belongs to the
# service endpoint itself, e.g. MapServer's "map".
REQUEST_PARAMETERS = frozenset(
    {
        "BBOX",
        "BGCOLOR",
        "CRS",
        "DPI",
        "ELEVATION",
        "EXCEPTIONS",
        "FEATURE_COUNT",
        "FORMAT",
        "FORMAT_OPTIONS",
        "HEIGHT",
        "I",
        "INFO_FORMAT",
        "J",
        "LAYER",
        "LAYERS",
        "MAP_RESOLUTION",
        "QUERY_LAYERS",
        "REQUEST",
        "SCALE",
        "SERVICE",
        "SLD",
        "SLD_BODY",
        "SLD_VERSION",
        "SRS",
        "STYLE",
        "STYLES",
        "TIME",
        "TRANSPARENT",
        "VERSION",
        "WIDTH",
        "WMTVER",
        "X",
        "Y",
    }
)

DEFAULT_VERSION = "1.3.0"

# Swisstopo services, searched by the dedicated geo.admin.ch filters, and the
# web pages of geo.admin.ch referenced as WMS by some catalogs
_GEO_ADMIN_RE = re.compile(
    r"^https?://([^/?#]+\.)?geo\.admin\.ch([:/?#]|$)", re.IGNORECASE
)


def is_geo_admin(url: str) -> bool:
    return bool(_GEO_ADMIN_RE.match(url.strip()))


def _query_items(query: str) -> list[tuple[str, str]]:
    # some catalogs HTML-escape the separators of the query
    return parse_qsl(query.replace("&amp;", "&"), keep_blank_values=True)


def service_url(url: str) -> str | None:
    """Return the endpoint of the WMS service a request URL belongs to.

    WMS request parameters are dropped, other parameters are kept. Scheme and
    host are lower-cased so that the same service always gets the same URL.
    Returns None if the URL is not an HTTP(S) URL.
    """
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    query = [
        (key, value)
        for key, value in _query_items(parts.query)
        if key.upper() not in REQUEST_PARAMETERS
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path or "/",
            urlencode(query),
            "",
        )
    )


def query_parameter(url: str, name: str) -> str | None:
    """Return a query parameter of a URL, matching its name case-insensitively."""
    name = name.upper()
    for key, value in _query_items(urlsplit(url).query):
        if key.upper() == name:
            return value
    return None


def capabilities_url(service: str) -> str:
    separator = "&" if "?" in service else "?"
    return f"{service}{separator}SERVICE=WMS&REQUEST=GetCapabilities"


def provider_url(service: str, version: str = DEFAULT_VERSION) -> str:
    """Return the value of the "url" key of a QGIS WMS provider URI.

    The keys of the provider URI are separated by "&", so the query of the URL
    is percent-encoded. The version is pinned to the one of the capabilities.
    """
    base, _, query = service.partition("?")
    query = "&".join(part for part in (query, f"VERSION={version}") if part)
    return f"{base}?{quote(query, safe='')}"
