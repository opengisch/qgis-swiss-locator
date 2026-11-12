"""
Generate a fake lidar point cloud along a line, for the elevation profile
example of the documentation.

    python3 fake_lidar.py FOLDER

The ground follows the terrain of the profile service of geo.admin.ch, so that
the points meet the profile the plugin draws. Trees and a farmhouse stand on
it. Standard library only: it writes an Entwine Point Tile dataset
(FOLDER/ept.json), which QGIS reads without PDAL.
"""

import json
import math
import os
import random
import struct
import sys
import urllib.parse
import urllib.request

# A line across the hills of Langnau im Emmental, in EPSG:2056
LINE = ((2626300.0, 1197200.0), (2627500.0, 1198000.0))
HALF_WIDTH = 25.0  # m, on each side of the line
GROUND_DENSITY = 4.0  # points per m²

# Along the line, in m from its start
FORESTS = ((40.0, 330.0), (930.0, 1180.0))
FARMHOUSES = ((620.0, 8.0), (1300.0, -12.0))  # (distance, offset from the line)
FRUIT_TREES = (585.0, 600.0, 655.0, 670.0, 1270.0, 1330.0)

# LAS classes
GROUND, LOW_VEGETATION, HIGH_VEGETATION, BUILDING = 2, 3, 5, 6

PROFILE_URL = "https://api3.geo.admin.ch/rest/services/profile.json"


