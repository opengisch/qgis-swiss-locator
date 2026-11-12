"""
Unit tests for swiss_locator.remote_data: format of the published files, local
copies, cache updates. The updates are tested against a local HTTP server.
"""

import json
import os
import tempfile
import threading
from datetime import datetime, timedelta, UTC
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from qgis.PyQt.QtTest import QSignalSpy
from qgis.testing import start_app, unittest

from swiss_locator.remote_data import spec
from swiss_locator.remote_data.remote_data_file import RemoteDataFile

start_app()

FILE_NAME = "test_data.json"
OLD = "2026-01-01T00:00:00Z"
NEW = "2026-06-01T00:00:00Z"


def _write(folder, document):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, FILE_NAME), "w", encoding="utf-8") as f:
        f.write(document if isinstance(document, str) else json.dumps(document))


def _timestamp(age: timedelta) -> str:
    return (datetime.now(UTC) - age).strftime(spec.TIMESTAMP_FORMAT)


class TestSpec(unittest.TestCase):
    def test_wrap_unwrap(self):
        generated, data = spec.unwrap(spec.wrap({"a": 1}, OLD))
        self.assertEqual(generated, OLD)
        self.assertEqual(data, {"a": 1})

    def test_wrap_sets_current_time(self):
        self.assertGreater(spec.wrap([])["generated"], OLD)

    def test_unwrap_invalid(self):
        for document in (
            [],
            {"version": spec.FORMAT_VERSION + 1, "generated": OLD, "data": {}},
            {"version": spec.FORMAT_VERSION, "data": {}},
            {"version": spec.FORMAT_VERSION, "generated": OLD},
        ):
            with self.subTest(document=document):
                with self.assertRaises(spec.InvalidDataFile):
                    spec.unwrap(document)

    def test_urls(self):
        self.assertEqual(
            spec.url(spec.MAP_GEO_ADMIN_LAYERS),
            f"{spec.BASE_URL}/{spec.MAP_GEO_ADMIN_LAYERS}",
        )
        self.assertTrue(spec.BASE_URL.endswith(f"/data/v{spec.FORMAT_VERSION}"))


class RemoteDataFileTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache_dir = os.path.join(self.tmp.name, "cache")
        self.bundled_dir = os.path.join(self.tmp.name, "bundled")

    def tearDown(self):
        self.tmp.cleanup()

    def remote_file(self, url="http://127.0.0.1:9/unused", **kwargs):
        return RemoteDataFile(
            FILE_NAME,
            cache_dir=self.cache_dir,
            bundled_dir=self.bundled_dir,
            url=url,
            **kwargs,
        )


class TestLocalCopies(RemoteDataFileTestCase):
    def test_no_copy(self):
        self.assertIsNone(self.remote_file().data())

    def test_bundled_copy(self):
        _write(self.bundled_dir, spec.wrap("bundled", OLD))
        self.assertEqual(self.remote_file().data(), "bundled")

    def test_fresher_cache_wins(self):
        _write(self.bundled_dir, spec.wrap("bundled", OLD))
        _write(self.cache_dir, spec.wrap("cache", NEW))
        remote_file = self.remote_file()
        self.assertEqual(remote_file.data(), "cache")
        self.assertEqual(remote_file.generated, NEW)

    def test_fresher_bundled_copy_wins(self):
        """The cache of an older plugin release must not shadow a newer bundle."""
        _write(self.bundled_dir, spec.wrap("bundled", NEW))
        _write(self.cache_dir, spec.wrap("cache", OLD))
        self.assertEqual(self.remote_file().data(), "bundled")

    def test_invalid_cache_is_ignored(self):
        _write(self.bundled_dir, spec.wrap("bundled", OLD))
        for invalid in ("{not json", json.dumps({"data": "no version"})):
            with self.subTest(invalid=invalid):
                _write(self.cache_dir, invalid)
                self.assertEqual(self.remote_file().data(), "bundled")

    def test_parse(self):
        _write(self.bundled_dir, spec.wrap([1, 2], OLD))
        self.assertEqual(self.remote_file(parse=sum).data(), 3)

    def test_parse_failure_invalidates_copy(self):
        def parse(data):
            if data == "bad":
                raise spec.InvalidDataFile("bad")
            return data

        _write(self.bundled_dir, spec.wrap("good", OLD))
        _write(self.cache_dir, spec.wrap("bad", NEW))
        self.assertEqual(self.remote_file(parse=parse).data(), "good")

    def test_set_document(self):
        _write(self.bundled_dir, spec.wrap("bundled", NEW))
        remote_file = self.remote_file()
        remote_file.set_document(spec.wrap("forced", OLD))
        self.assertEqual(remote_file.data(), "forced")


