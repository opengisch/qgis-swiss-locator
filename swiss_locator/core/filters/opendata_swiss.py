def opendata_swiss_url(search: str):
    url = "https://opendata.swiss/api/3/action/package_search"
    params = {
        "q": search,
        "fq": "res_format:WMS OR res_format:WMTS",
    }
    return url, params
