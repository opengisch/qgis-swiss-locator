from swiss_locator.core.constants import SEARCH_URL


def map_geo_admin_url(search: str, _type: str, crs: str, lang: str, limit: int):
    base_params = {
        "type": _type,
        "searchText": str(search),
        "returnGeometry": "true",
        "lang": lang,
        "sr": crs,
        "limit": str(limit),
        # bbox Must be provided if the searchText is not.
        # A comma separated list of 4 coordinates representing
        # the bounding box on which features should be filtered (SRID: 21781).
    }
    return SEARCH_URL, base_params
