import time

import numpy as np

from src.motion import MotionDetector


def frame_with_dot(x, y):
    return frame_with_dots([(x, y)])


def frame_with_dots(dots):
    frame = np.full((240, 320, 3), 90, np.uint8)
    for x, y in dots:
        frame[y - 2 : y + 3, x - 2 : x + 3] = 255
    return frame


def warmed_up():
    det = MotionDetector()
    for _ in range(20):
        det.detect(frame_with_dots([]))
    return det


def test_detects_a_moving_dot_after_warmup():
    det = MotionDetector()
    rng = np.random.default_rng(0)
    for _ in range(20):  # static background warm-up
        noise = rng.integers(-2, 3, (240, 320, 3))
        det.detect(np.clip(np.full((240, 320, 3), 90) + noise, 0, 255).astype(np.uint8))
    found = []
    for i in range(10):
        found = det.detect(frame_with_dot(60 + 8 * i, 100))
    assert len(found) == 1
    d = found[0]
    assert abs(d.u - (60 + 8 * 9)) < 8 and abs(d.v - 100) < 3
    assert 0.5 <= d.conf <= 1.0


def test_static_scene_yields_nothing():
    det = MotionDetector()
    frame = np.full((240, 320, 3), 90, np.uint8)
    assert all(det.detect(frame) == [] for _ in range(40))


def test_global_motion_is_ignored_and_stays_fast():
    det = MotionDetector()
    rng = np.random.default_rng(1)
    static = np.full((240, 320, 3), 90, np.uint8)
    for _ in range(20):
        det.detect(static)
    start = time.perf_counter()
    for _ in range(10):  # a different noisy scene each frame: thousands of small blobs
        noise = np.where(rng.random((240, 320, 1)) > 0.995, 255, 90).astype(np.uint8)
        assert det.detect(np.repeat(noise, 3, axis=2)) == []
    assert time.perf_counter() - start < 2.0


def test_flicker_and_shuffling_on_the_spot_are_not_reported():
    det = warmed_up()
    found = []
    for i in range(30):
        blinking = [(40, 40)] if i % 2 else []  # a lamp or a reflection switching on and off
        jitter = [(250 + (i % 3) - 1, 200 + (i % 2))]  # something shuffling on the spot
        found = det.detect(frame_with_dots(blinking + jitter + [(30 + 8 * i, 120)]))
        assert all(abs(d.v - 120) < 3 for d in found)  # only ever the travelling dot
    assert len(found) == 1 and abs(found[0].u - (30 + 8 * 29)) < 3


def test_a_fast_target_keeps_its_track_across_big_jumps():
    det = warmed_up()
    found = []
    for i in range(6):  # 45 px a frame, more than the plain gate of 0.08 * 320 = 26 px
        found = det.detect(frame_with_dot(20 + 45 * i, 60 + 20 * i))
    assert len(found) == 1
    assert abs(found[0].u - 245) < 3 and abs(found[0].v - 160) < 3


def test_reports_at_most_max_reports_fastest_first():
    det = warmed_up()
    det.max_reports = 2
    found = []
    for i in range(10):
        dots = [(20 + 4 * i, 30), (20 + 8 * i, 110), (20 + 12 * i, 190)]
        found = det.detect(frame_with_dots(dots))
    assert [round(d.v) for d in found] == [190, 110]
