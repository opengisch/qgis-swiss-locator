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

from PyQt5.QtCore import Qt
from PyQt5.QtWebKit import QWebSettings
from PyQt5.QtWebKitWidgets import QWebView, QWebPage
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QSizePolicy
from PyQt5.QtGui import QColor, QPalette, QDesktopServices
from qgis.core import Qgis, QgsPointXY, QgsMessageLog
from qgis.gui import QgsMapCanvas

from ..swiss_locator_plugin import DEBUG


class MapTip():
    def __init__(self, map_canvas: QgsMapCanvas, html: str, point: QgsPointXY):

        self.widget = QWidget(map_canvas)
        self.web_view = QWebView(self.widget)

        pixel_position = map_canvas.mapSettings().mapToPixel().transform(point)

        self.dbg_info(point.asWkt())
        self.dbg_info('pix: {} {}'.format(pixel_position.x(), pixel_position.y()))

        self.web_view.page().setLinkDelegationPolicy(QWebPage.DelegateAllLinks)  # Handle link clicks by yourself
        self.web_view.setContextMenuPolicy(Qt.NoContextMenu)  # No context menu is allowed if you don't need it
        self.web_view.linkClicked.connect(self.on_link_clicked)

        self.web_view.page().settings().setAttribute(QWebSettings.DeveloperExtrasEnabled, True)
        self.web_view.page().settings().setAttribute(QWebSettings.JavascriptEnabled, True)

        self.layout = QHBoxLayout()
        self.layout.addWidget(self.web_view)

        self.widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.widget.setLayout(self.layout)

        # assure the map tip is never larger than half the map canvas
        max_width = map_canvas.geometry().width() / 2
        max_height = map_canvas.geometry().height() / 2
        self.dbg_info('max {} {}'.format(max_height, max_width))
        self.widget.setMaximumSize(max_width, max_height)

        # start with 0 size,
        # the content will automatically make it grow up to MaximumSize
        self.widget.resize(300, 200)

        background_color = self.widget.palette().base().color()
        background_color.setAlpha(220)
        stroke_color = self.widget.palette().shadow().color()
        self.widget.setStyleSheet(".QWidget{{ border: 1px solid {stroke}; background-color: {bg} }}"
                                  .format(stroke=stroke_color.name(QColor.HexArgb), bg=background_color.name(QColor.HexArgb)))

        palette = self.web_view.palette()
        palette.setBrush(QPalette.Base, Qt.transparent)
        self.web_view.page().setPalette(palette)
        self.web_view.setAttribute(Qt.WA_OpaquePaintEvent, False)

        body_style = "background-color: {bg}; margin: 0".format(bg=background_color)
        container_style = "display: inline-block; margin: 0px"

        body_html = "<html><body style='{body_style}'>" \
                    "<div id='QgsWebViewContainer' style='{container_style}'>{html}</div><" \
                    "/body></html>".format(body_style=body_style,
                                           container_style=container_style,
                                           html=html )

        self.widget.move(pixel_position.x(), pixel_position.y())

        self.web_view.setHtml(body_html)

        self.widget.show()

        scrollbar_width = self.web_view.page().mainFrame().scrollBarGeometry(Qt.Vertical).width()
        scrollbar_height = self.web_view.page().mainFrame().scrollBarGeometry(Qt.Horizontal).height()
        if scrollbar_width > 0 or scrollbar_height > 0:
            # Get the content size
            container = self.web_view.page().mainFrame().findFirstElement("#QgsWebViewContainer")
            width = container.geometry().width() + 5 + scrollbar_width
            height = container.geometry().height() + 5 + scrollbar_height

            self.widget.resize(width, height)

    def on_link_clicked(self, url):
        QDesktopServices.openUrl(url)

    def info(self, msg="", level=Qgis.Info):
        QgsMessageLog.logMessage('{} {}'.format(self.__class__.__name__, msg), 'QgsLocatorFilter', level)

    def dbg_info(self, msg=""):
        if DEBUG:
            self.info(msg)
