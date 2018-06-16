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
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os
from PyQt5.QtWidgets import QDialog
from PyQt5.uic import loadUiType

from ..qgissettingmanager.setting_dialog import SettingDialog, UpdateMode
from ..core.settings import Settings

DialogUi, _ = loadUiType(os.path.join(os.path.dirname(__file__), '../ui/config.ui'))


class ConfigDialog(QDialog, DialogUi, SettingDialog):
    def __init__(self, parent=None):
        settings = Settings()
        QDialog.__init__(self, parent)
        SettingDialog.__init__(self, setting_manager=settings, mode=UpdateMode.DialogAccept)
        self.setupUi(self)
        self.lang.addItem(self.tr('use the application locale, defaults to English'), '')
        from ..swiss_locator_filter import AVAILABLE_LANGUAGES
        for key, val in AVAILABLE_LANGUAGES.items():
            self.lang.addItem(key, val)
        self.crs.addItem(self.tr('Use map CRS if possible, defaults to CH1903+'), 'project')
        self.crs.addItem('CH 1903+ (EPSG:2056)', '2056')
        self.crs.addItem('CH 1903 (EPSG:21781)', '21781')
        self.settings = settings
        self.init_widgets()