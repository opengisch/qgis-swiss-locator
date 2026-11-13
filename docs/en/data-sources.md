# Data sources

The plugin queries the services of the federal geoportal, of opendata.swiss
and of the cantons. It needs an internet connection.

| Service | Used by |
|---------|---------|
| [api3.geo.admin.ch](https://api3.geo.admin.ch) | locations, geocoding, WMS layers, features, elevation profile |
| [wms.geo.admin.ch](https://wms.geo.admin.ch) | WMS layers |
| [wmts.geo.admin.ch](https://wmts.geo.admin.ch) | WMTS layers |
| [vectortiles.geo.admin.ch](https://vectortiles.geo.admin.ch) | base maps |
| [data.geo.admin.ch](https://data.geo.admin.ch) | downloads |
| [viageo.ch](https://viageo.ch) | downloads |
| [opendata.swiss](https://opendata.swiss) and the WMS services it references | WMS layers |
| [opengisch.github.io/qgis-swiss-locator](https://opengisch.github.io/qgis-swiss-locator/data/v1/index.json) | WMS layers, features |

The data belongs to its publishers: check their terms of use before you
publish it.

## The data catalogues (STAC)

The [downloads](downloads/index.md) come from two data catalogues: that of the
federal geoportal, [data.geo.admin.ch](https://data.geo.admin.ch), and
[viageo.ch](https://viageo.ch), which publishes the geodata of cantons and
municipalities. Both follow the STAC standard (SpatioTemporal Asset Catalog),
and organise the data in:

- **collections**, the datasets, such as swissALTI3D;
- **items**, the parts of a dataset in space or time, such as a tile of one
  square kilometre at a date;
- **assets**, the files of an item, by format, resolution and coordinate
  system.

When QGIS starts, the plugin downloads the list of the collections of each
catalogue, in the background. The titles and descriptions of data.geo.admin.ch
in the language of the plugin come from the metadata catalogue
[geocat.ch](https://www.geocat.ch); those of viageo.ch are in French. A search
looks for the text in the titles and identifiers of these lists, without a
request. For each collection found, the plugin then asks for its first files:
when they are few, they are listed; otherwise, the collection opens the filter
panel.

The filter panel asks the catalogue for the items of the chosen extent, and
lists their assets by file type, resolution, timestamp and coordinate system.
It comes from the plugin [Swiss Geo Downloader](https://pimoll.github.io/swissgeodownloader/),
by Patricia Moll.

A Cloud Optimized GeoTIFF or Point Cloud added as *streamed* stays on the
server of its catalogue: QGIS reads the parts it displays over the network.

## Files published by the plugin

Two searches rely on lists the plugin prepares, as searching them online would
be too slow:

- the layers of map.geo.admin.ch whose features can be searched, for the
  [feature search](search/features.md);
- the layers of the WMS services referenced by opendata.swiss, for the
  [WMS layers](layers/wms.md).

A GitHub workflow of the repository of the plugin generates them regularly and publishes them on
[GitHub Pages](https://opengisch.github.io/qgis-swiss-locator/data/v1/index.json),
next to this documentation. QGIS checks for a new version at most once a day,
in the background, and keeps a copy in its profile. Each release of the
plugin also bundles a copy, used when GitHub cannot be reached.

A service of opendata.swiss that does not answer keeps its layers in the list
for up to 30 days.
