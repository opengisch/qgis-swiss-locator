"""
Unit tests for swiss_locator.map_geo_admin.layers module.

Tests the searchable_layers function on fixture data.
Does NOT require network access.
"""

from qgis.testing import start_app, unittest

from swiss_locator.core.settings import Settings
from swiss_locator.map_geo_admin.layers import SEARCHABLE_LAYERS, searchable_layers
from swiss_locator.remote_data import spec

start_app()

LAYERS = {
    "ch.swisstopo.amtliches-strassenverzeichnis": {
        "de": "Amtliches Strassenverzeichnis",
        "fr": "Répertoire officiel des rues",
        "it": "Elenco ufficiale delle vie",
        "rm": "Register uffizial da las vias",
        "en": "Official directory of streets",
    },
    "ch.bfs.gebaeude_wohnungs_register": {"de": "GWR: Gebäudestatus"},
}


class TestSearchableLayers(unittest.TestCase):
    def setUp(self):
        SEARCHABLE_LAYERS.set_document(spec.wrap(LAYERS))
        self.settings = Settings()
        self.restrict = self.settings.feature_search_restrict.value()
        self.layers_list = self.settings.feature_search_layers_list.value()

    def tearDown(self):
        self.settings.feature_search_restrict.setValue(self.restrict)
        self.settings.feature_search_layers_list.setValue(self.layers_list)

    def test_labels_in_language(self):
        result = searchable_layers("fr")
        self.assertEqual(
            result["ch.swisstopo.amtliches-strassenverzeichnis"],
            "Répertoire officiel des rues",
        )

    def test_missing_label_falls_back_to_german(self):
        result = searchable_layers("en")
        self.assertEqual(
            result["ch.bfs.gebaeude_wohnungs_register"], "GWR: Gebäudestatus"
        )

    def test_same_layers_in_all_languages(self):
        for lang in ("de", "fr", "it", "rm", "en"):
            self.assertEqual(set(searchable_layers(lang)), set(LAYERS))

    def test_invalid_language_raises(self):
        with self.assertRaises(AssertionError):
            searchable_layers("xx")

    def test_restriction(self):
        self.settings.feature_search_restrict.setValue(True)
        self.settings.feature_search_layers_list.setValue(
            ["ch.bfs.gebaeude_wohnungs_register"]
        )
        self.assertEqual(
            list(searchable_layers("de", restrict=True)),
            ["ch.bfs.gebaeude_wohnungs_register"],
        )
        # restriction applies only when asked
        self.assertEqual(len(searchable_layers("de")), 2)

    def test_invalid_data(self):
        with self.assertRaises(spec.InvalidDataFile):
            SEARCHABLE_LAYERS.set_document(spec.wrap({"ch.layer": "label"}))


if __name__ == "__main__":
    unittest.main()
