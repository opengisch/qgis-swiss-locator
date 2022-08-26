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

from PyQt5.QtCore import pyqtSignal, QPointF, QSizeF
from PyQt5.QtGui import QColor, QDesktopServices, QCloseEvent
from qgis.core import Qgis, QgsPointXY, QgsMessageLog, QgsHtmlAnnotation
from qgis.gui import QgisInterface

from swiss_locator import DEBUG


class MapTip(QgsHtmlAnnotation):

    closed = pyqtSignal()

    def __init__(self, iface: QgisInterface, html: str, point: QgsPointXY):
        super().__init__()
        self.map_canvas = iface.mapCanvas()

        body_style = "background-color: white; margin: 0"
        container_style = "display: inline-block; margin: 0px"
        body_html = (
            f"<html><body style='{body_style}'>"
            f"<div id='QgsWebViewContainer' style='{container_style}'>"
            f"{html}"
            "</div></body></html>"
        )

        self.fillSymbol().symbolLayer(0).setStrokeColor(QColor(0, 0, 0))
        self.markerSymbol().symbolLayer(0).setStrokeColor(QColor(0, 0, 0))
        self.setFrameSizeMm(QSizeF(400 / 3.7795275, 250 / 3.7795275))
        self.setFrameOffsetFromReferencePointMm(QPointF(70 / 3.7795275, 90 / 3.7795275))
        self.setHtmlSource(body_html)

        self.setMapPositionCrs(iface.mapCanvas().mapSettings().destinationCrs())
        self.setMapPosition(point)

        self.linkClicked.connect(self.on_link_clicked)

    @staticmethod
    def on_link_clicked(url):
        QDesktopServices.openUrl(url)

    def closeEvent(self, event: QCloseEvent):
        self.closed.emit()

    def info(self, msg="", level=Qgis.Info):
        QgsMessageLog.logMessage(
            "{} {}".format(self.__class__.__name__, msg), "Locator bar", level
        )

    def dbg_info(self, msg=""):
        if DEBUG:
            self.info(msg)
