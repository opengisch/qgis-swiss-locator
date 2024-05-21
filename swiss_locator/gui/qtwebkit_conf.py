
_WITH_QTWEBKIT = None


def with_qt_web_kit() -> bool:
    global _WITH_QTWEBKIT
    if _WITH_QTWEBKIT is None:
        try:
            from PyQt5.QtWebKit import QWebSettings
            from PyQt5.QtWebKitWidgets import QWebView, QWebPage
        except ModuleNotFoundError:
            _WITH_QTWEBKIT = False
        else:
            _WITH_QTWEBKIT = True

    return _WITH_QTWEBKIT
