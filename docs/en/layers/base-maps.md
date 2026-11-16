# Base maps

Prefix: `chb`

Add a base map of swisstopo, as vector tiles:

- **Base map**, in colour;
- **Light base map**, in light grey, to put your data forward;
- **Imagery base map**, aerial imagery with roads and names.

Vector tiles stay sharp at any scale.

Added to an empty project, a base map puts the project in LV95 (EPSG:2056),
rather than in Web Mercator, the CRS of the tiles. When **Use a default CRS**
is chosen in **Settings ▸ Options ▸ CRS and Transforms ▸ CRS Handling**, the
project keeps that CRS.

## Example

Type `chb` followed by a space: the three base maps are listed.

![The base maps](../assets/screenshots/base-maps-search.png)

Double-click **Light base map**. It is added at the bottom of the layers, under
your data.

![The light base map over Bern](../assets/screenshots/base-maps-result.png)
