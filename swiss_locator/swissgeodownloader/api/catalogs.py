from swiss_locator.core.constants import VIAGEO_STAC_URL
from swiss_locator.swissgeodownloader.api.datageoadmin import ApiDataGeoAdmin
from swiss_locator.swissgeodownloader.api.stac_catalog import ApiStacCatalog


class ApiViageo(ApiStacCatalog):
    """Cantonal and communal geodata published on viageo.ch"""

    CATALOG_ID = "viageo"
    NAME = "viageo.ch"
    URL = VIAGEO_STAC_URL


# The STAC catalogs whose files can be searched, downloaded and streamed
STAC_CATALOGS: dict[str, type[ApiStacCatalog]] = {
    catalog.CATALOG_ID: catalog for catalog in (ApiDataGeoAdmin, ApiViageo)
}


def createCatalogs(locale: str) -> dict[str, ApiStacCatalog]:
    return {catalogId: catalog(locale) for catalogId, catalog in STAC_CATALOGS.items()}
