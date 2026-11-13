"""
/***************************************************************************
 SwissGeoDownloader
                                 A QGIS plugin
 This plugin lets you comfortably download swiss geo data.
                             -------------------
        begin                : 2021-03-14
        copyright            : (C) 2025 by Patricia Moll
        email                : pimoll.dev@gmail.com
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

import os
import shutil
import zipfile
from typing import NamedTuple

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsPointCloudLayer,
    QgsProject,
    QgsProviderRegistry,
    QgsProviderSublayerDetails,
    QgsRasterLayer,
    QgsTask,
    QgsVectorLayer,
)

try:
    from qgis._3d import QgsPointCloudLayer3DRenderer
except ImportError:
    # QGIS built without 3D
    QgsPointCloudLayer3DRenderer = None

from swiss_locator.swissgeodownloader.api.response_objects import SgdAsset
from swiss_locator.swissgeodownloader.utils.utilities import log, translate

POINT_CLOUD_EXTENSIONS = (".las", ".laz")
# Files and folders (FileGDB) of a zip that are datasets
DATASET_EXTENSIONS = (
    ".csv",
    ".dwg",
    ".dxf",
    ".fgb",
    ".gdb",
    ".geojson",
    ".gpkg",
    ".itf",
    ".shp",
    ".tif",
    ".xtf",
)


class PointCloudSource(NamedTuple):
    source: str
    name: str
    provider: str
    # EPSG code from the STAC metadata, for files without CRS
    coordsys: str | None


def isPointCloud(path: str) -> bool:
    return path.lower().endswith(POINT_CLOUD_EXTENSIONS)


def pointCloudProvider(path: str) -> str:
    # COPC files are read as they are, other LAS/LAZ files are indexed by PDAL
    return "copc" if path.lower().endswith(".copc.laz") else "pdal"


def extractPointClouds(zipPath: str) -> list[str]:
    """Extract the point clouds of a zip file next to it, since PDAL cannot
    read inside a zip. They are named after the zip, because the names inside
    (e.g. 2496_1115.las) do not tell the years of a tile apart."""
    zipName = os.path.basename(zipPath)
    if zipName.lower().endswith(".zip"):
        zipName = zipName[: -len(".zip")]

    paths = []
    with zipfile.ZipFile(zipPath) as zf:
        members = [
            m for m in zf.infolist() if not m.is_dir() and isPointCloud(m.filename)
        ]
        for member in members:
            memberName = os.path.basename(member.filename)
            extension = os.path.splitext(memberName)[1].lower()
            if len(members) == 1 and zipName.lower().endswith(extension):
                name = zipName
            else:
                name = f"{zipName}_{memberName}"
            path = os.path.join(os.path.dirname(zipPath), name)
            # Keep a file extracted before, it may already be open in QGIS
            if not (os.path.exists(path) and os.path.getsize(path) == member.file_size):
                with zf.open(member) as src, open(path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            paths.append(path)
    return paths


def isZippedDataset(file: SgdAsset) -> bool:
    """A downloaded zip file whose STAC media type is the format of the dataset
    inside, e.g. a GeoPackage from Basel-Stadt. The zip files of
    data.geo.admin.ch have zip media types, e.g. application/x.geopackage+zip."""
    return (
        ".zip" in file.id
        and "zip" not in (file.mediaType() or "").lower()
        and zipfile.is_zipfile(file.path)
    )


def zippedDatasets(zipPath: str) -> list[str]:
    """The datasets of a zip file, as paths GDAL reads inside the zip"""
    datasets = []
    with zipfile.ZipFile(zipPath) as zf:
        for name in zf.namelist():
            parts = name.rstrip("/").split("/")
            # The dataset is the first part with its extension, e.g. the
            #  folder of a FileGDB
            for i, part in enumerate(parts):
                if part.lower().endswith(DATASET_EXTENSIONS):
                    dataset = "/".join(parts[: i + 1])
                    if dataset not in datasets:
                        datasets.append(dataset)
                    break
    return [f"/vsizip/{zipPath}/{dataset}" for dataset in datasets]


def layersOfZippedDatasets(zipPath: str) -> list[QgsVectorLayer | QgsRasterLayer]:
    options = QgsProviderSublayerDetails.LayerOptions(QgsCoordinateTransformContext())
    layers = []
    for dataset in zippedDatasets(zipPath):
        for sublayer in QgsProviderRegistry.instance().querySublayers(dataset):
            if sublayer.type() not in (Qgis.LayerType.Vector, Qgis.LayerType.Raster):
                continue
            layer = sublayer.toLayer(options)
            if layer and layer.isValid():
                layers.append(layer)
    return layers


def setup3DRenderer(layer: QgsPointCloudLayer):
    """Give a point cloud the 3D renderer QGIS gives to the point clouds it
    adds itself, so it shows in 3D map views. The layer keeps it in sync with
    its 2D renderer, which PDAL only sets once the file is indexed."""
    if QgsPointCloudLayer3DRenderer is None:
        return
    if layer.renderer3D() or not layer.sync3DRendererTo2DRenderer():
        return
    renderer3D = QgsPointCloudLayer3DRenderer()
    renderer3D.convertFrom2DRenderer(layer.renderer())
    layer.setRenderer3D(renderer3D)


def createQgisLayersInTask(fileList: list[SgdAsset], callback):
    # Create layer from files (streamed and downloaded) so they can be
    # added to qgis
    task = QgisLayerCreatorTask(translate("SGD", "Add data to QGIS"), fileList)
    task.taskCompleted.connect(lambda: callback(task.layerList, task.alreadyAdded))
    task.taskTerminated.connect(callback)
    QgsApplication.taskManager().addTask(task)


class QgisLayerCreatorTask(QgsTask):
    """QGIS can freeze when a lot of layers have to be created in the main
    thread. Instead, layers are created in this separate QTask and moved to
    the main thread. After the task has finished, they are added to the map
    in the main thread.
    Point cloud layers are the exception: they are created in finished(), in
    the main thread, since PDAL indexes the file in a task of its own that
    reports back to the layer."""

    def __init__(self, description, fileList: list[SgdAsset]):
        super().__init__(description, QgsTask.Flag.CanCancel)
        self.fileList = fileList
        self.layerList: list[QgsRasterLayer | QgsVectorLayer | QgsPointCloudLayer] = []
        # Point clouds to create in the main thread
        self.pointClouds: list[PointCloudSource] = []
        self.alreadyAdded: int = 0
        self.exception = None

    def run(self):
        if not self.fileList or len(self.fileList) == 0:
            return True

        qgsProject = QgsProject.instance()
        already_added = [lyr.source() for lyr in qgsProject.mapLayers().values()]

        progressStep = 100 / len(self.fileList)

        for i, file in enumerate(self.fileList):
            if self.isCanceled():
                return False

            self.setProgress(i * progressStep)

            try:
                pointClouds = self.pointCloudsOf(file)
            except (OSError, zipfile.BadZipFile) as e:
                log(
                    f"File {file.id}: Unable to extract point clouds: {e}",
                    Qgis.MessageLevel.Warning,
                )
                continue
            if pointClouds:
                # Point cloud layers are created in the main thread
                for pointCloud in pointClouds:
                    if pointCloud.source in already_added:
                        self.alreadyAdded += 1
                    else:
                        self.pointClouds.append(pointCloud)
                continue

            # Adding the file to QGIS if it's (1) a streamed file or (2) is
            #  present in the file system and (3) is not a .zip
            if file.isStreamable or os.path.exists(file.path):
                if ".zip" in file.id:
                    # Add the dataset of a zip whose format is known, other zip
                    #  files are only downloaded
                    if not file.isStreamable and isZippedDataset(file):
                        for layer in layersOfZippedDatasets(file.path):
                            if layer.source() in already_added:
                                self.alreadyAdded += 1
                            else:
                                self.layerList.append(layer)
                    continue
                if file.path in already_added:
                    self.alreadyAdded += 1
                    continue
                try:
                    rasterLyr = QgsRasterLayer(file.path, file.id)
                    if rasterLyr.isValid():
                        self.layerList.append(rasterLyr)
                        continue
                    else:
                        del rasterLyr
                except Exception:
                    pass
                try:
                    vectorLyr = QgsVectorLayer(file.path, file.id, "ogr")
                    if vectorLyr.isValid():
                        self.layerList.append(vectorLyr)
                        continue
                    else:
                        del vectorLyr
                except Exception:
                    pass

        self.setProgress(100)
        return True

    @staticmethod
    def pointCloudsOf(file: SgdAsset) -> list[PointCloudSource]:
        """Return the point clouds of a streamed or downloaded file,
        extracting them from zip files."""
        coordsys = file.coordsys
        if file.isStreamable:
            uri = file.uri()
            if uri.layerType == "pointcloud":
                return [PointCloudSource(uri.uri, file.id, uri.providerKey, coordsys)]
            return []
        if not os.path.exists(file.path):
            return []
        if ".zip" in file.id:
            return [
                PointCloudSource(
                    path, os.path.basename(path), pointCloudProvider(path), coordsys
                )
                for path in extractPointClouds(file.path)
            ]
        if isPointCloud(file.path):
            return [
                PointCloudSource(
                    file.path, file.id, pointCloudProvider(file.path), coordsys
                )
            ]
        return []

    def finished(self, result):
        if result:
            for pointCloud in self.pointClouds:
                layer = QgsPointCloudLayer(
                    pointCloud.source, pointCloud.name, pointCloud.provider
                )
                if not layer.isValid():
                    log(
                        f"Unable to load point cloud {pointCloud.source}",
                        Qgis.MessageLevel.Warning,
                    )
                    continue
                # Older swissSURFACE3D LAS files have no CRS in their header
                if not layer.crs().isValid() and pointCloud.coordsys:
                    layer.setCrs(
                        QgsCoordinateReferenceSystem(f"EPSG:{pointCloud.coordsys}")
                    )
                setup3DRenderer(layer)
                self.layerList.append(layer)
        if not result:
            if self.isCanceled():
                self.exception = self.tr("Aborted by user")
            elif self.exception is None:
                self.exception = self.tr("An unknown error occurred")
