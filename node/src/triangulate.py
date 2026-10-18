"""Pairwise triangulation on the node: its own rays against its peers' rays.

Each node hears every other node's rays (`rays/{id}`, computed by the broker from detections) and
crosses them with its own. A pair of nodes is handled by the one with the larger id, so each pair
of frames gives one fix, not two. The work is a few dot products per pair: it costs a Pi nothing,
and the ground only has to track the fixes.
"""

import math
import threading
from collections import deque
from dataclasses import dataclass

from .ecef import ecef_to_lla


@dataclass(frozen=True)
class Ray:
    node: str
    t: float  # capture time, node clock
    o: tuple[float, float, float]  # ECEF origin, m
    d: tuple[float, float, float]  # ECEF unit direction
    conf: float


def ray_from_message(msg: dict) -> Ray:
    """A `rays/{id}` message from the broker. Raises KeyError/TypeError/ValueError if malformed."""
    o = (float(msg["ox"]), float(msg["oy"]), float(msg["oz"]))
    d = (float(msg["dx"]), float(msg["dy"]), float(msg["dz"]))
    norm = math.sqrt(_dot(d, d))
    if not all(map(math.isfinite, o + d)) or not 0.99 < norm < 1.01:
        raise ValueError("not a ray")
    return Ray(str(msg["node"]), float(msg["t"]), o, d, float(msg["conf"]))


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(r1: Ray, r2: Ray, max_range_m: float, min_angle_deg: float):
    """Closest approach of two rays: (midpoint, miss, angle_deg, range1, range2), or None when
    they are nearly parallel, meet behind a camera or too far away."""
    b = _dot(r1.d, r2.d)
    den = 1 - b * b
    if den < math.sin(math.radians(min_angle_deg)) ** 2:
        return None
    w = tuple(p - q for p, q in zip(r1.o, r2.o, strict=True))
    d, e = _dot(r1.d, w), _dot(r2.d, w)
    s = (b * e - d) / den  # along r1
    u = (e - b * d) / den  # along r2
    if not (0 < s <= max_range_m and 0 < u <= max_range_m):
        return None
    p1 = tuple(o + s * k for o, k in zip(r1.o, r1.d, strict=True))
    p2 = tuple(o + u * k for o, k in zip(r2.o, r2.d, strict=True))
    mid = tuple((a + c) / 2 for a, c in zip(p1, p2, strict=True))
    miss = math.dist(p1, p2)
    return mid, miss, math.degrees(math.acos(max(-1.0, min(1.0, b)))), s, u


class Triangulator:
    """Thread-safe: own rays come from the camera loop, peer rays from the MQTT thread."""

    def __init__(
        self,
        node: str,
        sync_s: float = 0.05,
        max_miss_m: float = 2.0,
        min_angle_deg: float = 2.0,
        max_range_m: float = 2000.0,
        keep_s: float = 2.0,
    ):
        self.node = node
        self.sync_s = sync_s
        self.max_miss_m = max_miss_m
        self.min_angle_deg = min_angle_deg
        self.max_range_m = max_range_m
        self.keep_s = keep_s
        self._own: deque[Ray] = deque()
        self._peers: dict[str, deque[Ray]] = {}
        self._lock = threading.Lock()

    def owns_pair_with(self, peer: str) -> bool:
        return peer != self.node and self.node > peer

    def add_own(self, ray: Ray) -> list[dict]:
        with self._lock:
            self._keep(self._own, ray)
            return [
                f
                for rays in self._peers.values()
                for f in self._fixes(ray, self._closest(rays, ray.t))
            ]

    def add_peer(self, ray: Ray) -> list[dict]:
        if not self.owns_pair_with(ray.node):
            return []
        with self._lock:
            self._keep(self._peers.setdefault(ray.node, deque()), ray)
            # Same order as add_own: own ray first, so a fix is the same whichever arrived last.
            return [f for own in self._closest(self._own, ray.t) for f in self._fixes(own, [ray])]

    def _keep(self, rays: deque, ray: Ray) -> None:
        rays.append(ray)
        while rays and ray.t - rays[0].t > self.keep_s:
            rays.popleft()

    def _closest(self, rays, t: float) -> list[Ray]:
        """The rays of the frame nearest in time to `t`, if within `sync_s`."""
        near = [r for r in rays if abs(r.t - t) <= self.sync_s]
        if not near:
            return []
        best = min(abs(r.t - t) for r in near)
        return [r for r in near if abs(r.t - t) == best]

    def _fixes(self, own: Ray, peers: list[Ray]) -> list[dict]:
        out = []
        for peer in peers:
            hit = cross(own, peer, self.max_range_m, self.min_angle_deg)
            if hit is None:
                continue
            mid, miss, angle, range_own, _ = hit
            if miss > self.max_miss_m:
                continue
            lat, lon, alt = ecef_to_lla(*mid)
            out.append(
                {
                    "node": self.node,
                    "peer": peer.node,
                    "t": round((own.t + peer.t) / 2, 6),
                    "lat": round(lat, 7),
                    "lon": round(lon, 7),
                    "alt_m": round(alt, 2),
                    "miss_m": round(miss, 3),
                    "angle_deg": round(angle, 2),
                    "range_m": round(range_own, 1),
                    "conf": round(own.conf * peer.conf * (1 - miss / self.max_miss_m), 3),
                }
            )
        return out
