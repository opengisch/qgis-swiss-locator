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

import json
import urllib.request


def main():

    AVAILABLE_LANGUAGES = ('de', 'de', 'fr', 'it', 'rm', 'en')
    names = ["chargeableLayers", "notChargeableLayers", "tooltipLayers", "searchableLayers"]
    counts = {}

    for lang in AVAILABLE_LANGUAGES:
        counts[lang] = {}

        url = 'https://api3.geo.admin.ch/rest/services/api/faqlist?lang={}'.format(lang)
        contents = urllib.request.urlopen(url).read().decode('utf-8')
        with open('layers_{}.data'.format(lang), 'w') as f:
            f.write(contents)

        data = json.loads(contents)
        translations_api = data['translations']

        #print(translations_api)

        for name in names:
            counts[lang][name] = 0
            already_print = False
            for layer in data[name]:
                counts[lang][name] += 1
                if already_print:
                    continue
                print(layer, translations_api[layer])
                already_print = True

    for lang in AVAILABLE_LANGUAGES:
        print('****** {}'.format(lang))
        for name in names:
            print('{}: {}'.format(name, counts[lang][name]))


if __name__ == "__main__":
    main()