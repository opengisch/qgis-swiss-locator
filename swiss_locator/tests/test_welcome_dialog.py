from unittest import mock

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QDialog
from qgis.testing import start_app, unittest
from qgis.testing.mocked import get_iface

from swiss_locator.core.filters.swiss_locator_filter_stac import SwissLocatorFilterSTAC
from swiss_locator.core.settings import Settings
from swiss_locator.gui.config_dialog import ConfigDialog
from swiss_locator.gui.welcome_dialog import WELCOME_DIALOG_VERSION, WelcomeDialog
from swiss_locator.swiss_locator_plugin import SwissLocatorPlugin
from swiss_locator.swissgeodownloader.api.catalogs import ApiBaselStadt, ApiViageo
from swiss_locator.swissgeodownloader.api.datageoadmin import ApiDataGeoAdmin

start_app()

GEOADMIN = ApiDataGeoAdmin.CATALOG_ID
VIAGEO = ApiViageo.CATALOG_ID
BASEL = ApiBaselStadt.CATALOG_ID


class SettingsTestCase(unittest.TestCase):
    def setUp(self):
        self.settings = Settings()
        self.tearDown()

    def tearDown(self):
        self.settings.welcome_dialog_version.remove()
        self.settings.stac_local_catalogs.remove()


class TestWelcomeDialog(SettingsTestCase):
    def test_due_until_closed(self):
        self.assertTrue(WelcomeDialog.is_due())
        WelcomeDialog().reject()
        self.assertFalse(WelcomeDialog.is_due())
        # Closed without OK: nothing chosen
        self.assertEqual(self.settings.stac_local_catalogs.value(), [])

    def test_due_again_after_a_bump(self):
        self.settings.welcome_dialog_version.setValue(WELCOME_DIALOG_VERSION - 1)
        self.assertTrue(WelcomeDialog.is_due())

    def test_accept_saves_the_catalogs(self):
        dialog = WelcomeDialog()
        dialog.local_catalogs.check_boxes[BASEL].setChecked(True)
        dialog.accept()
        self.assertEqual(self.settings.stac_local_catalogs.value(), [BASEL])
        self.assertFalse(dialog.open_settings)
        self.assertFalse(WelcomeDialog.is_due())

    def test_shows_the_catalogs_chosen(self):
        self.settings.stac_local_catalogs.setValue([VIAGEO])
        dialog = WelcomeDialog()
        self.assertTrue(dialog.local_catalogs.check_boxes[VIAGEO].isChecked())
        self.assertFalse(dialog.local_catalogs.check_boxes[BASEL].isChecked())

    def test_open_settings(self):
        dialog = WelcomeDialog()
        dialog.local_catalogs.check_boxes[VIAGEO].setChecked(True)
        dialog.accept_and_open_settings()
        self.assertTrue(dialog.open_settings)
        self.assertEqual(self.settings.stac_local_catalogs.value(), [VIAGEO])
        self.assertFalse(WelcomeDialog.is_due())


@mock.patch.object(SwissLocatorFilterSTAC, "fetch_stac_collections")
class TestWelcomeDialogShown(SettingsTestCase):
    def setUp(self):
        super().setUp()
        self.plugin = SwissLocatorPlugin(get_iface())
        # Stands for the plugin manager, which runs modal
        self.plugin_manager = QDialog()
        self.plugin_manager.setModal(True)

    def close_plugin_manager(self):
        self.plugin_manager.reject()
        QCoreApplication.processEvents()

    def test_shown_at_once(self, _):
        self.plugin.show_welcome_dialog()
        self.assertTrue(self.plugin.welcome_dialog.isVisible())
        self.plugin.welcome_dialog.reject()

    def test_waits_for_the_plugin_manager(self, _):
        self.plugin_manager.show()
        self.plugin.show_welcome_dialog()
        self.assertIsNone(self.plugin.welcome_dialog)

        self.close_plugin_manager()
        self.assertTrue(self.plugin.welcome_dialog.isVisible())
        self.plugin.welcome_dialog.reject()

        # Shown once only
        self.plugin_manager.show()
        self.close_plugin_manager()
        self.assertIsNone(self.plugin.welcome_dialog)


class TestConfigDialog(SettingsTestCase):
    def test_local_catalogs(self):
        self.settings.stac_local_catalogs.setValue([BASEL])
        dialog = ConfigDialog()
        self.assertEqual(dialog.local_catalogs.catalog_ids(), [BASEL])
        dialog.local_catalogs.set_catalog_ids([VIAGEO, BASEL])
        dialog.accept()
        self.assertEqual(self.settings.stac_local_catalogs.value(), [VIAGEO, BASEL])


@mock.patch.object(SwissLocatorFilterSTAC, "fetch_stac_collections")
class TestStacFilters(SettingsTestCase):
    def setUp(self):
        super().setUp()
        self.iface = get_iface()
        self.plugin = SwissLocatorPlugin(self.iface)

    def stac_filters(self) -> dict[str, SwissLocatorFilterSTAC]:
        return {
            f.catalog.CATALOG_ID: f
            for f in self.plugin.locator_filters
            if isinstance(f, SwissLocatorFilterSTAC)
        }

    def test_geoadmin_only_by_default(self, _):
        self.plugin.update_stac_filters()
        self.assertEqual(list(self.stac_filters()), [GEOADMIN])

    def test_local_catalogs_chosen(self, _):
        self.plugin.update_stac_filters()
        geoadmin = self.stac_filters()[GEOADMIN]

        self.settings.stac_local_catalogs.setValue([BASEL, VIAGEO])
        self.plugin.update_stac_filters()
        filters = self.stac_filters()
        # In the order of the catalogs, those registered are kept
        self.assertEqual(list(filters), [GEOADMIN, VIAGEO, BASEL])
        self.assertIs(filters[GEOADMIN], geoadmin)

        self.settings.stac_local_catalogs.setValue([VIAGEO])
        self.plugin.update_stac_filters()
        self.assertEqual(list(self.stac_filters()), [GEOADMIN, VIAGEO])
        self.iface.deregisterLocatorFilter.assert_called_once_with(filters[BASEL])

    def test_unknown_catalog(self, _):
        self.settings.stac_local_catalogs.setValue(["unknown"])
        self.plugin.update_stac_filters()
        self.assertEqual(list(self.stac_filters()), [GEOADMIN])


if __name__ == "__main__":
    unittest.main()
