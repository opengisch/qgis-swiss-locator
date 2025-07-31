from enum import Enum


class FilterType(Enum):
    Location = "locations"
    Layers = "layers"  # this is used in map.geo.admin as the search type
    Feature = "featuresearch"  # this is used in map.geo.admin as the search type
    WMTS = "wmts"
    VectorTiles = "vectortiles"
    STAC = "stac"
