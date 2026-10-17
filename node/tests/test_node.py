import json
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.config import Config
from src.detector import load_detector
from src.motion import MotionDetector
from src.payloads import detection_payload
from src.publisher import DryRunPublisher


def test_load_detector_by_short_and_full_name():
    assert isinstance(load_detector("motion:MotionDetector"), MotionDetector)
    assert isinstance(load_detector("src.motion:MotionDetector"), MotionDetector)
    for bad in ("motion", "nope:X", "motion:Nope"):
        with pytest.raises((ValueError, ImportError, AttributeError)):
            load_detector(bad)


def test_dry_run_does_not_need_a_broker():
    cfg = Config.from_env({"NODE_ID": "rpi-1", "DRY_RUN": "1"})
    assert cfg.dry_run and cfg.mqtt_host is None
    with pytest.raises(ValueError):
        Config.from_env({"NODE_ID": "rpi-1"})


def test_dry_run_publisher_prints_topic_and_json(capsys, validate):
    pub = DryRunPublisher(Config.from_env({"NODE_ID": "rpi-1", "DRY_RUN": "1"}))
    assert pub.publish_detection(detection_payload("rpi-1", 1.0, 10.0, 5.0, 0.9, 1))
    topic, body = capsys.readouterr().out.strip().split(" ", 1)
    assert topic == "nodes/rpi-1/detections"
    validate("detection", json.loads(body))


def test_node_runs_end_to_end_on_a_video_file(tmp_path, validate):
    path = str(tmp_path / "dot.avi")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 30, (320, 240))
    rng = np.random.default_rng(0)
    for i in range(80):
        frame = np.clip(90 + rng.integers(-2, 3, (240, 320, 3)), 0, 255).astype(np.uint8)
        if i >= 20:
            cv2.circle(frame, (40 + 4 * (i - 20), 100), 4, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()

    env = {
        **os.environ,
        "NODE_ID": "rpi-1",
        "DRY_RUN": "1",
        "CAMERA_DEVICE": path,
        "NTP_SERVER": "127.0.0.1",
    }
    out = subprocess.run(
        [sys.executable, "-m", "src"],
        env=env,
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.splitlines()
    detections = [line.split(" ", 1) for line in out if line.startswith("nodes/rpi-1/detections")]
    assert detections, out
    for _, body in detections:
        validate("detection", json.loads(body))
