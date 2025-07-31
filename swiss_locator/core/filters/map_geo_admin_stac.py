import json
import urllib.request

from qgis._core import QgsStacCollection

from swiss_locator.core.stac.stac_client import StacClient

BASE_URL = "https://data.geo.admin.ch/api/stac/v1"


def fetchStacCollections(lang):
    # TODO: Make both calls async
    
    stac_client = StacClient(BASE_URL)
    collections = stac_client.fetchCollections()
    
    data_geo_admin_metadata = getGeoAdminMetadata(lang)
    
    stacCollections = {}
    
    for collection in collections:
        
        if collection.id() in data_geo_admin_metadata:
            metadata = data_geo_admin_metadata[collection.id()]
            
            collection.setTitle(metadata.get('title'))
            collection.setDescription(metadata.get('description'))
        
        stacCollections[collection.id()] = collection
    
    return stacCollections


def getGeoAdminMetadata(lang):
    """ Calls geoadmin API and retrieves translated titles and
    descriptions."""
    url = f"https://api3.geo.admin.ch/rest/services/api/MapServer?lang={lang}"
    contents = (
        urllib.request.urlopen(url)
        .read()
        .decode("utf-8")
    )
    data = json.loads(contents)
    
    metadata = {}
    
    for layer in data['layers']:
        
        title = ''
        description = ''
        if 'layerBodId' not in layer:
            continue
        collectionId = layer['layerBodId']
        if 'fullName' in layer:
            title = layer['fullName']
        if 'attributes' in layer and 'fullTextSearch' in layer['attributes']:
            description = layer['attributes']['fullTextSearch']
        
        metadata[collectionId] = {
            'title': title,
            'description': description
        }
    return metadata


def collectionsToSearchStrings(collections: dict[str, QgsStacCollection]):
    collectionIds = []
    collectionSearchStrings = []
    for (collId, collection) in collections.items():
        collectionIds.append(collId)
        parsedCollectionId = collId.lower().replace('.', ' ')
        parsedCollectionTitle = collection.title().lower()
        collectionSearchStrings.append(
                f"{parsedCollectionId} {parsedCollectionTitle}")
    return collectionSearchStrings, collectionIds


def map_geo_admin_stac_items_url(id: str, limit: int):
    base_url = f"https://data.geo.admin.ch/api/stac/v1/collections/{id}/items"
    base_params = {
        "limit": str(limit)
    }
    return base_url, base_params
