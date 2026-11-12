# Downloading data (STAC)

Prefix: `chd`

Download files from the data catalogue of the geoportal,
[data.geo.admin.ch](https://data.geo.admin.ch), and add them to the map:
elevation models, aerial images, boundaries, maps and more. The search looks in
the names of the datasets.

## A dataset with a few files

Type `chd swissboundaries3d`. When a dataset has a few files, they are listed
directly, with their format.

![The files of swissBOUNDARIES3D](assets/screenshots/downloads-search.png)

Double-click a file and choose a folder: the file is downloaded, then added to
the map. Archives (ZIP) are only downloaded.

Files that QGIS can read over the network, such as Cloud Optimized GeoTIFF,
are listed twice: the second entry, marked *streamed*, adds the file to the
map without downloading it.

## A dataset with many files

Type `chd swissalti3d`. The elevation model is cut in tiles of one square
kilometre, too many to list: the result opens a filter panel.

![Searching for swissALTI3D](assets/screenshots/downloads-filter-search.png)

In the panel **Swiss Locator: Filter files to download**:

1. **Extent**: the files covering the map view, by default. It can also be the
   full extent of the dataset, the extent of a layer, a print layout map or a
   bookmark.
2. **Request file list**, then choose the **file type**, the **resolution**
   and the **timestamp**. The footprints of the files are drawn on the map.
3. **Download**.

![The files of swissALTI3D around Lausanne](assets/screenshots/downloads-filter.png)

The number of files listed directly in the locator bar can be set in the
[configuration](configuration.md).
