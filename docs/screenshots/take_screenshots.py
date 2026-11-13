"""
Take the screenshots of the documentation. QGIS runs it at startup, see run.sh.

It drives QGIS as a user would: types in the locator bar, picks a result,
waits for the map. Each function of SHOTS writes one or more PNG files to
docs/<lang>/assets/screenshots/, in the language QGIS runs in. A red circle
marks where the user clicks.

Environment:
    SCREENSHOTS_LANG    en, fr, de or it
    SCREENSHOTS_ONLY    comma separated names of SHOTS to take, all by default
    SCREENSHOTS_LIDAR   ept.json of fake_lidar.py
"""

import os
import traceback

from qgis.PyQt import sip
from qgis.PyQt.QtCore import (
    QCoreApplication,
    QEventLoop,
    QModelIndex,
    QPoint,
    QSize,
    Qt,
    QTimer,
)
from qgis.PyQt.QtGui import QColor, QPainter, QPen
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import (
    QAction,
    QApplication,
    QDockWidget,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTreeView,
    QWidget,
)
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeedback,
    QgsLocatorModel,
    QgsPointCloudClassifiedRenderer,
    QgsPointCloudLayer,
    QgsPointXY,
    QgsProject,
    QgsSettingsTree,
    QgsVectorLayer,
)
from qgis.gui import QgsLocatorWidget
from qgis.utils import iface, plugins

LANG = os.environ.get("SCREENSHOTS_LANG", "en")
ONLY = [name for name in os.environ.get("SCREENSHOTS_ONLY", "").split(",") if name]
LIDAR = os.environ.get("SCREENSHOTS_LIDAR", "/tmp/lidar/ept.json")
OUTPUT = os.path.join(os.getcwd(), "docs", LANG, "assets", "screenshots")

WINDOW_SIZE = QSize(1280, 800)
MARKER_COLOR = QColor(230, 30, 30, 220)

COLOUR = "ch.swisstopo.pixelkarte-farbe"
GREY = "ch.swisstopo.pixelkarte-grau"

# Scales matching a resolution of the WMTS of geo.admin.ch, in m per pixel,
# so that the national maps are not resampled
SCALE = {res: res / 0.00026458333 for res in (500, 100, 20, 10, 5, 2, 1)}

# Map views: centre in EPSG:2056 and scale
SWITZERLAND = (2660000, 1185000, SCALE[500])
LAUSANNE = (2538300, 1152600, SCALE[1])
BERN = (2600600, 1199700, SCALE[2])
LAUTERBRUNNEN = (2636500, 1157000, SCALE[10])
ALETSCH = (2643000, 1142000, SCALE[20])
LANGNAU = (2626900, 1197600, SCALE[5])

# What is typed in the locator bar, by language
LAYER_SEARCH = {
    "en": "hiking",
    "fr": "randonnée",
    "de": "Wanderwege",
    "it": "escursionistici",
}
# A layer of a cantonal service, referenced by opendata.swiss: what is typed,
# a part of the URL of the service to pick, and where to look
TREES_IN_BERN = ("Baumkataster", "map.bern.ch", (2600700, 1199800, SCALE[1]))
OPENDATA_SEARCH = {
    "en": TREES_IN_BERN,
    "fr": (
        "arbres remarquables",
        "geoservices.jura.ch",
        (2583000, 1243000, SCALE[100]),
    ),
    "de": TREES_IN_BERN,
    "it": TREES_IN_BERN,
}
# Layers of the feature search example, which restricts the search to them
FEATURE_LAYERS = [
    "ch.bav.haltestellen-oev",
    "ch.bafu.unesco-weltnaturerbe",
    "ch.swisstopo.unterkuenfte-winter",
    "ch.swisstopo.geologie-geosites",
]
# The line of fake_lidar.py
PROFILE_LINE = ((2626300.0, 1197200.0), (2627500.0, 1198000.0))
# The table of the geocoding example: there is no Seftigenstrasse 355, and
# there are many Bahnhofstrasse 1
ADDRESSES = (
    "Bundesplatz 3, 3011 Bern",
    "Seftigenstrasse 264, 3084 Wabern",
    "Rue du Stand 15, 1204 Genève",
    "Piazza Grande 1, 6600 Locarno",
    "Seftigenstrasse 355, 3084 Wabern",
    "Bahnhofstrasse 1",
)
# The attributes of the geocoding result shown in its table
GEOCODING_COLUMNS = (
    "id",
    "address",
    "geocode_quality",
    "geocode_candidates",
    "geocode_label",
)


