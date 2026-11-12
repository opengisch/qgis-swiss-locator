# Data sources

The plugin queries the services of the federal geoportal, of opendata.swiss
and of the cantons. It needs an internet connection.

| Service | Used by |
|---------|---------|
| [api3.geo.admin.ch](https://api3.geo.admin.ch) | locations, map layers, features, elevation profile |
| [wms.geo.admin.ch](https://wms.geo.admin.ch) | map layers |
| [wmts.geo.admin.ch](https://wmts.geo.admin.ch) | WMTS layers |
| [vectortiles.geo.admin.ch](https://vectortiles.geo.admin.ch) | base maps |
| [data.geo.admin.ch](https://data.geo.admin.ch) | file downloads |
| [opendata.swiss](https://opendata.swiss) and the WMS services it references | map layers |
| [opengisch.github.io/qgis-swiss-locator](https://opengisch.github.io/qgis-swiss-locator/data/v1/index.json) | map layers, features |

The data belongs to its publishers: check their terms of use before you
publish it.

## Files published by the plugin

Two searches rely on lists the plugin prepares, as searching them online would
be too slow:

- the layers of map.geo.admin.ch whose features can be searched, for the
  [feature search](search/features.md);
- the layers of the WMS services referenced by opendata.swiss, for the
  [map layers](search/layers.md).

A GitHub workflow of the repository of the plugin generates them regularly and publishes them on
[GitHub Pages](https://opengisch.github.io/qgis-swiss-locator/data/v1/index.json),
next to this documentation. QGIS checks for a new version at most once a day,
in the background, and keeps a copy in its profile. Each release of the
plugin also bundles a copy, used when GitHub cannot be reached.

A service of opendata.swiss that does not answer keeps its layers in the list
for up to 30 days.
