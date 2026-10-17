import numpy as np

from src.motion import MotionDetector


def frame_with_dot(x, y):
    frame = np.full((240, 320, 3), 90, np.uint8)
    frame[y - 2 : y + 3, x - 2 : x + 3] = 255
    return frame


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
