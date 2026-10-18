import math
import random

import pytest

from src.ecef import bearing_to_ecef, ecef_to_lla, lla_to_ecef, ray
from src.sim import Sim, SimConfig, broker_ray, enu_to_lla, target_position
from src.triangulate import Ray, Triangulator, cross, ray_from_message

SITE = (42.6573, 23.3549, 560.0)


def test_ecef_round_trip():
    for lla in [SITE, (-33.9, 151.2, 12.0), (0.0, 0.0, 0.0), (89.9, -120.0, 9000.0)]:
        assert ecef_to_lla(*lla_to_ecef(*lla)) == pytest.approx(lla, abs=1e-6)


def test_bearing_points_where_it_should():
    up = bearing_to_ecef(*SITE[:2], 0.0, 90.0)
    o = lla_to_ecef(*SITE)
    assert up == pytest.approx(tuple(c / math.dist(o, (0, 0, 0)) for c in o), abs=3e-3)
    north = bearing_to_ecef(*SITE[:2], 0.0, 0.0)
    a = lla_to_ecef(*SITE)
    b = lla_to_ecef(SITE[0] + 0.001, SITE[1], SITE[2])
    d = tuple((q - p) / math.dist(a, b) for p, q in zip(a, b, strict=True))
    assert north == pytest.approx(d, abs=1e-3)


def rays_to(target_enu, nodes_enu, t=1.0):
    target = lla_to_ecef(*enu_to_lla(SITE, *target_enu))
    out = []
    for i, enu in enumerate(nodes_enu):
        o = lla_to_ecef(*enu_to_lla(SITE, *enu))
        d = tuple(q - p for p, q in zip(o, target, strict=True))
        n = math.sqrt(sum(c * c for c in d))
        out.append(Ray(f"n{i}", t, o, tuple(c / n for c in d), 0.9))
    return out


def test_cross_finds_the_target():
    r1, r2 = rays_to((3, 20, 10), [(-15, 0, 1.5), (15, 0, 1.5)])
    mid, miss, angle, s, u = cross(r1, r2, 2000, 2)
    lat, lon, alt = ecef_to_lla(*mid)
    assert (lat, lon, alt) == pytest.approx(enu_to_lla(SITE, 3, 20, 10), abs=1e-6)
    assert miss < 1e-3 and 60 < angle < 90


def test_cross_rejects_parallel_and_behind():
    r1, r2 = rays_to((0, 2000, 0), [(-0.5, 0, 0), (0.5, 0, 0)])
    assert cross(r1, r2, 5000, 2) is None  # 0.03 degrees apart
    a, b = rays_to((3, 20, 10), [(-15, 0, 1.5), (15, 0, 1.5)])
    back = Ray(b.node, b.t, b.o, tuple(-c for c in b.d), b.conf)
    assert cross(a, back, 2000, 2) is None


def test_each_pair_of_frames_gives_one_fix_whoever_arrives_last():
    low, high = rays_to((3, 20, 10), [(-15, 0, 1.5), (15, 0, 1.5)])
    low = Ray("a", 1.0, low.o, low.d, 0.9)
    high = Ray("b", 1.01, high.o, high.d, 0.9)
    for order in ("own first", "peer first"):
        tri_a, tri_b = Triangulator("a"), Triangulator("b")
        if order == "own first":
            got = tri_b.add_own(high) + tri_b.add_peer(low)
        else:
            got = tri_b.add_peer(low) + tri_b.add_own(high)
        got_a = tri_a.add_own(low) + tri_a.add_peer(high)
        assert len(got) == 1 and got_a == []  # "b" > "a" owns the pair
        assert got[0]["node"] == "b" and got[0]["peer"] == "a"


def test_rays_too_far_apart_in_time_do_not_pair():
    a, b = rays_to((3, 20, 10), [(-15, 0, 1.5), (15, 0, 1.5)])
    tri = Triangulator("n1", sync_s=0.05)
    tri.add_peer(Ray("n0", 1.0, a.o, a.d, 0.9))
    assert tri.add_own(Ray("n1", 1.2, b.o, b.d, 0.9)) == []


def test_ray_from_message_validates():
    o, d = ray(*SITE, 10.0, 20.0)
    msg = {"node": "rpi-1", "t": 1.0, "conf": 0.5, "ox": o[0], "oy": o[1], "oz": o[2],
           "dx": d[0], "dy": d[1], "dz": d[2]}  # fmt: skip
    assert ray_from_message(msg).o == o
    for bad in ({**msg, "dx": 5.0}, {**msg, "ox": "x"}, {k: v for k, v in msg.items() if k != "t"}):
        with pytest.raises((ValueError, KeyError, TypeError)):
            ray_from_message(bad)


def test_simulated_nodes_triangulate_the_target(validate):
    random.seed(4)
    sent = []
    sim = Sim(SimConfig(), lambda topic, p: sent.append((topic, p)), local_rays=True)
    for i in range(150):
        t = 1000 + i / 15
        sim.step(t)
        if i % 15 == 0:
            sim.status(t)
    fixes = [p for topic, p in sent if topic.endswith("/fixes")]
    errors = []
    for topic, p in sent:
        kind = topic.rsplit("/", 1)[-1]
        validate({"detections": "detection", "status": "status", "fixes": "fix"}[kind], p)
    for f in fixes:
        truth = enu_to_lla(SimConfig().origin, *target_position(0, f["t"]))
        a, b = lla_to_ecef(f["lat"], f["lon"], f["alt_m"]), lla_to_ecef(*truth)
        errors.append(math.dist(a, b))
    errors.sort()
    assert len(fixes) > 100  # about one per frame
    assert {f["node"] for f in fixes} == {"sim-b"}
    assert errors[len(errors) // 2] < 0.5


def test_broker_ray_matches_ray_schema_fields(validate):
    det = {"node": "rpi-1", "t": 1.0, "az": 10.0, "el": 5.0, "conf": 0.8, "frame": 1,
           "lat": SITE[0], "lon": SITE[1], "alt_m": SITE[2]}  # fmt: skip
    r = broker_ray(det)
    msg = {"node": r.node, "t": r.t, "conf": r.conf, "ingest_ms": 1000.0, "latency_ms": 0.0}
    msg |= dict(zip(("ox", "oy", "oz", "dx", "dy", "dz"), r.o + r.d, strict=True))
    validate("ray", msg)
    validate("detection", det)
