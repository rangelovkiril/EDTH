import json
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from .detection import MotionDetector
from .geometry import CameraModel, VoxelProjector, demo_models, triangulate
from .sources import Frame, Source, demo_frame


class Engine:
    def __init__(self, config, root):
        self.config, self.root = config, Path(root)
        self.mode = config.get("mode", "demo")
        if self.mode not in ("demo", "live"):
            raise ValueError("mode must be demo or live")
        self.camera_configs = config.get("cameras", [])
        if self.mode == "demo":
            self.camera_configs = [
                {"name": "West optical", "type": "synthetic"},
                {"name": "East optical", "type": "synthetic"},
            ]
            self.models = demo_models()
        else:
            if not 1 <= len(self.camera_configs) <= 8:
                raise ValueError("Configure 1..8 cameras")
            for cfg in self.camera_configs:
                if (
                    cfg["type"] not in ("serial", "usb", "stream", "file")
                    or not 1 <= cfg.get("fps", 10) <= 60
                ):
                    raise ValueError("Invalid camera type or fps")
            self.models = []
            if config.get("calibration"):
                data = json.loads((self.root / config["calibration"]).read_text())
                if data.get("simulated"):
                    raise ValueError("Synthetic calibration is forbidden in live mode")
                self.models = [CameraModel.from_dict(x) for x in data["cameras"]]
                if len(self.models) != 2:
                    raise ValueError("Calibration must describe the first two cameras")
                expected = [x.get("source") for x in self.camera_configs[:2]]
                if data.get("sources") != expected:
                    raise ValueError("Calibration source order does not match configured cameras")
        self.bounds = config.get("voxel_bounds", [[-12, 12], [-8, 8], [5, 65]])
        self.projector = VoxelProjector(self.bounds, config.get("voxel_resolution", 36))
        self.sources = [] if self.mode == "demo" else [Source(c) for c in self.camera_configs]
        self.detectors = [MotionDetector() for _ in self.camera_configs]
        self.latest_frames = [None] * len(self.camera_configs)
        self.last_sequences = [None] * len(self.camera_configs)
        self.results = [None] * len(self.camera_configs)
        self.jpegs = [None] * len(self.camera_configs)
        self.masks = [None] * len(self.camera_configs)
        self.settings = {"threshold": 20, "min_area": 5}
        self.events = deque(maxlen=1000)
        self.history = deque(maxlen=120)
        self.seen = set()
        self.event_count = 0
        self.frames_total = 0
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.started = time.monotonic()
        self.state = {
            "mode": self.mode,
            "cameras": [],
            "status": "Starting",
            "tracks": [],
            "voxels": [],
        }
        self.reset_requested = False

    def start(self):
        for source in self.sources:
            source.start()
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=4)
        for source in self.sources:
            source.stop()

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def update_settings(self, values):
        with self.lock:
            self.settings.update(values)
            return dict(self.settings)

    def save_pair(self):
        with self.lock:
            if self.mode != "live":
                raise ValueError("Calibration capture requires live cameras")
            frames = self.latest_frames[:2]
            if len(frames) < 2 or any(
                f is None or time.monotonic() - f.timestamp > 1 for f in frames
            ):
                raise ValueError("Two fresh camera frames are required")
            pair = uuid.uuid4().hex[:12]
            directory = self.root / "data" / "calibration"
            directory.mkdir(parents=True, exist_ok=True)
            for i, frame in enumerate(frames):
                cv2.imwrite(str(directory / f"{pair}_{i}.png"), frame.image)
            (directory / f"{pair}.json").write_text(
                json.dumps(
                    {
                        "sources": [c["source"] for c in self.camera_configs[:2]],
                        "host_skew_s": abs(frames[0].timestamp - frames[1].timestamp),
                    }
                )
            )
            return {"pair": pair, "directory": str(directory)}

    def run(self):
        sequence = 0
        while not self.stop_event.is_set():
            start = time.monotonic()
            try:
                self.tick(start, sequence)
            except Exception:
                logging.exception("Processing frame failed")
                with self.lock:
                    self.state.update(
                        status="Processing error — see server log", tracks=[], voxels=[]
                    )
            sequence += 1
            self.stop_event.wait(max(0, 0.1 - (time.monotonic() - start)))

    def tick(self, now, sequence):
        with self.lock:
            settings = dict(self.settings)
            if self.reset_requested:
                self.detectors = [MotionDetector() for _ in self.camera_configs]
                self.results = [None] * len(self.camera_configs)
                self.seen.clear()
                self.reset_requested = False
        cameras = []
        for i, cfg in enumerate(self.camera_configs):
            if self.mode == "demo":
                frame, error = (
                    Frame(demo_frame(self.models[i], now - self.started), now, 0, sequence),
                    None,
                )
            else:
                frame, error = self.sources[i].read()
            fresh = frame is not None and now - frame.timestamp < 1
            new = fresh and frame.sequence != self.last_sequences[i]
            if new:
                previous = self.latest_frames[i]
                if previous is not None and (
                    frame.image.shape != previous.image.shape
                    or frame.timestamp - previous.timestamp > 1
                ):
                    self.detectors[i] = MotionDetector()
                mask, tracks, suppressed = self.detectors[i].process(frame.image, **settings)
                self.results[i] = (mask, tracks, suppressed)
                self.last_sequences[i] = frame.sequence
                self.frames_total += 1
                annotated = frame.image.copy()
                for track in tracks:
                    x, y, w, h = track.box
                    cv2.rectangle(
                        annotated, (x - 5, y - 5), (x + w + 5, y + h + 5), (100, 235, 110), 1
                    )
                    cv2.putText(
                        annotated,
                        f"MOTION {i + 1}:{track.id}",
                        (max(0, x - 5), max(15, y - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.4,
                        (100, 235, 110),
                        1,
                    )
                    if len(track.trail) > 1:
                        cv2.polylines(
                            annotated,
                            [np.asarray(track.trail, np.int32)],
                            False,
                            (100, 235, 110),
                            1,
                        )
                    key = (i, track.id)
                    if key not in self.seen:
                        self.seen.add(key)
                        self.event_count += 1
                        with self.lock:
                            self.events.appendleft(
                                {
                                    "time": time.time(),
                                    "camera": i + 1,
                                    "track": track.id,
                                    "event": "Persistent motion",
                                    "mode": self.mode,
                                }
                            )
                _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
                _, mask_jpeg = cv2.imencode(".jpg", mask)
                with self.lock:
                    self.jpegs[i], self.masks[i] = jpeg.tobytes(), mask_jpeg.tobytes()
                    self.latest_frames[i] = frame
            result = self.results[i] if fresh else None
            tracks = result[1] if result else []
            cameras.append(
                {
                    "id": i,
                    "name": cfg.get("name", f"Camera {i + 1}"),
                    "type": cfg["type"],
                    "connected": fresh,
                    "error": error,
                    "age_ms": round((now - frame.timestamp) * 1000) if frame else None,
                    "size": [frame.image.shape[1], frame.image.shape[0]] if fresh else None,
                    "sequence": frame.sequence if fresh else None,
                    "timing_uncertainty_ms": round(frame.uncertainty * 1000, 2) if fresh else None,
                    "tracks": [asdict(t) for t in tracks],
                    "suppressed": bool(result[2]) if result else False,
                    "warming": self.detectors[i].frames <= 15,
                }
            )
        fused, voxels, skew = [], [], None
        if len(cameras) >= 2 and all(c["connected"] for c in cameras[:2]):
            pair = self.latest_frames[:2]
            if all(frame is not None for frame in pair):
                skew = abs(pair[0].timestamp - pair[1].timestamp) + sum(
                    frame.uncertainty for frame in pair
                )
        status = "Calibration required — motion tracking only"
        if self.models and len(cameras) >= 2:
            frames = self.latest_frames[:2]
            if not all(c["connected"] for c in cameras[:2]):
                status = "Waiting for two fresh cameras"
            elif any(tuple(cameras[i]["size"]) != self.models[i].size for i in range(2)):
                status = "Resolution differs from calibration — depth disabled"
            else:
                skew = abs(frames[0].timestamp - frames[1].timestamp) + sum(
                    f.uncertainty for f in frames
                )
                if skew > self.config.get("max_pair_skew_s", 0.2):
                    status = "Timing uncertainty too large — depth disabled"
                elif any(self.results[i] is None or self.results[i][2] for i in range(2)):
                    status = "Background settling / global motion suppressed"
                else:
                    masks = [r[0] for r in self.results[:2]]
                    voxels = self.projector.reconstruct(self.models, masks)
                    tracks = [r[1] for r in self.results[:2]]
                    status = "Observing — waiting for one target in each view"
                    if all(len(t) == 1 for t in tracks):
                        target = triangulate(
                            *self.models,
                            tracks[0][0].center,
                            tracks[1][0].center,
                            max_range=self.config.get("max_range_m", 5000),
                        )
                        if target:
                            target["label"] = "Unclassified motion"
                            fused = [target]
                            status = "Two-view candidate — identity unverified"
                        else:
                            status = "Geometry rejected — no reliable depth"
                    elif any(len(t) > 1 for t in tracks):
                        status = "Multiple candidates — depth association ambiguous"
        duration = (time.monotonic() - now) * 1000
        if sequence % 10 == 0:
            self.history.append(
                {
                    "time": time.time(),
                    "motion": sum(len(c["tracks"]) for c in cameras),
                    "processing_ms": round(duration, 1),
                    "voxels": len(voxels),
                }
            )
        with self.lock:
            self.state = {
                "mode": self.mode,
                "status": status,
                "cameras": cameras,
                "tracks": fused,
                "voxels": voxels,
                "voxel_size": self.projector.step.tolist(),
                "bounds": self.bounds,
                "camera_positions": [m.center.tolist() for m in self.models],
                "calibrated": bool(self.models),
                "pair_timing_ms": round(skew * 1000, 1) if skew is not None else None,
                "processing_ms": round(duration, 1),
                "uptime_s": round(now - self.started),
                "frames_total": self.frames_total,
                "events_total": self.event_count,
                "settings": settings,
                "history": list(self.history),
                "events": list(self.events)[:30],
            }
