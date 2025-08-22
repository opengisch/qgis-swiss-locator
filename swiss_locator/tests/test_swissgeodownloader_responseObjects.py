import unittest

from qgis.core import QgsStacAsset, QgsBox3D

from swiss_locator.swissgeodownloader.api.responseObjects import (
    SgdAsset,
    FILETYPE_STREAMED
)


class TestFileObject(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        pass
    
    @classmethod
    def tearDownClass(cls):
        pass
    
    @staticmethod
    def createAsset(title, mediaType, href) -> SgdAsset:
        stacAsset = QgsStacAsset(href, title, "", mediaType, [])
        return SgdAsset(title, stacAsset)
    
    @staticmethod
    def createQgsBox3d(bbox: list[float]) -> QgsBox3D:
        return QgsBox3D(bbox[0], bbox[1], None, bbox[2], bbox[3], None, None)
    
    def test_bbox_key_empty(self):
        file_obj = self.createAsset("test_file", "image",
                                    "http://example.com")
        self.assertEqual(file_obj.bboxKey, '')
    
    def test_bbox_key_valid(self):
        file_obj = self.createAsset("test_file", "image",
                                    "http://example.com")
        file_obj.setBbox(self.createQgsBox3d(
                [100.123456, 10.654321, 102.987654, 12.123456]))
        self.assertEqual(file_obj.bboxKey, '100.1235|10.6543|102.9877|12.1235')
    
    def test_set_bbox_valid(self):
        file_obj = self.createAsset("test_file", "image",
                                    "http://example.com")
        bbox = self.createQgsBox3d([100.0, 10.0, 102.0, 12.0])
        file_obj.setBbox(bbox)
        self.assertEqual(file_obj.bbox,
                         [bbox.xMinimum(), bbox.yMinimum(),
                             bbox.xMaximum(), bbox.yMaximum()])
    
    def test_set_bbox_invalid(self):
        file_obj = self.createAsset("test_file", "image",
                                    "http://example.com")
        # Invalid bbox length
        self.assertRaises(AssertionError, file_obj.setBbox, [1.0, 2.0, 3.0])
    
    def test_prop_key(self):
        file_obj = self.createAsset("test_file", "image",
                                    "http://example.com")
        file_obj.filetype = "image"
        file_obj.category = "jpeg"
        file_obj.resolution = "2.0"
        self.assertEqual(file_obj.propKey, 'image|jpeg|2.0')
    
    def test_isStreamable(self):
        file_obj = self.createAsset('myTestFile', 'tiff',
                                    'https://this.is.a.test.url')
        self.assertFalse(file_obj.isStreamable)
        file_obj.filetype = f"tiff {FILETYPE_STREAMED}"
        self.assertTrue(file_obj.isStreamable)
    
    def test_timestamp_parsing(self):
        file_obj = self.createAsset("test_file", "image",
                                    "http://example.com")
        file_obj.setTimestamp("2023-07-16T12:34:56Z")
        self.assertEqual(file_obj.timestampStr, "2023-07-16")
        self.assertRaises(ValueError, file_obj.setTimestamp, 'this is a test')
    
    def test_timestamp_range_parsing(self):
        file_obj = self.createAsset("test_file", "image",
                                    "http://example.com")
        file_obj.setTimestamp('2023-07-16T12:34:56Z', '2024-07-16T12:34:56Z')
        self.assertEqual(file_obj.timestampStr, '2023-07-16 / 2024-07-16')
        self.assertRaises(ValueError, file_obj.setTimestamp,
                          '2023-07-16T12:34:56Z', 'this is a test')
    
    def test_timestamp_invalid(self):
        file_obj = self.createAsset("test_file", "image",
                                    "http://example.com")
        self.assertRaises(ValueError, file_obj.setTimestamp, '20-12-12T00:00')
        self.assertEqual(file_obj.timestampStr, '')
    
    def test_filetype_fits_filter(self):
        file_obj = self.createAsset("test_file", "image",
                                    "http://example.com")
        self.assertTrue(file_obj.filetypeFitsFilter(None))
        # If property is None, it should always pass the filter
        file_obj.filetype = None
        self.assertTrue(file_obj.filetypeFitsFilter("abc"))
        file_obj.filetype = "image"
        self.assertTrue(file_obj.filetypeFitsFilter(None))
        self.assertTrue(file_obj.filetypeFitsFilter("image"))
        self.assertTrue(file_obj.filetypeFitsFilter(""))
        self.assertFalse(file_obj.filetypeFitsFilter("video"))
    
    def test_category_fits_filter(self):
        file_obj = self.createAsset("test_file", "image",
                                    "http://example.com")
        # If property is None, it should always pass the filter
        self.assertTrue(file_obj.categoryFitsFilter(None))
        self.assertTrue(file_obj.categoryFitsFilter("abc"))
        file_obj.category = "jpeg"
        self.assertTrue(file_obj.categoryFitsFilter(None))
        self.assertTrue(file_obj.categoryFitsFilter("jpeg"))
        self.assertTrue(file_obj.categoryFitsFilter(""))
        self.assertFalse(file_obj.categoryFitsFilter("png"))
    
    def test_has_similar_bbox(self):
        file_obj = self.createAsset("test_file", "image",
                                    "http://example.com")
        file_obj.setBbox(self.createQgsBox3d([100.0, 10.0, 102.0, 12.0]))
        similar_bbox = [100.1, 10.1, 102.1, 12.1]
        self.assertTrue(file_obj.hasSimilarBboxAs(similar_bbox))
    
    def test_huge_bboxes_similar(self):
        bboxes = {
            2023: [5.835645258473665, 45.73922949988648, 10.52253827249051,
                47.83944608953652],
            2022: [5.857755182140817, 45.73922949988648, 10.52253827249051,
                47.83944608953652],
            2016: [6.764889995565601, 45.794733721463004, 9.495713098753871,
                47.82656806522374],
            2010: [6.765054419290001, 45.80663032920316, 9.496159354475557,
                47.813699891059535],
            2014: [6.06848726911284, 46.09444142786817, 10.552510553220536,
                47.644093800799475],
        }
        
        file_obj = self.createAsset("test_file", "image",
                                    "http://example.com")
        
        file_obj.setBbox(self.createQgsBox3d(bboxes[2023]))
        similar_bbox = bboxes[2022]
        self.assertTrue(file_obj.hasSimilarBboxAs(similar_bbox))
        
        file_obj.setBbox(self.createQgsBox3d(bboxes[2016]))
        similar_bbox = bboxes[2010]
        self.assertTrue(file_obj.hasSimilarBboxAs(similar_bbox))
        
        file_obj.setBbox(self.createQgsBox3d(bboxes[2014]))
        for year, bbox in bboxes.items():
            if year != 2014:
                print(year)
                self.assertFalse(file_obj.hasSimilarBboxAs(bbox))
    
    def test_coordsys_fits_filter(self):
        file_obj = self.createAsset("test_file", "image",
                                    "http://example.com")
        # If property is None, it should always pass the filter
        self.assertTrue(file_obj.coordsysFitsFilter(None))
        self.assertTrue(file_obj.coordsysFitsFilter("abc"))
        file_obj.coordsys = "EPSG:4326"
        self.assertTrue(file_obj.coordsysFitsFilter(None))
        self.assertTrue(file_obj.coordsysFitsFilter("EPSG:4326"))
        self.assertTrue(file_obj.coordsysFitsFilter(""))
        self.assertFalse(file_obj.coordsysFitsFilter("EPSG:3857"))


if __name__ == '__main__':
    unittest.main()
