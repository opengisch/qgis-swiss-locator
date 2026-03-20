#!/usr/bin/env python3
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

import json
import urllib.request


def main():
    AVAILABLE_LANGUAGES = ("de", "fr", "it", "rm", "en")

    for lang in AVAILABLE_LANGUAGES:
        url = f"https://api3.geo.admin.ch/rest/services/all/MapServer/layersConfig?lang={lang}"
        raw = urllib.request.urlopen(url).read().decode("utf-8")
        layers_config = json.loads(raw)

        translations = {}
        searchable_layers = []

        for layer_id, props in sorted(layers_config.items()):
            label = props.get("label", layer_id)
            translations[layer_id] = label
            if props.get("searchable"):
                searchable_layers.append(layer_id)

        output = {
            "translations": translations,
            "searchableLayers": searchable_layers,
        }

        with open(f"layers_{lang}.json", "w") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(
            f"****** {lang}: {len(searchable_layers)} searchable / {len(translations)} total"
        )


if __name__ == "__main__":
    main()
