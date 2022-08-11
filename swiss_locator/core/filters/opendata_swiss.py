def opendata_swiss_url(search: str):
    url = "https://opendata.swiss/api/3/action/package_search?"
    params = {"q": "q=Layers+%C3" + str(search)}
    return url, params