# --------------------------------------------------------------------------
# Waiting
# --------------------------------------------------------------------------


def wait(ms: int):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_until(predicate, timeout: int = 60_000, step: int = 200) -> bool:
    elapsed = 0
    while not predicate():
        if elapsed >= timeout:
            log(f"  timeout after {timeout} ms")
            return False
        wait(step)
        elapsed += step
    return True


def wait_for_map(timeout: int = 90_000):
    """Wait until the map is drawn and the tasks are done."""
    canvas = iface.mapCanvas()
    wait(800)
    stable, elapsed = 0, 0
    while stable < 2000 and elapsed < timeout:
        wait(200)
        elapsed += 200
        busy = canvas.isDrawing() or QgsApplication.taskManager().countActiveTasks()
        stable = 0 if busy else stable + 200


def log(message: str):
    print(f"[{LANG}] {message}", flush=True)


# --------------------------------------------------------------------------
# Screenshots
# --------------------------------------------------------------------------


def save(name: str, widget: QWidget = None, markers=()):
    """Grab a widget, the main window by default, and save it as name.png.

    :param markers: points, in coordinates of the widget, to circle in red
    """
    widget = widget or iface.mainWindow()
    QApplication.processEvents()
    pixmap = widget.grab()
    if markers:
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(MARKER_COLOR, 3))
        for point in markers:
            painter.drawEllipse(point, 16, 16)
        painter.end()
    os.makedirs(OUTPUT, exist_ok=True)
    path = os.path.join(OUTPUT, f"{name}.png")
    pixmap.save(path)
    _compress(path)
    log(f"  saved {name}.png")


def _compress(path: str):
    """Reduce the PNG to 256 colours, a third of its size."""
    try:
        from PIL import Image
    except ImportError:
        return
    with Image.open(path) as image:
        image = image.convert("RGB").quantize(
            colors=256, method=Image.Quantize.LIBIMAGEQUANT
        )
    image.save(path, optimize=True)


def center_of(widget: QWidget) -> QPoint:
    """The centre of a widget, in the main window."""
    return widget.mapTo(iface.mainWindow(), widget.rect().center())


# --------------------------------------------------------------------------
# QGIS
# --------------------------------------------------------------------------


def find_widget(class_name: str, parent: QWidget = None) -> QWidget | None:
    for widget in (parent or iface.mainWindow()).findChildren(QWidget):
        if widget.metaObject().className() == class_name:
            return widget
    return None


def locator_widget() -> QgsLocatorWidget:
    return sip.cast(find_widget("QgsLocatorWidget"), QgsLocatorWidget)


def results_view() -> QTreeView:
    return find_widget("QgsLocatorResultsView")


def plugin_filter(filter_type: str):
    """The first filter of a type: for STAC, the one of data.geo.admin.ch."""
    plugin = plugins["swiss_locator"]
    return next(f for f in plugin.locator_filters if f.type.value == filter_type)


def stac_filter(catalog_id: str):
    """The filter of a STAC catalogue, such as viageo"""
    plugin = plugins["swiss_locator"]
    return next(
        f
        for f in plugin.locator_filters
        if f.type.value == "stac" and f.catalog.CATALOG_ID == catalog_id
    )


def set_view(view):
    """Centre the map on a point of EPSG:2056, at a scale."""
    x, y, scale = view
    canvas = iface.mapCanvas()
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:2056"),
        canvas.mapSettings().destinationCrs(),
        QgsProject.instance(),
    )
    canvas.setCenter(transform.transform(QgsPointXY(x, y)))
    canvas.zoomScale(scale)
    canvas.refresh()


def new_project():
    find_widget("QgsLocatorLineEdit").clear()
    project = QgsProject.instance()
    project.removeAllMapLayers()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:2056"))
    iface.messageBar().clearWidgets()


def add_wmts(layer_id: str):
    """Add a layer of the WMTS of geo.admin.ch, as the plugin does."""
    from swiss_locator.core.filters.swiss_locator_filter import result_from_data

    wmts = plugin_filter("wmts")
    wait_until(lambda: wmts.capabilities is not None)
    found = []
    wmts.resultFetched.connect(found.append)
    wmts.perform_fetch_results(layer_id, QgsFeedback())
    wmts.resultFetched.disconnect(found.append)
    for result in found:
        if result_from_data(result).layer == layer_id:
            wmts.triggerResult(result)
            break
    else:
        log(f"  WMTS layer {layer_id} not found")
    iface.messageBar().clearWidgets()


