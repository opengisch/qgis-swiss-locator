"""
Requests of the locator filters, sent to local servers.

The locator searches with a clone of each filter, in a thread of its own, and
cancels the search from the main thread each time the text changes. A search
that does not end keeps every following one waiting.
"""

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from qgis.PyQt.QtCore import QCoreApplication, QThread, QTimer, QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import QgsFeedback, QgsNetworkAccessManager
from qgis.testing import start_app, unittest

from swiss_locator.core.filters.filter_type import FilterType
from swiss_locator.core.network import fetch
from swiss_locator.core.filters.swiss_locator_filter import SwissLocatorFilter

start_app()

# Longer than a search should ever take here
GIVE_UP_S = 5


class SilentServer:
    """Accepts connections and never answers. Closing it resets them."""

    def __init__(self):
        self.socket = socket.create_server(("127.0.0.1", 0))
        self.url = QUrl(f"http://127.0.0.1:{self.socket.getsockname()[1]}/")

    def close(self):
        self.socket.close()


class JsonHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        content = json.dumps({"path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *args):
        pass


class FilterThread(QThread):
    """Runs the requests of a filter like the locator: in a thread of its own."""

    def __init__(self, locator_filter, requests, feedback):
        super().__init__()
        self.locator_filter = locator_filter
        self.requests = requests
        self.feedback = feedback
        self.contents = []
        locator_filter.moveToThread(self)

    def run(self):
        self.locator_filter.fetch_requests(
            self.requests,
            self.feedback,
            lambda content, feedback: self.contents.append(content),
        )


def wait_for_thread(thread: QThread, timeout_s: float) -> bool:
    """
    Waits for the thread to be finished, events processed meanwhile. Unlike
    QThread.wait(), without holding the GIL, which the thread can need as it
    ends, to delete objects made in Python.
    """
    end = time.monotonic() + timeout_s
    while not thread.isFinished() and time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)
    return thread.isFinished()


def new_filter():
    return SwissLocatorFilter(FilterType.Location, crs="2056")


class TestFetchRequests(unittest.TestCase):
    def silent_server(self):
        server = SilentServer()
        self.addCleanup(server.close)
        return server

    def fetch_in_main_thread(self, server, feedback):
        """Returns the duration of the requests, cut short by closing the server."""
        give_up = QTimer()
        give_up.setSingleShot(True)
        give_up.timeout.connect(server.close)
        give_up.start(GIVE_UP_S * 1000)
        contents = []
        start = time.monotonic()
        new_filter().fetch_requests(
            [QNetworkRequest(server.url)],
            feedback,
            lambda content, feedback: contents.append(content),
        )
        give_up.stop()
        self.assertEqual(contents, [])
        return time.monotonic() - start

    def run_in_thread(self, thread, server=None):
        """Waits for the thread, the server is closed if it takes too long."""
        start = time.monotonic()
        thread.start()
        if not wait_for_thread(thread, GIVE_UP_S):
            if server is not None:
                server.close()
            wait_for_thread(thread, GIVE_UP_S)
            self.fail(f"The requests did not end within {GIVE_UP_S} s")
        return time.monotonic() - start

    def test_cancelled_before_the_requests(self):
        # The locator cancels the feedback from the main thread: it can happen
        # before the filter is connected to it, the signal is not emitted again.
        # The search waited for every reply, without any timeout.
        server = self.silent_server()
        feedback = QgsFeedback()
        feedback.cancel()
        self.assertLess(self.fetch_in_main_thread(server, feedback), 1)

    def test_reply_never_coming(self):
        # A reply never finished without a cancellation: the locator stayed busy
        self.addCleanup(
            QgsNetworkAccessManager.setTimeout, QgsNetworkAccessManager.timeout()
        )
        QgsNetworkAccessManager.setTimeout(300)
        server = self.silent_server()
        self.assertLess(self.fetch_in_main_thread(server, QgsFeedback()), GIVE_UP_S - 1)

    def test_cancel_from_the_main_thread(self):
        server = self.silent_server()
        feedback = QgsFeedback()
        thread = FilterThread(new_filter(), [QNetworkRequest(server.url)], feedback)
        QTimer.singleShot(300, feedback.cancel)
        self.assertLess(self.run_in_thread(thread, server), 2)
        self.assertEqual(thread.contents, [])

    def json_server(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), JsonHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def test_replies_in_a_filter_thread(self):
        port = self.json_server().server_address[1]
        requests = [
            QNetworkRequest(QUrl(f"http://127.0.0.1:{port}/{i}")) for i in range(5)
        ]
        thread = FilterThread(new_filter(), requests, QgsFeedback())
        self.run_in_thread(thread)
        paths = sorted(json.loads(content)["path"] for content in thread.contents)
        self.assertEqual(paths, [f"/{i}" for i in range(5)])

    def test_unreadable_reply(self):
        # PyQt reports the deletion of an object deleted in a thread later, in
        # the main thread, and invalidates the wrapper at its address: by then
        # the wrapper of a reply created there in another filter thread. The
        # error escaped and the search waited for the reply forever.
        server = self.json_server()
        port = server.server_address[1]
        requests = [
            QNetworkRequest(QUrl(f"http://127.0.0.1:{port}/{i}")) for i in range(3)
        ]
        handled = []

        def handle(index, reply):
            handled.append(index)
            if index == 1:
                raise RuntimeError(
                    "wrapped C/C++ object of type QNetworkReply has been deleted"
                )

        start = time.monotonic()
        with self.assertRaises(RuntimeError):
            fetch(requests, QgsFeedback(), handle)
        self.assertLess(time.monotonic() - start, GIVE_UP_S)
        self.assertEqual(sorted(handled), [0, 1, 2])

    def test_invalidated_reply_in_a_filter(self):
        class InvalidatedReply:
            def error(self):
                raise RuntimeError(
                    "wrapped C/C++ object of type QNetworkReply has been deleted"
                )

        contents = []
        new_filter().handle_reply(
            InvalidatedReply(),
            QgsFeedback(),
            lambda content, feedback: contents.append(content),
        )
        self.assertEqual(contents, [])


if __name__ == "__main__":
    unittest.main()
