# Message protocol — v1 (normative)

Implementations: `protocol/c/trwire.h`, `protocol/python` (`trwire`).
Test vectors: `protocol/test-vectors/vectors.json`.

## 1. Transport

| Channel | Transport | Direction |
|---------|-----------|-----------|
| Detections, status | ESP-NOW unicast | observer → collector |
| Time sync (`TSYNC`) | ESP-NOW unicast | observer ↔ collector |
| Collector → ground | **open question** (root `AGENTS.md`) | collector → ground ESP |
| Ground ESP → ground host | **open question** | ground ESP → bridge |
| Decoded data, tracks | MQTT on the ground host, JSON | ground services |

One ESP-NOW frame = one message. No acks, no retransmits at the application
level: a stale detection is worthless, the next frame supersedes it.
Max message size is 220 bytes (ESP-NOW payload limit is 250).

## 2. Encoding

- Little-endian, packed, no implicit padding.
- Node IDs: `0` invalid, `1–19` observers, `100` collector, `110` ground node,
  `200–254` simulator/test, `255` reserved.

### 2.1 Header (8 bytes, every message)

| Off | Size | Type | Name | Meaning |
|-----|------|------|------|---------|
| 0 | 2 | char[2] | `magic` | `"TR"` (`0x54 0x52`) |
| 2 | 1 | u8 | `version` | `1` |
| 3 | 1 | u8 | `type` | see below |
| 4 | 1 | u8 | `node_id` | sender (for `TSYNC_RESP`: the requester) |
| 5 | 1 | u8 | `flags` | bit0 `TIME_SYNCED`, bit1 `TEST`, others 0 |
| 6 | 2 | u16 | `seq` | per-node counter across all types, wraps |

- `TIME_SYNCED`: sender's clock was synchronized within the tolerance in
  `time-sync.md` when the message was built. Fusion may ignore unsynced data.
- `TEST`: synthetic or replayed-for-test data (simulator sets it).

| `type` | Name |
|--------|------|
| `0x01` | `DETECTION_BATCH` |
| `0x02` | `STATUS` |
| `0x10` | `TSYNC_REQ` |
| `0x11` | `TSYNC_RESP` |

### 2.2 `DETECTION_BATCH` (0x01) — 28 + 12·count bytes

All detections from one frame. Send **only when `count > 0`**.

| Off | Size | Type | Name | Meaning |
|-----|------|------|------|---------|
| 8 | 8 | u64 | `t_capture_us` | capture time, network timescale (see `time-sync.md`) |
| 16 | 4 | u32 | `frame_id` | per-node frame counter |
| 20 | 2 | u16 | `width` | frame width in px the coordinates refer to |
| 22 | 2 | u16 | `height` | frame height in px |
| 24 | 1 | u8 | `count` | detections, 1..16 |
| 25 | 3 | — | reserved | 0 |
| 28 | 12·n | — | detections | see below |

Detection (12 bytes). Coordinates are **raw (distorted) pixel coordinates**;
undistortion and pose are applied on the ground from `config/`.

| Off | Size | Type | Name | Meaning |
|-----|------|------|------|---------|
| 0 | 2 | u16 | `cx_q3` | centroid x · 8 (1/8 px) |
| 2 | 2 | u16 | `cy_q3` | centroid y · 8 |
| 4 | 2 | u16 | `w` | bbox width px |
| 6 | 2 | u16 | `h` | bbox height px |
| 8 | 2 | u16 | `area` | blob pixel count, saturating |
| 10 | 1 | u8 | `conf` | confidence · 255 |
| 11 | 1 | — | reserved | 0 |

### 2.3 `STATUS` (0x02) — 32 bytes, 1 Hz

Sent by every ESP node (observers, collector, ground).

