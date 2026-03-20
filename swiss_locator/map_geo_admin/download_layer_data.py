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
    category_keys = {
        "searchable": "searchableLayers",
        "chargeable": "chargeableLayers",
        "tooltip": "tooltipLayers",
    }

    counts = {}

    for lang in AVAILABLE_LANGUAGES:
        counts[lang] = {}

        url = f"https://api3.geo.admin.ch/rest/services/all/MapServer/layersConfig?lang={lang}"
        raw = urllib.request.urlopen(url).read().decode("utf-8")
        layers_config = json.loads(raw)

        translations = {}
        categories = {name: [] for name in category_keys.values()}
        categories["notChargeableLayers"] = []

        for layer_id, props in layers_config.items():
            label = props.get("label", layer_id)
            translations[layer_id] = label

            for flag, list_name in category_keys.items():
                if props.get(flag):
                    categories[list_name].append(layer_id)

            if not props.get("chargeable"):
                categories["notChargeableLayers"].append(layer_id)

        output = {"translations": translations}
        output.update(categories)

        with open(f"layers_{lang}.json", "w") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        for name in categories:
            counts[lang][name] = len(categories[name])
            for layer_id in categories[name]:
                print(layer_id, translations[layer_id])

    for lang in AVAILABLE_LANGUAGES:
        print(f"****** {lang}")
        for name in categories:
            print(f"{name}: {counts[lang][name]}")


if __name__ == "__main__":
    main()
