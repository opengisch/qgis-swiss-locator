"""The documents published on GitHub Pages."""

import json
import logging
import os

from scripts.http_client import HttpError, get
from swiss_locator.remote_data import spec

log = logging.getLogger(__name__)


def published_document(file_name: str) -> dict | None:
    """Return the currently published document, None if there is no valid one."""
    try:
        document = json.loads(get(spec.url(file_name)))
        spec.unwrap(document)
    except (HttpError, ValueError) as e:
        log.info("%s: no valid published version (%s)", file_name, e)
        return None
    return document


def write_document(path: str, document: dict):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(document, f, ensure_ascii=False, separators=(",", ":"))


def download(destination: str) -> bool:
    """Download all the published documents. Return False if one is missing."""
    # created even if empty, the packaging adds it to the plugin package
    os.makedirs(destination, exist_ok=True)
    complete = True
    for file_name in spec.DATA_FILES:
        document = published_document(file_name)
        if document is None:
            log.error("%s is not published", file_name)
            complete = False
            continue
        write_document(os.path.join(destination, file_name), document)
        log.info("%s: generated on %s", file_name, document["generated"])
    return complete
