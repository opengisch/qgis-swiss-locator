"""
Tests of the elevation profile generator against a local HTTP server standing
in for the geo.admin.ch profile service: no access to the real one.
"""

import json
import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsLineString,
    QgsPoint,
    QgsProfileGenerationContext,
    QgsProfileRequest,
    QgsProject,
)
from qgis.testing import start_app, unittest

from swiss_locator.core.profiles.profile_generator import (
    SwissProfileGenerator,
    api_error_message,
    points_for_piece,
    spacing_for,
    split_line,
)

start_app()

PROFILE = [
    {
        "alts": {"COMB": 500.0, "DTM2": 500.0, "DTM25": 500.0},
        "dist": 0,
        "easting": 2600000.0,
        "northing": 1200000.0,
    },
    {
        "alts": {"COMB": 510.0, "DTM2": 510.0, "DTM25": 510.0},
        "dist": 10.0,
        "easting": 2600010.0,
        "northing": 1200000.0,
    },
]

TOO_MANY_POINTS = {
    "error": {
        "code": 413,
        "message": "Request Geometry contains too many points. "
        "Maximum number of points allowed: 5000, found 6000",
    },
    "success": False,
}


def profile_of(line):
    """What the profile service answers for a line of many vertices: a point
    on each vertex, with its distance from the start of the line."""
    coordinates = json.loads(line)["coordinates"]
    points = []
    dist = 0.0
    for i, (x, y) in enumerate(coordinates):
        if i:
            dist += math.dist(coordinates[i - 1], (x, y))
        alt = round(500 + (x - 2600000) / 100, 1)
        points.append(
            {
                "alts": {"COMB": alt, "DTM2": alt, "DTM25": alt},
                "dist": round(dist, 1),
                "easting": x,
                "northing": y,
            }
        )
    return points


class FakeProfileService(BaseHTTPRequestHandler):
    """Records the requests and answers like the profile service: with body,
    or with the profile of the line posted if body is None."""

    requests = []
    status = 200
    body = PROFILE

    def _answer(self):
        length = int(self.headers.get("Content-Length") or 0)
        request = {
            "method": self.command,
            "path": self.path,
            "content_type": self.headers.get("Content-Type"),
            "body": self.rfile.read(length),
        }
        FakeProfileService.requests.append(request)
        body = FakeProfileService.body
        if body is None:
            body = profile_of(request["body"])
        content = json.dumps(body).encode()
        self.send_response(FakeProfileService.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    do_GET = _answer
    do_POST = _answer

    def log_message(self, *args):
        pass


def long_line(vertices=300):
    """A line in LV95 whose GeoJSON is far over the 4 KB the profile service
    accepts in a request line, like the trail of issue #205."""
    return QgsLineString(
        [QgsPoint(2600000 + i * 1.5, 1200000 + (i % 7) * 2.25) for i in range(vertices)]
    )


def straight_line(length, vertices=2):
    """A straight line in LV95, of evenly spaced vertices."""
    step = length / (vertices - 1)
    return QgsLineString(
        [QgsPoint(2600000 + i * step, 1200000) for i in range(vertices)]
    )


def nb_points_asked(requests):
    return [int(parse_qs(urlparse(r["path"]).query)["nb_points"][0]) for r in requests]


class TestProfileGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeProfileService)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = (
            f"http://127.0.0.1:{cls.server.server_port}/rest/services/profile.json"
        )

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeProfileService.requests = []
        FakeProfileService.status = 200
        FakeProfileService.body = PROFILE
        patcher = patch("swiss_locator.core.profiles.profile_url.PROFILE_URL", self.url)
        patcher.start()
        self.addCleanup(patcher.stop)

    def generate(self, line):
        request = QgsProfileRequest(line)
        request.setCrs(QgsCoordinateReferenceSystem("EPSG:2056"))
        request.setTransformContext(QgsProject.instance().transformContext())
        generator = SwissProfileGenerator(request)
        ok = generator.generateProfile(QgsProfileGenerationContext())
        return ok, generator.takeResults()

    def test_long_line_is_posted(self):
        line = long_line()
        ok, results = self.generate(line.clone())

        self.assertTrue(ok)
        self.assertEqual(len(FakeProfileService.requests), 1)
        sent = FakeProfileService.requests[0]
        self.assertEqual(sent["method"], "POST")
        self.assertEqual(sent["content_type"], "application/json")
        self.assertEqual(
            json.loads(sent["body"])["coordinates"],
            [[p.x(), p.y()] for p in line.points()],
        )
        query = parse_qs(urlparse(sent["path"]).query)
        self.assertEqual(query["sr"], ["2056"])
        # A point every 2 m, the grid of the heights of the service
        self.assertEqual(query["nb_points"], [str(math.ceil(line.length() / 2) + 1)])
        self.assertEqual(query["distinct_points"], ["true"])
        self.assertNotIn("geom", query)

        self.assertEqual([p.z() for p in results.raw_points], [500.0, 510.0])
        self.assertEqual(results.min_z, 500.0)
        self.assertEqual(results.max_z, 510.0)

    def test_line_over_the_vertex_limit_is_split(self):
        FakeProfileService.body = None
        line = straight_line(11999, vertices=12000)
        ok, results = self.generate(line.clone())

        self.assertTrue(ok)
        requests = FakeProfileService.requests
        pieces = [json.loads(r["body"])["coordinates"] for r in requests]
        self.assertEqual([len(piece) for piece in pieces], [5000, 5000, 2002])
        for previous, piece in zip(pieces, pieces[1:]):
            self.assertEqual(previous[-1], piece[0])
        self.assertEqual(nb_points_asked(requests), [2501, 2501, 1002])

        # One point per vertex, without the doubled ends of the pieces, and
        # distances running on from one piece to the next
        self.assertEqual(
            [(p.x(), p.y()) for p in results.raw_points],
            [(p.x(), p.y()) for p in line.points()],
        )
        distances = [
            g.constGet().x() for g in results.ellipsoidal_cross_section_geometries
        ]
        self.assertTrue(all(a < b for a, b in zip(distances, distances[1:])))
        self.assertAlmostEqual(distances[-1], line.length(), delta=0.1)

    def test_line_over_10_km_is_split(self):
        FakeProfileService.body = None
        ok, results = self.generate(straight_line(25000))

        self.assertTrue(ok)
        requests = FakeProfileService.requests
        x = 2600000
        self.assertEqual(
            [json.loads(r["body"])["coordinates"] for r in requests],
            [
                [[x, 1200000], [x + 9998, 1200000]],
                [[x + 9998, 1200000], [x + 19996, 1200000]],
                [[x + 19996, 1200000], [x + 25000, 1200000]],
            ],
        )
        self.assertEqual(nb_points_asked(requests), [5000, 5000, 2503])
        self.assertEqual(
            [g.constGet().x() for g in results.ellipsoidal_cross_section_geometries],
            [0, 9998, 19996, 25000],
        )

    def test_line_over_100_km_takes_10_requests(self):
        FakeProfileService.body = None
        ok, _ = self.generate(straight_line(150000))

        self.assertTrue(ok)
        self.assertEqual(nb_points_asked(FakeProfileService.requests), [5000] * 10)

    def test_refusal_reason_is_logged(self):
        FakeProfileService.status = 413
        FakeProfileService.body = TOO_MANY_POINTS

        with patch(
            "swiss_locator.core.profiles.profile_generator.QgsMessageLog"
        ) as log:
            ok, _ = self.generate(long_line())

        self.assertFalse(ok)
        message = log.logMessage.call_args[0][0]
        self.assertIn("Maximum number of points allowed: 5000", message)
        self.assertIn("status code: 413", message)


