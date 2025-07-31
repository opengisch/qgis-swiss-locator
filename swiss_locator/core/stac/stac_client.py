from qgis.PyQt.QtCore import QUrl, QUrlQuery
from qgis.core import (
    QgsStacCollection,
    QgsStacCollectionList,
    QgsStacController,
)


class StacClient:
    
    def __init__(self, url):
        self.url = url
        self.controller = QgsStacController()
        self.assetProperties = {}
    
    def fetchCollections(self, params: dict = None
                         ) -> list[QgsStacCollection]:
        """Get a list of all available collections and read out title,
        description and other properties."""
        
        url = self._createUrl(f"{self.url}/collections", params)
        errorMsg = ""
        collections = []
        
        while url:
            response: QgsStacCollectionList = self.controller.fetchCollections(
                    url, errorMsg)
            
            if errorMsg or not response:
                raise Exception(errorMsg)
            
            collections += response.takeCollections()
            url = None
            if (
                    not params
                    or not params.get("limit")
                    or len(collections) < params["limit"]
            ):
                url = response.nextUrl() if not response.nextUrl().isEmpty() else None
        
        return collections
    
    @staticmethod
    def _createUrl(baseUrl: str, urlParams: dict):
        url = QUrl(baseUrl)
        if urlParams:
            queryParams = QUrlQuery()
            for key, value in urlParams.items():
                if value is None or value == "" or value == []:
                    continue
                if isinstance(value, list):
                    param = ",".join([str(v) for v in value])
                else:
                    param = str(value)
                queryParams.addQueryItem(key, param)
            url.setQuery(queryParams)
        
        return url
