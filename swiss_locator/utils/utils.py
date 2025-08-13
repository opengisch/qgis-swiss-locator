import os

from qgis.PyQt.QtCore import QUrl, QUrlQuery
from qgis.PyQt.QtWidgets import QFileDialog


def url_with_param(url: str, params: dict) -> QUrl:
    url = QUrl(url)
    q = QUrlQuery(url)
    for key, value in params.items():
        q.addQueryItem(key, value)
    url.setQuery(q)
    return url


def get_save_location(prompt: str = "Choose download location",
                      open_dir: str = None):
    if not open_dir:
        open_dir = os.path.expanduser('~')
    path = QFileDialog.getExistingDirectory(None, prompt, open_dir,
                                            QFileDialog.Option.ShowDirsOnly)
    return path
