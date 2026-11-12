"""Searchable layers of map.geo.admin.ch, see spec.MAP_GEO_ADMIN_LAYERS."""

from scripts.http_client import get_json
from swiss_locator.core.constants import API_BASE_URL
from swiss_locator.core.parameters import AVAILABLE_LANGUAGES

LAYERS_CONFIG_URL = f"{API_BASE_URL}/rest/services/all/MapServer/layersConfig"
LANGUAGES = sorted(set(AVAILABLE_LANGUAGES.values()))


def build(previous=None, get_json=get_json) -> dict[str, dict[str, str]]:
    """Return the label of each searchable layer, by language."""
    layers = {}
    for lang in LANGUAGES:
        layers_config = get_json(LAYERS_CONFIG_URL, {"lang": lang})
        for layer_id, properties in layers_config.items():
            if properties.get("searchable"):
                label = properties.get("label") or layer_id
                layers.setdefault(layer_id, {})[lang] = label
    return dict(sorted(layers.items()))
