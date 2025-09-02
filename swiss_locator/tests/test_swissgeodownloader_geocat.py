import unittest
from unittest.mock import patch

from swiss_locator.swissgeodownloader.api.geocat import ApiGeoCat


class TestApiGeoCat(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.locale = "en"
        cls.api: ApiGeoCat = ApiGeoCat(cls.locale, 'test_path')
    
    @classmethod
    def tearDownClass(cls):
        cls.api = None
    
    @patch("swiss_locator.swissgeodownloader.api.geocat.loadFromFile")
    def test_load_pre_saved_metadata(self, mock_load):
        """Test loading pre-saved metadata."""
        mock_load.return_value = {"testId": {"en": {"title": "Test Title"}}}
        self.api.loadPreSavedMetadata()
        self.assertIn("testId", self.api.preSavedMetadata)
        self.assertIn("en", self.api.preSavedMetadata["testId"])
        self.assertEqual(
                self.api.preSavedMetadata["testId"]["en"]["title"],
                "Test Title")
    
    def test_extract_uuid_from_valid_url_of_typeA(self):
        url = 'https://www.geocat.ch/geonetwork/srv/api/records/a7109ba7-9dcc-46d6-829f-c94b2214a1e5?language=all'
        self.assertEqual(self.api.extractUuid(url),
                         'a7109ba7-9dcc-46d6-829f-c94b2214a1e5')
    
    def test_extract_uuid_from_valid_url_of_typeB(self):
        url = 'https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/0d216c1b-2998-4eb9-a47b-ac88aafb7271'
        self.assertEqual(self.api.extractUuid(url),
                         '0d216c1b-2998-4eb9-a47b-ac88aafb7271')
    
    def test_extract_uuid_from_url_with_invalid_id(self):
        url = 'https://www.geocat.ch/geonetwork/srv/api/records/a7109ba7-9a1e5?language=all'
        self.assertIsNone(self.api.extractUuid(url))
    
    def test_extract_uuid_from_invalid_url(self):
        url = '//www.geocat.ch/geonetwork/srv/api/records/a7109ba7-9a1e5?language=all'
        self.assertIsNone(self.api.extractUuid(url))


if __name__ == '__main__':
    unittest.main()