def background(layer_id: str = COLOUR, view=SWITZERLAND):
    new_project()
    add_wmts(layer_id)
    # The welcome page hides the map of an empty project, the map must be
    # shown at its actual size before zooming
    wait(1000)
    set_view(view)
    wait_for_map()


# --------------------------------------------------------------------------
# The locator bar
# --------------------------------------------------------------------------


def search(text: str, timeout: int = 90_000):
    """Type in the locator bar and wait for all its results."""
    widget = locator_widget()
    done = []

    def finished():
        done.append(True)

    widget.locator().finished.connect(finished)
    widget.search(text)
    wait_until(lambda: done, timeout)
    widget.locator().finished.disconnect(finished)
    wait(1500)
    for index in results():
        log(
            f"    {_text(index)!r} {_text(index, 1)!r} {(_user_data(index) or '')[:100]}"
        )


def results() -> list[QModelIndex]:
    model = results_view().model()
    return [model.index(row, 0) for row in range(model.rowCount())]


def _text(index: QModelIndex, column: int = 0) -> str:
    return index.siblingAtColumn(column).data(Qt.ItemDataRole.DisplayRole) or ""


def _user_data(index: QModelIndex) -> str | None:
    try:
        result = index.data(QgsLocatorModel.CustomRole.ResultData)
    except Exception:
        return None
    if result is None:
        return None
    for getter in ("getUserData", "userData"):
        value = getattr(result, getter, None)
        if callable(value):
            value = value()
        if isinstance(value, str):
            return value
    return None


def find_result(text: str = None, data: str = None) -> QModelIndex:
    """The first result whose text contains text and user data contains data."""
    for index in results():
        if text and text.lower() not in (_text(index) + _text(index, 1)).lower():
            continue
        if data and data not in (_user_data(index) or ""):
            continue
        return index
    raise LookupError(f"no result with text {text!r} and data {data!r}")


def select(index: QModelIndex) -> QPoint:
    """Select a result, return where to circle it in the main window."""
    view = results_view()
    view.setCurrentIndex(index)
    view.scrollTo(index)
    wait(300)
    rect = view.visualRect(index)
    point = QPoint(rect.left() + 40, rect.center().y())
    return view.viewport().mapTo(iface.mainWindow(), point)


def trigger(index: QModelIndex):
    """Pick a result, as a double click does."""
    results_view().setCurrentIndex(index)
    QTest.keyClick(find_widget("QgsLocatorLineEdit"), Qt.Key.Key_Return)
    wait(500)


def close_locator():
    QTest.keyClick(find_widget("QgsLocatorLineEdit"), Qt.Key.Key_Escape)
    iface.mapCanvas().setFocus()
    wait(300)


# --------------------------------------------------------------------------
# The shots
# --------------------------------------------------------------------------


def shot_search_all():
    background(GREY)
    # Without text, the locator lists the searches with their prefix
    search("")
    index = find_result(text=plugin_filter("locations").displayName())
    save("search-prefixes", markers=[select(index)])
    trigger(index)
    prefix = find_widget("QgsLocatorLineEdit").text()
    if prefix.strip() != "chs":
        raise ValueError(f"the prefix was not set, the locator shows {prefix!r}")
    close_locator()

    background(GREY)
    search("Lausanne")
    save("search-all")
    close_locator()


def shot_locations():
    background()
    search("chs Lausanne")
    index = find_result(data="swissboundaries3d-gemeinde-flaeche")
    save("locations-search", markers=[select(index)])
    trigger(index)
    wait_for_map()
    save("locations-result")

    # The map centres on a point at the current scale: start from the city
    background(view=BERN)
    search("chs Bundesplatz 3 Bern")
    trigger(find_result(text="Bundesplatz 3"))
    wait_for_map()
    save("locations-address")


def shot_layers():
    background(GREY, LAUTERBRUNNEN)
    search(f"chl {LAYER_SEARCH[LANG]}")
    index = find_result(data='"ch.swisstopo.swisstlm3d-wanderwege"')
    save("layers-search", markers=[select(index)])
    trigger(index)
    wait_for_map()
    save("layers-result")

    text, service, view = OPENDATA_SEARCH[LANG]
    background(GREY, view)
    search(f"chl {text}")
    index = find_result(data=service)
    save("layers-opendata-search", markers=[select(index)])
    trigger(index)
    wait_for_map()
    save("layers-opendata-result")


