# Swiss Locator plugin


## What 
A Swiss Geoportal locator filter plugin for QGIS 3

Similarly to the online geoportal [https://map.geo.admin.ch](https://map.geo.admin.ch/), this plugin allows to search within [QGIS](https://qgis.org/) desktop for

* locations:
   * cantons, cities and communes,
   * all names as printed on the national map (SwissNames)
   * districts
   * ZIP codes
   * addresses
   * cadastral parcels
* WMS layers from Federal Geoportal (map.geo.admin.ch) or opendata.swiss, which can easily be added to the map
* features (search through features descriptions)


## Where

The search is performed through the QGIS [locator bar](https://qgis.org/en/site/forusers/visualchangelog30/#feature-locator-bar).

Configuration is achieved in the main application settings under the `locator` tab. You will be able to:
* enable or disable searches (locations, layers, features)
* customize prefixes, define if they are default filters (used without prefix)
* access to the configuration of the plugin

In the configuration of the plugin, further customization can be achieved:
* language definition (English, German, French, Italian, Rumantsch)
* CRS definition (project, CH1903 or CH1903+)
* defining if the plugin will try to display further information in a tool tip
* defining layers used in the feature search

## How

Type the text to search in the locator bar.

If the result is a **WMS layer**, double-clicking on it will try to add it to the map. 
It might not be possible since some layers are only visible in the geoportal.
In any case, a link will be shown to display the layer in the geoportal.
If an opendata.swiss service contains more layers, a datasource to the WMS will be established.

If the result is a **location** or **feature**, 
double-clicking on it will move the map canvas to the result and highlight its position.
If any further information can be shown, an info window will be shown over the map.
