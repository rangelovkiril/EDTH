# Triangulum USB camera bench

A local hackathon prototype for two **Seeed XIAO ESP32S3 Sense** camera boards connected by USB. Python/OpenCV does the heavy processing on the laptop or a Raspberry Pi. The ESP32s capture JPEGs. A browser dashboard shows annotated feeds, persistent motion, a rotatable voxel evidence view, event history, processing latency, and approximate stereo range when calibrated.

**This detects unclassified moving blobs. It does not reliably distinguish drones, planes, birds, insects, or clouds. There is no validated detection range. The simulation is explicitly labeled and is not evidence of hardware performance.**

This is the repository's standalone USB bench path. Read [INTEGRATION.md](INTEGRATION.md) for its boundary with the existing UDP/MQTT architecture. It does not complete the EDTH P0/P1 service milestones.

## Install and run live

```bash
cd bench/usb-poc
uv sync
cp config/live.example.json config/live.json
# Set the two camera paths in config/live.json.
uv run skywatch --config config/live.json
```

Open http://127.0.0.1:8000. The two development boards were already flashed and physically tested; a fresh setup needs the firmware and permission steps below.

## Run the demo now

```bash
cd bench/usb-poc
uv run skywatch
```

Open **http://127.0.0.1:8000**. `uv sync` creates the environment from the lockfile. Without uv, `./run.sh` creates a venv and installs this package. Python 3.11+ recommended (tested here on Python 3.14). The dashboard has no CDN dependencies or build step. Stop with Ctrl+C.

Simulation renders two camera views of a moving silhouette from a known 3D path, then passes the **images** through the same detector and reconstruction as live cameras. Ground truth is never fed into the detector. Some tracks fragment near changes in direction: this is a simple baseline tracker.

## Get the XIAO cameras live

1. Use XIAO **ESP32S3 Sense** boards with the camera expansion module seated correctly. The bare XIAO has no camera. Use USB data cables.
2. On Arch Linux, serial devices generally belong to the `uucp` group. Grant temporary access:

   ```bash
   sudo setfacl -m u:"$USER":rw /dev/ttyACM0 /dev/ttyACM1
   ```

   Replugging or resetting a board can recreate its device node and remove this ACL. For persistent access, run `sudo usermod -aG uucp "$USER"`, then `newgrp uucp` or log out and back in. Other Linux distributions may use `dialout`. Never run the dashboard as root.

3. Flash [firmware/skycam/skycam.ino](firmware/skycam/skycam.ino) to each board. Arduino IDE settings:
   - Espressif ESP32 board package **3.3.8**; board **XIAO_ESP32S3**.
   - USB CDC On Boot: **Enabled**; USB Mode: **Hardware CDC and JTAG**.
   - PSRAM: **OPI PSRAM**; camera resolution is **640×480**.
   - Close Serial Monitor while using the dashboard. BOOT + RESET may be necessary to enter the downloader on first flash.

   The helper uses `arduino-cli` from PATH, or the `ARDUINO_CLI` override:

   ```bash
   tools/firmware.sh build
   tools/firmware.sh flash /dev/ttyACM0
   tools/firmware.sh flash /dev/ttyACM1
   ```


   Arduino CLI equivalent (install the official Arduino CLI first):

   ```bash
   arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
   arduino-cli core install esp32:esp32@3.3.8 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
   arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3:USBMode=hwcdc,CDCOnBoot=default,PSRAM=opi firmware/skycam
   arduino-cli upload --fqbn esp32:esp32:XIAO_ESP32S3:USBMode=hwcdc,CDCOnBoot=default,PSRAM=opi --port /dev/ttyACM0 firmware/skycam
   arduino-cli upload --fqbn esp32:esp32:XIAO_ESP32S3:USBMode=hwcdc,CDCOnBoot=default,PSRAM=opi --port /dev/ttyACM1 firmware/skycam
   ```

   Flashing replaces the firmware on each board. Preserve existing work first if needed.

4. Check camera paths and permissions:

   ```bash
   uv run python tools/diagnose.py
   ```

   Copy [config/live.example.json](config/live.example.json) to ignored `config/live.json` and set the stable paths reported by the diagnostic tool. Confirm that the first camera is the intended left/reference camera. Update paths if USB identities change after flashing.

5. Start live capture:

   ```bash
   uv run skywatch --config config/live.json
   ```

   Keep both cameras rigidly mounted and still. Allow about 15 frames for the background model to settle. Move a dark object against a plain bright background first. The live profile starts **without calibration** and shows 2D tracks only; no synthetic depth is substituted. Reconnect is automatic. A disconnected source is labeled offline, and its old image is hidden.

## Calibrate for actual 3D

