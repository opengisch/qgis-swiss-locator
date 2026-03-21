# Centralised API base URLs for geo.admin.ch services.
# Keeping them in one place makes it easy to find and update endpoints.

API_BASE_URL = "https://api3.geo.admin.ch"

SEARCH_URL = f"{API_BASE_URL}/rest/services/api/SearchServer"
MAP_SERVER_URL = f"{API_BASE_URL}/rest/services/api/MapServer"
PROFILE_URL = f"{API_BASE_URL}/rest/services/profile.json"

WMTS_BASE_URL = "https://wmts.geo.admin.ch"
WMS_BASE_URL = "http://wms.geo.admin.ch"

STAC_BASE_URL = "https://data.geo.admin.ch/api/stac/v1"

VECTOR_TILES_BASE_URL = "https://vectortiles.geo.admin.ch"

OPENDATA_SWISS_URL = "https://opendata.swiss/api/3/action/package_search"

MAP_GEO_ADMIN_URL = "https://map.geo.admin.ch"

USER_AGENT = b"Mozilla/5.0 QGIS Swiss Geoportal Locator Filter"
