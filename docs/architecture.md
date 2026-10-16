# Architecture

## Components and data flow

```
 capture ─→ detect ─→ DETECTION_BATCH ─ESP-NOW─→ collector ──(TBD)──→ ground ESP ──(TBD)──→ bridge ─MQTT─→ fusion ─MQTT─→ cot ─→ ATAK
 (observer) (observer)  STATUS ─────────ESP-NOW─→ collector                                     bridge ─MQTT─→ trctl
 time: collector (master) ─TSYNC over ESP-NOW─→ observers
```

- **Observers** do capture, motion detection and timestamping only. No
  calibration on the node: they send raw pixel centroids. Calibration changes
  never need a reflash.
- **Collector** owns the network timescale and the observer network, and
  relays observer traffic towards the ground.
- **Ground ESP** receives from the collector and hands messages to the ground host.
- **Ground host** owns geometry: undistortion, poses, triangulation, tracking,
  affiliation, outward formats.

The two links marked TBD are open questions (root `AGENTS.md`).

## Frames and conventions

- World: local ENU in metres around `origin` in `config/site.yaml`
  (x east, y north, z up). Geodetic origin is used only for CoT output.
- Camera: OpenCV (x right, y down, z forward along the optical axis).
- Node pose in config: `position` (ENU m) and `yaw`, `pitch`, `roll` (deg):
  - `yaw`: azimuth of the optical axis, clockwise from north (0 = north, 90 = east).
  - `pitch`: elevation of the optical axis, up positive.
  - `roll`: rotation about the optical axis, clockwise as seen from behind the camera.
  The camera→world rotation is implemented once in `ground/fusion` and reused by
  `tools/sim`. Do not reimplement it elsewhere.

## Latency

Measure, don't assume. Capture→collector latency can be measured on the
network timescale (collector stamps receive time in its log). End-to-end to the
ground host needs a mapping between network time and host time, which depends
on the open questions.

## Failure modes (must degrade, not crash)

| Failure | Expected behaviour |
|---------|--------------------|
| Observer offline | Fusion continues with remaining nodes; status goes stale; `trctl` shows it |
| Observer unsynced | Its data flagged; fusion drops it by default (configurable) |
| Collector reboot | New network timescale; observers resync; consumers handle the time jump (`time-sync.md`) |
| Only one observer sees target | No 3D fix |
| MQTT down | Bridge keeps recording raw messages |
