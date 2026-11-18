import time


class ResponseCache:
    """The contents of replies by URL, kept for a while. Shared by a filter and
    its clones, which search in other threads: a search typed key by key asks
    for the same URLs again and again."""

    def __init__(self, max_age: float = 3600):
        # Seconds a content is kept
        self.max_age = max_age
        self._contents: dict[str, tuple[float, str]] = {}

    def get(self, url: str) -> str | None:
        kept = self._contents.get(url)
        if kept is None or time.monotonic() - kept[0] > self.max_age:
            return None
        return kept[1]

    def put(self, url: str, content: str):
        self._contents[url] = (time.monotonic(), content)
