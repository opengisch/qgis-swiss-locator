import os
import tempfile
import unittest
from unittest import mock

from qgis.PyQt.QtCore import QEventLoop, QTimer
from qgis.core import QgsTask
from qgis.testing import start_app

from swiss_locator.swissgeodownloader.api import network_request
from swiss_locator.swissgeodownloader.api.network_request import fetchFile

start_app()


class Task(QgsTask):
    def __init__(self):
        super().__init__("download")
        self.exception = None

    def run(self):
        return True


class BoundedEventLoop(QEventLoop):
    """Quits after 10 s, so that a download waiting forever fails the test
    instead of hanging it"""

    timedOut = False

    def exec(self, *args):
        def timeout():
            BoundedEventLoop.timedOut = True
            self.quit()

        QTimer.singleShot(10000, timeout)
        return super().exec(*args)


class TestFetchFile(unittest.TestCase):
    def test_failed_download_raises(self):
        """A file that cannot be downloaded, e.g. one that needs a login on
        geodienste.ch, ends the download task instead of blocking it"""
        BoundedEventLoop.timedOut = False
        task = Task()
        with (
            tempfile.TemporaryDirectory() as folder,
            mock.patch.object(network_request, "QEventLoop", BoundedEventLoop),
        ):
            path = os.path.join(folder, "file.zip")
            with self.assertRaises(Exception):
                # Nothing listens there: the connection is refused
                fetchFile(task, "http://127.0.0.1:9/file.zip", "file.zip", path, 100)
            self.assertFalse(os.path.exists(path))
        self.assertFalse(BoundedEventLoop.timedOut)
        self.assertIn("file.zip", task.exception)


if __name__ == "__main__":
    unittest.main()
