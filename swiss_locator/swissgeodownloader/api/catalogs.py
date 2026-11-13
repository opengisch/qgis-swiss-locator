from swiss_locator.core.constants import BASEL_STADT_STAC_URL, VIAGEO_STAC_URL
from swiss_locator.swissgeodownloader.api.datageoadmin import ApiDataGeoAdmin
from swiss_locator.swissgeodownloader.api.stac_catalog import ApiStacCatalog


class ApiViageo(ApiStacCatalog):
    """Cantonal and communal geodata published on viageo.ch"""

    CATALOG_ID = "viageo"
    NAME = "viageo.ch"
    URL = VIAGEO_STAC_URL


class ApiBaselStadt(ApiStacCatalog):
    """Geodata of the canton of Basel-Stadt, each dataset in several formats"""

    CATALOG_ID = "baselstadt"
    NAME = "geo.bs.ch"
    URL = BASEL_STADT_STAC_URL

    def fileName(self, collectionId: str, itemId: str, assetId: str, href: str) -> str:
        # The URL of a file ends with its format, e.g. .../AFBA/latest/gpkg, and
        #  the file is the dataset zipped: name it as the server does
        return f"{collectionId}_{itemId}_{assetId}.zip"


# The STAC catalogs whose files can be searched, downloaded and streamed
STAC_CATALOGS: dict[str, type[ApiStacCatalog]] = {
    catalog.CATALOG_ID: catalog
    for catalog in (ApiDataGeoAdmin, ApiViageo, ApiBaselStadt)
}


def createCatalogs(locale: str) -> dict[str, ApiStacCatalog]:
    return {catalogId: catalog(locale) for catalogId, catalog in STAC_CATALOGS.items()}
