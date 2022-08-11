from enum import Enum


class FilterType(Enum):
    Location = "locations"
    Layers = "layers"
    Feature = "featuresearch"
    WMTS = "wmts"
