# Validation record

Local checks on 2026-10-17, Arch Linux x86_64, Python 3.14.8, OpenCV 5.0.0.

- `python -m pytest -q`: **13 passed**. Tests include known-position stereo reconstruction, degenerate/behind-camera/inconsistent ray rejection, both-camera voxel support, fragmented/corrupt serial packets, stray-byte recovery, static/global-change suppression, detection from synthetic images, API validation, cross-origin mutation rejection, live staleness/timing/resolution gates, asymmetric USB clock-offset uncertainty, and stale clock-reply rejection.
- Existing repository protocol tests: **14 passed**, without protocol changes.
- `ruff check .`, `ruff format --check .`, and `node --check src/skywatch/static/app.js`: passed.
- `uv build`: wheel and source distribution built; the wheel includes the dashboard assets and CLI entry points.
- `python tools/browser_check.py`: passed in Chromium 156. Verified two decoded camera images, settings reaching the engine, motion-mask control, background reset, CSV download, orbit interaction, mobile document width, and stale-data labeling after API failure. No JavaScript page exceptions.
- Simulation produced motion tracks and reconstructed a target around 25 m from generated images rather than injected detection coordinates. This is **not a hardware benchmark**.
- [Desktop screenshot](dashboard-desktop.png), [mobile screenshot](dashboard-mobile.png). Both use synthetic imagery.

## Physical camera validation

**Both XIAO ESP32S3 Sense boards were flashed and both physical cameras streamed 640×480 JPEGs into the live dashboard.** Both devices report 8 MB flash and 8 MB embedded PSRAM. Stable serial identities are recorded in ignored `config/live.json`.

ESP32 core 3.3.8 compiled the firmware: **366,997 bytes** of program storage and **33,232 bytes** of global variables. Esptool verified flash writes on both boards. The sketch uses ESP-IDF's USB Serial/JTAG driver directly; Arduino's HWCDC wrapper exhibited intermittent 64-byte losses in sustained testing. The board configuration remains hardware USB mode, CDC enabled, OPI PSRAM. On this XIAO core version, `CDCOnBoot=default` means **enabled**.

Original full 8 MB flash contents were saved before modifications in the original standalone directory's `data/firmware-backups/`, with SHA256 hashes. They are excluded from Git. The development account was added to `uucp`; hardware tests ran with that group, without running the server as root.

Final hardware soak results: Reproduce with the live server running:

```sh
uv run python tools/hardware_check.py --duration 120
```

| Check | Result |
| --- | --- |
| Test duration | 120.08 seconds |
| Both physical cameras online | 468 / 468 samples |
| Combined processed frames | 1908 (about 8 fps per camera) |
| Image resolution | 640×480 on each camera |
| Source errors / server packet warnings | None during the final soak |
| Median pair timing estimate | 90.7 ms, including uncertainty allowances |
| Live browser | Both images decoded; calibration warning present; range withheld; no JS exceptions |

This verifies sustained capture with repeated clock exchanges for this two-minute
bench run. It does not establish a maximum capture rate or a synchronization guarantee.

Machine-readable measurements and a live screenshot are saved under ignored `data/`. The live browser check verifies both physical images decode, LIVE mode is shown, and uncalibrated range is withheld. Timing values are software estimates, not measurements against a shared exposure trigger.

Full official S3 compiler/core/library/esptool archives were checked against upstream SHA256 values. An S3-only dependency index was used locally to avoid downloading unrelated chip-family SDKs. The README includes the full official installation recipe for fresh environments.

## Remaining physical validation

Physical stereo calibration, known-distance ranging, outdoor aircraft detection, false-positive rates, and drone classification remain **unvalidated**. A brief successful USB soak is not an endurance or outdoor detection test.

1. Mount both cameras rigidly with overlapping views and detect a nearby moving object against a plain background.
2. Capture varied static checkerboard pairs; solve calibration and independently measure the baseline.
3. Test an object at several measured distances. Record range error and rejected pairs.
4. Measure timing uncertainty and image displacement during that interval. Accept 2D-only output when the timing gate fails.
5. Record real plane footage and label objects and false positives. Measure missed detections and false alarms before claiming useful detection range.

No 100 km capability, drone identification accuracy, precision positioning, or production readiness is claimed.
