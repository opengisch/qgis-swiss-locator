import json
import re
import urllib.request

from qgis._core import QgsStacCollection

from swiss_locator.core.stac.stac_client import StacClient

BASE_URL = "https://data.geo.admin.ch/api/stac/v1"


def fetch_stac_collections(_task, lang):
    stac_client = StacClient(BASE_URL)
    collections = stac_client.fetchCollections()
    
    data_geo_admin_metadata = fetch_geo_admin_metadata(lang)
    
    stacCollections = {}
    
    for collection in collections:
        
        if collection.id() in data_geo_admin_metadata:
            metadata = data_geo_admin_metadata[collection.id()]
            
            collection.setTitle(metadata.get('title'))
            collection.setDescription(metadata.get('description'))
        
        stacCollections[collection.id()] = collection
    
    return stacCollections


def fetch_geo_admin_metadata(lang):
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


def collections_to_searchable_strings(
        collections: dict[str, QgsStacCollection]):
    collection_ids = []
    collection_search_strings = []
    for (coll_id, collection) in collections.items():
        collection_ids.append(coll_id)
        # Clean up strings by replacing any non-alphanumeric characters with spaces
        parsed_collection_id = re.sub(r'[.,-–_/\\()]', ' ', coll_id.lower())
        parsed_collection_title = re.sub(r'[.,-–_/\\()]', ' ',
                                         collection.title().lower())
        collection_search_strings.append(
                " ".join([parsed_collection_id, parsed_collection_title]))
    return collection_search_strings, collection_ids


def map_geo_admin_stac_items_url(collection_id: str, limit: int):
    base_url = f"{BASE_URL}/collections/{collection_id}/items"
    base_params = {
        "limit": str(limit)
    }
    return base_url, base_params
