"""
The demo video of the plugin. QGIS runs it at startup, see run.sh.

It drives QGIS as a user would, from an empty project:

1. adds the light base map, from the locator bar
2. searches for the station of Vevey and zooms to it
3. opens an elevation profile and draws a line across the town
4. searches for lidar data and opens swissSURFACE3D
5. requests the files of the map view, deselects them all, selects one tile
   on the map and downloads it: streamed, the point cloud shows in the
   profile
6. opens a 3D view and moves the camera over the town, then close to it

The real mouse pointer glides to each widget before the script clicks it,
and a red ring shows each click. The clicks, the moves and the keys are Qt
events sent to the window of QGIS: macOS does not need to let the script
control the computer, only to warp the pointer.

It talks with run.sh through files in DEMO_CONTROL:

    region       written once the window is ready: x,y,w,h to record
    go           written by run.sh once it records
    marks.json   when the demo begins and ends, and the waits to speed up
    done         "ok" or "failed"
"""

import ctypes
import json
import math
import os
import random
import time
import traceback

from qgis.PyQt.QtCore import (
    QEvent,
    QEventLoop,
    QModelIndex,
    QObject,
    QPoint,
    QPointF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
)
from qgis.PyQt.QtGui import QColor, QCursor, QPainter, QPen, QWheelEvent
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QAbstractButton,
    QAction,
    QApplication,
    QDockWidget,
    QLineEdit,
    QPushButton,
    QSplitter,
    QToolBar,
    QToolButton,
    QWidget,
)
from qgis.core import (
    QgsApplication,
    QgsLocatorModel,
    QgsPointCloudLayer,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsSettingsTree,
    QgsVector3D,
)
from qgis.utils import iface, plugins

CONTROL = os.environ.get("DEMO_CONTROL", "/tmp/swiss-locator-demo")

# The window with its title bar: the size of the video
FRAME = QSize(1280, 800)
LAYERS_WIDTH = 200
DOWNLOAD_WIDTH = 360
PROFILE_HEIGHT = 210
VIEW_3D_WIDTH = 620
# The clicks, in the red of the Swiss flag
CLICK_COLOR = QColor(218, 41, 28)

# In EPSG:2056. The station of Vevey is in the tile 2554-1145 of
# swissSURFACE3D, on its northern edge, the lake in the south
STATION = QgsPointXY(2554290, 1145880)
STATION_SCALE = 7000
# From the lake shore through the old town to the tracks
PROFILE_LINE = ((2554120, 1145570), (2554300, 1145730), (2554420, 1145960))
# Dragged on the map to select the tile 2554-1145 only
SELECTION = ((2554450, 1145720), (2554700, 1145480))
TILE = "2554-1145"
# The 3D view: the map lies on a flat terrain at the height of the town, the
# camera looks at the station from the lake, then turns
TERRAIN_HEIGHT = 380
VIEW_3D_EXTENT = QgsRectangle(2552500, 1144300, 2556500, 1147300)
# Far enough to see the map around the tile, then closer
CAMERA_TARGET = QgsVector3D(2554450, 1145600, 385)
CAMERA_DISTANCE = 1600
CAMERA_PITCH = 55
CAMERA_YAW = -25
# Then it turns and comes close to the old town and the station
CAMERA_CLOSE_TARGET = QgsVector3D(2554300, 1145720, 390)
CAMERA_CLOSE_DISTANCE = 600
CAMERA_CLOSE_PITCH = 60
CAMERA_TURN = 45


# --------------------------------------------------------------------------
# Waiting
# --------------------------------------------------------------------------


def wait(ms: int):
    loop = QEventLoop()
    QTimer.singleShot(int(ms), loop.quit)
    loop.exec()


def wait_until(predicate, timeout: int = 60_000, step: int = 100) -> bool:
    start = time.monotonic()
    while not predicate():
        if (time.monotonic() - start) * 1000 > timeout:
            log(f"  timeout after {timeout} ms")
            return False
        wait(step)
    return True


def busy() -> bool:
    canvas = iface.mapCanvas()
    return canvas.isDrawing() or QgsApplication.taskManager().countActiveTasks() > 0


