import sys
import time
import types

import numpy as np
import pytest

from src import camera
from src.config import Config
from src.publisher import DryRunPublisher
from src.status import StatusReporter


def install_fake_picamera2(monkeypatch):
    calls = {}

    class Request:
        def __init__(self, stamp):
            self.stamp, self.released = stamp, False

        def make_array(self, name):
            assert name == "main"
            return np.zeros((720, 1280, 3), np.uint8)

        def get_metadata(self):
            return {"SensorTimestamp": self.stamp}

        def release(self):
            self.released = True

    class Picamera2:
        camera_controls = {"LensPosition": (0.0, 32.0, 1.0)}

        def create_video_configuration(self, **kw):
            calls["config"] = kw
            return kw

        def configure(self, config):
            calls["configured"] = config

        def start(self):
            calls["started"] = True

        def set_controls(self, controls):
            calls["controls"] = controls

        def capture_request(self):
            calls["request"] = Request(time.clock_gettime_ns(time.CLOCK_BOOTTIME) - 40_000_000)
            return calls["request"]

        def stop(self):
            calls["stopped"] = True

        def close(self):
            calls["closed"] = True

    class AfModeEnum:
        Manual = 0

    monkeypatch.setitem(sys.modules, "picamera2", types.SimpleNamespace(Picamera2=Picamera2))
    monkeypatch.setitem(
        sys.modules,
        "libcamera",
        types.SimpleNamespace(controls=types.SimpleNamespace(AfModeEnum=AfModeEnum)),
    )
    return calls


def test_open_camera_csi_configures_bgr_fixed_focus_and_stamps_sensor_time(monkeypatch):
    calls = install_fake_picamera2(monkeypatch)
    cam = camera.open_camera("csi", 1280, 720, 30)

    config = calls["config"]
    assert config["main"] == {"size": (1280, 720), "format": "RGB888"}  # B,G,R in memory
    assert config["controls"] == {"FrameRate": 30}
    assert calls["controls"] == {"AfMode": 0, "LensPosition": 0.0}  # infinity

    before = time.time()
    frame = cam.read()
    assert frame.shape == (720, 1280, 3) and frame.dtype == np.uint8
    assert calls["request"].released
    # the frame was exposed ~40 ms before we read it
    assert 0.02 < before - cam.captured_at < 0.2
    cam.close()
    assert calls["stopped"] and calls["closed"]


def test_sensor_time_falls_back_when_missing_or_implausible():
    assert camera._sensor_time_to_unix(None) is None
    now_ns = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    assert camera._sensor_time_to_unix(now_ns - 60_000_000_000) is None  # a minute old
    assert camera._sensor_time_to_unix(now_ns + 60_000_000_000) is None  # from the future


def test_csi_without_picamera2_explains_itself(monkeypatch):
    monkeypatch.setitem(sys.modules, "picamera2", None)  # makes the import fail
    with pytest.raises(RuntimeError, match="python3-picamera2"):
        camera.open_camera("csi", 640, 480)


def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_health_file_moves_only_while_frames_flow(tmp_path):
    cfg = Config.from_env({"NODE_ID": "rpi-1", "DRY_RUN": "1"})
    health = tmp_path / "alive"
    reporter = StatusReporter(
        DryRunPublisher(cfg), "127.0.0.1", interval=0.05, ntp_every=1e9, health_file=str(health)
    )
    reporter.start()
    try:
        time.sleep(0.5)
        assert not health.exists()  # no frames yet: not alive
        reporter.tick()
        assert wait_for(health.exists)
        time.sleep(0.2)
        first = health.stat().st_mtime
        time.sleep(0.3)
        assert health.stat().st_mtime == first  # no new frames: the file stops moving
    finally:
        reporter.stop()
