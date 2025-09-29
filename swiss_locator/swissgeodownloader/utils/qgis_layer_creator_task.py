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

from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsRasterLayer,
    QgsTask,
    QgsVectorLayer
)

from swiss_locator.swissgeodownloader.api.response_objects import SgdAsset
from swiss_locator.swissgeodownloader.utils.utilities import translate


def createQgisLayersInTask(fileList: list[SgdAsset], callback):
    # Create layer from files (streamed and downloaded) so they can be
    # added to qgis
    task = QgisLayerCreatorTask(
            translate('SGD', 'Daten zu QGIS hinzufügen'),
            fileList)
    task.taskCompleted.connect(
            lambda: callback(task.layerList, task.alreadyAdded))
    task.taskTerminated.connect(callback)
    QgsApplication.taskManager().addTask(task)


class QgisLayerCreatorTask(QgsTask):
    """ QGIS can freeze when a lot of layers have to be created in the main
     thread. Instead, layers are created in this separate QTask and moved to
     the main thread. After the task has finished, they are added to the map
     in the main thread."""
    
    def __init__(self, description, fileList: list[SgdAsset]):
        super().__init__(description, QgsTask.Flag.CanCancel)
        self.fileList = fileList
        self.layerList: list[QgsRasterLayer | QgsVectorLayer] = []
        self.alreadyAdded: int = 0
        self.exception = None
    
    def run(self):
        if not self.fileList or len(self.fileList) == 0:
            return True
        
        qgsProject = QgsProject.instance()
        already_added = [lyr.source() for lyr in
            qgsProject.mapLayers().values()]
        
        progressStep = 100 / len(self.fileList)
        
        for i, file in enumerate(self.fileList):
            if self.isCanceled():
                return False
            
            self.setProgress(i * progressStep)
            
            # Adding the file to QGIS if it's (1) a streamed file or (2) is
            #  present in the file system and (3) is not a .zip
            if file.isStreamable or os.path.exists(file.path):
                if '.zip' in file.id:
                    # Can't add zip files to QGIS
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
    
    def finished(self, result):
        if not result:
            if self.isCanceled():
                self.exception = self.tr('Aborted by user')
            elif self.exception is None:
                self.exception = self.tr('An unknown error occurred')