class TestSplitLine(unittest.TestCase):
    def test_line_under_the_limit_is_one_piece(self):
        coordinates = [[i, 0] for i in range(5000)]
        self.assertEqual(split_line(coordinates), [coordinates])

    def test_pieces_start_where_the_previous_ends(self):
        coordinates = [[i, 0] for i in range(7)]
        self.assertEqual(
            split_line(coordinates, max_vertices=3),
            [coordinates[0:3], coordinates[2:5], coordinates[4:7]],
        )

    def test_one_vertex_over_the_limit(self):
        coordinates = [[i, 0] for i in range(5001)]
        self.assertEqual([len(p) for p in split_line(coordinates)], [5000, 2])

    def test_long_segment_is_cut(self):
        self.assertEqual(
            split_line([[0, 0], [25, 0]], max_length=10),
            [[[0, 0], [10, 0]], [[10, 0], [20, 0]], [[20, 0], [25, 0]]],
        )

    def test_cut_between_vertices(self):
        self.assertEqual(
            split_line([[0, 0], [6, 0], [12, 0], [18, 0]], max_length=10),
            [[[0, 0], [6, 0], [10, 0]], [[10, 0], [12, 0], [18, 0]]],
        )

    def test_vertex_on_the_cut(self):
        self.assertEqual(
            split_line([[0, 0], [10, 0], [15, 0]], max_length=10),
            [[[0, 0], [10, 0]], [[10, 0], [15, 0]]],
        )

    def test_both_limits(self):
        self.assertEqual(
            split_line(
                [[0, 0], [1, 0], [2, 0], [30, 0]], max_vertices=3, max_length=10
            ),
            [
                [[0, 0], [1, 0], [2, 0]],
                [[2, 0], [12, 0]],
                [[12, 0], [22, 0]],
                [[22, 0], [30, 0]],
            ],
        )


class TestPointsForPiece(unittest.TestCase):
    def test_a_point_every_2_m(self):
        self.assertEqual(points_for_piece(100, 2), 51)

    def test_longest_piece(self):
        self.assertEqual(points_for_piece(4999 * 2, 2), 5000)

    def test_at_most_what_the_service_accepts(self):
        self.assertEqual(points_for_piece(20000, 2), 5000)

    def test_at_least_the_ends(self):
        self.assertEqual(points_for_piece(1, 2), 2)
        self.assertEqual(points_for_piece(0, 2), 2)


class TestSpacingFor(unittest.TestCase):
    def test_2_m_up_to_100_km(self):
        self.assertEqual(spacing_for(1000), 2)
        self.assertEqual(spacing_for(10 * 4999 * 2), 2)

    def test_further_apart_over_100_km(self):
        self.assertAlmostEqual(spacing_for(10 * 4999 * 3), 3)


class TestApiErrorMessage(unittest.TestCase):
    def test_message(self):
        content = json.dumps(TOO_MANY_POINTS).encode()
        self.assertEqual(
            api_error_message(content), TOO_MANY_POINTS["error"]["message"]
        )

    def test_not_json(self):
        self.assertIsNone(api_error_message(b"<html>Bad Request</html>"))

    def test_empty(self):
        self.assertIsNone(api_error_message(b""))

    def test_other_json(self):
        self.assertIsNone(api_error_message(b'{"error": "nope"}'))
        self.assertIsNone(api_error_message(b"[]"))


if __name__ == "__main__":
    unittest.main()
