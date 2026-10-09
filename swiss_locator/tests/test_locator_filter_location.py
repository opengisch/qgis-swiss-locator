"""
/***************************************************************************

                            QGIS Swiss Locator Plugin

                             -------------------
        begin                : 2026-10-08
        copyright            : (C) 2026 by Tristan Carel
        email                : tristan.carel@protonmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

# Unit tests for the location filter.
#
# These tests do NOT require network access: the network entry point of the
# geocoder is replaced by canned SearchServer responses.

import json
from unittest.mock import patch

from qgis.PyQt.QtCore import QUrlQuery
from qgis.core import QgsFeedback, QgsLocatorContext
from qgis.testing import start_app, unittest

from swiss_locator.core.filters.swiss_locator_filter_location import (
    SwissLocatorFilterLocation,
)
from swiss_locator.core.geocoder.swiss_geocoder import (
    GeocoderRequestError,
    SwissGeocoder,
)
from swiss_locator.core.results import LocationResult, result_from_data
from swiss_locator.tests.test_geocoder import (
    EMPTY_RESPONSE,
    WABERN_EASTING,
    WABERN_LABEL,
    WABERN_NORTHING,
    WABERN_RESPONSE,
    make_result,
)

# A municipality, whose bounding box is a real extent
KOENIZ = make_result(
    "<b>Köniz (BE)</b>",
    "koeniz be",
    2599000,
    1195000,
    origin="gg25",
    geom_st_box2d="BOX(2592000 1189000,2606000 1201000)",
)

start_app()


class TestLocatorFilterLocation(unittest.TestCase):
    def search(self, text, response, crs="2056"):
        """Runs a search with a canned response, returns (results, requests)."""
        # No iface: the filter behaves as the clone used by the locator thread
        locator_filter = SwissLocatorFilterLocation(crs=crs)
        results = []
        locator_filter.resultFetched.connect(results.append)
        requests = []

        def fetch(request, feedback=None):
            requests.append(dict(QUrlQuery(request.url()).queryItems()))
            if isinstance(response, Exception):
                raise response
            return response

        with patch.object(SwissGeocoder, "fetch_json", side_effect=fetch):
            locator_filter.fetchResults(text, QgsLocatorContext(), QgsFeedback())
        return results, requests

    def test_request(self):
        results, requests = self.search("Seftigenstrasse 264", WABERN_RESPONSE)
        self.assertEqual(len(requests), 1)
        params = requests[0]
        self.assertEqual(params["searchText"], "Seftigenstrasse 264")
        self.assertEqual(params["type"], "locations")
        self.assertEqual(params["sr"], "2056")
        self.assertEqual(params["limit"], "8")
        # All kinds of locations are searched
        self.assertNotIn("origins", params)

    def test_location_result(self):
        results, requests = self.search("Seftigenstrasse 264", WABERN_RESPONSE)
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.displayString, "Seftigenstrasse 264 3084 Wabern")
        self.assertEqual(result.group, "Address")
        self.assertFalse(result.icon.isNull())

        location = result_from_data(result.userData)
        self.assertIsInstance(location, LocationResult)
        self.assertAlmostEqual(location.point.x(), WABERN_EASTING, places=3)
        self.assertAlmostEqual(location.point.y(), WABERN_NORTHING, places=3)
        self.assertEqual(location.layer, "ch.bfs.gebaeude_wohnungs_register")
        self.assertEqual(location.feature_id, "1272199_0")
        self.assertEqual(location.html_label, WABERN_LABEL)

    def test_municipality_result(self):
        results, requests = self.search("Köniz", {"results": [KOENIZ]})
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.displayString, "Köniz (BE)")
        self.assertEqual(result.group, "Municipal boundaries")
        location = result_from_data(result.userData)
        self.assertEqual(
            location.layer, "ch.swisstopo.swissboundaries3d-gemeinde-flaeche.fill"
        )
        self.assertEqual(location.bbox.xMinimum(), 2592000)
        self.assertEqual(location.bbox.yMaximum(), 1201000)
        self.assertEqual(location.html_label, "<b>Köniz (BE)</b>")

    def test_no_result(self):
        results, requests = self.search("xyzzy", EMPTY_RESPONSE)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].displayString, "No result found.")
        self.assertEqual(json.loads(results[0].userData)["type"], "NoResult")

    def test_request_error(self):
        error = GeocoderRequestError("Service unavailable (HTTP 503)", 503)
        results, requests = self.search("Bern", error)
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].displayString, "No result found.")

    def test_short_search(self):
        results, requests = self.search("B", WABERN_RESPONSE)
        self.assertEqual(requests, [])
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
