from qgis.core import QgsApplication

from swiss_locator.swissgeodownloader.api.api_caller_task import ApiCallerTask
from swiss_locator.swissgeodownloader.api.datageoadmin import ApiDataGeoAdmin


# Updates api/datageoadmin_geocat_metadata.json with metadata of all available
#  STAC collections to reduce network requests when using the plugin.
#  Currently, can't be run in a GitHub workflow, must be run on a system
#  with QGIS.


def refreshMetadata():
    api = ApiDataGeoAdmin()
    task = ApiCallerTask(api, None, '')
    api.refreshAllMetadata(task)


if __name__ == '__main__':
    QGIS_APP = QgsApplication([], False)
    QGIS_APP.initQgis()
    
    refreshMetadata()
