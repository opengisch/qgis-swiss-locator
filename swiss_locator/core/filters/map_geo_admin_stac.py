from qgis.core import QgsStacCollection

BASE_URL = "https://data.geo.admin.ch/api/stac/v1"


def collections_to_searchable_strings(
        collections: dict[str, QgsStacCollection]):
    collection_ids = []
    collection_search_strings = []
    for (coll_id, collection) in collections.items():
        collection_ids.append(coll_id)
        collection_search_strings.append(
            (" ".join([collection.title(), coll_id])).lower())
    return collection_search_strings, collection_ids


def map_geo_admin_stac_items_url(collection_id: str, limit: int):
    url = f"{BASE_URL}/collections/{collection_id}/items"
    base_params = {
        "limit": str(limit)
    }
    return url, base_params