def shot_wmts():
    background(GREY, LAUSANNE)
    search("chw swissimage")
    index = find_result(data='"layer": "ch.swisstopo.swissimage"')
    save("wmts-search", markers=[select(index)])
    trigger(index)
    wait_for_map()
    save("wmts-result")


def shot_base_maps():
    new_project()
    # Without layers, the map keeps its last image until refreshed
    iface.mapCanvas().refresh()
    wait_for_map()
    search("chb ")
    index = find_result(data="lightbasemap")
    save("base-maps-search", markers=[select(index)])
    trigger(index)
    wait(1000)
    set_view((2600600, 1199700, 15000))
    wait_for_map()
    save("base-maps-result")


def shot_features():
    from swiss_locator.core.settings import Settings

    settings = Settings()
    settings.feature_search_restrict.setValue(True)
    settings.feature_search_layers_list.setValue(FEATURE_LAYERS)
    try:
        background(view=ALETSCH)
        search("chf Aletsch")
        index = find_result(text="oberaletsch", data="unterkuenfte-winter")
        save("features-search", markers=[select(index)])
        trigger(index)
        wait_for_map()
        save("features-result")
    finally:
        settings.feature_search_restrict.setValue(False)
        settings.feature_search_layers_list.setValue([])


def shot_downloads():
    stac = plugin_filter("stac")
    wait_until(lambda: stac.available_collections)
    background(view=(2538000, 1152500, SCALE[10]))
    search("chd swissboundaries3d")
    save("downloads-search")
    close_locator()

    search("chd swissalti3d")
    index = find_result(data="ch.swisstopo.swissalti3d")
    save("downloads-filter-search", markers=[select(index)])
    trigger(index)
    wait_for_map()
    dock = plugins["swiss_locator"].stac_filter_widget
    request = dock.findChild(QPushButton, "guiRequestListBtn")
    wait_until(request.isEnabled)
    request.click()
    wait_until(
        lambda: not dock.findChild(QPushButton, "guiRequestCancelBtn").isVisible()
    )
    wait_for_map()
    save("downloads-filter", markers=[center_of(request)])
    dock.close()


def shot_downloads_viageo():
    # Both catalogues answer to chd, each under its own name
    for catalog_id in ("geoadmin", "viageo"):
        stac = stac_filter(catalog_id)
        wait_until(lambda: stac.available_collections)
    background(view=(2538000, 1152500, SCALE[10]))
    search("chd lidar")
    find_result(text=stac_filter("viageo").displayName())
    save("downloads-viageo")
    close_locator()


def shot_geocoding():
    import processing

    background(GREY)
    # A table without geometry, as loaded from a CSV file
    table = QgsVectorLayer(
        "None?field=id:integer&field=address:string", "addresses", "memory"
    )
    for number, address in enumerate(ADDRESSES, 1):
        feature = QgsFeature(table.fields())
        feature.setAttributes([number, address])
        table.dataProvider().addFeature(feature)
    QgsProject.instance().addMapLayer(table)

    algorithm = "swiss_locator:geocodeaddresses"
    dialog = processing.createAlgorithmDialog(
        algorithm, {"INPUT": table.id(), "FIELD": "address"}
    )
    # QGIS restores the last size of the dialog, a minimum overrides it
    dialog.setMinimumSize(1000, 640)
    dialog.show()
    wait(1500)
    save("geocoding-dialog", widget=dialog)
    dialog.close()

    output = processing.runAndLoadResults(
        algorithm,
        {"INPUT": table, "FIELD": "address", "OUTPUT": "TEMPORARY_OUTPUT"},
    )["OUTPUT"]
    layer = (
        output
        if isinstance(output, QgsVectorLayer)
        else QgsProject.instance().mapLayer(output)
    )
    for feature in layer.getFeatures():
        log(f"    {[feature[name] for name in GEOCODING_COLUMNS]}")
    config = layer.attributeTableConfig()
    columns = config.columns()
    for column in columns:
        column.hidden = column.name not in GEOCODING_COLUMNS
    config.setColumns(columns)
    layer.setAttributeTableConfig(config)
    table_dialog = iface.showAttributeTable(layer)
    wait(1500)
    table_dialog.resize(760, 300)
    wait(500)
    find_widget("QgsAttributeTableView", table_dialog).resizeColumnsToContents()
    wait(500)
    save("geocoding-table", widget=table_dialog)
    table_dialog.close()


