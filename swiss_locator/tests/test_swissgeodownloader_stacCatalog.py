import unittest

from qgis.core import QgsBox3D, QgsGeometry, QgsStacAsset, QgsStacItem
from qgis.testing import start_app

from swiss_locator.swissgeodownloader.api.catalogs import ApiBaselStadt, ApiViageo

start_app()

COPC = "application/vnd.laszip+copc"


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
                    ("gpkg", "application/geopackage+sqlite3"),
                    ("shp", "application/vnd.shp"),
                )
            }
        )
        result = ApiBaselStadt()._processItems([item], FakeTask(), "DEFI")
        self.assertEqual(
            [f.id for f in result["files"]],
            ["DEFI_latest_gpkg.zip", "DEFI_latest_shp.zip"],
        )


if __name__ == "__main__":
    unittest.main()
