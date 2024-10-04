#!/usr/bin/env python3
#  -*- coding: utf-8 -*-
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
import json
from swiss_locator.core.parameters import AVAILABLE_LANGUAGES
from swiss_locator.core.settings import Settings


def data_file(lang: str):
    cur_dir = os.path.dirname(__file__)
    return os.path.join(cur_dir, "layers_{}.json".format(lang))


def searchable_layers(lang: str, restrict: bool = False) -> dict:
    """
    Returns the searchable layers
    :param lang: 2 characters lang.
    :param restrict: if True, restrict from the list from settings if restriction is enabled
    :return: a dict of searchable layers (key: layer id, value: description in given language)
    """
    assert lang in AVAILABLE_LANGUAGES.values()

    settings = Settings()
    restrict_enabled_by_user = settings.feature_search_restrict.value()
    restrict_layer_list = settings.feature_search_layers_list.value()

    layers = {}

    with open(data_file(lang), "r") as f:
        content = f.read()

    data = json.loads(content)
    translations_api = data["translations"]

    for layer in data["searchableLayers"]:
        if restrict and restrict_enabled_by_user and layer not in restrict_layer_list:
            continue
        layers[layer] = translations_api[layer]

    return layers
