# -*- coding: utf-8 -*-
# -----------------------------------------------------------
#
# QGIS Swiss Locator Plugin
# Copyright (C) 2018 Denis Rouzaud
#
# -----------------------------------------------------------
#
# licensed under the terms of GNU GPL 2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# ---------------------------------------------------------------------

from qgis.PyQt.QtCore import QLocale, QSettings
from .settings import Settings
from qgis.core import NULL
from .parameters import AVAILABLE_LANGUAGES


def get_language() -> str:
    """
    Returns the language to be used.
    Reads from the settings, if it's None, try to use the locale one and defaults to English
    :return: 2 chars long string representing the language to be used
    """
    # get lang from settings
    lang = Settings().lang.value()
    if not lang:
        locale = str(QSettings().value("locale/userLocale")).replace(str(NULL), "en_CH")
        locale_lang = QLocale.languageToString(QLocale(locale).language())
        if locale_lang in AVAILABLE_LANGUAGES.keys():
            lang = AVAILABLE_LANGUAGES[locale_lang]
    if lang not in AVAILABLE_LANGUAGES.values():
        lang = "en"

    return lang
