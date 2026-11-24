import unittest
from unittest import mock

from qgis.core import (
    QgsBox3D,
    QgsGeometry,
    QgsStacAsset,
    QgsStacCollection,
    QgsStacExtent,
    QgsStacItem,
)
from qgis.testing import start_app

from swiss_locator.swissgeodownloader.api.catalogs import (
    ApiBaselStadt,
    ApiGeodienste,
    ApiViageo,
)
from swiss_locator.swissgeodownloader.api.response_objects import SgdStacCollection

start_app()

COPC = "application/vnd.laszip+copc"
ZIP = "application/zip"
XTF = "application/interlis+xml"


class FakeTask:
    @staticmethod
    def isCanceled():
        return False


def viageoTile(name: str, x: float) -> QgsStacItem:
    """A point cloud tile as viageo.ch publishes it: the asset is named after
    its format and the coordinate system is given on the item."""
    item = QgsStacItem(
        name,
        "1.1.0",
        QgsGeometry(),
        {"datetime": "2012-11-15T00:00:00Z", "proj:epsg": 2056},
        [],
        {},
        QgsBox3D(x, 46.50, None, x + 0.01, 46.51, None),
    )
    href = f"https://data.viageo.ch/pully/{name}.copc.laz"
    item.setAssets({"laz_copc": QgsStacAsset(href, "", "", COPC, [])})
    return item


def geodiensteCanton(canton: str, transfers: int = 1) -> QgsStacItem:
    """The wildlife rest zones of a canton as geodienste.ch publishes them:
    each format zipped under application/zip, and the INTERLIS transfers."""
    item = QgsStacItem(
        f"wildruhezonen_v2_1-{canton}",
        "1.0.0",
        QgsGeometry(),
        {"datetime": "2023-09-29T10:02:08Z", "title": f"Wildruhezonen - {canton}"},
        [],
        {},
        QgsBox3D(9.19, 47.24, None, 9.63, 47.46, None),
    )
    url = "https://geodienste.ch/downloads"
    name = f"wildruhezonen_v2_1_{canton}"
    assets = {
        "interlis": (f"interlis/wildruhezonen/{canton}/{name}_lv95.zip", ZIP),
        "geopackage_zip": (
            f"geopackage/wildruhezonen/{canton}/deu/{name}_gpkg_lv95.zip",
            ZIP,
        ),
        "shapefile_zip": (
            f"shapefile/wildruhezonen/{canton}/deu/{name}_shp_lv95.zip",
            ZIP,
        ),
        "csv_zip": (f"csv/wildruhezonen/{canton}/deu/{name}_csv_lv95.zip", ZIP),
    }
    for i in range(transfers):
        xtf = f"{canton}_Wildruhezonen_{i}.xtf"
        assets[xtf] = (f"interlis/wildruhezonen/{canton}/{xtf}", XTF)
    item.setAssets(
        {
            key: QgsStacAsset(f"{url}/{path}", "", "", mediaType, ["data"])
            for key, (path, mediaType) in assets.items()
        }
    )
    return item


