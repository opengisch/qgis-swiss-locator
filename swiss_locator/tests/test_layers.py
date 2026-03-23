"""
Unit tests for swiss_locator.map_geo_admin.layers module.

Tests layer data loading, in-memory caching, and the searchable_layers function.
Does NOT require network access.
"""

from qgis.testing import start_app, unittest

from swiss_locator.map_geo_admin.layers import (
    _layers_cache,
    _load_data,
    data_file,
    searchable_layers,
)

start_app()


class TestDataFile(unittest.TestCase):
    """Verify data_file() returns correct paths."""

    def test_path_ends_with_json(self):
        path = data_file("de")
        self.assertTrue(path.endswith("layers_de.json"))

    def test_path_for_each_language(self):
        for lang in ("de", "fr", "it", "rm", "en"):
            path = data_file(lang)
            self.assertIn(f"layers_{lang}.json", path)


class TestLoadData(unittest.TestCase):
    """Test _load_data reads JSON and caches it."""

    def setUp(self):
        # Clear cache before each test
        _layers_cache.clear()

    def test_load_returns_dict(self):
        data = _load_data("de")
        self.assertIsInstance(data, dict)

    def test_has_expected_keys(self):
        data = _load_data("de")
        self.assertIn("searchableLayers", data)
        self.assertIn("translations", data)

    def test_cache_is_populated(self):
        self.assertNotIn("fr", _layers_cache)
        _load_data("fr")
        self.assertIn("fr", _layers_cache)

    def test_cache_returns_same_object(self):
        """Second call should return the exact same dict object (cached)."""
        first = _load_data("de")
        second = _load_data("de")
        self.assertIs(first, second)


class TestSearchableLayers(unittest.TestCase):
    """Test searchable_layers function."""

    def setUp(self):
        _layers_cache.clear()

    def test_returns_dict(self):
        result = searchable_layers("de")
        self.assertIsInstance(result, dict)

    def test_returns_non_empty(self):
        result = searchable_layers("de")
        self.assertGreater(len(result), 0)

    def test_all_languages(self):
        for lang in ("de", "fr", "it", "rm", "en"):
            result = searchable_layers(lang)
            self.assertIsInstance(result, dict)
            self.assertGreater(len(result), 0, f"No layers found for lang={lang}")

    def test_keys_are_layer_ids(self):
        """Layer IDs should be dot-separated strings like 'ch.swisstopo.xxx'."""
        result = searchable_layers("de")
        for key in result:
            self.assertIsInstance(key, str)
            self.assertIn(".", key, f"Layer id '{key}' does not look like a layer id")

    def test_values_are_strings(self):
        result = searchable_layers("de")
        for val in result.values():
            self.assertIsInstance(val, str)

    def test_invalid_language_raises(self):
        with self.assertRaises(AssertionError):
            searchable_layers("xx")

    def test_consistent_layer_set_across_languages(self):
        """All languages should have the same layer IDs."""
        de_keys = set(searchable_layers("de").keys())
        for lang in ("fr", "it", "en"):
            lang_keys = set(searchable_layers(lang).keys())
            self.assertEqual(
                de_keys,
                lang_keys,
                f"Layer keys differ between 'de' and '{lang}'",
            )


if __name__ == "__main__":
    unittest.main()
