# node — RPi node software

Passive sensing: reads a camera, finds airborne objects, publishes bearings.
No video leaves the device. Contract: [`../docs/contract.md`](../docs/contract.md).

## Layout

| File | Owner | Notes |
|------|-------|-------|
| `camera.py` | **detector teammates** | Frame source: `Camera.read() -> ndarray \| None` |
| `detectors/base.py`, `detectors/motion.py` | **detector teammates** | `Detector.detect(frame) -> list[Detection]`; `motion.py` is a baseline |
| `config.py`, `publisher.py`, `status.py`, `geometry.py`, `__main__.py` | platform | Env config, MQTT, heartbeat, pixel → az/el |
| `tests/` | platform | Every published payload is validated against `docs/schemas/` |

Detectors return **pixel** centres plus confidence. The platform converts to az/el.
To add a detector: implement `Detector`, select it in `__main__.py`; do not touch
publishing, status or geometry.

## Configuration (environment)

| Variable | Default | Meaning |
|----------|---------|---------|
| `NODE_ID` | required | e.g. `rpi-1`; also the MQTT client id |
| `MQTT_HOST` | required | broker host |
| `MQTT_PORT` | `8883` | |
| `MQTT_TLS` | `1` | `0` for a local plain broker |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | unset | per-node credentials |
| `MQTT_CA_FILE` | system CAs | custom CA bundle |
| `CAMERA_DEVICE` | `0` | V4L2 index, or a video file path for development |
| `CAMERA_WIDTH`, `CAMERA_HEIGHT` | `640`, `480` | requested capture size |
| `CAMERA_HFOV_DEG` | `70` | horizontal field of view when no calibration is given |
| `CAMERA_FX`, `CAMERA_FY`, `CAMERA_CX`, `CAMERA_CY` | unset | calibrated intrinsics (override HFOV) |
| `CAMERA_DIST` | unset | comma-separated distortion coefficients |
| `NODE_HEADING_DEG`, `NODE_PITCH_DEG`, `NODE_ROLL_DEG` | `0` | mount pose: heading clockwise from north, pitch up, roll clockwise |
| `NTP_SERVER` | `pool.ntp.org` | for `clock_offset_ms` |

## Commands

```sh
uv sync
uv run pytest
uv run ruff check .
```