class TestProcessDownload(RemoteDataFileTestCase):
    def test_valid_download_is_used_and_cached(self):
        _write(self.bundled_dir, spec.wrap("bundled", OLD))
        remote_file = self.remote_file()
        content = json.dumps(spec.wrap("downloaded", NEW)).encode()
        self.assertTrue(remote_file.process_download(content, etag='"abc"'))
        self.assertEqual(remote_file.data(), "downloaded")
        # persisted for the next session
        self.assertEqual(self.remote_file().data(), "downloaded")
        with open(os.path.join(self.cache_dir, f"{FILE_NAME}.meta.json")) as f:
            self.assertEqual(json.load(f)["etag"], '"abc"')

    def test_invalid_download_is_ignored(self):
        _write(self.cache_dir, spec.wrap("cache", OLD))
        remote_file = self.remote_file()
        for content in (b"<html>GitHub is down</html>", b'{"version": 999}'):
            with self.subTest(content=content):
                self.assertFalse(remote_file.process_download(content))
                self.assertEqual(remote_file.data(), "cache")
        self.assertEqual(self.remote_file().data(), "cache")

    def test_older_download_is_ignored(self):
        _write(self.bundled_dir, spec.wrap("bundled", NEW))
        remote_file = self.remote_file()
        content = json.dumps(spec.wrap("downloaded", OLD)).encode()
        self.assertFalse(remote_file.process_download(content))
        self.assertEqual(remote_file.data(), "bundled")
        self.assertFalse(os.path.exists(os.path.join(self.cache_dir, FILE_NAME)))


class TestOutdated(RemoteDataFileTestCase):
    def test_is_outdated(self):
        remote_file = self.remote_file(max_age=timedelta(days=1))
        for meta, outdated in (
            ({}, True),
            ({"checked": "garbage"}, True),
            ({"checked": _timestamp(timedelta(hours=1))}, False),
            ({"checked": _timestamp(timedelta(days=2))}, True),
            ({"checked": _timestamp(-timedelta(days=1))}, True),
        ):
            with self.subTest(meta=meta):
                self.assertEqual(remote_file._is_outdated(meta), outdated)


class _Server:
    """Local HTTP server serving one document, with ETag support."""

    def __init__(self):
        self.status = 200
        self.content = b""
        self.etag = '"v1"'
        self.requests = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                server.requests.append(dict(self.headers))
                if server.status != 200:
                    self.send_response(server.status)
                    self.end_headers()
                elif self.headers.get("If-None-Match") == server.etag:
                    self.send_response(304)
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.send_header("ETag", server.etag)
                    self.send_header("Content-Length", str(len(server.content)))
                    self.end_headers()
                    self.wfile.write(server.content)

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/{FILE_NAME}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class TestRefresh(RemoteDataFileTestCase):
    def setUp(self):
        super().setUp()
        self.server = _Server()
        self.server.content = json.dumps(spec.wrap("published", NEW)).encode()

    def tearDown(self):
        self.server.stop()
        super().tearDown()

    def refresh(self, remote_file, force=False):
        reply = remote_file.refresh(force=force)
        if reply is not None:
            spy = QSignalSpy(reply.finished)
            self.assertTrue(spy.wait(10000))
        return reply

    def test_download_then_not_modified(self):
        _write(self.bundled_dir, spec.wrap("bundled", OLD))
        remote_file = self.remote_file(url=self.server.url)

        self.assertIsNotNone(self.refresh(remote_file))
        self.assertEqual(remote_file.data(), "published")
        self.assertNotIn("If-None-Match", self.server.requests[0])

        # checked recently: no request
        self.assertIsNone(self.refresh(remote_file))
        self.assertEqual(len(self.server.requests), 1)

        # next session, forced: conditional request answered with 304
        remote_file = self.remote_file(url=self.server.url)
        self.refresh(remote_file, force=True)
        self.assertEqual(self.server.requests[1].get("If-None-Match"), '"v1"')
        self.assertEqual(remote_file.data(), "published")

    def test_new_version(self):
        remote_file = self.remote_file(url=self.server.url)
        self.refresh(remote_file)
        self.server.content = json.dumps(
            spec.wrap("newer", "2026-07-01T00:00:00Z")
        ).encode()
        self.server.etag = '"v2"'
        self.refresh(remote_file, force=True)
        self.assertEqual(remote_file.data(), "newer")

    def test_server_error_keeps_local_copy(self):
        _write(self.bundled_dir, spec.wrap("bundled", OLD))
        self.server.status = 503
        remote_file = self.remote_file(url=self.server.url)
        self.refresh(remote_file)
        self.assertEqual(remote_file.data(), "bundled")
        # retried at the next session, as the check was not recorded
        self.assertIsNotNone(self.refresh(self.remote_file(url=self.server.url)))

    def test_unreachable_server_keeps_local_copy(self):
        _write(self.bundled_dir, spec.wrap("bundled", OLD))
        self.server.stop()
        remote_file = self.remote_file(url=self.server.url)
        self.refresh(remote_file)
        self.assertEqual(remote_file.data(), "bundled")
        self.server = _Server()  # for tearDown

    def test_no_conditional_request_without_valid_cache(self):
        """A 304 would leave the plugin with an invalid cache."""
        _write(self.cache_dir, "{corrupted")
        with open(os.path.join(self.cache_dir, f"{FILE_NAME}.meta.json"), "w") as f:
            json.dump({"etag": '"v1"'}, f)
        remote_file = self.remote_file(url=self.server.url)
        self.refresh(remote_file)
        self.assertNotIn("If-None-Match", self.server.requests[0])
        self.assertEqual(remote_file.data(), "published")


if __name__ == "__main__":
    unittest.main()
