# sensors/pi-node/ — Raspberry Pi camera sensor node

## Purpose
Same job as the ESP node, on the gateway Pi: capture, detect, timestamp,
send `DETECTION_BATCH` / `STATUS` (via `trwire`) to `127.0.0.1:5600`.
One process per camera: `tr-pi-node --node-id 21 --source csi:0`
(`csi:N` = Picamera2, `usb:/dev/videoN` = V4L2 via OpenCV).

## Constraints
- Runs **on the gateway**, next to ingest, mosquitto and chrony. Budget:
  ≤ 50% of one core per camera. Profile before adding features.
- `picamera2` and `python3-opencv` come from apt, not PyPI. The venv must be
  created with system site packages: `uv venv --system-site-packages`.
- Same detection algorithm and parameters as the firmware so nodes behave
  alike. Keep it numpy-vectorized; use `cv2.connectedComponentsWithStats`.

## Capture and timestamps
- CSI: use a **lores YUV420** stream and take the Y plane — grayscale for free,
  no conversion. Use frame metadata `SensorTimestamp` (ns, kernel clock) as the
  capture time. Verify its clock domain (MONOTONIC vs BOOTTIME), convert to
  realtime by sampling both clocks once per frame. Document what you verified.
- USB: V4L2 buffer timestamps are not exposed by OpenCV; stamp right after
  `read()` and rely on `latency_us` in `config/site.yaml` from the LED test.
- The Pi shares chrony's clock, so `TIME_SYNCED` = chrony reports synced
  (or `local stratum` mode) — check via `chronyc -c tracking` at startup and every 10 s.

## Done criteria
- Runs as a systemd template unit (`tr-pi-node@21`, provided by `infra/`).
- Detections appear on `tr/v1/det/21`; status at 1 Hz with real fps and temp.
- Measured CPU per camera written in this file.
