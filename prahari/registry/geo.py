"""Small geodesy helpers. Straight-line (great-circle) distance is a LOWER bound
on road distance, so a speed computed from it is a lower bound on real speed:
if even that is implausible, the hop is implausible."""
from __future__ import annotations

import math

EARTH_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def valid_coord(lat, lon) -> bool:
    return (lat is not None and lon is not None
            and -90 <= lat <= 90 and -180 <= lon <= 180
            and not (lat == 0 and lon == 0))


def parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    """'minLon,minLat,maxLon,maxLat' (GeoJSON / RFC 7946 order)."""
    parts = [float(x) for x in bbox.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be minLon,minLat,maxLon,maxLat")
    min_lon, min_lat, max_lon, max_lat = parts
    if min_lon > max_lon or min_lat > max_lat:
        raise ValueError("bbox min must be <= max")
    return min_lon, min_lat, max_lon, max_lat
