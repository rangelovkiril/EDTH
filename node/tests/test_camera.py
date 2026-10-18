import sys
import time
import types

import numpy as np
import pytest

from src import camera


def install_fake_picamera2(
    monkeypatch, model="imx708_wide", array=(4608, 2592), crop=(0, 0, 4608, 2592)
):
    calls = {}

    class Request:
        def __init__(self, stamp):
            self.stamp, self.released = stamp, False

        def make_array(self, name):
            assert name == "main"
            return np.zeros((720, 1280, 3), np.uint8)

        def get_metadata(self):
            return {"SensorTimestamp": self.stamp, "ScalerCrop": crop}

        def release(self):
            self.released = True

    class Picamera2:
        camera_controls = {"LensPosition": (0.0, 32.0, 1.0)}
        camera_properties = {"Model": model, "PixelArraySize": array}

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


def test_hfov_comes_from_the_sensor_and_the_crop_the_isp_applies(monkeypatch):
    install_fake_picamera2(monkeypatch)  # Camera Module 3 Wide, whole array
    wide = camera.open_camera("csi", 1280, 720)
    assert wide.model == "imx708_wide" and wide.hfov_deg is None  # not known before a frame
    wide.read()
    assert wide.hfov_deg == pytest.approx(102.0)

    install_fake_picamera2(monkeypatch, "imx219", (3280, 2464), (0, 0, 3280, 1845))  # V2, 16:9
    v2 = camera.open_camera("csi", 1280, 720)
    v2.read()
    assert v2.hfov_deg == pytest.approx(62.2)  # 16:9 only trims rows

    # the 640x480 sensor mode is a crop of the middle of the array
    install_fake_picamera2(monkeypatch, "imx219", (3280, 2464), (1000, 752, 1280, 960))
    cropped = camera.open_camera("csi", 640, 480)
    cropped.read()
    assert 25 < cropped.hfov_deg < 28  # much narrower


def test_hfov_is_unknown_for_a_sensor_without_a_datasheet_value(monkeypatch):
    install_fake_picamera2(monkeypatch, "imx477", (4056, 3040), (0, 0, 4056, 3040))
    hq = camera.open_camera("csi", 1280, 720)
    hq.read()
    assert hq.hfov_deg is None  # the lens is interchangeable: set CAMERA_HFOV_DEG


def test_sensor_time_falls_back_when_missing_or_implausible():
    assert camera._sensor_time_to_unix(None) is None
    now_ns = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    assert camera._sensor_time_to_unix(now_ns - 60_000_000_000) is None  # a minute old
    assert camera._sensor_time_to_unix(now_ns + 60_000_000_000) is None  # from the future


def test_csi_without_picamera2_explains_itself(monkeypatch):
    monkeypatch.setitem(sys.modules, "picamera2", None)  # makes the import fail
    with pytest.raises(RuntimeError, match="python3-picamera2"):
        camera.open_camera("csi", 640, 480)
