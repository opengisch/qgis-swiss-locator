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
from copy import deepcopy

from qgis.core import QgsBox3D, QgsStacAsset, QgsStacCollection

from swiss_locator.swissgeodownloader.utils.utilities import \
    getDateFromIsoString

ALL_VALUE = "all"
CURRENT_VALUE = "current"
P_SIMILAR = 0.20  # max 20% difference
FILETYPE_STREAMED = "streamed (COG)"
STREAMED_SOURCE_PREFIX = "/vsicurl/"


class SgdStacCollection(QgsStacCollection):
    def __init__(self, collection: QgsStacCollection):
        super().__init__(collection)
        self._selectByBBox = True
        self._isEmpty = None
        self._avgSize = {}
        self._analysed = False
    
    def selectByBBox(self):
        return self._selectByBBox
    
    def setSelectByBBox(self, selectByBBox):
        self._selectByBBox = selectByBBox
    
    def isEmpty(self):
        return self._isEmpty
    
    def setIsEmpty(self, isEmpty):
        self._isEmpty = isEmpty
    
    def avgSize(self):
        return self._avgSize
    
    def setAvgSize(self, avgSize):
        self._avgSize = avgSize
    
    def analysed(self):
        return self._analysed
    
    def setAnalysed(self, analysed):
        self._analysed = analysed
    
    def bbox(self):
        extent = self.extent().spatialExtent()
        return [
            extent.xMinimum(),
            extent.yMinimum(),
            extent.xMaximum(),
            extent.yMaximum(),
        ]
    
    def metadataLink(self):
        return self._linkByRelation("describedby")
    
    def itemsLink(self):
        return self._linkByRelation("items")
    
    def _linkByRelation(self, relation):
        try:
            return [link.href() for link in self.links() if
                link.relation() == relation][0]
        except IndexError:
            return ""
    
    def searchText(self):
        return (
            " ".join([self.id() or "", self.title() or "",
                         self.description() or ""])
            .lower()
        )
    
    def reportCompleteness(self):
        msg = []
        if not self.description():
            msg.append("No description available")
        if not self.bbox():
            msg.append("No bbox available")
        if not self.metadataLink():
            msg.append("No metadata link available for")
        if msg:
            return f"The collection '{self.id()}' is incomplete: {', '.join(msg)}"
        else:
            return None