def shot_profile():
    background()
    lidar = QgsPointCloudLayer(LIDAR, "Lidar", "ept")
    lidar.setCrs(QgsCoordinateReferenceSystem("EPSG:2056"))
    renderer = QgsPointCloudClassifiedRenderer(
        "Classification", QgsPointCloudClassifiedRenderer.defaultCategories()
    )
    renderer.setPointSize(1)
    lidar.setRenderer(renderer)
    properties = lidar.elevationProperties()
    properties.setRespectLayerColors(True)
    properties.setPointSize(1.2)
    QgsProject.instance().addMapLayer(lidar)

    # Points of the cloud within this distance of the line show in the profile
    elevation_profile = QgsSettingsTree.treeRoot().childNode("elevation-profile")
    elevation_profile.childSetting("tolerance").setVariantValue(15.0)
    iface.mainWindow().findChild(QAction, "mActionElevationProfile").trigger()
    wait(2000)
    profile = find_widget("QgsElevationProfileWidget")
    dock = profile.parent()
    while dock is not None and not isinstance(dock, QDockWidget):
        dock = dock.parent()
    # A taller window, the profile below the map
    iface.mainWindow().resize(WINDOW_SIZE.width(), 960)
    dock.setFloating(False)
    iface.mainWindow().addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
    iface.mainWindow().resizeDocks([dock], [420], Qt.Orientation.Vertical)
    profile.findChild(QSplitter).setSizes([190, 1090])
    wait(1000)
    set_view(LANGNAU)
    wait_for_map()

    capture = QCoreApplication.translate("QgsElevationProfileWidget", "Capture Curve")
    for action in profile.findChildren(QAction):
        if action.text() == capture:
            action.trigger()
            break
    else:
        raise LookupError(f"no action {capture!r} in the elevation profile")
    wait(500)
    canvas = iface.mapCanvas()
    viewport = canvas.viewport()
    points = []
    for x, y in PROFILE_LINE:
        pixel = canvas.getCoordinateTransform().transform(QgsPointXY(x, y))
        points.append(QPoint(round(pixel.x()), round(pixel.y())))
    for point in points:
        QTest.mouseMove(viewport, point)
        QTest.mouseClick(
            viewport,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            point,
        )
        wait(300)
    QTest.mouseClick(
        viewport, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, points[-1]
    )
    wait(3000)
    wait_for_map()
    wait(8000)
    save("profile")
    dock.close()
    iface.mainWindow().resize(WINDOW_SIZE)


def shot_configuration():
    from swiss_locator.gui.config_dialog import ConfigDialog

    dialog = ConfigDialog(iface.mainWindow())
    dialog.show()
    wait(800)
    save("configuration", widget=dialog)
    tabs = dialog.findChild(QTabWidget, "tabWidget")
    tabs.setCurrentWidget(tabs.findChild(QWidget, "featuresearch"))
    dialog.feature_search_restrict.setChecked(True)
    wait(500)
    save("configuration-features", widget=dialog)
    dialog.reject()

    def grab_options():
        dialog = QApplication.activeModalWidget()
        wait(1500)
        save("options-locator", widget=dialog)
        dialog.reject()

    QTimer.singleShot(2000, grab_options)
    iface.showOptionsDialog(iface.mainWindow(), "mOptionsLocatorSettings")


SHOTS = {
    "search_all": shot_search_all,
    "locations": shot_locations,
    "layers": shot_layers,
    "wmts": shot_wmts,
    "base_maps": shot_base_maps,
    "features": shot_features,
    "downloads": shot_downloads,
    "downloads_viageo": shot_downloads_viageo,
    "geocoding": shot_geocoding,
    "profile": shot_profile,
    "configuration": shot_configuration,
}


def main():
    window = iface.mainWindow()
    window.showNormal()
    window.resize(WINDOW_SIZE)
    window.move(0, 0)
    for dock in window.findChildren(QDockWidget):
        if dock.objectName() == "Browser":
            dock.close()
    # The welcome page, a QML view, hangs a grab under Xvfb: a layer hides it
    background()
    new_project()
    wait(2000)

    failures = []
    for name, shot in SHOTS.items():
        if ONLY and name not in ONLY:
            continue
        log(name)
        try:
            shot()
        except Exception:
            traceback.print_exc()
            failures.append(name)
        iface.messageBar().clearWidgets()
    if failures:
        log(f"FAILED: {', '.join(failures)}")
    os._exit(1 if failures else 0)


QTimer.singleShot(3000, main)
