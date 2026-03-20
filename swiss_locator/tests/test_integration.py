"""
Integration tests for Swiss Locator filters.

These tests exercise the full QGIS QgsLocator pipeline: filter registration,
network requests, signal emission, and result collection.  They require a
running X server (or xvfb) and network access.
"""

from qgis.PyQt.QtTest import QSignalSpy
from qgis.core import QgsLocator, QgsLocatorContext
from qgis.testing import start_app, unittest
from qgis.testing.mocked import get_iface

from swiss_locator.core.filters.swiss_locator_filter_layer import (
    SwissLocatorFilterLayer,
)
from swiss_locator.core.filters.swiss_locator_filter_wmts import (
    SwissLocatorFilterWMTS,
)

start_app()


class TestLocatorFilterWMTS(unittest.TestCase):
    """Integration test for the WMTS locator filter."""

    def test_wmts_pixelkarte(self):
        results = []

        def got_hit(result):
            results.append(result.displayString)

        loc = QgsLocator()
        _filter = SwissLocatorFilterWMTS(get_iface())
        loc.registerFilter(_filter)
        loc.foundResult.connect(got_hit)

        spy = QSignalSpy(loc.foundResult)
        loc.fetchResults("pixelkarte-farbe", QgsLocatorContext())
        spy.wait(10000)

        self.assertTrue(
            len(results) > 0, "Expected at least one WMTS result for 'pixelkarte-farbe'"
        )
        self.assertTrue(results[0].startswith("National Map"))


class TestLocatorFilterLayer(unittest.TestCase):
    """Integration test for the Layer locator filter (geo.admin + opendata.swiss)."""

    def _run_layer_search(self, search, timeout=30000):
        """Helper: run a layer search through QgsLocator and return (display, description, group) tuples."""
        results = []

        def got_hit(result):
            results.append((result.displayString, result.description, result.group))

        loc = QgsLocator()
        _filter = SwissLocatorFilterLayer(get_iface())
        loc.registerFilter(_filter)
        loc.foundResult.connect(got_hit)

        # Wait for `finished` (emitted when fetchResults returns), not
        # `foundResult` – the latter fires on the first hit, which may arrive
        # before the opendata.swiss pipeline has completed.
        spy = QSignalSpy(loc.finished)
        loc.fetchResults(search, QgsLocatorContext())
        spy.wait(timeout)

        return results

    # -- geo.admin.ch results ------------------------------------------------

    def test_geoadmin_search(self):
        """Searching 'pixelkarte' should return geo.admin layers."""
        results = self._run_layer_search("pixelkarte")
        geoadmin = [r for r in results if r[2] == "Swiss Geoportal"]
        self.assertGreater(
            len(geoadmin),
            0,
            f"Expected geo.admin results for 'pixelkarte', got: {results}",
        )

    # -- opendata.swiss results via GetCapabilities --------------------------

    def test_opendata_swiss_layer_asiat(self):
        """'asiat' should return opendata.swiss layers (Asiatische Hornisse)."""
        results = self._run_layer_search("asiat")
        opendata = [r for r in results if r[2] == "opendata.swiss"]
        self.assertGreater(
            len(opendata),
            0,
            f"Expected opendata.swiss results for 'asiat', got all: {results}",
        )

    def test_opendata_swiss_layer_asia(self):
        """'asia' (partial word) should also return opendata.swiss layers."""
        results = self._run_layer_search("asia")
        opendata = [r for r in results if r[2] == "opendata.swiss"]
        self.assertGreater(
            len(opendata),
            0,
            f"Expected opendata.swiss results for 'asia', got all: {results}",
        )

    def test_opendata_swiss_layer_wasser(self):
        """'wasser' should return opendata.swiss WMS layers."""
        results = self._run_layer_search("wasser")
        opendata = [r for r in results if r[2] == "opendata.swiss"]
        self.assertGreater(
            len(opendata),
            0,
            f"Expected opendata.swiss results for 'wasser', got all: {results}",
        )

    def test_no_result_for_gibberish(self):
        """A nonsense query should return 'No result found.'."""
        results = self._run_layer_search("xyzzy12345zzz")
        self.assertTrue(
            any("No result" in r[0] for r in results),
            f"Expected 'No result found.' for gibberish, got: {results}",
        )


if __name__ == "__main__":
    unittest.main()
