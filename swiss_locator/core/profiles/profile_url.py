from swiss_locator.core.constants import PROFILE_URL


def profile_url(geojson: str):
    base_url = PROFILE_URL
    base_params = {
        "geom": geojson,
        "sr": "2056",
        "nb_points": "200",  # Number of points used for polyline segmentation. API: 200
        "distinct_points": "true",
    }
    return base_url, base_params
