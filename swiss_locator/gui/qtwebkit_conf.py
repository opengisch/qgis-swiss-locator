_WITH_QTWEBKIT = None


def with_qt_web_kit() -> bool:
    global _WITH_QTWEBKIT
    if _WITH_QTWEBKIT is None:
        try:
            from qgis.PyQt.QtWebKit import QWebSettings  # noqa: F401
            from qgis.PyQt.QtWebKitWidgets import QWebView, QWebPage  # noqa: F401
        except ModuleNotFoundError:
            _WITH_QTWEBKIT = False
        else:
            _WITH_QTWEBKIT = True

    return _WITH_QTWEBKIT
