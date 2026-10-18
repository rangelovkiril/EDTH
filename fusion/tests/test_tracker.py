import json
import math
import random

import numpy as np
import pytest

from src.__main__ import handle
from src.config import Config
from src.geo import LocalFrame
from src.tracker import Tracker

SITE = (42.6573, 23.3549, 560.0)
CFG = Config(origin=SITE)
FRAME = LocalFrame(*SITE)


def circle(t):
    return np.array([10 * math.cos(0.4 * t), 25 + 10 * math.sin(0.4 * t), 12.0])


def fix(t, enu, miss=0.1, node="b", peer="a"):
    lat, lon, alt = FRAME.to_lla(enu)
    return {"node": node, "peer": peer, "t": t, "lat": lat, "lon": lon, "alt_m": alt,
            "miss_m": miss, "angle_deg": 50.0, "range_m": 30.0, "conf": 0.6}  # fmt: skip


def raw(payload):
    return json.dumps(payload).encode()


def feed(tracker, seconds, noise=0.0, fps=15, t0=1000.0, path=circle):
    for i in range(int(seconds * fps)):
        t = t0 + i / fps
        z = path(t) + np.random.normal(0, noise, 3) if noise else path(t)
        assert handle(tracker, "fixes/b", raw(fix(t, z)), t)
    return t0 + seconds


def test_a_track_follows_a_circling_target_and_predicts_ahead():
    np.random.seed(1)
    tracker = Tracker(CFG)
    t = feed(tracker, 6, noise=0.2)
    (p,) = tracker.report(t, t)
    pos = np.array([p["e"], p["n"], p["u"]])
    assert p["id"] == 1 and np.linalg.norm(pos - circle(t)) < 0.6
    assert 3 < p["speed_mps"] < 5  # 0.4 rad/s on a 10 m circle
    pred = FRAME.to_enu(p["pred_lat"], p["pred_lon"], p["pred_alt_m"])
    # Constant velocity on a 10 m circle: ~0.8 m of curve in 1 s, plus the lag of the velocity.
    assert np.linalg.norm(pred - circle(t + 1)) < 2.5
    assert p["sigma_m"] < p["pred_sigma_m"] and 0.3 < p["conf"] <= 1


def test_tentative_until_confirmed_and_ids_have_no_gaps():
    tracker = Tracker(CFG)
    handle(tracker, "fixes/b", raw(fix(1.0, np.array([50.0, 50, 5]))), 1.0)  # a lone ghost
    assert tracker.report(1.0, 1.0) == []
    feed(tracker, 1)
    assert [p["id"] for p in tracker.report(1001, 1001)] == [1]


def test_two_targets_two_tracks():
    tracker = Tracker(CFG)
    other = lambda t: circle(t) + np.array([0, 0, 15])  # noqa: E731
    for i in range(30):
        t = 1000 + i / 15
        handle(tracker, "fixes/b", raw(fix(t, circle(t))), t)
        handle(tracker, "fixes/b", raw(fix(t, other(t))), t)
    assert sorted(p["id"] for p in tracker.report(1002, 1002)) == [1, 2]


def test_tracks_expire():
    tracker = Tracker(CFG)
    t = feed(tracker, 1)
    tracker.expire(t + CFG.track_timeout_s + 0.1)
    assert tracker.report(t + 3, t + 3) == []


def test_origin_defaults_to_the_first_fix():
    tracker = Tracker(Config())
    handle(tracker, "fixes/b", raw(fix(1.0, np.array([3.0, 4, 5]))), 1.0)
    assert tracker.frame.to_enu(*FRAME.to_lla([3.0, 4, 5])) == pytest.approx([0, 0, 0], abs=1e-6)


@pytest.mark.parametrize(
    "topic,payload",
    [
        ("fixes/b", b"not json"),
        ("fixes/b", b'{"node":"b"}'),
        ("fixes/b", raw({**fix(1.0, np.zeros(3)), "lat": "x"})),
        ("fixes/b", raw({**fix(1.0, np.zeros(3)), "node": 3})),
        (
            "fixes/b",
            b'{"node":"b","peer":"a","t":1,"lat":NaN,"lon":1,"alt_m":1,"miss_m":0,"conf":1}',
        ),
        ("nodes/b/fixes", raw(fix(1.0, np.zeros(3)))),
    ],
)
def test_malformed_fixes_are_rejected(topic, payload):
    tracker = Tracker(CFG)
    assert not handle(tracker, topic, payload, 1.0)
    assert tracker.tracks == []


def test_payloads_match_schemas(validate):
    random.seed(2)
    tracker = Tracker(CFG)
    t = feed(tracker, 2)
    validate("fix", fix(1.0, circle(1.0)))
    for p in tracker.report(t, t):
        validate("track", p)