class SgdAsset(QgsStacAsset):
    def __init__(self, assetId: str, asset: QgsStacAsset):
        super().__init__(asset)
        self.id = assetId
        self.href = self.href()
        # Additional properties extending QgsStacAsset
        self.properties = {}
        self.bbox = None
        self.path = None
        self.selected = False
        self.filetype = self._simpleFileType()
        self.category = None
        self.resolution = None
        self.timestamp = None
        self.timestampStr = ""
        self.coordsys = None
        
        self.isMostCurrent = False
    
    @property
    def bboxKey(self):
        if not self.bbox:
            return ""
        # This will round the coordinates to ~ 5-10 m
        return "|".join([str(round(coord, 4)) for coord in self.bbox])
    
    @property
    def propKey(self):
        propList = [self.filetype, self.category, self.resolution]
        return "|".join([elem for elem in propList if elem is not None])
    
    @property
    def isStreamable(self):
        return FILETYPE_STREAMED in self.filetype
    
    @property
    def displayName(self):
        return self.title() or self.id
    
    def _simpleFileType(self):
        filetype = None
        if self.mediaType():
            filetype = self.mediaType().split(';')[0]
            if '/' in filetype:
                filetype = filetype.split('/')[1]
            if filetype.startswith('x.'):
                filetype = filetype[2:]
        return filetype
    
    def setBbox(self, bbox: QgsBox3D):
        # Bbox entries should be numbers and inside coordinate ranges of WGS84
        bboxList = []
        try:
            assert isinstance(bbox, QgsBox3D), "bbox is not a QgsBox3D"
            assert bbox.isNull() is False, "bbox is null"
            bboxList = [
                min(bbox.xMinimum(), bbox.xMaximum()),
                min(bbox.yMinimum(), bbox.yMaximum()),
                max(bbox.xMinimum(), bbox.xMaximum()),
                max(bbox.yMinimum(), bbox.yMaximum())]
            assert [
                isinstance(c, float) or isinstance(c, int) for c in bboxList
            ], "bbox contains non-numeric values"
            assert (
                    -180 <= bboxList[0] <= 180 and -180 <= bboxList[2] <= 180
            ), "bbox coordinates out of range"
            assert (
                    -90 <= bboxList[1] <= 90 and -90 <= bboxList[3] <= 90
            ), "bbox coordinates out of range"
            assert (
                    bboxList[0] != bboxList[2] and bboxList[1] != bboxList[3]
            ), "Warning - bbox coordinates are overlapping"
            assert (
                    bboxList[0] < bboxList[2] and bboxList[1] < bboxList[3]
            ), "bbox coordinates are not ordered"
        except AssertionError as e:
            self.bbox = None
            if str(e).startswith("Warning"):
                self.bbox = bboxList
            raise e
        
        self.bbox = bboxList
    
    def setTimestamp(self, startTimestamp, endTimestamp=None):
        try:
            self.timestamp = getDateFromIsoString(startTimestamp, False)
            self.timestampStr = getDateFromIsoString(startTimestamp)
            if endTimestamp:
                self.timestampStr = " / ".join(
                        [getDateFromIsoString(ts) for ts in
                            [startTimestamp, endTimestamp]]
                )
        except ValueError as e:
            self.timestamp = None
            self.timestampStr = ""
            raise e
    
    def filetypeFitsFilter(self, filterValue):
        return (not filterValue
                or (filterValue and self.filetype == filterValue)
                or (self.filetype is None)
                or (filterValue == ALL_VALUE))
    
    def categoryFitsFilter(self, filterValue):
        return (not filterValue
                or (filterValue and self.category == filterValue)
                or (self.category is None)
                or (filterValue == ALL_VALUE))
    
    def resolutionFitsFilter(self, filterValue):
        return (not filterValue
                or (filterValue and self.resolution == filterValue)
                or (self.resolution is None)
                or (filterValue == ALL_VALUE))
    
    def timestampFitsFilter(self, filterValue):
        return (not filterValue
                or (filterValue and self.timestampStr == filterValue)
                or (self.timestampStr is None)
                or (filterValue == ALL_VALUE)
                or (filterValue == CURRENT_VALUE and self.isMostCurrent))
    
    def coordsysFitsFilter(self, filterValue):
        return (not filterValue
                or (filterValue and self.coordsys == filterValue)
                or (self.coordsys is None)
                or (filterValue == ALL_VALUE))
    
    def hasSimilarBboxAs(self, bbox: list[float]):
        if not self.bbox or not bbox:
            return False
        
        try:
            # bbox pattern: E1, N1, E2, N2 (e.g. 5°, 45°, 7°, 47°)
            height = bbox[3] - bbox[1]
            s_height = self.bbox[3] - self.bbox[1]
            length = bbox[2] - bbox[0]
            s_length = self.bbox[2] - self.bbox[0]
            
            assert s_height != 0 and s_length != 0
            
            # Check if similar bbox length
            assert (1 - P_SIMILAR) < abs(length / s_length) < (
                    1 + P_SIMILAR)
            # Check if similar bbox height
            assert (1 - P_SIMILAR) < abs(height / s_height) < (
                    1 + P_SIMILAR)
            
            # Check if similar absolute position of corner points
            assert abs(self.bbox[0] - bbox[0]) < s_length * P_SIMILAR
            assert abs(self.bbox[1] - bbox[1]) < s_height * P_SIMILAR
            assert abs(self.bbox[2] - bbox[2]) < s_length * P_SIMILAR
            assert abs(self.bbox[3] - bbox[3]) < s_height * P_SIMILAR
        
        except AssertionError:
            return False
        return True
    
    def copy(self):
        copy = SgdAsset(self.id, self)
        copy.properties = deepcopy(self.properties)
        copy.bbox = deepcopy(self.bbox)
        copy.path = self.path
        copy.filetype = self.filetype
        copy.category = self.category
        copy.resolution = self.resolution
        copy.timestamp = self.timestamp
        copy.timestampStr = self.timestampStr
        copy.coordsys = self.coordsys
        copy.isMostCurrent = self.isMostCurrent
        return copy
