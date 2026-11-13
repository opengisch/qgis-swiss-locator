import unittest

from qgis.core import QgsBox3D, QgsGeometry, QgsStacAsset, QgsStacItem
from qgis.testing import start_app

from swiss_locator.swissgeodownloader.api.catalogs import ApiViageo

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


if __name__ == "__main__":
    unittest.main()
