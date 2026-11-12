"""The generated datasets, one per file of spec.DATA_FILES."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from scripts.datasets import map_geo_admin, opendata_swiss
from swiss_locator.remote_data import spec


@dataclass(frozen=True)
class Dataset:
    file_name: str
    # returns the data, given the published data (None if not available)
    build: Callable[[Any], Any]
    # number of items of the data, to detect a broken generation
    count: Callable[[Any], int]


DATASETS = (
    Dataset(spec.MAP_GEO_ADMIN_LAYERS, map_geo_admin.build, len),
    Dataset(spec.OPENDATA_SWISS_WMS_LAYERS, opendata_swiss.build, opendata_swiss.count),
)
