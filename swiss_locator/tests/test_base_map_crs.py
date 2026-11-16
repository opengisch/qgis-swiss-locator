"""
The CRS of an empty project to which a base map (EPSG:3857) is added.

Does NOT require network access.
"""

from qgis.PyQt import sip
from qgis.PyQt.QtTest import QSignalSpy
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProject,
    QgsSettings,
    QgsVectorLayer,
)
from qgis.gui import QgsGui, QgsLayerTreeMapCanvasBridge
from qgis.testing import start_app, unittest
from qgis.testing.mocked import get_iface

from swiss_locator.core.filters.swiss_locator_filter_vector_tiles import (
    SwissLocatorFilterVectorTiles,
)

start_app()

NEW_PROJECT_CRS_BEHAVIOR = "projections/newProjectCrsBehavior"


class TestBaseMapCrs(unittest.TestCase):
    def setUp(self):
        self.project = QgsProject.instance()
        self.project.clear()
        self.iface = get_iface()
        self.bridge = QgsLayerTreeMapCanvasBridge(
            self.project.layerTreeRoot(), self.iface.mapCanvas()
        )
        self.iface.layerTreeCanvasBridge.return_value = self.bridge
        self.filter = SwissLocatorFilterVectorTiles(self.iface)

    def tearDown(self):
        QgsSettings().remove(NEW_PROJECT_CRS_BEHAVIOR, QgsSettings.Section.App)
        self.project.clear()
        sip.delete(self.bridge)

    def add_layer_in_3857(self):
        spy = QSignalSpy(self.bridge.canvasLayersChanged)
        layer = QgsVectorLayer("Point?crs=EPSG:3857", "base map", "memory")
        self.project.addMapLayer(layer)
        self.assertTrue(spy.wait(5000))

    def test_qgis_takes_crs_of_first_layer(self):
        self.add_layer_in_3857()
        self.assertEqual(self.project.crs().authid(), "EPSG:3857")

    def test_project_kept_in_lv95(self):
        self.filter.keep_swiss_crs_in_empty_project()
        self.add_layer_in_3857()
        self.assertEqual(self.project.crs().authid(), "EPSG:2056")

    def test_crs_set_once(self):
        self.filter.keep_swiss_crs_in_empty_project()
        self.add_layer_in_3857()
        self.project.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        spy = QSignalSpy(self.bridge.canvasLayersChanged)
        self.project.addMapLayer(QgsVectorLayer("Point", "other", "memory"))
        self.assertTrue(spy.wait(5000))
        self.assertEqual(self.project.crs().authid(), "EPSG:4326")

    def test_crs_for_new_projects_respected(self):
        QgsSettings().setEnumValue(
            NEW_PROJECT_CRS_BEHAVIOR,
            QgsGui.ProjectCrsBehavior.UsePresetCrs,
            QgsSettings.Section.App,
        )
        self.project.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        self.filter.keep_swiss_crs_in_empty_project()
        self.add_layer_in_3857()
        self.assertEqual(self.project.crs().authid(), "EPSG:4326")


if __name__ == "__main__":
    unittest.main()
