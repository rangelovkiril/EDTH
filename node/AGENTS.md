# node — guide for people writing code here

The node reads frames from a camera, asks a **detector** where the airborne objects are in the
image, converts each pixel to a bearing (azimuth/elevation) and publishes it over MQTT. Passive
sensing only. Contract: [`../docs/contract.md`](../docs/contract.md).

## Quick start (no camera, no broker)

```sh
cd node
uv sync
uv run pytest                                   # should be green before you start
NODE_ID=rpi-1 DRY_RUN=1 CAMERA_DEVICE=clip.mp4 uv run python -m src
```

`DRY_RUN=1` prints `topic payload` lines to stdout instead of publishing (logs go to stderr).
`CAMERA_DEVICE` is a video file path, or `0` for the first V4L2 camera. Set `LOG_LEVEL=DEBUG` to
see every detection.

## What lives where

| File | Who edits | What it does |
|------|-----------|--------------|
| `src/detector.py` | detector authors (rarely) | `Detection` and the `Detector` protocol |
| `src/motion.py` | detector authors | baseline motion detector; copy it as a starting point |
| `src/<yours>.py` | detector authors | **add your detector here, as a new file** |
| `src/camera.py` | camera authors | frame source (V4L2 or file) |
| `src/config.py`, `publisher.py`, `status.py`, `geometry.py`, `__main__.py` | platform owner | env config, MQTT, heartbeat, pixel → az/el, main loop |
| `deploy.py`, `pis.json`, `edth-node.container`, `deploy.env.example` | platform owner | deploy to the Pis (below) |
| `tests/` | everyone, for their own code | all published payloads are checked against `../docs/*.schema.json` |

If you need a change in a platform file, ask rather than editing: it keeps parallel work from
colliding.

## Writing a detector

A detector is any class with a no-argument constructor and a `detect` method. It gets one BGR
frame (`numpy` array, `uint8`, shape `H×W×3`) and returns the **pixel** centres of what it found.
You never deal with angles, MQTT or time.

```python
# src/yolo.py
import numpy as np

from .detector import Detection


class YoloDetector:
    def __init__(self): ...  # load the model once

    def detect(self, frame: np.ndarray) -> list[Detection]:
        # u = x pixel (right), v = y pixel (down), conf in [0, 1]
        return [Detection(u=412.0, v=88.5, conf=0.9)]
```

Run it by name, without touching `__main__.py`:

```sh
DETECTOR=yolo:YoloDetector NODE_ID=rpi-1 DRY_RUN=1 CAMERA_DEVICE=clip.mp4 uv run python -m src
```

`DETECTOR` is `module:Class`; a module name without a dot is looked up inside `src`.

Things to know:

- **Return only what you believe.** Several detections per frame are fine. Return `[]` when
  there is nothing. The broker later drops anything with `conf < 0.5`, so calibrate `conf` honestly.
- **Keep up with the camera.** The Pi has to stay near the camera frame rate. `status.fps` shows
  the real rate; if it drops, shrink the input or skip work. Detectors are called once per frame,
  on the main thread.
- **State is fine.** Trackers and background models can live on the instance (see `motion.py`).
- **No network, no files at import time**, and no printing to stdout: stdout is the payload
  stream in `DRY_RUN`. Use `logging`.
- **Add dependencies** with `uv add <pkg>`; the lockfile is committed. The Pi image is arm64, so
  prefer packages with arm64 wheels, and keep the image small (`opencv-python-headless`, no GUI).
- **Test it** with a synthetic frame, like `tests/test_motion.py`.

## Configuration (environment)

| Variable | Default | Meaning |
|----------|---------|---------|
| `NODE_ID` | required | e.g. `rpi-1`; also the MQTT client id and username |
| `DRY_RUN` | `0` | `1`: print instead of publishing; `MQTT_HOST` not needed |
| `DETECTOR` | `motion:MotionDetector` | `module:Class` |
| `LOG_LEVEL` | `INFO` | |
| `MQTT_HOST` | required unless `DRY_RUN` | broker host |
| `MQTT_PORT` | `8883` | |
| `MQTT_TLS` | `1` | `0` for a local plain broker |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | unset | per-node credentials |
| `MQTT_CA_FILE` | system CAs | custom CA bundle |
| `CAMERA_DEVICE` | `0` | V4L2 index, or a video file path |
| `CAMERA_WIDTH`, `CAMERA_HEIGHT` | `640`, `480` | requested capture size (cameras only) |
| `CAMERA_HFOV_DEG` | `70` | horizontal field of view when there is no calibration |
| `CAMERA_FX`, `CAMERA_FY`, `CAMERA_CX`, `CAMERA_CY` | unset | calibrated intrinsics (override HFOV) |
| `CAMERA_DIST` | unset | comma-separated distortion coefficients |
| `NODE_HEADING_DEG`, `NODE_PITCH_DEG`, `NODE_ROLL_DEG` | `0` | mount pose: heading clockwise from north, pitch up, roll clockwise |
| `NTP_SERVER` | `pool.ntp.org` | for `clock_offset_ms` |

## Before you push

```sh
uv run ruff check . && uv run ruff format . && uv run pytest
```

CI runs the same, then builds the arm64 image on `main`.

## Deploying to the Pis

`pis.json` is the list of Pis: `id` (becomes `NODE_ID` and the MQTT username), `host` (anything
`ssh` accepts) and an optional `env` for per-Pi settings such as the mount heading.
`deploy.py` reads it, plus `deploy.env` (gitignored; copy `deploy.env.example`) for the broker
and passwords, and for each Pi installs the quadlet, writes the env file and the MQTT secret,
pulls the image and restarts the service.

One-time setup per Pi:

```sh
sudo apt install -y podman chrony        # chrony keeps the clock right, which timestamps rely on
sudo usermod -aG video $USER             # camera access; log out and in again
sudo loginctl enable-linger $USER        # lets the service run without a login session
```

Plus SSH access without a password prompt (`ssh-copy-id`) from the machine you deploy from, which
must be able to reach the Pi (same network, VPN or tailnet). The image is public once CI has pushed it;
if `podman pull` is denied, make the `edth-node` package public in the GitHub package settings.

First deploy:

```sh
cd node
cp deploy.env.example deploy.env        # fill in MQTT_HOST and the passwords
$EDITOR pis.json                        # real ids and hosts
./deploy.py --dry-run                   # prints what would run; passwords hidden
./deploy.py --only rpi-1                # try one Pi first
./deploy.py                             # then all of them
```

By default it deploys `sha-<first 7 of HEAD>`, the tag CI pushes after `main` goes green, so push
first and wait for the `build` job. `--tag latest` or any older `sha-...` also works, which is the
rollback. On a Pi: `journalctl --user -u edth-node -f` shows the logs, `podman ps` the container.
