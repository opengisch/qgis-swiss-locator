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
from qgis.core import Qgis, QgsTask

from swiss_locator.swissgeodownloader.utils.utilities import (
    MESSAGE_CATEGORY,
    log
)


class ApiCallerTask(QgsTask):
    
    def __init__(self, apiRef, msgBar=None, description='', **kwargs):
        super().__init__(description, QgsTask.Flag.CanCancel)
        self.apiRef = apiRef
        self.msgBar = msgBar
        self.kwargs = kwargs
        self.output = None
        self.exception = None
        self.successMsg = self.tr('request completed')
    
    def run(self):
        try:
            self.run_task()
            return True
        except Exception as e:
            if not self.exception:
                msg = self.tr('An unknown error occurred')
                self.exception = f"{msg}: {e}"
            raise e
    
    def run_task(self):
        raise NotImplementedError
    
    def finished(self, result):
        """This function is called when the task has completed, successfully or not"""
        if self.isCanceled():
            log(self.tr('Aborted by user'))
        elif result and self.output is not False:
            log(self.successMsg, Qgis.MessageLevel.Success)
        else:
            log(self.exception, Qgis.MessageLevel.Critical)
            self.message(self.exception, Qgis.MessageLevel.Warning)
    
    def message(self, msg, level=Qgis.MessageLevel.Info):
        if self.msgBar:
            self.msgBar.pushMessage(f"{MESSAGE_CATEGORY}: {msg}", level)


class GetCollectionsTask(ApiCallerTask):
    def run_task(self):
        self.successMsg = self.tr('available datasets received')
        self.output = self.apiRef.getCollections(self)


class AnalyseCollectionTask(ApiCallerTask):
    def run_task(self):
        self.successMsg = self.tr('available datasets received')
        self.output = self.apiRef.analyseCollectionItems(self, **self.kwargs)


class GetFileListTask(ApiCallerTask):
    def run_task(self):
        self.successMsg = self.tr('file list received')
        self.output = self.apiRef.getFileList(self, **self.kwargs)


class DownloadFilesTask(ApiCallerTask):
    def run_task(self):
        self.successMsg = self.tr('files downloaded')
        self.output = self.apiRef.downloadFiles(self, **self.kwargs)
