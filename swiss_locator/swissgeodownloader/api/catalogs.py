from swiss_locator.core.constants import (
    BASEL_STADT_STAC_URL,
    GEODIENSTE_STAC_URL,
    VIAGEO_STAC_URL,
)
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


class ApiGeodienste(ApiStacCatalog):
    """Geodata of the cantons on geodienste.ch, in the data models of the
    Confederation: an item per canton, each in several formats"""

    CATALOG_ID = "geodienste"
    NAME = "geodienste.ch"
    URL = f"{GEODIENSTE_STAC_URL}/deu"
    # The catalog, and the attributes of its files, in German, French or Italian
    LANGUAGES = {"fr": "fra", "it": "ita"}
    # Each format is a zip file under application/zip: give it the media type
    #  of the dataset inside, which tells the formats apart and adds the
    #  dataset to the project once downloaded. The INTERLIS transfer comes with
    #  its model and is only downloaded, as those of data.geo.admin.ch.
    ZIP_MEDIA_TYPES = {
        "geopackage_zip": "application/geopackage+sqlite3",
        "shapefile_zip": "application/vnd.shp",
        "csv_zip": "text/csv",
        "interlis": "application/x.interlis+zip",
    }

    def __init__(self, locale="en"):
        self.URL = f"{GEODIENSTE_STAC_URL}/{self.LANGUAGES.get(locale, 'deu')}"
        super().__init__(locale)

    def mediaType(self, assetId: str, mediaType: str) -> str:
        if mediaType == "application/zip":
            return self.ZIP_MEDIA_TYPES.get(assetId, mediaType)
        return mediaType


# The STAC catalogs whose files can be searched, downloaded and streamed
STAC_CATALOGS: dict[str, type[ApiStacCatalog]] = {
    catalog.CATALOG_ID: catalog
    for catalog in (ApiDataGeoAdmin, ApiGeodienste, ApiViageo, ApiBaselStadt)
}

# The catalogs of cantons and municipalities: the user chooses those to search
#  in the locator, on top of data.geo.admin.ch
LOCAL_STAC_CATALOGS: tuple[type[ApiStacCatalog], ...] = (
    ApiGeodienste,
    ApiViageo,
    ApiBaselStadt,
)


def createCatalogs(locale: str) -> dict[str, ApiStacCatalog]:
    return {catalogId: catalog(locale) for catalogId, catalog in STAC_CATALOGS.items()}
