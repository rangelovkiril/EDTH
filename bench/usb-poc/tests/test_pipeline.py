import json
import struct
import time
import zlib

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from skywatch.app import create_app
from skywatch.detection import MotionDetector
from skywatch.engine import Engine
from skywatch.geometry import VoxelProjector, demo_models, triangulate
from skywatch.sources import (
    HEADER,
    MAGIC,
    Frame,
    clock_offset,
    decode_clock_reply,
    decode_packet,
    demo_frame,
)


def test_stereo_recovers_known_point_and_rejects_degenerate_geometry():
    a, b = demo_models()
    point = np.array([2.0, -1.0, 30.0])
    pa = a.project([point])[0][0]
    pb = b.project([point])[0][0]
    result = triangulate(a, b, pa, pb)
    assert np.allclose(result["position"], point, atol=1e-6)
    assert triangulate(a, b, [320, 240], [320, 240]) is None
    assert triangulate(a, b, pa, pb + [0, 40]) is None
    assert triangulate(a, b, pb, pa) is None


def test_voxels_require_both_camera_masks():
    models = demo_models()
    grid = VoxelProjector([[-4, 4], [-4, 4], [10, 40]], 16)
    blank = np.zeros((480, 640), np.uint8)
    full = np.full_like(blank, 255)
    assert grid.reconstruct(models, [full, blank]) == []
    assert len(grid.reconstruct(models, [full, full])) > 0


def test_packet_resynchronizes_fragmentation_and_corrupt_crc():
    _, jpeg = cv2.imencode(".jpg", np.full((24, 32, 3), 120, np.uint8))
    payload = jpeg.tobytes()
    packet = MAGIC + HEADER.pack(len(payload), 7, 123456, zlib.crc32(payload)) + payload
    buffer = bytearray(b"boot log\n" + packet[:17])
    assert decode_packet(buffer) is None
    buffer.extend(packet[17:])
    image, seq, timestamp = decode_packet(buffer)
    assert image.shape == (24, 32, 3) and seq == 7 and timestamp == 123456
    bad = MAGIC + HEADER.pack(len(payload), 0, 0, 123) + payload
    assert decode_packet(bytearray(bad + packet))[1] == 7
    assert decode_packet(bytearray(MAGIC + HEADER.pack(0xFFFFFFFF, 0, 0, 0) + packet))[1] == 7
    # Stray bytes outside the JPEG length must not consume any bytes of the
    # next reply, including when it arrives in fragments.
    buffer = bytearray(packet + b"\x00" + packet[:11])
    assert decode_packet(buffer)[1] == 7
    assert decode_packet(buffer) is None
    buffer.extend(packet[11:])
    assert decode_packet(buffer)[1] == 7


def test_static_and_global_motion_suppressed_and_moving_object_tracked():
    detector = MotionDetector()
    image = np.full((240, 320, 3), 160, np.uint8)
    for _ in range(25):
        _, tracks, _ = detector.process(image)
    assert tracks == []
    found = []
    for i in range(20):
        moving = image.copy()
        cv2.rectangle(moving, (30 + i * 3, 100), (40 + i * 3, 108), (0, 0, 0), -1)
        _, found, _ = detector.process(moving)
    assert found
    mask, tracks, suppressed = detector.process(np.zeros_like(image))
    assert suppressed and not tracks and not mask.any()


def test_bad_jpeg_requests_retry_instead_of_waiting_for_transport_timeout():
    payload = b"not a JPEG"
    packet = MAGIC + HEADER.pack(len(payload), 9, 100, zlib.crc32(payload)) + payload
    retries = []
    assert decode_packet(bytearray(packet), on_invalid=lambda: retries.append(True)) is None
    assert retries == [True]


def test_demo_pixels_produce_real_tracks_and_range(tmp_path):
    engine = Engine({"mode": "demo"}, tmp_path)
    start = engine.started
    accepted = 0
    for seq in range(55):
        engine.tick(start + seq * 0.1, seq)
        state = engine.snapshot()
        if state["tracks"]:
            accepted += 1
            assert 15 < state["tracks"][0]["range_m"] < 45
    assert accepted >= 10
    assert engine.snapshot()["events_total"] >= 2


def test_api_validation_and_csv():
    with TestClient(create_app({"mode": "demo"})) as client:
        assert client.get("/").status_code == 200
        assert (
            client.post("/api/settings", json={"threshold": -1, "min_area": 0}).status_code == 422
        )
        assert (
            client.post("/api/settings", json={"threshold": 25, "min_area": 8}).status_code == 200
        )
        assert (
            client.post("/api/reset", headers={"Origin": "https://untrusted.example"}).status_code
            == 403
        )
        assert client.post("/api/calibration/capture").status_code == 409
        assert client.get("/api/cameras/9/frame.jpg").status_code == 404
        assert "skywatch_simulation 1" in client.get("/metrics").text
        assert client.get("/api/events.csv").text.startswith("time,camera,track,event,mode")


def test_live_never_uses_synthetic_calibration(tmp_path):
    (tmp_path / "bad.json").write_text(json.dumps({"simulated": True}))
    with pytest.raises(ValueError, match="Synthetic"):
        Engine(
            {"mode": "live", "cameras": [{"type": "usb", "source": 0}], "calibration": "bad.json"},
            tmp_path,
        )


def test_clock_offset_bounds_include_asymmetric_usb_delay():
    # Device is 100 seconds behind host; request reaches board 8 ms after sending.
    offset, uncertainty = clock_offset(110.0, 110.010, 10_008_000)
    assert offset - uncertainty <= 100 <= offset + uncertainty
    assert uncertainty == pytest.approx(0.005)


def test_clock_reply_rejects_old_nonce_and_recovers_partial_response():
    old = b"SKYTIME2" + struct.pack("<IQ", 41, 100)
    current = b"SKYTIME2" + struct.pack("<IQ", 42, 200)
    buffer = bytearray(b"boot noise\r\n" + old + current[:13])
    assert decode_clock_reply(buffer, 42) is None
    buffer.extend(current[13:])
    assert decode_clock_reply(buffer, 42) == 200
    assert not buffer


class FakeSource:
    def __init__(self, frame):
        self.frame = frame

    def read(self):
        return self.frame, None


@pytest.mark.parametrize("problem", ["stale", "uncertain", "size"])
def test_live_depth_gates(problem, tmp_path):
    engine = Engine(
        {"mode": "live", "cameras": [{"type": "usb", "source": 0}, {"type": "usb", "source": 1}]},
        tmp_path,
    )
    engine.models = demo_models()
    now = time.monotonic()
    image = demo_frame(engine.models[0], 2)
    if problem == "size":
        image = cv2.resize(image, (320, 240))
    frame = Frame(
        image, now - (2 if problem == "stale" else 0), 1 if problem == "uncertain" else 0, 1
    )
    engine.sources = [FakeSource(frame), FakeSource(frame)]
    engine.tick(now, 1)
    state = engine.snapshot()
    assert not state["tracks"] and not state["voxels"]
    expected = {"stale": "fresh", "uncertain": "Timing", "size": "Resolution"}[problem]
    assert expected in state["status"]
