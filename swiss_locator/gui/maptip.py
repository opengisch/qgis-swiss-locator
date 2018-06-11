# -*- coding: utf-8 -*-
"""
/***************************************************************************

                                 QgisLocator

                             -------------------
        begin                : 2018-05-03
        copyright            : (C) 2018 by Denis Rouzaud
        email                : denis@opengis.ch
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtWebKit import QWebSettings
from PyQt5.QtWebKitWidgets import QWebView, QWebPage
from PyQt5.QtWidgets import QSizePolicy, QDockWidget
from PyQt5.QtGui import QPalette, QDesktopServices
from qgis.core import Qgis, QgsPointXY, QgsMessageLog
from qgis.gui import QgsMapCanvas

from ..swiss_locator_plugin import DEBUG


class MapTip(QDockWidget):
    def __init__(self, map_canvas: QgsMapCanvas, html: str, point: QgsPointXY):
        super().__init__()
        self.map_canvas = map_canvas
        self.point = point
        self.web_view = QWebView(self)

        self.dbg_info('map position: {}'.format(point.asWkt()))

        self.web_view.page().setLinkDelegationPolicy(QWebPage.DelegateAllLinks)  # Handle link clicks by yourself
        self.web_view.setContextMenuPolicy(Qt.NoContextMenu)  # No context menu is allowed if you don't need it
        self.web_view.linkClicked.connect(self.on_link_clicked)

        self.web_view.page().settings().setAttribute(QWebSettings.DeveloperExtrasEnabled, True)
        self.web_view.page().settings().setAttribute(QWebSettings.JavascriptEnabled, True)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setWidget(self.web_view)

        # assure the map tip is never larger than half the map canvas
        max_width = int(self.map_canvas.geometry().width() / 1.1)
        max_height = int(self.map_canvas.geometry().height() / 1.1)
        self.dbg_info('max size {} {}'.format(max_height, max_width))
        self.setMaximumSize(max_width, max_height)

        # start with 0 size,
        # the content will automatically make it grow up to MaximumSize
        self.resize(300, 200)
        pixel_position = self.map_canvas.mapSettings().mapToPixel().transform(self.point)
        pixel_position = self.map_canvas.mapToGlobal(QPoint(pixel_position.x(), pixel_position.y()))
        self.move(pixel_position.x() + 10, pixel_position.y() + 10)

        background_color = self.palette().base().color()
        background_color.setAlpha(235)
        stroke_color = self.palette().shadow().color()
        #self.setStyleSheet(".QDocWidget{{ border: 1px solid {stroke}; background-color: {bg} }}"
        #                          .format(stroke=stroke_color.name(QColor.HexArgb),
        #                                  bg=background_color.name(QColor.HexArgb)))

        palette = self.web_view.palette()
        palette.setBrush(QPalette.Base, Qt.transparent)
        palette.setBrush(QPalette.Base, background_color)
        self.web_view.page().setPalette(palette)
        self.web_view.setAttribute(Qt.WA_OpaquePaintEvent, False)

        body_style = "background-color: {bg}; margin: 0".format(bg=background_color)
        container_style = "display: inline-block; margin: 0px"

        body_html = "<html><body style='{body_style}'>" \
                    "<div id='QgsWebViewContainer' style='{container_style}'>{html}</div><" \
                    "/body></html>".format(body_style=body_style,
                                           container_style=container_style,
                                           html=html)

        self.web_view.setHtml(body_html)

        self.setWindowOpacity(0.9)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint ^ Qt.WindowMinimizeButtonHint)
        self.show()

        scrollbar_width = self.web_view.page().mainFrame().scrollBarGeometry(Qt.Vertical).width()
        scrollbar_height = self.web_view.page().mainFrame().scrollBarGeometry(Qt.Horizontal).height()
        if scrollbar_width > 0 or scrollbar_height > 0:
            # Get the content size
            container = self.web_view.page().mainFrame().findFirstElement("#QgsWebViewContainer")
            width = container.geometry().width() + 25 + scrollbar_width
            height = container.geometry().height() + 25 + scrollbar_height

            #self.resize(width, height)

    def on_link_clicked(self, url):
        QDesktopServices.openUrl(url)

    def info(self, msg="", level=Qgis.Info):
        QgsMessageLog.logMessage('{} {}'.format(self.__class__.__name__, msg), 'QgsLocatorFilter', level)

    def dbg_info(self, msg=""):
        if DEBUG:
            self.info(msg)
