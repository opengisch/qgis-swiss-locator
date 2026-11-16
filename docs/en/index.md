# Swiss Locator

Swiss Locator is the Swiss Army knife of QGIS, with the main goal of bringing
the solutions offered by swisstopo and some cantonal actors into QGIS.

Type in the
[locator bar](https://docs.qgis.org/3.44/en/docs/user_manual/introduction/qgis_gui.html#locator-bar)
of QGIS, as you would on [map.geo.admin.ch](https://map.geo.admin.ch), and find:

- **places**: cantons, municipalities, districts, ZIP codes, addresses,
  parcels and the names of the national map;
- **map layers** of the federal geoportal and of the cantonal services
  referenced by [opendata.swiss](https://opendata.swiss), as WMS or WMTS;
- **base maps** of swisstopo, as vector tiles;
- **features** of the layers of the geoportal, such as a public transport stop
  or a mountain hut;
- **files to download** from the data catalogues of the geoportal, of
  [viageo.ch](https://viageo.ch) for cantons and municipalities, and of
  [Basel-Stadt](https://www.geo.bs.ch) (STAC).

It also draws the terrain of swissALTI3D in the **elevation profiles** of
QGIS, and [geocodes](geocoding.md) **tables of addresses** with Processing.

In a minute: a base map, a place and an elevation profile, then the lidar
data of swissSURFACE3D, selected on the map, downloaded and shown in 3D.

<video controls muted playsinline preload="none" width="100%"
       poster="assets/images/demo.jpg"
       src="https://github.com/user-attachments/assets/e1571d17-ff0a-41a3-ae48-93357aeb86c0"></video>

## Get started

1. In QGIS, open **Plugins ▸ Manage and Install Plugins**, search for
   *Swiss Locator* and install it. It needs QGIS 3.44 or newer.
2. Click in the locator bar, at the bottom left of the window, or press
   ++ctrl+k++.
3. Type a place, such as `Lausanne`, and double-click a result.

[Getting started](getting-started.md) explains the locator bar. Then
[search for locations and features](search/index.md),
[add layers](layers/index.md) or [download data](downloads/swisstopo.md).

## About

The plugin is developed by [OPENGIS.ch](https://opengis.ch) with the support of
the [Swiss QGIS user group](https://qgis.ch). Its code is on
[GitHub](https://github.com/opengisch/qgis-swiss-locator), where you can report
issues.
