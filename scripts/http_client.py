"""HTTP requests of the data generators."""

import json
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote, urlencode

from swiss_locator.core.constants import USER_AGENT

TIMEOUT = 60
MAX_BYTES = 50 * 1024 * 1024
RETRIES = 2

# characters left as they are when encoding a URL, "%" keeps existing escapes
_URL_SAFE = ":/?#[]@!$&'()*+,;=%~"


class HttpError(Exception):
    """A request failed. The reason is short, to group failures in summaries."""

    def __init__(self, reason: str, detail: str = "", status: int | None = None):
        super().__init__(f"{reason} ({detail})" if detail else reason)
        self.reason = reason
        self.status = status


def get(
    url: str,
    params: dict | None = None,
    timeout: float = TIMEOUT,
    max_bytes: int = MAX_BYTES,
    retries: int = RETRIES,
) -> bytes:
    """Return the content of a URL, retrying on network and server errors."""
    if params:
        url = f"{url}{'&' if '?' in url else '?'}{urlencode(params)}"
    # URLs of catalogs sometimes contain non-ASCII characters
    url = quote(url, safe=_URL_SAFE)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT.decode()})
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(2 ** (attempt - 1))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content = response.read(max_bytes + 1)
        except urllib.error.HTTPError as e:
            error = HttpError(f"HTTP error {e.code}", status=e.code)
            if e.code < 500:
                raise error from e
        except OSError as e:
            error = HttpError("unreachable", str(e))
        else:
            if len(content) > max_bytes:
                raise HttpError("too large", f"more than {max_bytes} bytes")
            return content
    raise error


def get_json(url: str, params: dict | None = None, **kwargs) -> Any:
    return json.loads(get(url, params, **kwargs))
