# Architecture

## Components and data flow

```
 capture ─→ detect ─→ DETECTION_BATCH ─UDP─→ ingest ─MQTT─→ fusion ─MQTT─→ cot ─UDP mcast─→ ATAK
 (node)     (node)                          (gateway)       (ground)       (ground)
                     STATUS ─UDP─→ ingest ─MQTT─→ trctl / dashboards
 time:  chrony on gateway ─NTP/TSYNC─→ nodes, laptop
```

- **Nodes** do capture, motion detection and timestamping only. No calibration
  on the node: they send raw pixel centroids. Calibration changes never need a
  reflash.
- **Gateway** owns time, the sensor network, ingest and the MQTT broker.
- **Ground** owns geometry: undistortion, poses, triangulation, tracking,
  affiliation, outward formats.

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

## Latency budget (target, measured in P2)

| Stage | Target |
|-------|--------|
| Exposure → detection on node | ≤ 70 ms (ESP), ≤ 40 ms (Pi) |
| Wi-Fi (power save off) | ≤ 10 ms |
| Ingest decode + publish | ≤ 2 ms |
| Fusion update | ≤ 20 ms |
| CoT out | ≤ 10 ms |
| **Capture → track on MQTT** | **≤ 150 ms** |

Measured as `track.last_update_us − det.t_us` and `det.rx_us − det.t_us`.

## Failure modes (must degrade, not crash)

| Failure | Expected behaviour |
|---------|--------------------|
| Node offline | Fusion continues with remaining nodes; status goes stale; `trctl` shows it |
| Node unsynced | Its data flagged; fusion drops it by default (configurable) |
| Only one node sees target | No 3D fix; fusion may publish bearing-only info later (stretch) |
| MQTT down | Ingest keeps recording raw packets |
| Gateway reboot | Services start on boot; nodes reconnect and resync without manual steps |

## Field version (for the pitch)

- **Passive sensing.** Cameras emit nothing; a radar does. Keep the radio side
  quiet too: nodes transmit only on detection, batched, at minimum power.
- **Transport-agnostic.** Messages are ≤ 220-byte binary datagrams. Prototype
  uses Wi-Fi; field version uses wired/fibre for static nodes, ESP-NOW/LoRa or
  LPI mesh radio for the rest. A persistent Wi-Fi AP is a beacon to direction
  finding — prototype only.
- **Time without GNSS.** Gateway is the time master; in the field it is
  GNSS-PPS disciplined when available and holds over on a stable oscillator.
- **Elevated nodes.** Tethered aerostats extend line of sight over terrain;
  the node pose then comes from IMU + visual references instead of a tape measure.
- **Night.** Thermal cameras; the detector interface does not change.
- **Interoperability.** CoT/TAK today; SAPIENT (BSI Flex 335) for C-UAS sensor
  integration and ASTERIX for air-picture consumers.