class TestProcessItems(unittest.TestCase):
    def test_viageo_tiles(self):
        result = ApiViageo()._processItems(
            [viageoTile("2538_1150", 6.63), viageoTile("2539_1150", 6.64)],
            FakeTask(),
            "9ad6c580-94b8-4887-a2ad-3c22e91f5629",
        )
        self.assertEqual(
            [(f.id, f.filetype, f.coordsys) for f in result["files"]],
            [
                ("2538_1150.copc.laz", "vnd.laszip+copc", "2056"),
                ("2538_1150.copc.laz", "vnd.laszip+copc, streamed", "2056"),
                ("2539_1150.copc.laz", "vnd.laszip+copc", "2056"),
                ("2539_1150.copc.laz", "vnd.laszip+copc, streamed", "2056"),
            ],
        )
        self.assertEqual(result["filters"]["coordsys"], ["2056"])

    def test_basel_stadt_formats(self):
        """The URL of a file of Basel-Stadt ends with its format, the file is
        named as the server names it."""
        item = QgsStacItem(
            "latest",
            "1.0.0",
            QgsGeometry(),
            {"datetime": "2026-11-12T02:00:05Z"},
            [],
            {},
            QgsBox3D(7.55, 47.52, None, 7.63, 47.59, None),
        )
        item.setAssets(
            {
                key: QgsStacAsset(
                    f"{ApiBaselStadt.URL}/download/DEFI/latest/{key}", "", "", t, []
                )
                for key, t in (
                    ("fgb", "application/vnd.flatgeobuf"),
                    ("gpkg", "application/geopackage+sqlite3"),
                    ("shp", "application/vnd.shp"),
                )
            }
        )
        result = ApiBaselStadt()._processItems([item], FakeTask(), "DEFI")
        # The FlatGeobuf is zipped: not streamed, though QGIS 4.3 streams FlatGeobuf
        self.assertEqual(
            [(f.id, f.filetype) for f in result["files"]],
            [
                ("DEFI_latest_fgb.zip", "vnd.flatgeobuf"),
                ("DEFI_latest_gpkg.zip", "geopackage+sqlite3"),
                ("DEFI_latest_shp.zip", "vnd.shp"),
            ],
        )

    def test_geodienste_formats(self):
        """Each format of geodienste.ch is a zip under application/zip: it gets
        the media type of the dataset inside, but the INTERLIS transfer."""
        result = ApiGeodienste()._processItems(
            [geodiensteCanton("AR")], FakeTask(), "wildruhezonen"
        )
        self.assertEqual(
            sorted((f.id, f.filetype) for f in result["files"]),
            [
                ("AR_Wildruhezonen_0.xtf", "interlis+xml"),
                ("wildruhezonen_v2_1_AR_csv_lv95.zip", "csv"),
                ("wildruhezonen_v2_1_AR_gpkg_lv95.zip", "geopackage+sqlite3"),
                ("wildruhezonen_v2_1_AR_lv95.zip", "interlis+zip"),
                ("wildruhezonen_v2_1_AR_shp_lv95.zip", "vnd.shp"),
            ],
        )


class TestGeodienste(unittest.TestCase):
    def test_language(self):
        """The catalog in German, French or Italian, in German otherwise"""
        self.assertEqual(
            [ApiGeodienste(locale).URL for locale in ("de", "fr", "it", "en", "rm")],
            [
                f"https://geodienste.ch/stac/{language}"
                for language in ("deu", "fra", "ita", "deu", "deu")
            ],
        )
        self.assertEqual(
            ApiGeodienste("fr").stacClient.url, "https://geodienste.ch/stac/fra"
        )

    def test_size_requested_once_per_format(self):
        """A canton of the cadastral survey has a file per municipality, in
        the same format: the size of one of them is requested."""
        catalog = ApiGeodienste()
        catalog.stacClient.fetchItems = lambda *args: [
            geodiensteCanton("AR", transfers=20)
        ]
        collection = SgdStacCollection(
            QgsStacCollection("wildruhezonen", None, None, [], None, QgsStacExtent()),
            ApiGeodienste.CATALOG_ID,
        )
        header = mock.Mock()
        header.hasRawHeader.return_value = True
        header.rawHeader.return_value = b"1000"
        with mock.patch(
            "swiss_locator.swissgeodownloader.api.stac_catalog.fetch",
            return_value=header,
        ) as fetch:
            catalog.analyseCollectionItems(FakeTask(), collection)
        self.assertEqual(fetch.call_count, 5)
        self.assertEqual(
            sorted(collection.avgSize()),
            [
                "application/geopackage+sqlite3",
                "application/interlis+xml",
                "application/vnd.shp",
                "application/x.interlis+zip",
                "text/csv",
            ],
        )


if __name__ == "__main__":
    unittest.main()
