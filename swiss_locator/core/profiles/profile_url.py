def profile_url(geojson: str):
    base_url = "https://api3.geo.admin.ch/rest/services/profile.json"
    base_params = {
        "geom": geojson,
        "sr": "2056",
        "nb_points": "200",  # Number of points used for polyline segmentation. API: 200
        "distinct_points": "true"
    }
    return base_url, base_params
