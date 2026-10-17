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
| `HEALTH_FILE` | `/tmp/edth-alive` | touched while frames flow; the container healthcheck watches it |
| `CAMERA_HFOV_DEG` | `70` | horizontal field of view when there is no calibration |
| `CAMERA_FX`, `CAMERA_FY`, `CAMERA_CX`, `CAMERA_CY` | unset | calibrated intrinsics (override HFOV) |
| `CAMERA_DIST` | unset | comma-separated distortion coefficients |
| `NODE_HEADING_DEG`, `NODE_PITCH_DEG`, `NODE_ROLL_DEG` | `0` | mount pose: heading clockwise from north, pitch up, roll clockwise |
| `NTP_SERVER` | `pool.ntp.org` | for `clock_offset_ms` |