Start with a rigid 20–50 cm baseline and a subject a few metres away. Both cameras need an overlapping view. A wider baseline helps depth sensitivity but complicates calibration and matching. Do not change camera resolution, focus, mounting, or left/right order after calibration.

1. Print a flat checkerboard with **9×6 inner corners** (10×7 squares). Measure the printed square size; do not trust printer scaling. Add a mark outside one corner to keep orientation consistent.
2. Run live mode. Hold the board **stationary** in both views and click **Capture calibration pair**. Move it between captures, covering edges, centre, distances, and tilts. Capture 20–30 good pairs; hold still for each pair because the cameras are not hardware synchronized. Avoid 180° board flips that can reverse corner correspondence.
3. Run, for example, for measured 25 mm squares:

   ```bash
   uv run skywatch-calibrate --cols 9 --rows 6 --square-m 0.025
   ```

   The tool rejects fewer than 12 usable pairs, mixed resolution/source order, and RMS reprojection error over 1.5 pixels. RMS alone does not prove accurate calibration: compare the estimated baseline to a ruler and test a separate target at measured distances.
4. Set `"calibration": "config/calibration.json"` in `config/live.json`, then restart.
5. Adjust `voxel_bounds` to cover your test volume. Coordinates are metres relative to camera 1: **x right, y down, z forward**. The default live grid covers roughly 0.5–15 m forward. Voxel cells are an evidence display, not exact shape or guaranteed occupancy.

The first two cameras drive stereo and voxel fusion. Additional sources appear in the dashboard and run independent 2D tracking. More-than-two-view calibrated fusion is future work.

## How it works and how it uses Pixel-to-Voxel

