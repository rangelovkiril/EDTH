# firmware/esp-node/ — ESP32-S3 camera sensor node

## Purpose
Capture frames, detect moving blobs, timestamp precisely, send
`DETECTION_BATCH` and `STATUS` to the gateway. Nothing else: no calibration,
no geometry, no decisions.

## Target
- Board: Seeed Studio **XIAO ESP32S3 Sense** (ESP32-S3, 8 MB octal PSRAM,
  8 MB flash, OV2640 or OV3660 depending on revision).
- Framework: **ESP-IDF v5.x** (record the exact version in `IDF_VERSION`
  and keep the team on it). Camera driver: `espressif/esp32-camera` via the
  IDF component manager (`main/idf_component.yml`).
- Protocol: include `protocol/c/trwire.h` (add `../../../protocol/c` to
  `INCLUDE_DIRS` in `main/CMakeLists.txt`). Never redefine message structs.

## Layout (to create)
```
CMakeLists.txt  sdkconfig.defaults  IDF_VERSION
sdkconfig.secrets.example            # Wi-Fi creds template; real file gitignored
nodes/node-01.defaults               # CONFIG_TR_NODE_ID=1 etc.
main/
  Kconfig.projbuild   # menu "Triangulum node": TR_NODE_ID, TR_GATEWAY_IP,
                      # TR_WIFI_SSID, TR_WIFI_PASS, TR_FRAME_SIZE, TR_DETECT_*
  app_main.c  wifi.c  timesync.c  camera.c  detect.c  net.c
```
Build one board:
```sh
idf.py -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.secrets;nodes/node-01.defaults" \
  build flash monitor
```
Delete `sdkconfig` when switching node files, or the old ID sticks.

## Camera pins (CAMERA_MODEL_XIAO_ESP32S3 — verify against Seeed's wiki)
PWDN −1, RESET −1, XCLK 10, SIOD 40, SIOC 39, Y9 48, Y8 11, Y7 12, Y6 14,
Y5 16, Y4 18, Y3 17, Y2 15, VSYNC 38, HREF 47, PCLK 13.

## Pipeline
1. Camera: `PIXFORMAT_GRAYSCALE`, `FRAMESIZE_QVGA` (320×240) to start,
   `fb_count = 2`, `CAMERA_GRAB_LATEST`, frame buffers in PSRAM.
   Fix exposure/gain after warm-up so auto-exposure doesn't create motion.
2. Timestamp: take the capture time from the frame buffer timestamp if the
   driver sets it near VSYNC (check `esp32-camera` source and document it),
   otherwise `esp_timer_get_time()` right after `esp_camera_fb_get()`.
   Subtract a constant latency (`CONFIG_TR_CAPTURE_LATENCY_US`, from the LED test).
   Convert local monotonic → gateway timescale (`docs/time-sync.md`).
3. Detect: running background (exponential average, fixed-point), absolute
   difference, threshold, optional 2× downsample, connected components
   (iterative, bounded memory — no recursion), drop blobs below `min_area`,
   intensity-weighted centroid in full-resolution pixels, keep the 16 largest.
   Confidence = simple monotonic score (area and contrast), documented in code.
4. Send `DETECTION_BATCH` **only if count > 0**. `STATUS` at 1 Hz.
5. `seq` increments per message across types.

## Wi-Fi and time
- STA mode, WPA3/WPA2, reconnect loop with backoff. Gateway `10.42.0.1`.
- `esp_wifi_set_ps(WIFI_PS_NONE)` — **mandatory**: power save adds tens to
  hundreds of ms of jitter and breaks sync.
- Phase 1: `esp_sntp` against the gateway. Phase 2: `TSYNC` on UDP 5601.
- Set `TR_FLAG_TIME_SYNCED` per `docs/time-sync.md`.

## Gotchas
- **Attach the external U.FL antenna** that ships with the Sense board.
  Without it range and RSSI collapse.
- The board runs hot with camera + Wi-Fi: cap fps, report `temp_c`, add a heatsink.
- Enable PSRAM (octal) in `sdkconfig.defaults` or the camera init fails.
- USB power from laptops can brown out during Wi-Fi TX bursts — use a good supply.
- Never block the capture loop on the network: send from a separate task via a queue;
  drop (and count in `dropped_frames`) when the queue is full.

## Done criteria
- Board boots, joins AP, syncs, and `tr/v1/status/<id>` updates at 1 Hz.
- Waving a hand produces `tr/v1/det/<id>` with sensible centroids.
- Measured fps and capture→rx latency written in this file.
