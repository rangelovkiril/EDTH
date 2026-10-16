# firmware/observer/ — camera node

## Purpose
Capture frames, detect moving blobs, timestamp precisely, send
`DETECTION_BATCH` and `STATUS` to the collector. Nothing else: no calibration,
no geometry, no decisions.

## Target
- Board: Seeed Studio **XIAO ESP32S3 Sense** (8 MB octal PSRAM, 8 MB flash,
  OV2640 or OV3660 depending on revision).
- Camera driver: `espressif/esp32-camera` via the IDF component manager.
- Uses `tr_link` (client side) and `tr_timesync` (client).

## Layout (to create)
```
CMakeLists.txt  sdkconfig.defaults
nodes/node-01.defaults   # CONFIG_TR_NODE_ID=1 etc.
main/
  Kconfig.projbuild   # TR_NODE_ID, TR_FRAME_SIZE, TR_CAPTURE_LATENCY_US, TR_DETECT_*
  app_main.c  camera.c  detect.c
```

## Camera pins (CAMERA_MODEL_XIAO_ESP32S3 — verify against Seeed's wiki)
PWDN −1, RESET −1, XCLK 10, SIOD 40, SIOC 39, Y9 48, Y8 11, Y7 12, Y6 14,
Y5 16, Y4 18, Y3 17, Y2 15, VSYNC 38, HREF 47, PCLK 13.

## Pipeline
1. Camera: `PIXFORMAT_GRAYSCALE`, `FRAMESIZE_QVGA` (320×240) to start,
   `fb_count = 2`, `CAMERA_GRAB_LATEST`, frame buffers in PSRAM.
   Fix exposure/gain after warm-up so auto-exposure doesn't create motion.
2. Timestamp: frame buffer timestamp if the driver sets it near VSYNC (check
   the `esp32-camera` source and document it), otherwise `esp_timer_get_time()`
   right after `esp_camera_fb_get()`. Subtract `CONFIG_TR_CAPTURE_LATENCY_US`.
   Convert with `tr_time_from_local()`.
3. Detect: running background (exponential average, fixed-point), absolute
   difference, threshold, optional 2× downsample, connected components
   (iterative, bounded memory — no recursion), drop blobs below `min_area`,
   intensity-weighted centroid in full-resolution pixels, keep the 16 largest.
   Confidence = simple monotonic score (area and contrast), documented in code.
4. Send `DETECTION_BATCH` **only if count > 0**. `STATUS` at 1 Hz.
5. `seq` increments per message across types.
6. Set `TR_FLAG_TIME_SYNCED` from `tr_time_synced()`.

## Gotchas
- **Attach the external U.FL antenna** that ships with the Sense board.
- The board runs hot with camera + radio: cap fps, report `temp_c`, add a heatsink.
- Enable PSRAM (octal) in `sdkconfig.defaults` or camera init fails.
- Never block the capture loop on the radio: `tr_link_send` enqueues; drops are
  counted in `dropped_frames`.

## Done criteria
- Status from this node visible on the collector at 1 Hz, `TIME_SYNCED` set.
- Waving a hand produces detections with sensible centroids.
- Measured fps and capture latency written in this file.