| Off | Size | Type | Name | Meaning |
|-----|------|------|------|---------|
| 8 | 4 | u32 | `uptime_ms` | since boot |
| 12 | 4 | u32 | `sync_age_ms` | since last good sync; `0xFFFFFFFF` = never |
| 16 | 4 | i32 | `clock_offset_us` | last applied correction (network − local) |
| 20 | 4 | u32 | `rtt_us` | last sync round-trip; 0 if N/A |
| 24 | 2 | u16 | `fps_x10` | processed fps · 10; 0 for non-camera nodes |
| 26 | 2 | u16 | `dropped_frames` | since boot, saturating |
| 28 | 1 | i8 | `rssi_dbm` | RSSI of last frame from the time master; 0 if N/A |
| 29 | 1 | i8 | `temp_c` | chip temperature; −128 if N/A |
| 30 | 2 | — | reserved | 0 |

### 2.4 `TSYNC_REQ` (0x10) — 16 bytes, observer → collector

| Off | Size | Type | Name | Meaning |
|-----|------|------|------|---------|
| 8 | 8 | u64 | `t1_us` | observer local monotonic µs at send |

### 2.5 `TSYNC_RESP` (0x11) — 32 bytes, collector → observer

Header `node_id` and `seq` echo the request.

| Off | Size | Type | Name | Meaning |
|-----|------|------|------|---------|
| 8 | 8 | u64 | `t1_us` | echoed |
| 16 | 8 | u64 | `t2_us` | network time at request receive |
| 24 | 8 | u64 | `t3_us` | network time at response send |

## 3. MQTT on the ground host (JSON, QoS 0)

Prefix `tr/v1/`. `t_*_us` are network time; `*_host_us` are ground-host clock.

| Topic | Retain | Publisher | Payload |
|-------|--------|-----------|---------|
| `tr/v1/det/{node}` | no | bridge | detection batch |
| `tr/v1/status/{node}` | yes | bridge | node status |
| `tr/v1/bridge/stats` | yes | bridge | bridge counters, 1 Hz |
| `tr/v1/friendly/{id}` | no | friendly source | friendly position |
| `tr/v1/tracks` | no | fusion | all current tracks, 10 Hz |

`tr/v1/det/{node}`:
```json
{"node": 1, "seq": 812, "flags": 1, "synced": true, "test": false,
 "t_us": 1234567890, "rx_host_us": 1760700000131002, "frame": 4512,
 "w": 320, "h": 240,
 "dets": [{"x": 160.125, "y": 80.5, "bw": 12, "bh": 9, "area": 80, "conf": 0.8}]}
```

`tr/v1/status/{node}`:
```json
{"node": 1, "seq": 813, "rx_host_us": 1760700000200000, "uptime_ms": 912345,
 "sync_age_ms": 400, "clock_offset_us": -132, "rtt_us": 2310,
 "fps": 14.5, "dropped_frames": 3, "rssi_dbm": -54, "temp_c": 61}
```

`tr/v1/bridge/stats`:
```json
{"t_host_us": 1760700000000000, "rx": 1234, "bad": 0,
 "per_node": {"1": {"rx": 610, "gaps": 2, "last_rx_host_us": 1760699999990000}}}
```

`tr/v1/friendly/{id}` — exactly one of `enu` (metres) or `llh` (deg, deg, m HAE):
```json
{"id": "int-1", "t_us": 1234567890, "enu": [3.2, 7.9, 1.5]}
```

`tr/v1/tracks`:
```json
{"t_us": 1234600000,
 "tracks": [{"id": "T17", "enu": [4.1, 8.0, 2.2], "vel": [1.5, -0.2, 0.0],
             "sigma_m": 0.35, "nodes": [1, 2], "age_ms": 1800,
             "last_update_us": 1234590000,
             "affil": "hostile"}]}
```
`affil` ∈ `hostile | friendly | unknown`.

## 4. Recording format

The bridge writes every received message, raw, to
`recordings/<YYYYmmdd-HHMMSS>.jsonl`, one per line:
```json
{"rx_host_us": 1760700000131002, "hex": "5452..."}
```
Raw (not decoded) so a replay exercises the decoder too. Replay feeds the
bytes back through the bridge's decode path, preserving inter-arrival timing
(speed factor allowed).
