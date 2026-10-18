# Node configuration

All settings are environment variables. On a Pi they live in `/etc/edth/node.env` (see
[`../deploy/`](../deploy/README.md)); for local runs put them on the command line.

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
| `CAMERA_DEVICE` | `0` | `csi` (Raspberry Pi camera), a V4L2 index, or a video file path |
| `CAMERA_WIDTH`, `CAMERA_HEIGHT`, `CAMERA_FPS` | `640`, `480`, `30` | requested capture size and rate (cameras only) |
| `STREAM_PORT` | unset (off) | serve a live view of the camera on this port (see below) |
| `STREAM_ROTATE` | `0` | turn the live view by 0, 90, 180 or 270 degrees |
| `HEALTH_FILE` | `/tmp/edth-alive` | touched while frames flow; the container healthcheck watches it |
| `CAMERA_HFOV_DEG` | from the camera | horizontal field of view when there is no calibration. Raspberry Pi cameras report it themselves (v1, v2, 3, 3 Wide, allowing for the sensor mode's crop); set it for an HQ camera, a USB camera (else 70), or to override |
| `CAMERA_FX`, `CAMERA_FY`, `CAMERA_CX`, `CAMERA_CY` | unset | calibrated intrinsics (override HFOV) |
| `CAMERA_DIST` | unset | comma-separated distortion coefficients |
| `NODE_HEADING_DEG`, `NODE_PITCH_DEG`, `NODE_ROLL_DEG` | `0` | mount pose: heading clockwise from north, pitch up, roll clockwise |
| `NTP_SERVER` | `pool.ntp.org` | for `clock_offset_ms` |

## Live view

With `STREAM_PORT=8080` the node serves its camera on that port, for showing people what it sees:
`http://<pi-address>:8080/` is a page, `/stream.mjpg` is a motion-JPEG stream (browser, VLC), `/snapshot.jpg`
one frame. Detections are drawn on the picture with their bearing. Add `?rotate=90` to turn it, or set
`STREAM_ROTATE`.

It is a local demo tool: **no password**, so anyone on the same network can watch, and nothing in it goes
to the MQTT broker. Leave `STREAM_PORT` unset to turn it off.