def terrain_profile() -> list[tuple[float, float]]:
    """Return (distance, height) along the line, from swissALTI3D."""
    geometry = {"type": "LineString", "coordinates": [list(p) for p in LINE]}
    query = urllib.parse.urlencode(
        {"geom": json.dumps(geometry), "sr": 2056, "nb_points": 400}
    )
    request = urllib.request.Request(
        f"{PROFILE_URL}?{query}", headers={"User-Agent": "qgis-swiss-locator docs"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        points = json.load(response)
    return [(point["dist"], point["alts"]["DTM2"]) for point in points]


class Terrain:
    def __init__(self, profile: list[tuple[float, float]]):
        self.profile = profile
        (x1, y1), (x2, y2) = LINE
        self.length = math.hypot(x2 - x1, y2 - y1)
        self.ux, self.uy = (x2 - x1) / self.length, (y2 - y1) / self.length

    def height(self, distance: float) -> float:
        profile = self.profile
        if distance <= profile[0][0]:
            return profile[0][1]
        for (d1, z1), (d2, z2) in zip(profile, profile[1:]):
            if distance <= d2:
                return z1 + (z2 - z1) * (distance - d1) / (d2 - d1)
        return profile[-1][1]

    def position(self, distance: float, offset: float) -> tuple[float, float]:
        """Map coordinates of a point at a distance along the line and an
        offset to its left."""
        x0, y0 = LINE[0]
        return (
            x0 + self.ux * distance - self.uy * offset,
            y0 + self.uy * distance + self.ux * offset,
        )


def generate(terrain: Terrain, rng: random.Random) -> list[tuple]:
    """Return points as (x, y, z, class, intensity)."""
    points = []

    def add(distance, offset, z, classification, intensity):
        x, y = terrain.position(distance, offset)
        points.append((x, y, z, classification, intensity))

    def in_forest(distance):
        return any(start <= distance <= end for start, end in FORESTS)

    # Ground, fewer points under the trees
    area = terrain.length * 2 * HALF_WIDTH
    for _ in range(int(area * GROUND_DENSITY)):
        distance = rng.uniform(0, terrain.length)
        if in_forest(distance) and rng.random() < 0.7:
            continue
        offset = rng.uniform(-HALF_WIDTH, HALF_WIDTH)
        z = terrain.height(distance) + rng.gauss(0, 0.05)
        add(distance, offset, z, GROUND, rng.randint(80, 140))
        if not in_forest(distance) and rng.random() < 0.05:
            # grass and bushes
            add(distance, offset, z + rng.uniform(0.2, 1.5), LOW_VEGETATION, 60)

    def tree(distance, offset, height, radius):
        ground = terrain.height(distance)
        crown_base = ground + height * rng.uniform(0.35, 0.5)
        for _ in range(int(radius * radius * 18)):
            # mostly on the top of the crown, as seen from the plane
            angle = rng.uniform(0, 2 * math.pi)
            r = radius * math.sqrt(rng.random())
            top = height - (height + ground - crown_base) * (r / radius) ** 2 * 0.6
            z = ground + top - abs(rng.gauss(0, 0.8))
            z = max(z, crown_base)
            add(
                distance + r * math.cos(angle),
                offset + r * math.sin(angle),
                z,
                HIGH_VEGETATION,
                rng.randint(20, 60),
            )

    for start, end in FORESTS:
        for _ in range(int((end - start) * 2 * HALF_WIDTH / 30)):
            tree(
                rng.uniform(start, end),
                rng.uniform(-HALF_WIDTH, HALF_WIDTH),
                rng.uniform(22, 34),
                rng.uniform(2.5, 4.5),
            )
    for distance in FRUIT_TREES:
        tree(distance, rng.uniform(-15, 15), rng.uniform(7, 10), rng.uniform(3, 4))

    # Emmental farmhouses: a large hipped roof down to a few metres above ground
    for center, center_offset in FARMHOUSES:
        length, width, eaves, ridge = 30.0, 20.0, 4.5, 14.0
        ground = terrain.height(center)
        for _ in range(int(length * width * 12)):
            along = rng.uniform(-length / 2, length / 2)
            across = rng.uniform(-width / 2, width / 2)
            # distance to the nearest edge, the roof rises to the ridge
            edge = min(width / 2 - abs(across), (length / 2 - abs(along)) * 0.8)
            z = ground + eaves + (ridge - eaves) * min(1.0, edge / (width / 2))
            add(
                center + along,
                center_offset + across,
                z + rng.gauss(0, 0.04),
                BUILDING,
                rng.randint(150, 220),
            )

    return points


def write_ept(folder: str, points: list[tuple]):
    """Write an Entwine Point Tile dataset with a single node, uncompressed,
    which the native ept provider of QGIS reads."""
    scale = 0.01
    xs, ys, zs = ([p[i] for p in points] for i in range(3))
    tight = [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)]
    # EPT needs a cube
    center = [(tight[i] + tight[i + 3]) / 2 for i in range(3)]
    half = max(tight[i + 3] - tight[i] for i in range(3)) / 2 + 1
    cube = [c - half for c in center] + [c + half for c in center]
    offset = [round(c) for c in center]

    schema = [
        {"name": axis, "type": "signed", "size": 4, "scale": scale, "offset": o}
        for axis, o in zip("XYZ", offset)
    ] + [
        {"name": "Intensity", "type": "unsigned", "size": 2},
        {"name": "Classification", "type": "unsigned", "size": 1},
    ]
    ept = {
        "bounds": cube,
        "boundsConforming": tight,
        "dataType": "binary",
        "hierarchyType": "json",
        "points": len(points),
        "schema": schema,
        "span": 128,
        "srs": {"authority": "EPSG", "horizontal": "2056"},
        "version": "1.0.0",
    }

    os.makedirs(os.path.join(folder, "ept-data"), exist_ok=True)
    os.makedirs(os.path.join(folder, "ept-hierarchy"), exist_ok=True)
    with open(os.path.join(folder, "ept.json"), "w") as f:
        json.dump(ept, f, indent=2)
    with open(os.path.join(folder, "ept-hierarchy", "0-0-0-0.json"), "w") as f:
        json.dump({"0-0-0-0": len(points)}, f)

    record = struct.Struct("<iiiHB")
    with open(os.path.join(folder, "ept-data", "0-0-0-0.bin"), "wb") as f:
        for x, y, z, classification, intensity in points:
            f.write(
                record.pack(
                    round((x - offset[0]) / scale),
                    round((y - offset[1]) / scale),
                    round((z - offset[2]) / scale),
                    intensity,
                    classification,
                )
            )


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    terrain = Terrain(terrain_profile())
    points = generate(terrain, random.Random(2056))
    write_ept(sys.argv[1], points)
    print(f"{len(points)} points written to {sys.argv[1]}")


if __name__ == "__main__":
    main()