The [reference project](https://github.com/ConsistentlyInconsistentYT/Pixeltovoxelprojector) detects frame differences, casts rays using camera poses, and accumulates a voxel grid offline. This POC independently implements its **motion-to-spatial-evidence idea** for live operation; it does not import or execute the upstream C++ or viewer code.

```text
XIAO camera A ── USB request → JPEG + CRC ──┐
                                          ├─ latest-frame buffers → motion masks → persistent 2D tracks
XIAO camera B ── USB request → JPEG + CRC ──┘                              │
                                      camera calibration + timing gate ─┤
                                                                         ├─ shared voxel support
                                                                         └─ single-candidate triangulation
                                                                     FastAPI → local dashboard + /metrics
```

- MOG2 foreground segmentation; small component filtering; three-observation persistence; simple nearest-neighbour tracks. Large image-wide changes suppress detections. No image stabilizer: mount cameras rigidly.
- Voxel-centre projection into both motion masks is an inverse form of ray voting. Each camera contributes at most one vote; two simultaneous supporting views are required. No accumulated stale rays. Ghost intersections and coarse-grid misses remain possible.
- Range is accepted only for **one current confirmed track in each camera**, positive ray distances, sufficient ray angle, low reprojection error, and matching calibrated resolution. This is a tentative correspondence, not proof that both observations are the same object.
- The host synchronizes each boot clock with three short `T` exchanges every five seconds, selecting the smallest round-trip sample. A timestamp generated between request and response yields an offset interval even with asymmetric USB delay. The camera's **first DMA buffer timestamp** is mapped to host monotonic time; independent device uptime clocks are never compared directly. Uncertainty adds half the sync round trip, a 100 ppm drift allowance, and a configurable `exposure_uncertainty_s` (default 0.04 s) for exposure/readout. Check this allowance against actual exposure, especially in low light. The pair estimate includes timestamp difference and both uncertainties. USB clock estimation is not a shared hardware trigger or a guaranteed timing bound; it is unsuitable for precise long-range fast-target positioning without validation. `max_pair_skew_s` is an experimental gate.
- `sensitivity_m` estimates depth sensitivity to one pixel of centroid error. It is **not a confidence interval** and excludes lens/calibration errors and target motion during timing skew.
- Transport framing: host `F` requests `SKYCAM01`, little-endian `<IIQI>` payload length, sequence, device capture uptime in µs, CRC32; then JPEG bytes. Host `T` + uint32 nonce requests `SKYTIME2` + echoed uint32 nonce + uint64 device uptime in µs (little-endian). The nonce rejects stale replies after reconnects; steady-state acquisition does not flush the USB receive queue. The frame parser recovers from boot text and corrupt packets.
- The firmware uses ESP-IDF's `usb_serial_jtag` driver directly inside the Arduino sketch. Arduino core 3.3.8's `HWCDC` wrapper lost 64-byte packets during sustained JPEG testing. Do not add `Serial.begin()` or writes through `Serial`: that would attach another handler to the same USB peripheral. The wire protocol is unchanged.

## Raspberry Pi, webcams, files, and RTSP

Edit the `cameras` array. Examples:

```json
{"name":"UVC camera", "type":"usb", "source":0, "width":640, "height":480, "fps":10}
{"name":"Recorded test", "type":"file", "source":"/absolute/path/test.mp4", "fps":10}
{"name":"Pi stream", "type":"stream", "source":"http://192.168.1.50:8080/stream", "fps":10}
{"name":"RTSP camera", "type":"stream", "source":"rtsp://192.168.1.51:8554/camera", "fps":10}
```

OpenCV must support the selected format; network adapters use FFmpeg with read/open timeouts. For a Pi CSI camera, provide an MJPEG/RTSP stream from the Pi camera stack or use a Pi-compatible V4L2 source; native Picamera2 integration is not included. Files loop and are paced by the configured FPS, not synchronized media timestamps. Non-serial sources default to **10 seconds of timing uncertainty**, disabling 3D fusion. Only set `timing_uncertainty_s` after measuring acquisition and buffering; do not set it to zero just to enable depth.

## API and Grafana

The included dashboard is styled like an observability console. Actual Grafana is optional: Prometheus can scrape `http://127.0.0.1:8000/metrics`.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/state` | Camera health, tracks, voxel cells, timing, recent events |
| `GET /api/cameras/0/frame.jpg` | Annotated JPEG; add `?mask=true` for foreground |
| `POST /api/settings` | `{"threshold":20,"min_area":5}` |
| `POST /api/reset` | Relearn background after repositioning |
| `POST /api/calibration/capture` | Save two raw calibration frames locally |
| `GET /api/events.csv` | Latest 1,000 motion events; includes simulation/live label |
| `GET /metrics` | Prometheus metrics |
| `/docs` | Interactive API documentation |

Example Prometheus scrape configuration:

```yaml
scrape_configs:
  - job_name: skywatch
    scrape_interval: 5s
    static_configs:
      - targets: ['127.0.0.1:8000']
```

Useful Grafana queries: `rate(skywatch_frames_total[1m])`, `skywatch_processing_ms`, `skywatch_voxel_candidates`, `skywatch_camera_up`, `skywatch_simulation`. Target `127.0.0.1` assumes Prometheus runs on the same host network.

State and event history are bounded in memory; CSV exports are manual. Calibration captures persist under `data/calibration`. Settings changes are in-memory and reset on restart. The server binds to loopback by default and has no user authentication. Use it locally; adding shared network access requires authentication and transport security.

## Range reality

**100 km drone detection is not a credible objective for these stock camera modules.** A pinhole example: at 640-pixel width and 60° horizontal field of view, focal length is about 554 pixels. Projected target width is approximately `f_px × target_width_m / distance_m`:

| Target | At 1 km | At 100 km |
| --- | --- | --- |
| 0.5 m drone | 0.28 px | 0.0028 px |
| 35 m aircraft | 19.4 px | 0.19 px |

These are illustrative optical calculations, not measured performance of your lens. Actual field of view depends on the installed lens and crop. Detectable contrast may vary, but subpixel image energy does not provide reliable object identification. Haze, atmospheric turbulence, exposure, vibration, line of sight and the horizon further constrain range. Pixel-to-voxel projection does not add missing optical resolution.

For the hackathon: demonstrate a nearby moving object first, measure precision at known distances, then try a clearly visible plane against clean sky. Report motion detection separately from classification and range accuracy. Longer-range work needs suitable optics, higher-resolution sensors, measured camera poses, reliable synchronization, and field validation; sensor fusion is a later research step.

## Checks

```bash
uv sync
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
node --check src/skywatch/static/app.js
# With the live server running in another terminal:
uv run python tools/hardware_check.py --duration 120
```

Tests cover synthetic-image detection, known-point triangulation, geometry rejection, two-view voxel support, serial corruption/resynchronization, live timing/staleness/resolution gates, API bounds, and simulation separation. Test results and remaining hardware verification limits are recorded in [docs/VALIDATION.md](docs/VALIDATION.md).

## Sources

- [Pixel-to-Voxel project and Apache-2.0 license](https://github.com/ConsistentlyInconsistentYT/Pixeltovoxelprojector): algorithmic inspiration; no upstream source copied.
- [Seeed XIAO camera guide](https://wiki.seeedstudio.com/xiao_esp32s3_camera_usage/): Sense camera pins and PSRAM setup.
- [Espressif camera driver](https://github.com/espressif/esp32-camera): JPEG capture and buffer configuration.
- [Espressif USB CDC guide](https://docs.espressif.com/projects/arduino-esp32/en/latest/tutorials/cdc_dfu_flash.html): native USB serial setup.
