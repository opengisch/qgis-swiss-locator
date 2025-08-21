"""
/***************************************************************************
 SwissGeoDownloaderDockWidget
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

from qgis.PyQt import uic
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (QFileDialog, QMessageBox)
from qgis.core import (
    QgsRasterLayer,
    QgsVectorLayer,
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsRectangle
)
from qgis.gui import QgsDockWidget, QgisInterface, QgsExtentGroupBox

from swiss_locator.swissgeodownloader.api.apiCallerTask import (
    GetCollectionsTask,
    AnalyseCollectionTask,
    GetFileListTask,
    DownloadFilesTask
)
from swiss_locator.swissgeodownloader.api.datageoadmin import (
    API_EPSG,
    ApiDataGeoAdmin
)
from swiss_locator.swissgeodownloader.api.responseObjects import (
    ALL_VALUE, CURRENT_VALUE,
    STREAMED_SOURCE_PREFIX,
    SgdStacCollection, SgdAsset
)
from swiss_locator.swissgeodownloader.ui.bboxDrawer import BboxPainter
from swiss_locator.swissgeodownloader.ui.datsetListTable import \
    CollectionListTable
from swiss_locator.swissgeodownloader.ui.fileListTable import FileListTable
from swiss_locator.swissgeodownloader.ui.qgis_utilities import (
    RECOMMENDED_CRS,
    addLayersToQgis,
    addOverviewMap,
    switchToCrs,
    transformBbox,
    validateBbox
)
from swiss_locator.swissgeodownloader.ui.waitingSpinnerWidget import \
    QtWaitingSpinner
from swiss_locator.swissgeodownloader.utils.qgisLayerCreatorTask import \
    createQgisLayersInTask
from swiss_locator.swissgeodownloader.utils.utilities import (
    MESSAGE_CATEGORY,
    filesizeFormatter
)

UI_FILE = os.path.join(os.path.dirname(__file__), 'sgd_dockwidget_base.ui')
FORM_CLASS, _ = uic.loadUiType(UI_FILE)

VERSION = Qgis.QGIS_VERSION_INT


class SwissGeoDownloaderDockWidget(QgsDockWidget, FORM_CLASS):
    closingPlugin = pyqtSignal()

    LABEL_DEFAULT_STYLE = 'QLabel { color : black; font-weight: normal;}'
    LABEL_SUCCESS_STYLE = 'QLabel { color : green; font-weight: bold;}'

    def __init__(self, interface: QgisInterface, locale, parent=None):
        super(SwissGeoDownloaderDockWidget, self).__init__(parent)
        self.setupUi(self)
        self.iface = interface
        self.locale = locale
        self.canvas = self.iface.mapCanvas()
        self.annManager = QgsProject.instance().annotationManager()

        # Initialize variables
        self.collectionList: dict[str, SgdStacCollection] = {}
        self.currentCollection: SgdStacCollection | None = None
        self.fileList: list[SgdAsset] = []
        self.fileListFiltered: dict[str, SgdAsset] = {}
        self.filesListDownload: list[SgdAsset] = []
        self.filesListStreamed: list[SgdAsset] = []
        self.currentFilters = {
            'filetype': None,
            'category': None,
            'resolution': None,
            'timestamp': None,
            'coordsys': None,
        }
        
        self.outputPath = None
        self.msgBar = self.iface.messageBar()
        
        # Coordinate system
        self.mapRefSys = QgsProject.instance().crs()
        self.apiRefSys = QgsCoordinateReferenceSystem(API_EPSG)
        self.transformProj2Api = QgsCoordinateTransform(
                self.mapRefSys, self.apiRefSys, QgsProject.instance())
        self.transformApi2Proj = QgsCoordinateTransform(
                self.apiRefSys, self.mapRefSys, QgsProject.instance())
        
        # Init QgsExtentBoxGroup Widget
        self.guiExtentWidget: QgsExtentGroupBox
        # Set current (=map view) extent
        self.guiExtentWidget.setCurrentExtent(self.canvas.extent(),
                                              self.mapRefSys)
        self.guiExtentWidget.setOutputExtentFromCurrent()
        
        # Initialize class to draw bbox of files in map
        self.bboxPainter = BboxPainter(self.canvas,
                                       self.transformApi2Proj, self.annManager)
        
        # Collection and file list table
        self.collectionListTbl = CollectionListTable(self, self.guiDatasets)
        self.collectionListTbl.sig_selectionChanged.connect(
                self.onCollectionSelectionChange)
        
        self.fileListTbl = FileListTable(self, self.guiFileListLayout)
        self.fileListTbl.sig_selectionChanged.connect(
            self.onFileSelectionChange)
        
        # Create spinners to indicate data loading
        # Spinner for getCollections request
        self.spinnerCol = QtWaitingSpinner(self)
        self.verticalLayout.addWidget(self.spinnerCol)
        
        # Spinner for file list request
        self.spinnerFl = QtWaitingSpinner(self)
        self.guiFileListLayout.addWidget(self.spinnerFl)
        
        # Connect signals
        self.guiShowMapBtn.clicked.connect(self.onShowMapClicked)
        self.guiRefreshDatasetsBtn.clicked.connect(
                self.onRefreshCollectionsClicked)
        self.guiInfoBtn.clicked.connect(self.onInfoClicked)
        
        self.filterFields = {
            'filetype': self.guiFileType,
            'category': self.guiCategory,
            'resolution': self.guiResolution,
            'timestamp': self.guiTimestamp,
            'coordsys': self.guiCoordsys,
        }
        
        self.filterFieldLabels = {
            'filetype': self.guiFileTypeL,
            'category': self.guiCategoryL,
            'resolution': self.guiResolutionL,
            'timestamp': self.guiTimestampL,
            'coordsys': self.guiCoordsysL,
        }
        
        # API caller task
        self.collectionsRequest: GetCollectionsTask | None = None
        self.fileListRequest: GetFileListTask | None = None
        self.guiRequestCancelBtn.setHidden(True)

        # Deactivate unused ui-elements
        self.guiGroupExtent.setDisabled(True)
        self.guiExtentWidget.setCollapsed(True)
        self.guiGroupFiles.setDisabled(True)
        self.guiDownloadBtn.setDisabled(True)
        
        self.guiFileType.currentIndexChanged.connect(self.onFilterChanged)
        self.guiCategory.currentTextChanged.connect(self.onFilterChanged)
        self.guiResolution.currentIndexChanged.connect(self.onFilterChanged)
        self.guiTimestamp.currentIndexChanged.connect(self.onFilterChanged)
        self.guiCoordsys.currentIndexChanged.connect(self.onFilterChanged)
        
        self.guiExtentWidget.extentChanged.connect(self.onExtentChanged)
        self.guiFullExtentChbox.clicked.connect(self.onUseFullExtentClicked)
        
        self.guiRequestListBtn.clicked.connect(self.onLoadFileListClicked)
        self.guiDownloadBtn.clicked.connect(self.onDownloadFilesClicked)
        self.guiRequestCancelBtn.clicked.connect(self.onCancelRequestClicked)
        
        QgsProject.instance().crsChanged.connect(self.onMapRefSysChanged)
        self.canvas.extentsChanged.connect(self.onMapExtentChanged)
        self.iface.newProjectCreated.connect(self.resetFileList)
        self.canvas.scaleChanged.connect(self.setBboxVisibility)
        
        # Check current project crs and ask user to change it
        self.checkSupportedCrs()
        
        self.deactivateFilterFields()
        
        # Finally, initialize apis and request available collections
        self.apiDGA = ApiDataGeoAdmin(self.locale)
        self.loadCollectionList()
    
    def setCurrentCollection(self, collectionId: str):
        self.onUnselectCollection()
        
        def searchAndSelectCollection():
            self.collectionListTbl.searchAndSelectByID(collectionId)
        
        if self.collectionsRequest in QgsApplication.taskManager().activeTasks():
            self.collectionsRequest.taskCompleted.connect(
                    searchAndSelectCollection)
        else:
            searchAndSelectCollection()
    
    def closeEvent(self, event, **kwargs):
        self.bboxPainter.removeAll()
        self.closingPlugin.emit()
        event.accept()
    
    def loadCollectionList(self):
        # Create separate task for request to not block ui
        self.spinnerCol.start()
        self.collectionsRequest = GetCollectionsTask(self.apiDGA, self.msgBar,
                                    'get STAC collections')
        # Listen for finished api call
        self.collectionsRequest.taskCompleted.connect(
                lambda: self.onReceiveCollections(
                        self.collectionsRequest.output))
        self.collectionsRequest.taskTerminated.connect(
                lambda: self.onReceiveCollections({}))
        QgsApplication.taskManager().addTask(self.collectionsRequest)
    
    def onMapRefSysChanged(self):
        """Listen for map canvas reference system changes and apply the new
        crs to extent widget."""
        self.mapRefSys = QgsProject.instance().crs()
        # Update transformations
        self.transformProj2Api = QgsCoordinateTransform(
                self.mapRefSys, self.apiRefSys, QgsProject.instance())
        self.transformApi2Proj = QgsCoordinateTransform(
                self.apiRefSys, self.mapRefSys, QgsProject.instance())
        # Update displayed extent
        mapExtent: QgsRectangle = self.canvas.extent()
        self.updateExtentValues(mapExtent, self.mapRefSys)
        # Redraw bbox in map
        self.bboxPainter.transformer = self.transformApi2Proj
        self.bboxPainter.paintBoxes(self.fileListFiltered)
    
    def checkSupportedCrs(self):
        if self.mapRefSys.authid() not in RECOMMENDED_CRS:
            # If project is empty, we set the project crs automatically to LV95
            if len(QgsProject.instance().mapLayers()) == 0:
                switchToCrs(self.canvas)
                return
            
            confirmed = self.showDialog('Swiss Geo Downloader',
                                        self.tr(
                                            'To download Swiss geo data it is recommended to use '
                                            'the Swiss coordinate reference system.\n\nSwitch map '
                                            'to Swiss LV95?'), 'YesNo')
            if confirmed:
                switchToCrs(self.canvas)
    
    def onExtentChanged(self):
        """ Update output extent when the following cases occur:
        2 - User changes coordinates in extent fields
        3 - User selects a layer from option 'calculate from layer'
        """
        if self.guiExtentWidget.extentState() in [2, 3]:
            newExtent = self.guiExtentWidget.outputExtent()
            extentCrs = self.guiExtentWidget.outputCrs()
            
            # If extent originates from a layer and layer extent does not match
            #  map coordinate system, transform the extent
            if self.guiExtentWidget.extentState() == 3 \
                    and extentCrs != self.mapRefSys and extentCrs.isValid():
                transformer = QgsCoordinateTransform(
                        extentCrs, self.mapRefSys, QgsProject.instance())
                trafoRectangle = transformBbox(newExtent, transformer)
                newExtent = QgsRectangle(*tuple(trafoRectangle))
            
            self.guiExtentWidget.setCurrentExtent(newExtent, self.mapRefSys)
    
    def onMapExtentChanged(self):
        """Show extent of current map view in extent widget."""
        if self.guiExtentWidget.extentState() == 1:
            # Only update widget if its current state is to display the map
            #  view extent
            mapExtent: QgsRectangle = self.canvas.extent()
            self.updateExtentValues(mapExtent, self.mapRefSys)
    
    def onUseFullExtentClicked(self):
        if self.guiFullExtentChbox.isChecked():
            self.updateSelectMode()
            self.guiExtentWidget.setDisabled(True)
        else:
            self.guiExtentWidget.setDisabled(False)
            self.resetFileList()
            self.onMapExtentChanged()
    
    def onShowMapClicked(self):
        self.checkSupportedCrs()
        message, level = addOverviewMap(self.canvas, self.mapRefSys.authid())
        self.msgBar.pushMessage(f"{MESSAGE_CATEGORY}: {message}", level)
    
    def onRefreshCollectionsClicked(self):
        self.resetFileList()
        self.collectionListTbl.resetSearch()
        self.collectionListTbl.unselect()
        self.loadCollectionList()
    
    def onInfoClicked(self):
        self.showDialog(self.tr('Swiss Geo Downloader - Info'),
                        self.tr('PLUGIN_INFO').format(
                            'https://pimoll.github.io/swissgeodownloader/'),
                        'Ok')
    
    def updateExtentValues(self, extent, refSys):
        self.guiExtentWidget.setCurrentExtent(extent, refSys)
        self.guiExtentWidget.setOutputExtentFromCurrent()

    def setBboxVisibility(self):
        if not self.bboxPainter:
            return
        self.bboxPainter.switchNumberVisibility()
    
    def onReceiveCollections(self,
                             collectionList: dict[str, SgdStacCollection]):
        """Receive list of available collections"""
        self.collectionList = collectionList
        self.collectionListTbl.fill(
                self.collectionList.values() if self.collectionList else [])
        self.spinnerCol.stop()
    
    def onCollectionSelectionChange(self, collectionId: str):
        """Set collection and load details on first selection"""
        # Ignore double clicks or very fast clicks
        if self.currentCollection and collectionId == self.currentCollection.id():
            return
        if not collectionId:
            self.onUnselectCollection()
            return
        
        self.currentCollection = self.collectionList.get(collectionId)
        if not self.currentCollection:
            return
        
        if not self.currentCollection.analysed():
            caller = AnalyseCollectionTask(self.apiDGA, self.msgBar,
                                           'analyse STAC collection',
                                           collection=self.currentCollection)
            # Listen for finished api call
            caller.taskCompleted.connect(
                    lambda: self.onLoadCollectionDetails(caller.output))
            caller.taskTerminated.connect(
                    lambda: self.onLoadCollectionDetails())
            QgsApplication.taskManager().addTask(caller)
        else:
            self.onLoadCollectionDetails()
    
    def onLoadCollectionDetails(self, collection: SgdStacCollection = None):
        """Set up ui according to the nature of the selected collection"""
        if collection:
            self.collectionList[collection.id()] = collection
            self.currentCollection = collection
        
        # Show collection status if no files are available
        if not self.currentCollection or self.currentCollection.isEmpty():
            self.guiGroupExtent.setDisabled(True)
            self.guiExtentWidget.setCollapsed(True)
            self.guiGroupFiles.setDisabled(True)
            self.resetFileList()
            self.fileListTbl.onEmptyList(self.tr('No files available in this '
                                                 'dataset'))
            self.guiRequestListBtn.setDisabled(True)
            return
        
        self.deactivateFilterFields()

        # Activate / deactivate Extent
        if not self.currentCollection.selectByBBox():
            self.guiExtentWidget.setCollapsed(True)
            self.updateSelectMode()
            self.guiGroupExtent.setDisabled(True)
        else:
            self.updateSelectMode()
            self.guiExtentWidget.setCollapsed(False)
            self.guiGroupExtent.setDisabled(False)
        
        # Activate files list
        self.guiGroupFiles.setDisabled(False)
        self.guiRequestListBtn.setDisabled(False)
        self.guiRequestListBtn.setHidden(False)
        self.resetFileList()
        
        # If collection has few files, get the file list directly
        if not self.currentCollection.selectByBBox():
            self.onLoadFileListClicked()
            self.guiRequestListBtn.setDisabled(True)
    
    def blockFilterSignals(self):
        for uiElem in self.filterFields.values():
            uiElem.blockSignals(True)
    
    def unblockFilterSignals(self):
        for uiElem in self.filterFields.values():
            uiElem.blockSignals(False)
    
    def emptyFilterFields(self):
        self.blockFilterSignals()
        for uiElem in self.filterFields.values():
            uiElem.clear()
        self.unblockFilterSignals()
    
    def deactivateFilterFields(self, filterItem=''):
        if filterItem:
            self.filterFields[filterItem].setDisabled(True)
            self.filterFields[filterItem].setHidden(True)
            self.filterFieldLabels[filterItem].setDisabled(True)
            self.filterFieldLabels[filterItem].setHidden(True)
            return
        
        for uiElem in self.filterFields.values():
            uiElem.setEnabled(False)
            uiElem.setHidden(True)
        for labelElem in self.filterFieldLabels.values():
            labelElem.setEnabled(False)
            labelElem.setHidden(True)

    def activateFilterFields(self, filterItem=''):
        if filterItem:
            self.filterFields[filterItem].setEnabled(True)
            self.filterFields[filterItem].setHidden(False)
            self.filterFieldLabels[filterItem].setEnabled(True)
            self.filterFieldLabels[filterItem].setHidden(False)
            return
        
        for uiElem in self.filterFields.values():
            uiElem.setEnabled(True)
            uiElem.setHidden(False)
        for labelElem in self.filterFieldLabels.values():
            labelElem.setEnabled(True)
            labelElem.setHidden(False)
    
    def onUnselectCollection(self):
        self.currentCollection = None
        
        self.onReceiveFileList([])
        self.guiGroupExtent.setDisabled(True)
        self.guiExtentWidget.setCollapsed(True)
        self.guiGroupFiles.setDisabled(True)
        self.guiDownloadBtn.setDisabled(True)
    
    def resetFileList(self):
        self.fileList = []
        self.fileListFiltered = {}
        self.fileListTbl.clear()
        self.guiDownloadBtn.setDisabled(True)
        self.guiFileListStatus.setText('')
        self.guiFileListStatus.setStyleSheet(self.LABEL_DEFAULT_STYLE)
        self.bboxPainter.removeAll()
    
    def onFilterChanged(self, newVal):
        for filterName, uiElem in self.filterFields.items():
            filterVal = uiElem.currentData()
            if filterVal:
                self.currentFilters[filterName] = filterVal
        
        self.applyFilters(userChange=True)
    
    def updateSelectMode(self):
        if self.guiFullExtentChbox.isChecked():
            bbox = QgsRectangle(*tuple(self.currentCollection.bbox()))
            self.updateExtentValues(bbox, self.apiRefSys)
    
    def getBbox(self) -> list:
        """Read out coordinates of bounding box, transform coordinates if
        necessary"""
        if self.guiFullExtentChbox.isChecked() or \
                not self.guiExtentWidget.isEnabled():
            return []
        
        rectangle = self.guiExtentWidget.currentExtent()
        bbox = transformBbox(rectangle, self.transformProj2Api)
        bbox = validateBbox(bbox, self.apiRefSys.authid())
        if float('inf') in bbox:
            bbox = []
        return bbox

    def onLoadFileListClicked(self):
        """Call api to retrieve list of items for currently selected bbox."""
        self.guiRequestListBtn.setHidden(True)
        # Remove current file list
        self.resetFileList()
        
        # Read out extent
        bbox = self.getBbox()
        
        # Call api
        # Create a separate task for request to not block ui
        self.fileListRequest = GetFileListTask(self.apiDGA, self.msgBar,
                                               'get file list',
                                               collectionId=self.currentCollection.id(),
                                               bbox=bbox)
        # Listen for finished api call
        self.fileListRequest.taskCompleted.connect(
                lambda: self.onReceiveFileList(self.fileListRequest.output))
        self.fileListRequest.taskTerminated.connect(
                lambda: self.onReceiveFileList({}))
        # Start spinner to indicate data loading
        self.spinnerFl.start()
        # Add task to task manager
        QgsApplication.taskManager().addTask(self.fileListRequest)
        self.guiRequestCancelBtn.setHidden(False)

    def onCancelRequestClicked(self):
        if self.fileListRequest.status() == self.fileListRequest.Running:
            self.fileListRequest.cancel()
            self.guiRequestCancelBtn.setHidden(True)
            self.guiRequestListBtn.setHidden(False)

    def onReceiveFileList(self, fileList):
        self.guiRequestCancelBtn.setHidden(True)
        if not fileList:
            fileList = {'files': [], 'filters': None}
        if not fileList['files']:
            fileList['files'] = []
        self.fileList = fileList['files']
        # Update file type filter and file list
        self.updateFilterFields(fileList['filters'])
        self.applyFilters()

        if self.fileList:
            # Enable download button
            self.updateDownloadBtnState()
        else:
            # Add info message to file list
            if self.getBbox():
                self.fileListTbl.onEmptyList(self.tr('No files available in '
                                                     'current extent'))
            else:
                self.fileListTbl.onEmptyList(self.tr('No files available'))

        self.spinnerFl.stop()
        self.guiRequestListBtn.setHidden(False)
    
    def updateFilterFields(self, filterableProps):
        self.emptyFilterFields()

        if not filterableProps:
            for key in self.currentFilters.keys():
                self.currentFilters[key] = None
            self.deactivateFilterFields()
            return
        
        self.blockFilterSignals()
        
        for filterName, uiElem in self.filterFields.items():
            filterVals = filterableProps[filterName]
            for filterVal in filterVals:
                uiElem.addItem(self.formatFilterVal(filterVal, filterName),
                               filterVal)
            
            if len(filterVals) > 1:
                # Show filter and set current filter value
                self.activateFilterFields(filterName)
                
                if self.currentFilters[filterName] in filterVals:
                    idx = uiElem.findData(self.currentFilters[filterName])
                    uiElem.setCurrentIndex(idx)
                else:
                    self.currentFilters[filterName] = filterVals[0]
            
            else:
                # Hide filter and unset current filter value
                self.deactivateFilterFields(filterName)
                self.currentFilters[filterName] = None

        self.unblockFilterSignals()
    
    def formatFilterVal(self, val, filterName):
        if val == ALL_VALUE:
            return self.tr('all')
        elif val == CURRENT_VALUE:
            return self.tr('current')
        
        elif filterName == 'coordsys':
            # Create a coordinate system object and get its friendly identifier
            cs = QgsCoordinateReferenceSystem(f'EPSG:{val}')
            if VERSION < 31003:
                return cs.description()
            else:
                return cs.userFriendlyIdentifier()
        else:
            return val
    
    def populateFileList(self, orderedFileList):
        # There are files but all of them are currently filtered out
        if self.fileList and not orderedFileList:
            self.fileListTbl.onEmptyList(self.tr('Currently selected filters '
                                                 'do not match any files'))
        else:
            self.fileListTbl.fill(orderedFileList)
        self.updateSummary()
        self.updateDownloadBtnState()
    
    def getCurrentlySelectedFilesAsList(self) -> list[SgdAsset]:
        return [file for file in self.fileListFiltered.values() if
            file.selected]
    
    def applyFilters(self, userChange=False):
        self.fileListFiltered = {}
        orderedFilesForTbl = []
        for file in self.fileList:
            
            if (file.filetypeFitsFilter(self.currentFilters['filetype'])
                    and file.categoryFitsFilter(
                            self.currentFilters['category'])
                    and file.resolutionFitsFilter(
                            self.currentFilters['resolution'])
                    and file.timestampFitsFilter(
                            self.currentFilters['timestamp'])
                    and file.coordsysFitsFilter(
                            self.currentFilters['coordsys'])
            ):
                file.selected = True
                self.fileListFiltered[file.id] = file
                # This list is necessary because dictionaries do not have a
                #  stable order, but we want the original order from the
                #  API response in the table
                orderedFilesForTbl.append(file)
            else:
                file.selected = False
        
        # If none of the files match the current filter criteria, reset one
        #  filter at the time
        if (not userChange and len(self.fileList) > 0
                and len(orderedFilesForTbl) == 0):
            self.resetFilter()
            self.applyFilters(userChange)
            return
        
        self.populateFileList(orderedFilesForTbl)
        self.bboxPainter.paintBoxes(self.fileListFiltered)
    
    def resetFilter(self):
        """When the file list is empty, this function resets one filter
        at the time to 'all' until file list is not empty any more."""
        for filterName, uiElem in self.filterFields.items():
            if (uiElem.isEnabled() and uiElem.isVisible()
                    and uiElem.currentData() != ALL_VALUE):
                
                idx = uiElem.findData(ALL_VALUE)
                if idx:
                    uiElem.setDisabled(True)
                    uiElem.setCurrentIndex(idx)
                    self.currentFilters[filterName] = ALL_VALUE
                    uiElem.setEnabled(True)
                    # Only reset one filter at a time
                    break
    
    def onFileSelectionChange(self, fileId, isChecked):
        self.fileListFiltered[fileId].selected = isChecked
        self.bboxPainter.switchSelectState(fileId)
        self.updateSummary()
        self.updateDownloadBtnState()
    
    def updateSummary(self):
        if self.fileListFiltered:
            fileSize = 0
            count = 0
            for file in self.getCurrentlySelectedFilesAsList():
                count += 1
                if file.mediaType() in self.currentCollection.avgSize().keys():
                    fileSize += self.currentCollection.avgSize()[
                        file.mediaType()]
            
            if fileSize > 0:
                status = self.tr("{} file(s), approximately {}") \
                    .format(count, filesizeFormatter(fileSize))
            else:
                status = self.tr("{} file(s)").format(count)
        else:
            status = self.tr('No files found.')
        
        self.guiFileListStatus.setText(status)
        self.guiFileListStatus.setStyleSheet(self.LABEL_DEFAULT_STYLE)
    
    def updateDownloadBtnState(self):
        if len(self.getCurrentlySelectedFilesAsList()) == 0:
            self.guiDownloadBtn.setDisabled(True)
        else:
            self.guiDownloadBtn.setDisabled(False)
    
    def onDownloadFilesClicked(self):
        self.guiDownloadBtn.setDisabled(True)
        self.spinnerFl.start()
        self.filesListStreamed = []
        self.filesListDownload = []
        filesToDownload = self.getCurrentlySelectedFilesAsList()
        
        # Set href as path for streamed files so qgis knows to stream them directly
        for file in filesToDownload:
            if file.isStreamable:
                file.path = STREAMED_SOURCE_PREFIX + file.href
                self.filesListStreamed.append(file)
        
        # If there is no need for a download folder, the selected files
        #  are added directly as streamed layers to qgis
        if len(self.filesListStreamed) == len(filesToDownload):
            # Start spinner to indicate data loading
            createQgisLayersInTask(self.filesListStreamed,
                                   self.onCreateQgisLayersFinished)
        
        else:
            folder = self.selectDownloadFolder()
            if not folder:
                self.stopDownload()
                return
            
            # Save path for next download
            self.outputPath = folder
            waitForConfirm = False
            # Sort out all selected files from list
            for file in filesToDownload:
                if not file.isStreamable:
                    file.path = os.path.join(self.outputPath, file.id)
                    self.filesListDownload.append(file)
                    # Check if there are files that are going to be overwritten
                    if os.path.exists(file.path):
                        waitForConfirm = True
            
            if waitForConfirm:
                confirmed = self.showDialog(self.tr('Overwrite files?'),
                                            self.tr(
                                                    'At least one file will be overwritten. Continue?'))
                if not confirmed:
                    self.stopDownload()
                    return
            self.startDownload()
    
    def stopDownload(self):
        self.guiDownloadBtn.setDisabled(False)
        self.spinnerFl.stop()
        self.filesListStreamed = []
        self.filesListDownload = []
    
    def selectDownloadFolder(self) -> str:
        # Let user choose output directory
        if self.outputPath:
            openDir = self.outputPath
        else:
            openDir = os.path.expanduser('~')
        folder = QFileDialog.getExistingDirectory(self, self.tr(
                'Choose output folder'), openDir,
                                                  QFileDialog.Option.ShowDirsOnly)
        return folder
    
    def startDownload(self):
        # Create separate task for request to not block ui
        caller = DownloadFilesTask(self.apiDGA, self.msgBar, 'download files',
                                   fileList=self.filesListDownload,
                                   outputDir=self.outputPath)
        # Listen for finished api call
        caller.taskCompleted.connect(
                lambda: self.onDownloadFinished(caller.output))
        caller.taskTerminated.connect(lambda: self.onDownloadFinished(False))
        # Add task to task manager
        QgsApplication.taskManager().addTask(caller)
    
    def onDownloadFinished(self, success):
        if success:
            # Confirm successful download
            self.guiFileListStatus.setText(
                self.tr('Files successfully downloaded!'))
            self.guiFileListStatus.setStyleSheet(self.LABEL_SUCCESS_STYLE)
            self.msgBar.pushMessage(f"{MESSAGE_CATEGORY}: "
                                    + self.tr(
                '{} file(s) successfully downloaded').format(
                    len(self.filesListDownload)), Qgis.MessageLevel.Success)
        
        filesToAdd = self.filesListDownload + self.filesListStreamed
        createQgisLayersInTask(filesToAdd, self.onCreateQgisLayersFinished)
    
    def onCreateQgisLayersFinished(
            self,
            layers: list[QgsRasterLayer | QgsVectorLayer] | None = None,
            alreadyAdded: int = 0,
            exception=None
    ):
        self.stopDownload()
        
        if exception:
            errorMsg = self.tr('Not possible to add layers to QGIS')
            self.msgBar.pushMessage(
                    f"{MESSAGE_CATEGORY}: {errorMsg}: {exception}",
                    Qgis.MessageLevel.Warning)
        if layers:
            addLayersToQgis(layers)
        
        if alreadyAdded > 0:
            msg = self.tr(
                    '{} layers added to QGIS, {} skipped because they are already present').format(
                    len(layers), alreadyAdded)
            
            self.msgBar.pushMessage(f"{MESSAGE_CATEGORY}: {msg}",
                                    Qgis.MessageLevel.Info)
    
    def cleanCanvas(self):
        if self.bboxPainter:
            self.bboxPainter.removeAll()
    
    @staticmethod
    def showDialog(title, msg, mode='OkCancel'):
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Icon.Question)
        msgBox.setWindowTitle(title)
        msgBox.setText(msg)
        if mode == 'OkCancel':
            msgBox.setStandardButtons(
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        elif mode == 'YesNo':
            msgBox.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        elif mode == 'error':
            msgBox.setIcon(QMessageBox.Icon.Critical)
            msgBox.setStandardButtons(QMessageBox.StandardButton.Ok)
        elif mode == 'Ok':
            msgBox.setStandardButtons(QMessageBox.StandardButton.Ok)
        else:
            msgBox.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        returnValue = msgBox.exec()
        return returnValue == QMessageBox.StandardButton.Ok or returnValue == QMessageBox.StandardButton.Yes
