"""WGS84 Earth-centred, Earth-fixed coordinates: a frame every node shares without agreeing on a
site origin. The broker's rule engine computes rays from detections with the same formulas
(EDTH-infra apps/emqx), so a node's own rays and its peers' rays match."""

import math

A = 6378137.0  # WGS84 semi-major axis, m
E2 = 6.69437999014e-3  # first eccentricity squared
DEG = math.pi / 180


def lla_to_ecef(lat: float, lon: float, alt: float) -> tuple[float, float, float]:
    sp, cp = math.sin(lat * DEG), math.cos(lat * DEG)
    sl, cl = math.sin(lon * DEG), math.cos(lon * DEG)
    n = A / math.sqrt(1 - E2 * sp * sp)
    return ((n + alt) * cp * cl, (n + alt) * cp * sl, (n * (1 - E2) + alt) * sp)


def ecef_to_lla(x: float, y: float, z: float) -> tuple[float, float, float]:
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - E2))
    for _ in range(5):  # converges to well under a millimetre
        sp = math.sin(lat)
        n = A / math.sqrt(1 - E2 * sp * sp)
        alt = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1 - E2 * n / (n + alt)))
    sp = math.sin(lat)
    n = A / math.sqrt(1 - E2 * sp * sp)
    return lat / DEG, lon / DEG, p / math.cos(lat) - n


def bearing_to_ecef(lat: float, lon: float, az: float, el: float) -> tuple[float, float, float]:
    """Unit vector in ECEF for a bearing (az clockwise from north, el up) seen from lat/lon."""
    sp, cp = math.sin(lat * DEG), math.cos(lat * DEG)
    sl, cl = math.sin(lon * DEG), math.cos(lon * DEG)
    e = math.sin(az * DEG) * math.cos(el * DEG)
    n = math.cos(az * DEG) * math.cos(el * DEG)
    u = math.sin(el * DEG)
    return (
        -sl * e - sp * cl * n + cp * cl * u,
        cl * e - sp * sl * n + cp * sl * u,
        cp * n + sp * u,
    )


def ray(lat: float, lon: float, alt: float, az: float, el: float):
    """(origin, direction) in ECEF for a detection seen from a node at lat/lon/alt."""
    return lla_to_ecef(lat, lon, alt), bearing_to_ecef(lat, lon, az, el)
