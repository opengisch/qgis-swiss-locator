import os
import re

from qgis.PyQt.QtCore import QUrl, QUrlQuery
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.core import QgsRectangle

from swiss_locator import PLUGIN_PATH

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


class InvalidBox(Exception):
    pass


def box2geometry(box: str) -> QgsRectangle:
    """
    Creates a rectangle from a Box definition as string,
    e.g. "BOX(2600968.668 1197426.954,2600968.668 1197426.954)"
    :param box: the box as a string
    :return: the rectangle
    :raises InvalidBox: when the string does not hold four coordinates
    """
    coords = _NUMBER.findall(box or "")
    if len(coords) != 4:
        raise InvalidBox(f"Could not parse: {box}")
    return QgsRectangle(
        float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3])
    )


def url_with_param(url: str, params: dict) -> QUrl:
    url = QUrl(url)
    q = QUrlQuery(url)
    for key, value in params.items():
        q.addQueryItem(key, value)
    url.setQuery(q)
    return url


def get_save_location(prompt: str = "Choose download location", open_dir: str = None):
    if not open_dir:
        open_dir = os.path.expanduser("~")
    path = QFileDialog.getExistingDirectory(
        None, prompt, open_dir, QFileDialog.Option.ShowDirsOnly
    )
    return path


def get_icon_path(icon_file_name: str) -> str:
    return os.path.join(PLUGIN_PATH, "icons", icon_file_name)
