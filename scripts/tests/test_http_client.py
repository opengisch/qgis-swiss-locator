"""Unit tests of the HTTP client, without network."""

import io
import unittest
import urllib.error
from unittest import mock

from scripts import http_client


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class TestGet(unittest.TestCase):
    def get(self, url, responses, **kwargs):
        """Call get() with urlopen answering the given responses in turn."""
        requested = []

        def urlopen(request, timeout):
            requested.append(request.full_url)
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return FakeResponse(response)

        with (
            mock.patch.object(http_client.urllib.request, "urlopen", urlopen),
            mock.patch.object(http_client.time, "sleep"),
        ):
            return http_client.get(url, **kwargs), requested

    @staticmethod
    def http_error(code):
        return urllib.error.HTTPError("u", code, "error", {}, None)

    def test_non_ascii_url_is_encoded(self):
        content, requested = self.get(
            "https://maps.fr.ch/ags/Nœuds_–_routes/WMSServer?a=%2F&b=ü", [b"ok"]
        )
        self.assertEqual(content, b"ok")
        self.assertEqual(
            requested,
            [
                "https://maps.fr.ch/ags/N%C5%93uds_%E2%80%93_routes/WMSServer"
                "?a=%2F&b=%C3%BC"
            ],
        )

    def test_params(self):
        _, requested = self.get("https://a.ch/wms?x=1", [b""], params={"y": "2 3"})
        self.assertEqual(requested, ["https://a.ch/wms?x=1&y=2+3"])

    def test_server_errors_are_retried(self):
        content, requested = self.get(
            "https://a.ch", [self.http_error(503), OSError("reset"), b"ok"]
        )
        self.assertEqual(content, b"ok")
        self.assertEqual(len(requested), 3)

    def test_client_errors_are_not_retried(self):
        with self.assertRaises(http_client.HttpError) as context:
            self.get("https://a.ch", [self.http_error(404)])
        self.assertEqual(context.exception.status, 404)
        self.assertEqual(context.exception.reason, "HTTP error 404")

    def test_unreachable(self):
        with self.assertRaises(http_client.HttpError) as context:
            self.get("https://a.ch", [OSError("refused")] * 3)
        self.assertEqual(context.exception.reason, "unreachable")
        self.assertIsNone(context.exception.status)

    def test_too_large(self):
        with self.assertRaises(http_client.HttpError) as context:
            self.get("https://a.ch", [b"12345"], max_bytes=4)
        self.assertEqual(context.exception.reason, "too large")


if __name__ == "__main__":
    unittest.main()
