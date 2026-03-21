from swiss_locator.core.constants import OPENDATA_SWISS_URL


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
