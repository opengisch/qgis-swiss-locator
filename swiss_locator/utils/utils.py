from qgis.PyQt.QtCore import QUrl, QUrlQuery


def url_with_param(url: str, params: dict) -> str:
    url = QUrl(url)
    q = QUrlQuery(url)
    for key, value in params.items():
        q.addQueryItem(key, value)
    url.setQuery(q)
    return url
