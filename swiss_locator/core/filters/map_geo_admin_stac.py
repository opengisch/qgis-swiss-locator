from qgis.core import QgsStacCollection


def collections_to_searchable_strings(collections: dict[str, QgsStacCollection]):
    collection_ids = []
    collection_search_strings = []
    for coll_id, collection in collections.items():
        collection_ids.append(coll_id)
        collection_search_strings.append(
            (" ".join([collection.title(), coll_id])).lower()
        )
    return collection_search_strings, collection_ids


def stac_items_url(catalog_url: str, collection_id: str, limit: int):
    url = f"{catalog_url}/collections/{collection_id}/items"
    base_params = {"limit": str(limit)}
    return url, base_params
