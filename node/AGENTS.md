# node — the program that runs on each Pi

Reads frames from a camera, asks a detector where the airborne objects are, converts each pixel to
a bearing (azimuth/elevation) and publishes it over MQTT. Passive sensing only; no video leaves the
device. Contract: [`../docs/contract.md`](../docs/contract.md).

| Read | For |
|------|-----|
| [`DETECTORS.md`](DETECTORS.md) | writing a detector (most of you) |
| [`CONFIG.md`](CONFIG.md) | every environment setting |
| [`../deploy/README.md`](../deploy/README.md) | how code gets onto a Pi |

## Quick start (no camera, no broker)

```sh
cd node
uv sync
uv run pytest                                   # should be green before you start
NODE_ID=rpi-1 DRY_RUN=1 CAMERA_DEVICE=clip.mp4 uv run python -m src
```

`DRY_RUN=1` prints `topic payload` lines to stdout instead of publishing (logs go to stderr).
`CAMERA_DEVICE` is a video file, `0` for a USB camera, or `csi` for a Raspberry Pi camera
(only inside the image or on a Pi with `python3-picamera2`). `LOG_LEVEL=DEBUG` shows every detection.

## What lives where

| File | Who edits | What it does |
|------|-----------|--------------|
| `src/detector.py` | detector authors (rarely) | `Detection` and the `Detector` protocol |
| `src/motion.py` | detector authors | baseline motion detector; copy it as a starting point |
| `src/<yours>.py` | detector authors | **your detector goes in a new file** |
| `src/camera.py` | camera authors | frame sources: Pi camera (`csi`), V4L2, video file |
| `src/config.py`, `__main__.py` | platform owner | env settings, the main loop |
| `src/payloads.py`, `publisher.py` | platform owner | message bodies, MQTT |
| `src/status.py`, `clock.py` | platform owner | heartbeat, health file, NTP offset |
| `src/geometry.py` | platform owner | pixel → az/el |
| `tests/` | everyone, for their own code | published payloads are checked against `../docs/*.schema.json` |

If you need a change in a platform file, ask rather than editing: it keeps parallel work from
colliding.

## Before you push

```sh
uv run ruff check . && uv run ruff format . && uv run pytest
```

Pushing to `main` runs the same in CI, builds the arm64 image, and the Pi picks it up by itself.
