import os
import tempfile
import unittest
import zipfile

from qgis.core import QgsStacAsset
from qgis.testing import start_app

from swiss_locator.core.results import STACResult
from swiss_locator.swissgeodownloader.api.response_objects import (
    FILETYPE_STREAMED,
    SgdAsset,
)
from swiss_locator.swissgeodownloader.utils.qgis_layer_creator_task import (
    QgisLayerCreatorTask,
    extractPointClouds,
)

start_app()

COPC = "application/vnd.laszip+copc"
COPC_HREF = "https://data.geo.admin.ch/c/tile_2025.copc.laz"


def createAsset(assetId, mediaType, href, path=None, streamed=False) -> SgdAsset:
    asset = SgdAsset(assetId, QgsStacAsset(href, assetId, "", mediaType, []))
    if streamed:
        asset.filetype = f"{asset.filetype}, {FILETYPE_STREAMED}"
    asset.path = path
    asset.coordsys = "2056"
    return asset


class TestExtractPointClouds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def createZip(self, name, members: dict[str, bytes]) -> str:
        path = os.path.join(self.dir, name)
        with zipfile.ZipFile(path, "w") as zf:
            for member, data in members.items():
                zf.writestr(member, data)
        return path

    def test_single_point_cloud_named_after_zip(self):
        """The year is only in the zip name, so the extracted file takes it."""
        path = self.createZip(
            "swisssurface3d_2019_2496-1115_2056_5728.las.zip",
            {"2496_1115.las": b"LASF", "readme.txt": b"hello"},
        )
        self.assertEqual(
            extractPointClouds(path),
            [os.path.join(self.dir, "swisssurface3d_2019_2496-1115_2056_5728.las")],
        )
        self.assertEqual(
            sorted(os.listdir(self.dir)),
            [
                "swisssurface3d_2019_2496-1115_2056_5728.las",
                "swisssurface3d_2019_2496-1115_2056_5728.las.zip",
            ],
        )

    def test_several_point_clouds_prefixed_with_zip_name(self):
        path = self.createZip("tiles.zip", {"a/1.las": b"1", "b/2.laz": b"2"})
        self.assertEqual(
            extractPointClouds(path),
            [
                os.path.join(self.dir, "tiles_1.las"),
                os.path.join(self.dir, "tiles_2.laz"),
            ],
        )

    def test_no_point_cloud(self):
        path = self.createZip("data.shp.zip", {"data.shp": b"", "data.dbf": b""})
        self.assertEqual(extractPointClouds(path), [])
        self.assertEqual(os.listdir(self.dir), ["data.shp.zip"])

    def test_already_extracted_file_is_kept(self):
        path = self.createZip("tile.las.zip", {"1.las": b"LASF"})
        extracted = extractPointClouds(path)[0]
        os.utime(extracted, (0, 0))
        extractPointClouds(path)
        self.assertEqual(os.path.getmtime(extracted), 0)


class TestPointCloudsOf(unittest.TestCase):
    def test_streamed_copc(self):
        asset = createAsset("tile_2025.copc.laz", COPC, COPC_HREF, streamed=True)
        self.assertEqual(
            QgisLayerCreatorTask.pointCloudsOf(asset),
            [(COPC_HREF, "tile_2025.copc.laz", "copc", "2056")],
        )

    def test_streamed_copc_from_locator(self):
        result = STACResult(
            "c",
            "n",
            "tile_2025.copc.laz",
            "",
            COPC,
            COPC_HREF,
            path=COPC_HREF,
            coordsys="2056",
        )
        self.assertEqual(
            QgisLayerCreatorTask.pointCloudsOf(result),
            [(COPC_HREF, "tile_2025.copc.laz", "copc", "2056")],
        )

    def test_streamed_cog_is_no_point_cloud(self):
        asset = createAsset(
            "tile.tif",
            "image/tiff; application=geotiff; profile=cloud-optimized",
            "https://example.com/tile.tif",
            streamed=True,
        )
        self.assertEqual(QgisLayerCreatorTask.pointCloudsOf(asset), [])

    def test_downloaded_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            copc = os.path.join(tmp, "tile_2025.copc.laz")
            las_zip = os.path.join(tmp, "tile_2019.las.zip")
            tif = os.path.join(tmp, "tile.tif")
            open(copc, "wb").close()
            open(tif, "wb").close()
            with zipfile.ZipFile(las_zip, "w") as zf:
                zf.writestr("2496_1115.las", b"LASF")

            def pointCloudsOf(assetId, mediaType, path):
                asset = createAsset(assetId, mediaType, "https://x/" + assetId, path)
                return QgisLayerCreatorTask.pointCloudsOf(asset)

            self.assertEqual(
                pointCloudsOf("tile_2025.copc.laz", COPC, copc),
                [(copc, "tile_2025.copc.laz", "copc", "2056")],
            )
            las = os.path.join(tmp, "tile_2019.las")
            self.assertEqual(
                pointCloudsOf("tile_2019.las.zip", "application/vnd.laszip", las_zip),
                [(las, "tile_2019.las", "pdal", "2056")],
            )
            self.assertEqual(pointCloudsOf("tile.tif", "image/tiff", tif), [])


if __name__ == "__main__":
    unittest.main()
