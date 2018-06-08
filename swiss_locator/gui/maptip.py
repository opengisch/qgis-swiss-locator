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
        #self.widget.resize(0, 0)

        background_color = self.widget.palette().base().color().name()
        stroke_color = self.widget.palette().shadow().color().name()
        self.widget.setStyleSheet(".QWidget{{ border: 1px solid {stroke}; background-color: {bg} }}"
                                  .format(stroke=stroke_color, bg=background_color))

        body_style = "background-color: {bg}; margin: 0".format(bg=background_color)
        container_style = "display: inline-block; margin: 0px"

        """
        tipHtml = QString(
              "<html>"
              "<body style='%1'>"
              "<div id='QgsWebViewContainer' style='%2'>%3</div>"
              "</body>"
              "</html>" ).arg( bodyStyle, containerStyle, tipText );
        """

        self.widget.move(pixel_position.x(), pixel_position.y())

        self.web_view.setHtml(html)

        self.widget.show()

        """
        #if WITH_QTWEBKIT
        int scrollbarWidth = self.web_view.page().mainFrame().scrollBarGeometry(
                             Qt.Vertical ).width()
        int scrollbarHeight = self.web_view.page().mainFrame().scrollBarGeometry(
                              Qt.Horizontal ).height()
        
        if ( scrollbarWidth > 0 || scrollbarHeight > 0 )
        {
        # Get the content size
        QWebElement container = self.web_view.page().mainFrame().findFirstElement(
                                  QStringLiteral( "#QgsWebViewContainer" ) )
        int width = container.geometry().width() + 5 + scrollbarWidth
        int height = container.geometry().height() + 5 + scrollbarHeight
        
        self.widget.resize( width, height )
        }
        #endif
        }
        """

    def on_link_clicked(self, url):
        pass

    def info(self, msg="", level=Qgis.Info):
        QgsMessageLog.logMessage('{} {}'.format(self.__class__.__name__, msg), 'QgsLocatorFilter', level)

    def dbg_info(self, msg=""):
        if DEBUG:
            self.info(msg)
