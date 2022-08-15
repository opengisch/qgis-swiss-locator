def map_geo_admin_url(search: str, _type: str, crs: str, lang: str, limit: int):
    base_url = "https://api3.geo.admin.ch/rest/services/api/SearchServer"
    base_params = {
        "type": _type,
        "searchText": str(search),
        "returnGeometry": "true",
        "lang": lang,
        "sr": crs,
        "limit": str(limit)
        # bbox Must be provided if the searchText is not.
        # A comma separated list of 4 coordinates representing
        # the bounding box on which features should be filtered (SRID: 21781).
    }
    return base_url, base_params
