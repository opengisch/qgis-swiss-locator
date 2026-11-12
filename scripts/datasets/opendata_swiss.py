"""Layers of the WMS services referenced by opendata.swiss, see spec.OPENDATA_SWISS_WMS_LAYERS."""

import logging
import re
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from scripts import summary
from scripts.http_client import HttpError, get, get_json
from swiss_locator.core.constants import OPENDATA_SWISS_URL
from swiss_locator.remote_data import spec
from swiss_locator.utils import safe_xml, wms

PAGE_SIZE = 1000
WORKERS = 16
CAPABILITIES_ROOTS = ("WMS_Capabilities", "WMT_MS_Capabilities")

# A service that cannot be harvested keeps its previously published layers if
# it was harvested more recently than this: a server being down during a run
# does not remove its layers from the plugin.
MAX_OFFLINE = timedelta(days=30)

log = logging.getLogger(__name__)


class HarvestError(Exception):
    """A service answered with something unusable."""

    NOT_CAPABILITIES = "not a WMS capabilities document"
    NO_LAYER = "no named layer"

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason} ({detail})" if detail else reason)
        self.reason = reason


def build(previous: dict | None = None, get_json=get_json, get=get) -> dict:
    """Harvest the services.

    :param previous: the published data, to keep the layers of offline services
    """
    urls = service_urls(datasets(get_json))
    log.info("%d WMS services referenced by opendata.swiss", len(urls))
    with ThreadPoolExecutor(WORKERS) as executor:
        results = list(executor.map(lambda url: _try_harvest(url, get), urls))

    now = spec.utc_now()
    published = _published_services(previous, now)
    services = {}
    kept = 0
    failures = Counter()
    for url, (service, reason) in zip(urls, results):
        if service is not None:
            service["harvested"] = now
        else:
            # harvested from its lowercased URL if wrongly cased, see harvest()
            service = published.get(url) or published.get(_with_lowercase_path(url))
            if service is None:
                failures[reason] += 1
                continue
            kept += 1
        # different URLs can lead to the same service, see harvest()
        services.setdefault(service["url"], service)

    summary.info(
        "%d services: %d harvested, %d kept from the published version, %d failed",
        len(urls),
        len(urls) - kept - sum(failures.values()),
        kept,
        sum(failures.values()),
    )
    for reason, number in failures.most_common():
        summary.info("  failed, %s: %d", reason, number)
    return {"services": sorted(services.values(), key=lambda s: s["url"])}


def count(data: dict) -> int:
    return sum(len(service["layers"]) for service in data["services"])


def datasets(get_json):
    """Yield the opendata.swiss datasets having a WMS resource."""
    start = 0
    while True:
        params = {"fq": "res_format:WMS", "rows": PAGE_SIZE, "start": start}
        result = get_json(OPENDATA_SWISS_URL, params)["result"]
        yield from result["results"]
        start += PAGE_SIZE
        if not result["results"] or start >= result["count"]:
            return


def service_urls(datasets) -> list[str]:
    """Return the distinct URLs of the WMS services of the datasets' resources."""
    services = {}
    for dataset in datasets:
        for resource in dataset.get("resources") or []:
            url = resource.get("url") or ""
            is_wms = (
                "wms" in url.lower() or (resource.get("format") or "").upper() == "WMS"
            )
            service = wms.service_url(url) if is_wms else None
            if service is None or wms.is_geo_admin(service):
                continue
            # the same service is sometimes referenced with http and https
            key = service.split("://", 1)[1]
            if key not in services or service.startswith("https://"):
                services[key] = service
    return sorted(services.values())


def harvest(service: str, get=get) -> dict:
    """Return a service with its layers. Raises an exception if not usable."""
    try:
        content = get(wms.capabilities_url(service))
    except HttpError as e:
        # Some catalog entries have a wrongly cased path, while the servers are
        # case-sensitive (seen for Zug). The service gets its working URL.
        lowercase = _with_lowercase_path(service)
        if e.status != 404 or lowercase == service:
            raise
        content = get(wms.capabilities_url(lowercase))
        service = lowercase
    try:
        capabilities = safe_xml.fromstring(content)
    except safe_xml.ParseError as e:
        raise HarvestError(HarvestError.NOT_CAPABILITIES, str(e)) from e
    return parse_capabilities(service, capabilities)


def parse_capabilities(service: str, root: ET.Element) -> dict:
    match = re.match(r"\{.*\}", root.tag)
    namespace = match.group(0) if match else ""
    if root.tag[len(namespace) :] not in CAPABILITIES_ROOTS:
        raise HarvestError(HarvestError.NOT_CAPABILITIES, root.tag)

    layers = {}
    for layer in root.iter(f"{namespace}Layer"):
        name = _text(layer, f"{namespace}Name")
        if name and name not in layers:
            layers[name] = _text(layer, f"{namespace}Title") or name
    if not layers:
        raise HarvestError(HarvestError.NO_LAYER)

    return {
        "url": service,
        "version": root.get("version") or wms.DEFAULT_VERSION,
        "title": _text(root, f"{namespace}Service/{namespace}Title"),
        "layers": sorted([name, title] for name, title in layers.items()),
    }


def _try_harvest(url: str, get) -> tuple[dict | None, str]:
    """Return the harvested service, or None and the reason of the failure."""
    try:
        return harvest(url, get), ""
    except (HttpError, HarvestError) as e:
        log.info("%s: %s", url, e)
        return None, e.reason
    except Exception as e:
        # third party servers fail in all possible ways
        log.info("%s: %r", url, e)
        return None, f"unexpected error ({type(e).__name__})"


def _published_services(previous: dict | None, now: str) -> dict[str, dict]:
    """Return the published services harvested recently enough, by URL."""
    services = {}
    try:
        for service in (previous or {}).get("services", []):
            harvested = datetime.strptime(service["harvested"], spec.TIMESTAMP_FORMAT)
            if datetime.strptime(now, spec.TIMESTAMP_FORMAT) - harvested < MAX_OFFLINE:
                services[service["url"]] = service
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        log.warning("ignoring the published services, they cannot be read: %r", e)
        return {}
    return services


def _with_lowercase_path(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=parts.path.lower()))


def _text(element: ET.Element, path: str) -> str:
    node = element.find(path)
    return (node.text or "").strip() if node is not None else ""
