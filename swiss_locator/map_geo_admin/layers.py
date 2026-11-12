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

from swiss_locator.core.parameters import AVAILABLE_LANGUAGES
from swiss_locator.core.settings import Settings
from swiss_locator.remote_data import spec
from swiss_locator.remote_data.remote_data_file import RemoteDataFile


def _parse(data) -> dict[str, dict[str, str]]:
    if not isinstance(data, dict) or not all(
        isinstance(labels, dict) for labels in data.values()
    ):
        raise spec.InvalidDataFile("expected {layer_id: {lang: label}}")
    return data


SEARCHABLE_LAYERS = RemoteDataFile(spec.MAP_GEO_ADMIN_LAYERS, parse=_parse)


def searchable_layers(lang: str, restrict: bool = False) -> dict:
    """
    Returns the searchable layers
    :param lang: 2 characters lang.
    :param restrict: if True, restrict from the list from settings if restriction is enabled
    :return: a dict of searchable layers (key: layer id, value: description in given language)
    """
    assert lang in AVAILABLE_LANGUAGES.values()

    settings = Settings()
    restrict = restrict and settings.feature_search_restrict.value()
    restrict_layer_list = settings.feature_search_layers_list.value()

    layers = {}
    for layer_id, labels in (SEARCHABLE_LAYERS.data() or {}).items():
        if restrict and layer_id not in restrict_layer_list:
            continue
        layers[layer_id] = labels.get(lang) or labels.get("de") or layer_id
    return layers
