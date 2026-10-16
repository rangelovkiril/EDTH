# Wire and MQTT protocol — v1 (normative)

Implementations: `protocol/c/trwire.h`, `protocol/python` (`trwire`).
Test vectors: `protocol/test-vectors/vectors.json`.

## 1. Transport

| Channel | Transport | Direction |
|---------|-----------|-----------|
| Detections, status | UDP unicast → gateway `:5600` | node → gateway |
| Time sync (`TSYNC`) | UDP unicast ↔ gateway `:5601` | node ↔ gateway |
| Decoded data, tracks | MQTT on gateway `:1883`, JSON | services |

One UDP datagram = one message. No fragmentation, no acks, no retransmits:
a stale detection is worthless, the next frame supersedes it.
Max message size is 220 bytes (fits ESP-NOW's 250-byte limit, kept as an option).

## 2. Encoding

- Little-endian, packed, no implicit padding.
- Node IDs: `0` invalid, `1–19` ESP nodes, `20–39` Pi camera nodes,
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

All detections from one frame. Send **only when `count > 0`** (emission
discipline: silent when nothing is seen).

| Off | Size | Type | Name | Meaning |
|-----|------|------|------|---------|
| 8 | 8 | u64 | `t_capture_us` | capture time, gateway timescale (see `time-sync.md`) |
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

| Off | Size | Type | Name | Meaning |
|-----|------|------|------|---------|
| 8 | 4 | u32 | `uptime_ms` | since boot |
| 12 | 4 | u32 | `sync_age_ms` | since last good sync; `0xFFFFFFFF` = never |
| 16 | 4 | i32 | `clock_offset_us` | last applied correction (gateway − local) |
| 20 | 4 | u32 | `rtt_us` | last sync round-trip; 0 if N/A |
| 24 | 2 | u16 | `fps_x10` | processed fps · 10 |
| 26 | 2 | u16 | `dropped_frames` | since boot, saturating |
| 28 | 1 | i8 | `rssi_dbm` | Wi-Fi RSSI; 0 if N/A |
| 29 | 1 | i8 | `temp_c` | chip temperature; −128 if N/A |
| 30 | 2 | — | reserved | 0 |

### 2.4 `TSYNC_REQ` (0x10) — 16 bytes, node → gateway `:5601`

| Off | Size | Type | Name | Meaning |
|-----|------|------|------|---------|
| 8 | 8 | u64 | `t1_us` | node local monotonic µs at send |

### 2.5 `TSYNC_RESP` (0x11) — 32 bytes, gateway → node

Header `node_id` and `seq` echo the request.

| Off | Size | Type | Name | Meaning |
|-----|------|------|------|---------|
| 8 | 8 | u64 | `t1_us` | echoed |
| 16 | 8 | u64 | `t2_us` | gateway UTC µs at request receive (kernel RX stamp) |
| 24 | 8 | u64 | `t3_us` | gateway UTC µs at response send |

## 3. MQTT (JSON, QoS 0)

Prefix `tr/v1/`. All times `t_*_us` integers as in §2.

| Topic | Retain | Publisher | Payload |
|-------|--------|-----------|---------|
| `tr/v1/det/{node}` | no | ingest | detection batch |
| `tr/v1/status/{node}` | yes | ingest | node status |
| `tr/v1/ingest/stats` | yes | ingest | ingest counters, 1 Hz |
| `tr/v1/friendly/{id}` | no | friendly source | friendly position |
| `tr/v1/tracks` | no | fusion | all current tracks, 10 Hz |

`tr/v1/det/{node}`:
```json
{"node": 1, "seq": 812, "flags": 1, "synced": true, "test": false,
 "t_us": 1760700000123456, "rx_us": 1760700000131002, "frame": 4512,
 "w": 320, "h": 240,
 "dets": [{"x": 160.125, "y": 80.5, "bw": 12, "bh": 9, "area": 80, "conf": 0.8}]}
```

`tr/v1/status/{node}`:
```json
{"node": 1, "seq": 813, "rx_us": 1760700000200000, "uptime_ms": 912345,
 "sync_age_ms": 4200, "clock_offset_us": -132, "rtt_us": 2310,
 "fps": 14.5, "dropped_frames": 3, "rssi_dbm": -54, "temp_c": 61}
```

`tr/v1/ingest/stats`:
```json
{"t_us": 1760700000000000, "rx": 1234, "bad": 0,
 "per_node": {"1": {"rx": 610, "gaps": 2, "last_rx_us": 1760699999990000}}}
```

`tr/v1/friendly/{id}` — exactly one of `enu` (metres) or `llh` (deg, deg, m HAE):
```json
{"id": "int-1", "t_us": 1760700000123456, "enu": [3.2, 7.9, 1.5]}
```

`tr/v1/tracks`:
```json
{"t_us": 1760700000150000,
 "tracks": [{"id": "T17", "enu": [4.1, 8.0, 2.2], "vel": [1.5, -0.2, 0.0],
             "sigma_m": 0.35, "nodes": [1, 2, 21], "age_ms": 1800,
             "last_update_us": 1760700000140000,
             "affil": "hostile"}]}
```
`affil` ∈ `hostile | friendly | unknown`.

## 4. Recording format

Ingest writes raw datagrams to `recordings/<YYYYmmdd-HHMMSS>.jsonl`, one per line:
```json
{"rx_us": 1760700000131002, "src": "10.42.0.23:51234", "port": 5600, "hex": "5452..."}
```
Raw (not decoded) so a replay exercises the decoder too. Replay sends the
bytes back to an ingest port, preserving inter-arrival timing (speed factor
allowed).
