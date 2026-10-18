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
            meta = {"SensorTimestamp": self.stamp}
            if crop:
                meta["ScalerCrop"] = crop
            return meta

        def release(self):
            self.released = True

    class Picamera2:
        camera_controls = {"LensPosition": (0.0, 32.0, 1.0)}
        camera_properties = {"Model": model, "PixelArraySize": array}

        @property
        def sensor_modes(self):
            raise AssertionError("listing modes configures 4608x2592: ENOMEM on a Pi 5")

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


def test_the_isp_crop_of_the_first_frame_overrides_the_estimate(monkeypatch):
    install_fake_picamera2(monkeypatch, "imx219", (3280, 2464), (0, 0, 3280, 1845))  # V2, 16:9
    v2 = camera.open_camera("csi", 1280, 720)
    v2.read()
    assert v2.hfov_deg == pytest.approx(62.2)  # 16:9 only trims rows

    # a crop of the middle of the array, e.g. a digital zoom
    install_fake_picamera2(monkeypatch, "imx219", (3280, 2464), (1000, 752, 1280, 960))
    cropped = camera.open_camera("csi", 640, 480)
    assert cropped.hfov_deg == pytest.approx(62.2)  # the estimate from the mode
    cropped.read()
    assert 25 < cropped.hfov_deg < 28  # what the frames really show


def test_runs_the_binned_mode_that_sees_the_whole_array(monkeypatch):
    calls = install_fake_picamera2(monkeypatch, crop=None)
    wide = camera.open_camera("csi", 1280, 720)
    # not 1536x864, which libcamera picks by itself and which crops to 79 degrees
    assert calls["config"]["sensor"] == {"output_size": (2304, 1296), "bit_depth": 10}
    assert wide.hfov_deg == pytest.approx(102.0)  # known before a frame

    # without a ScalerCrop in the metadata the mode alone gives the HFOV
    calls = install_fake_picamera2(monkeypatch, "imx219", (3280, 2464), None)
    v2 = camera.open_camera("csi", 640, 480)
    v2.read()
    assert calls["config"]["sensor"]["output_size"] == (1640, 1232)
    assert v2.hfov_deg == pytest.approx(62.2)


def test_a_4_3_frame_from_a_16_9_mode_loses_some_width(monkeypatch):
    install_fake_picamera2(monkeypatch, crop=None)
    assert 85 < camera.open_camera("csi", 640, 480).hfov_deg < 86  # 3456 of 4608 columns


def test_a_frame_larger_than_the_binned_mode_leaves_the_choice_to_libcamera(monkeypatch):
    calls = install_fake_picamera2(monkeypatch, "imx219", (3280, 2464), None)
    big = camera.open_camera("csi", 1920, 1080)
    assert "sensor" not in calls["config"] and big.hfov_deg is None


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
