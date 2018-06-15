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
import swiss_locator.swiss_locator_filter


def data_file(lang: str):
    cur_dir = os.path.dirname(__file__)
    return os.path.join(cur_dir, 'layers_{}.data'.format(lang))


def searchable_layers(lang: str) -> (dict, str):
    """
    Returns the searchable layers
    :param lang: 2 characters lang.
    :return: a dict of searchable layers (key: layer id, value: description in given language)
    """
    assert lang in swiss_locator.swiss_locator_filter.AVAILABLE_LANGUAGES.values()

    layers = {}

    with open(data_file(lang), 'r') as f:
        content = f.read()

    data = json.loads(content)
    translations_api = data['translations']

    for layer in data['searchableLayers']:
        layers[layer] = translations_api[layer]

    return layers
