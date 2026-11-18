from swiss_locator.core.constants import PROFILE_URL

# The profile service refuses lines with more vertices, and requests for more
# points
MAX_VERTICES = 5000
MAX_POINTS = 5000

# The service reads its heights in a 2 m grid: closer points repeat a height
SPACING = 2


def profile_url(nb_points: int):
    """URL and query parameters of the profile service, for a line on which it
    adds points to reach nb_points, besides keeping its vertices.

    The line itself is posted as the body of the request: the server refuses
    request lines over 4 KB, which a GET query reaches with about 150 vertices.
    """
    base_url = PROFILE_URL
    base_params = {
        "sr": "2056",
        "nb_points": str(nb_points),
        "distinct_points": "true",
    }
    return base_url, base_params