def wait_for_map(timeout: int = 60_000, quiet: int = 1000):
    """Wait until the map is drawn and the tasks are done, for quiet ms."""
    wait(500)
    start = calm = time.monotonic()
    while (time.monotonic() - calm) * 1000 < quiet:
        if (time.monotonic() - start) * 1000 > timeout:
            log(f"  map still busy after {timeout} ms")
            return
        wait(100)
        if busy():
            calm = time.monotonic()


def log(message: str):
    print(f"[demo] {message}", flush=True)


# --------------------------------------------------------------------------
# What run.sh gets: the region to record, and marks in time
# --------------------------------------------------------------------------


class Marks:
    def __init__(self):
        self.begin = None
        self.end = None
        self.fast = []
        self._fast_since = None

    def start_fast(self):
        self._fast_since = time.time()

    def stop_fast(self):
        if self._fast_since is not None:
            self.fast.append([self._fast_since, time.time()])
            self._fast_since = None

    def write(self):
        with open(os.path.join(CONTROL, "marks.json"), "w") as f:
            json.dump({"begin": self.begin, "end": self.end, "fast": self.fast}, f)


MARKS = Marks()


def waiting(function, *args, **kwargs):
    """A wait the video speeds up."""
    MARKS.start_fast()
    try:
        return function(*args, **kwargs)
    finally:
        MARKS.stop_fast()


# --------------------------------------------------------------------------
# The pointer
# --------------------------------------------------------------------------


class _CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


_CORE_GRAPHICS = ctypes.CDLL(
    "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
)
_CORE_GRAPHICS.CGWarpMouseCursorPosition.argtypes = [_CGPoint]
_CORE_GRAPHICS.CGWarpMouseCursorPosition.restype = ctypes.c_int32


