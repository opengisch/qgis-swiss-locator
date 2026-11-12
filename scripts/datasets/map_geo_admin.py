"""Searchable layers of map.geo.admin.ch, see spec.MAP_GEO_ADMIN_LAYERS."""

import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from scripts import summary
from scripts.http_client import HttpError, get_json
from swiss_locator.core.constants import API_BASE_URL, SEARCH_URL
from swiss_locator.core.parameters import AVAILABLE_LANGUAGES

LAYERS_CONFIG_URL = f"{API_BASE_URL}/rest/services/all/MapServer/layersConfig"
LANGUAGES = sorted(set(AVAILABLE_LANGUAGES.values()))
WORKERS = 16

log = logging.getLogger(__name__)


def build(previous=None, get_json=get_json) -> dict[str, dict[str, str]]:
    """Return the label of each searchable layer, by language.

    A layer is searchable when the layers configuration says so and the search
    service has an index for it: the plugin searches several layers per
    request, and a single layer without index fails the whole request.

    :param previous: the published data. A layer whose index cannot be checked,
                     the search service being down, is kept if it is published.
    """
    layers = {}
    for lang in LANGUAGES:
        layers_config = get_json(LAYERS_CONFIG_URL, {"lang": lang})
        for layer_id, properties in layers_config.items():
            if properties.get("searchable"):
                label = properties.get("label") or layer_id
                layers.setdefault(layer_id, {})[lang] = label

    with ThreadPoolExecutor(WORKERS) as executor:
        indexed = list(
            executor.map(lambda layer_id: has_search_index(layer_id, get_json), layers)
        )
    published = previous or {}
    left_out = Counter()
    kept = 0
    for layer_id, has_index in zip(list(layers), indexed):
        if has_index:
            continue
        if has_index is None and layer_id in published:
            kept += 1
            continue
        left_out["no search index" if has_index is False else "not checked"] += 1
        del layers[layer_id]

    summary.info(
        "%d searchable layers, %d kept from the published version as their "
        "search index could not be checked",
        len(layers),
        kept,
    )
    for reason, number in left_out.most_common():
        summary.info("  left out, %s: %d", reason, number)
    return dict(sorted(layers.items()))


def has_search_index(layer_id: str, get_json=get_json) -> bool | None:
    """Whether the search service can search the features of a layer, None if
    it could not be checked."""
    params = {
        "type": "featuresearch",
        "features": layer_id,
        "searchText": "a",
        "limit": 1,
        "sr": 2056,
    }
    try:
        get_json(SEARCH_URL, params)
    except HttpError as e:
        # 404 for a layer without index: "unknown local index"
        if e.status is not None and e.status < 500:
            return False
        log.warning("%s: search index not checked, %s", layer_id, e)
        return None
    return True
