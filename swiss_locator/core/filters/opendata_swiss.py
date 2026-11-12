import heapq
from dataclasses import dataclass

from swiss_locator.core.constants import OPENDATA_SWISS_URL
from swiss_locator.remote_data import spec
from swiss_locator.remote_data.remote_data_file import RemoteDataFile
from swiss_locator.utils import wms


def opendata_swiss_url(search: str):
    url = OPENDATA_SWISS_URL
    # Combine default search (benefits from Solr German stemming) with
    # explicit title wildcard (prefix match on unstemmed tokens).
    # E.g. "asia" is not a German stem so the default field misses
    # "Asiatische", but title:asia* catches it.
    words = search.split()
    title_wildcard = " ".join(f"title:{w}*" for w in words)  # noqa: E231
    q = f"{search} OR ({title_wildcard})"
    params = {
        "q": q,
        "fq": "res_format:WMS OR res_format:WMTS",
    }
    return url, params


@dataclass(frozen=True)
class WmsLayer:
    name: str
    title: str
    service_url: str
    service_title: str
    version: str


class WmsLayerIndex:
    """Searchable index of the layers of the WMS services referenced by opendata.swiss.

    Built from the data of spec.OPENDATA_SWISS_WMS_LAYERS.
    """

    def __init__(self, data: dict):
        # (lower-case name, lower-case title, lower-case searched text, layer)
        self._entries = []
        try:
            for service in data["services"]:
                service_title = service.get("title") or ""
                for name, title in service["layers"]:
                    layer = WmsLayer(
                        name=name,
                        title=title or name,
                        service_url=service["url"],
                        service_title=service_title,
                        version=service.get("version") or wms.DEFAULT_VERSION,
                    )
                    self._entries.append(
                        (
                            name.lower(),
                            layer.title.lower(),
                            f"{name} {layer.title} {service_title}".lower(),
                            layer,
                        )
                    )
        except (AttributeError, KeyError, TypeError, ValueError) as e:
            raise spec.InvalidDataFile(f"invalid WMS layers index: {e!r}") from e

    def __len__(self):
        return len(self._entries)

    def search(self, text: str, limit: int) -> list[tuple[WmsLayer, float]]:
        """Return the best matching layers with their score (1 is a perfect match).

        Every word must be found in the name, the title or the service title.
        """
        text = text.strip().lower()
        words = text.split()
        if not words:
            return []
        matches = (
            (self._rank(text, name, title), title, layer)
            for name, title, searched_text, layer in self._entries
            if all(word in searched_text for word in words)
        )
        best = heapq.nsmallest(limit, matches, key=lambda match: match[:2])
        return [(layer, 1 - rank / 10) for rank, _, layer in best]

    @staticmethod
    def _rank(text: str, name: str, title: str) -> int:
        """0 for the best match, 5 for the worst."""
        if text in (name, title):
            return 0
        if name.startswith(text):
            return 1
        if title.startswith(text):
            return 2
        if text in name:
            return 3
        if text in title:
            return 4
        return 5


WMS_LAYERS_INDEX = RemoteDataFile(spec.OPENDATA_SWISS_WMS_LAYERS, parse=WmsLayerIndex)