class Ring(QWidget):
    """A ring growing and fading where the pointer clicks, on top of all."""

    SIZE = 72
    rings = []

    def __init__(self, center: QPoint, color: QColor = CLICK_COLOR):
        super().__init__(
            None,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        for attribute in (
            Qt.WidgetAttribute.WA_TranslucentBackground,
            Qt.WidgetAttribute.WA_ShowWithoutActivating,
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
        ):
            self.setAttribute(attribute)
        self.color = color
        self.progress = 0.0
        self.setGeometry(
            center.x() - self.SIZE // 2,
            center.y() - self.SIZE // 2,
            self.SIZE,
            self.SIZE,
        )
        self.animation = QVariantAnimation(self)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setDuration(500)
        self.animation.valueChanged.connect(self._step)
        self.animation.finished.connect(self._finish)
        Ring.rings.append(self)
        self.show()
        self.animation.start()

    def _step(self, value):
        self.progress = value
        self.update()

    def _finish(self):
        self.hide()
        Ring.rings.remove(self)
        self.deleteLater()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fade = 1.0 - self.progress
        pen = QColor(self.color)
        pen.setAlphaF(0.9 * fade)
        fill = QColor(self.color)
        fill.setAlphaF(0.25 * fade)
        painter.setPen(QPen(pen, 3))
        painter.setBrush(fill)
        radius = 8 + 22 * self.progress
        center = QPointF(self.SIZE / 2, self.SIZE / 2)
        painter.drawEllipse(center, radius, radius)
        painter.end()


class Pointer:
    """The real mouse pointer, and the Qt events of a mouse at its place."""

    def __init__(self):
        self.pos = QCursor.pos()
        self.under = None

    @staticmethod
    def window():
        return iface.mainWindow().windowHandle()

    def local(self):
        return self.window().mapFromGlobal(self.pos)

    def warp(self, point: QPoint, send_move: bool = False):
        self.pos = QPoint(point)
        _CORE_GRAPHICS.CGWarpMouseCursorPosition(_CGPoint(point.x(), point.y()))
        if send_move:
            QTest.mouseMove(self.window(), self.local())
        self.update_shape()

    def update_shape(self):
        """macOS changes the shape of the pointer on real moves only: it would
        stay an I-beam once out of the locator bar. The shape of the widget
        under the pointer, the map tool on the map, as an override."""
        widget = QApplication.widgetAt(self.pos)
        under = (widget, widget.cursor().shape()) if widget is not None else None
        if under == self.under:
            return
        cursor = widget.cursor() if widget is not None else QCursor()
        if self.under is None and QApplication.overrideCursor() is None:
            QApplication.setOverrideCursor(cursor)
        else:
            QApplication.changeOverrideCursor(cursor)
        self.under = under

    def glide(self, target: QPoint, duration: int = None, send_move: bool = False):
        """Move to a point in global coordinates, along a slight curve, as a
        hand moves a mouse. Mouse moves are sent only when asked: those over
        the elevation profile leave a crosshair on it."""
        start = QPointF(self.pos)
        delta = QPointF(target) - start
        distance = math.hypot(delta.x(), delta.y())
        if distance < 3:
            self.warp(target, send_move)
            return
        if duration is None:
            duration = min(850, 300 + distance * 0.45)
        normal = QPointF(-delta.y(), delta.x()) / distance
        bow = random.choice((-1, 1)) * min(50.0, distance * 0.08)
        begin = time.monotonic()
        while True:
            t = min(1.0, (time.monotonic() - begin) * 1000 / duration)
            eased = t * t * (3 - 2 * t)
            point = start + delta * eased + normal * bow * math.sin(math.pi * eased)
            self.warp(point.toPoint(), send_move)
            if t >= 1.0:
                break
            wait(15)
        self.warp(target, send_move)

    def click(self, button=Qt.MouseButton.LeftButton, double: bool = False):
        Ring(self.pos)
        if double:
            QTest.mouseDClick(
                self.window(), button, Qt.KeyboardModifier.NoModifier, self.local()
            )
            wait(120)
            Ring(self.pos)
        else:
            QTest.mouseClick(
                self.window(), button, Qt.KeyboardModifier.NoModifier, self.local()
            )

    def press(self):
        Ring(self.pos)
        QTest.mousePress(
            self.window(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self.local(),
        )

    def release(self):
        QTest.mouseRelease(
            self.window(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self.local(),
        )

    def click_widget(
        self, widget: QWidget, pos: QPoint = None, pause: int = 120, **kwargs
    ):
        """Glide to a widget, its centre by default, and click it."""
        pos = pos if pos is not None else widget.rect().center()
        self.glide(widget.mapToGlobal(pos))
        wait(pause)
        self.click(**kwargs)
        wait(80)

    def wheel(self, widget: QWidget, delta: int):
        local = QPointF(widget.mapFromGlobal(self.pos))
        event = QWheelEvent(
            local,
            QPointF(self.pos),
            QPoint(0, 0),
            QPoint(0, delta),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(widget, event)


POINTER = Pointer()


def type_text(widget: QWidget, text: str):
    for char in text:
        QTest.keyClicks(widget, char)
        wait(random.randint(35, 75))


# --------------------------------------------------------------------------
# QGIS
# --------------------------------------------------------------------------


def find_widget(class_name: str, parent: QWidget = None) -> QWidget | None:
    for widget in (parent or iface.mainWindow()).findChildren(QWidget):
        if widget.metaObject().className() == class_name:
            return widget
    return None


def dock_of(widget: QWidget) -> QDockWidget | None:
    while widget is not None and not isinstance(widget, QDockWidget):
        widget = widget.parentWidget()
    return widget


def place_dock(dock: QDockWidget, area, size: int):
    window = iface.mainWindow()
    dock.setFloating(False)
    window.addDockWidget(area, dock)
    dock.show()
    orientation = (
        Qt.Orientation.Vertical
        if area
        in (Qt.DockWidgetArea.TopDockWidgetArea, Qt.DockWidgetArea.BottomDockWidgetArea)
        else Qt.Orientation.Horizontal
    )
    window.resizeDocks([dock], [size], orientation)


def toolbar_button(action_name: str) -> QToolButton:
    action = iface.mainWindow().findChild(QAction, action_name)
    for toolbar in iface.mainWindow().findChildren(QToolBar):
        if toolbar.isVisible() and action in toolbar.actions():
            return toolbar.widgetForAction(action)
    raise LookupError(f"no button for {action_name}")


def canvas_point(x: float, y: float) -> QPoint:
    """A point of EPSG:2056, the project CRS, in global coordinates."""
    canvas = iface.mapCanvas()
    pixel = canvas.getCoordinateTransform().transform(QgsPointXY(x, y))
    return canvas.viewport().mapToGlobal(QPoint(round(pixel.x()), round(pixel.y())))


def bring_to_front():
    """QGIS in front of the other apps, as the region recorded is a part of
    the screen."""
    window = iface.mainWindow()
    window.raise_()
    window.activateWindow()
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    send = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
        ("objc_msgSend", objc)
    )
    send_bool = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool)(
        ("objc_msgSend", objc)
    )
    application = send(
        objc.objc_getClass(b"NSApplication"),
        objc.sel_registerName(b"sharedApplication"),
    )
    send_bool(application, objc.sel_registerName(b"activateIgnoringOtherApps:"), True)


def setup_window():
    window = iface.mainWindow()
    window.showNormal()
    # The welcome page of QGIS 4 covers the map of an empty project: its news
    # change over time
    find_widget("QgsWelcomeScreen").hide()
    iface.messageBar().clearWidgets()
    # Left and right docks take the full height, the profile goes under the map
    window.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
    window.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
    for dock in window.findChildren(QDockWidget):
        if dock.objectName() == "Browser":
            dock.close()
    keep = ("mFileToolBar", "mMapNavToolBar", "mAttributesToolBar")
    for toolbar in window.findChildren(QToolBar):
        if toolbar.parent() is window and toolbar.objectName() not in keep:
            toolbar.hide()
    # No toolbar has the elevation profile: next to the 3D view
    navigation = window.findChild(QToolBar, "mMapNavToolBar")
    new_3d = window.findChild(QAction, "mActionNew3DMapCanvas")
    profile = window.findChild(QAction, "mActionElevationProfile")
    actions = navigation.actions()
    after = actions[actions.index(new_3d) + 1]
    navigation.insertAction(after, profile)

    wait(500)
    title_bar = window.frameGeometry().height() - window.geometry().height()
    window.resize(FRAME.width(), FRAME.height() - title_bar)
    screen = window.screen().availableGeometry()
    window.move(
        screen.x() + (screen.width() - FRAME.width()) // 2,
        screen.y() + (screen.height() - FRAME.height()) // 2,
    )
    bring_to_front()
    wait(1000)
    place_dock(
        window.findChild(QDockWidget, "Layers"),
        Qt.DockWidgetArea.LeftDockWidgetArea,
        LAYERS_WIDTH,
    )
    # Points of the cloud within this distance of the line show in the profile
    profile_settings = QgsSettingsTree.treeRoot().childNode("elevation-profile")
    profile_settings.childSetting("tolerance").setVariantValue(3.0)
    wait(500)
    frame = window.frameGeometry()
    log(
        f"window {frame} on {window.screen().name()}, ratio {window.devicePixelRatio()}"
    )
    return frame


# --------------------------------------------------------------------------
# The locator bar
# --------------------------------------------------------------------------


def locator_edit() -> QWidget:
    return find_widget("QgsLocatorLineEdit")


def results_view():
    return find_widget("QgsLocatorResultsView")


def results() -> list[QModelIndex]:
    model = results_view().model()
    return [model.index(row, 0) for row in range(model.rowCount())]


def _text(index: QModelIndex, column: int = 0) -> str:
    return index.siblingAtColumn(column).data(Qt.ItemDataRole.DisplayRole) or ""


def _user_data(index: QModelIndex) -> str:
    try:
        result = index.data(QgsLocatorModel.CustomRole.ResultData)
    except Exception:
        return ""
    if result is None:
        return ""
    value = getattr(result, "userData", None)
    if callable(value):
        value = value()
    return value if isinstance(value, str) else ""


def find_result(text: str = None, data: str = None) -> QModelIndex | None:
    for index in results():
        if text and not all(
            word in (_text(index) + " " + _text(index, 1)).lower()
            for word in text.lower().split()
        ):
            continue
        if data and data not in _user_data(index):
            continue
        return index
    return None


def search(text: str, result_text: str = None, result_data: str = None) -> QModelIndex:
    """Click the locator bar, type, and wait for a result. Not for all: some
    searches, such as opendata.swiss, take long to answer."""
    edit = locator_edit()
    edit.clear()
    POINTER.click_widget(edit, QPoint(60, edit.height() // 2))
    type_text(edit, text)
    MARKS.start_fast()
    found = wait_until(
        lambda: find_result(result_text, result_data) is not None, 30_000
    )
    MARKS.stop_fast()
    # Time to read, and for the other searches to answer
    wait(400)
    for index in results():
        log(f"    {_text(index)!r} {_text(index, 1)!r} {_user_data(index)[:90]}")
    if not found:
        raise LookupError(f"no result for {text!r}: {result_text!r} {result_data!r}")
    return find_result(result_text, result_data)


def scroll_to(view, index: QModelIndex):
    """Scroll the results to a row as a hand would, the pointer over the
    list, rather than jumping to it."""
    view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    bar = view.verticalScrollBar()
    start = bar.value()
    view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
    end = bar.value()
    bar.setValue(start)
    if end == start:
        return
    viewport = view.viewport()
    POINTER.glide(
        viewport.mapToGlobal(QPoint(viewport.width() // 3, viewport.height() // 2))
    )
    wait(150)
    duration = min(1300, 450 + abs(end - start) * 0.8)
    begin = time.monotonic()
    while True:
        t = min(1.0, (time.monotonic() - begin) * 1000 / duration)
        bar.setValue(round(start + (end - start) * t * t * (3 - 2 * t)))
        if t >= 1.0:
            break
        wait(16)
    wait(250)


def pick(result_text: str = None, result_data: str = None):
    """Double-click a result, as the documentation says."""
    view = results_view()
    scroll_to(view, find_result(result_text, result_data))
    index = find_result(result_text, result_data)
    rect = view.visualRect(index)
    POINTER.glide(
        view.viewport().mapToGlobal(QPoint(rect.left() + 70, rect.center().y()))
    )
    wait(200)
    # The results may have moved while the pointer moved
    index = find_result(result_text, result_data)
    rect = view.visualRect(index)
    POINTER.glide(
        view.viewport().mapToGlobal(QPoint(rect.left() + 70, rect.center().y())), 150
    )
    view.setCurrentIndex(index)
    POINTER.click(double=True)
    wait(200)
    if view.isVisible():
        log("  the double click did not pick the result, Return does")
        QTest.keyClick(locator_edit(), Qt.Key.Key_Return)
        wait(500)
    # Else the locator, still focused, lists its searches again
    iface.mapCanvas().setFocus()


# --------------------------------------------------------------------------
# The demo
# --------------------------------------------------------------------------


def add_base_map():
    search("chb ", result_data="lightbasemap")
    wait(500)
    pick(result_data="lightbasemap")
    # The next search starts while the map loads
    wait(300)


def zoom_to_station():
    search("gare de vevey", result_text="gare vevey")
    wait(300)
    pick(result_text="gare vevey")
    # Zoom at once, as a hand would, without waiting for the map
    wait(300)
    canvas = iface.mapCanvas()
    POINTER.glide(canvas_point(STATION.x(), STATION.y()), 650)
    wait(150)
    # Wheel steps zoom twice, the last one less, to the scale wanted
    while canvas.scale() > STATION_SCALE * 1.05:
        factor = min(2.0, canvas.scale() / STATION_SCALE)
        POINTER.wheel(canvas.viewport(), round((factor - 1) * 120))
        wait(140)
    log(f"  scale 1:{canvas.scale():.0f}")
    wait(250)


def draw_profile():
    POINTER.click_widget(toolbar_button("mActionElevationProfile"))
    profile = None

    def opened():
        nonlocal profile
        profile = find_widget("QgsElevationProfileWidget")
        return profile is not None

    wait_until(opened, 10_000)
    place_dock(dock_of(profile), Qt.DockWidgetArea.BottomDockWidgetArea, PROFILE_HEIGHT)
    profile.findChild(QSplitter).setSizes([150, 1000])
    wait(600)

    capture = next(
        action
        for action in profile.findChildren(QAction)
        if action.text() == "Capture Curve"
    )
    button = next(
        button
        for button in profile.findChildren(QToolButton)
        if button.defaultAction() is capture and button.isVisible()
    )
    POINTER.click_widget(button)
    wait(150)
    for x, y in PROFILE_LINE:
        POINTER.glide(canvas_point(x, y), send_move=True)
        wait(100)
        POINTER.click()
        wait(120)
    POINTER.click(button=Qt.MouseButton.RightButton)
    wait(300)
    waiting(wait_until, lambda: not busy(), 20_000)
    wait(1200)


def hide_selection(dock):
    """When a button of the panel hides or is disabled, Qt gives the focus to
    the next field, the first of the extent, which then shows all its text
    selected: the fields of the panel take no focus."""
    iface.mapCanvas().setFocus()
    for edit in dock.findChildren(QLineEdit):
        edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)


def select_tile():
    search("lidar", result_data='"collection_id": "ch.swisstopo.swisssurface3d"')
    wait(400)
    pick(result_data='"collection_id": "ch.swisstopo.swisssurface3d"')
    plugin = plugins["swiss_locator"]
    wait_until(lambda: plugin.stac_filter_widget is not None, 10_000)
    dock = plugin.stac_filter_widget
    place_dock(dock, Qt.DockWidgetArea.RightDockWidgetArea, DOWNLOAD_WIDTH)
    hide_selection(dock)
    request = dock.findChild(QPushButton, "guiRequestListBtn")
    waiting(wait_until, request.isEnabled, 30_000)
    wait(500)

    POINTER.click_widget(request)
    cancel = dock.findChild(QPushButton, "guiRequestCancelBtn")
    waiting(
        wait_until, lambda: not cancel.isVisible() and dock.fileListTbl.items, 30_000
    )
    waiting(wait_for_map)
    log(f"  files {list(dock.fileListTbl.items)}")
    wait(600)

    POINTER.click_widget(dock.fileListTbl.toggleAllBtn)
    wait(300)
    POINTER.click_widget(dock.mapSelectBtn)

    start, end = (canvas_point(x, y) for x, y in SELECTION)
    POINTER.glide(start)
    wait(80)
    POINTER.press()
    wait(150)
    POINTER.glide(end, duration=700, send_move=True)
    wait(150)
    POINTER.release()
    wait(200)
    selected = [
        file
        for file, item in dock.fileListTbl.items.items()
        if item.checkState() == Qt.CheckState.Checked
    ]
    log(f"  selected {selected}")
    if len(selected) != 1 or TILE not in selected[0]:
        raise ValueError(f"the rectangle selected {selected}, not the tile {TILE}")
    wait(500)

    clicks, added, messages = [], [], []
    dock.guiDownloadBtn.clicked.connect(lambda: clicks.append(time.time()))
    QgsProject.instance().layersAdded.connect(
        lambda layers: added.extend(layer.name() for layer in layers)
    )
    iface.messageBar().widgetAdded.connect(
        lambda item: messages.append(f"{item.title()} {item.text()}")
    )
    POINTER.click_widget(dock.guiDownloadBtn)
    waiting(
        wait_until,
        lambda: any(
            isinstance(layer, QgsPointCloudLayer)
            for layer in QgsProject.instance().mapLayers().values()
        ),
        60_000,
    )
    waiting(wait_for_map, 90_000, 2000)
    wait(1600)
    log(f"  download clicked {len(clicks)} times, added {added}, messages {messages}")
    # Once, the download ran twice: the second one shows a message
    if len(clicks) != 1 or len(added) != 1 or messages:
        raise ValueError("the download did not run once")


class HideNewWindows(QObject):
    """Hides what QGIS 4.2 shows with a new 3D view: the view in a window of
    its own, until docked, and the identify results."""

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show and isinstance(watched, QWidget):
            if watched.windowTitle() == "Identify Results":
                # Closed at once, else it shows a moment
                watched.hide()
                QTimer.singleShot(0, watched.close)
            elif (
                watched.isWindow()
                and watched is not iface.mainWindow()
                and not isinstance(watched, Ring)
            ):
                watched.setWindowOpacity(0.0)
        return False


def open_3d_view():
    dock = plugins["swiss_locator"].stac_filter_widget
    close = next(
        button
        for button in dock.findChildren(QAbstractButton)
        if button.objectName() == "qt_dockwidget_closebutton"
    )
    POINTER.click_widget(close)
    wait(150)

    POINTER.glide(toolbar_button("mActionNew3DMapCanvas").mapToGlobal(QPoint(12, 12)))
    wait(250)
    # The view opens in a window of its own, docked at once: a QWindow, in a
    # container of a Qgs3DMapCanvasWidget
    hide = HideNewWindows()
    QApplication.instance().installEventFilter(hide)
    POINTER.click()
    canvas = iface.mapCanvases3D()[-1]
    widget = next(
        widget
        for widget in QApplication.allWidgets()
        if widget.metaObject().className() == "Qgs3DMapCanvasWidget"
    )
    for action in widget.findChildren(QAction):
        if action.text() == "Dock 3D Map View" and not action.isChecked():
            action.trigger()
    dock = dock_of(widget)
    if dock is None:
        raise LookupError("the 3D view is not in a dock")
    place_dock(dock, Qt.DockWidgetArea.RightDockWidgetArea, VIEW_3D_WIDTH)
    wait(100)
    QApplication.instance().removeEventFilter(hide)
    settings = canvas.mapSettings()
    # The 3D map takes the extent of the 2D map, narrow now: the map around
    settings.setExtent(VIEW_3D_EXTENT)
    settings.setTerrainElevationOffset(TERRAIN_HEIGHT)
    settings.setEyeDomeLightingEnabled(True)
    wait(1000)

    camera = canvas.cameraController()
    start = camera.lookingAtMapPoint()
    log(
        f"  camera at {start}, distance {camera.distance():.0f}, pitch {camera.pitch():.0f}, yaw {camera.yaw():.0f}"
    )
    POINTER.glide(
        canvas.mapToGlobal(QPoint(canvas.width() // 2, canvas.height() // 2)),
        send_move=False,
    )
    wait(200)

    # From the view of the whole map to the town
    begin = (start, max(camera.distance(), 1.0), camera.pitch(), camera.yaw())
    end = (CAMERA_TARGET, CAMERA_DISTANCE, CAMERA_PITCH, CAMERA_YAW)
    animate_camera(camera, begin, end, 3000)
    wait(200)
    # Turn and come close, as a drag would
    origin = POINTER.pos
    Ring(origin)
    close = (
        CAMERA_CLOSE_TARGET,
        CAMERA_CLOSE_DISTANCE,
        CAMERA_CLOSE_PITCH,
        CAMERA_YAW + CAMERA_TURN,
    )

    def drag(eased):
        offset = QPoint(round(-160 * eased), round(-12 * math.sin(math.pi * eased)))
        POINTER.warp(origin + offset)

    animate_camera(camera, end, close, 5500, drag)
    wait(2500)


def animate_camera(camera, begin, end, duration: int, step=None):
    """From a pose to another: centre, distance, pitch and yaw. step is
    called at each frame with the progress, eased."""
    (c0, d0, p0, y0), (c1, d1, p1, y1) = begin, end
    start = time.monotonic()
    while True:
        t = min(1.0, (time.monotonic() - start) * 1000 / duration)
        eased = t * t * (3 - 2 * t)
        center = QgsVector3D(
            c0.x() + (c1.x() - c0.x()) * eased,
            c0.y() + (c1.y() - c0.y()) * eased,
            c0.z() + (c1.z() - c0.z()) * eased,
        )
        # The distance changes by orders of magnitude: interpolate its log
        distance = math.exp(math.log(d0) + (math.log(d1) - math.log(d0)) * eased)
        camera.setLookingAtMapPoint(
            center, distance, p0 + (p1 - p0) * eased, y0 + (y1 - y0) * eased
        )
        if step:
            step(eased)
        if t >= 1.0:
            break
        wait(16)


STEPS = (
    ("base map", add_base_map),
    ("station", zoom_to_station),
    ("profile", draw_profile),
    ("download", select_tile),
    ("3D", open_3d_view),
)


def main():
    status = "failed"
    try:
        frame = setup_window()
        POINTER.warp(iface.mapCanvas().mapToGlobal(iface.mapCanvas().rect().center()))
        with open(os.path.join(CONTROL, "region"), "w") as f:
            f.write(f"{frame.x()},{frame.y()},{frame.width()},{frame.height()}")
        wait_until(lambda: os.path.exists(os.path.join(CONTROL, "go")), 120_000)
        bring_to_front()
        wait(300)
        MARKS.begin = time.time()
        wait(800)
        for name, step in STEPS:
            log(name)
            bring_to_front()
            step()
        MARKS.end = time.time()
        status = "ok"
    except Exception:
        traceback.print_exc()
        MARKS.end = time.time()
    MARKS.write()
    with open(os.path.join(CONTROL, "done"), "w") as f:
        f.write(status)
    wait(1500)
    os._exit(0 if status == "ok" else 1)


QTimer.singleShot(3000, main)
