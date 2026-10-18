# Message contract

Passive sensing only: nodes publish bearings to airborne objects and the points where their
bearings cross; nothing here controls anything. The JSON Schemas
([`detection`](detection.schema.json), [`status`](status.schema.json), [`ray`](ray.schema.json),
[`fix`](fix.schema.json), [`track`](track.schema.json)) are normative; this page explains them.

## Who computes what

The work is spread out so the ground does little: each step runs where its inputs already are.

```
node:   camera → detector → az/el ──────────────→ nodes/{id}/detections ─┐
broker: rule "rays":  detection + node position → ECEF ray → rays/{id} ←─┘
node:   own rays × peers' rays/+ → closest approach → nodes/{id}/fixes ──┐
broker: rule "fixes": validate, add ingest time  → fixes/{id} ←──────────┘
ground: fusion: associate fixes, Kalman filter   → fusion/tracks (prediction, confidence)
```

- **Node** (Raspberry Pi): detection, pixel → bearing, and the triangulation of its own rays with
  every peer's. A pair of nodes is crossed by the one with the larger id, so each pair of frames
  makes one fix. A few dot products per pair.
- **Broker** (EMQX rule engine, in EDTH-infra `apps/emqx`): stateless per message. Turns a
  detection into a ray in WGS84 ECEF (a frame all nodes share without agreeing on a site origin),
  rejects messages whose `node` is not the topic's, and stamps `ingest_ms`/`latency_ms`.
- **Ground** (`fusion/`): says which fixes are the same object and smooths them. No geometry.

## Topics

| Topic | Publisher | QoS | Retained | Rate |
|-------|-----------|-----|----------|------|
| `nodes/{id}/detections` | node `{id}` | 0 | no | per detection |
| `nodes/{id}/status` | node `{id}` | 0 | no | ≈1 Hz |
| `rays/{id}` | broker rule `rays` | 0 | no | per detection with a position and `conf ≥ 0.3` |
| `nodes/{id}/fixes` | node `{id}` | 0 | no | per crossing pair of frames |
| `fixes/{id}` | broker rule `fixes` | 0 | no | per accepted fix |
| `fusion/tracks` | fusion | 0 | no | per confirmed track per step (≈10 Hz) |

`{id}` matches `^[a-z0-9][a-z0-9_-]*$` (on a Pi `pi-` + the last 8 hex digits of its serial, e.g.
`pi-8584f1f2`) and equals the MQTT client id. All nodes log in as user `node`; the broker's ACL lets
that user publish only under `nodes/<its client id>/` and subscribe only to `rays/+`.

## `nodes/{id}/detections`

```json
{"node": "rpi-1", "t": 1760000000.123456, "az": 123.456, "el": 12.345, "conf": 0.82, "frame": 4711,
 "lat": 42.6573, "lon": 23.3549, "alt_m": 561.5}
```

| Field | Type | Meaning |
|-------|------|---------|
| `node` | string | Node id; must equal the topic `{id}` |
| `t` | number | Unix time in seconds at frame capture, node clock |
| `az` | number | Degrees clockwise from true north, [0, 360) |
| `el` | number | Degrees above the horizon, [-90, 90] |
| `conf` | number | Detector confidence, [0, 1] |
| `frame` | integer | Node-local frame counter; several detections may share one |
| `lat`, `lon`, `alt_m` | number, optional | Where the camera was at that frame (WGS84 degrees, metres) |

One message per detection. No video or pixels are sent to the broker. (For demos a node can also
serve a live view on its own HTTP port, and push small frames to a video relay over HTTPS,
`VIDEO_PUSH_URL`; both are opt-in and not part of this contract.)
The position comes together or not at all (`NODE_LAT`/`NODE_LON`/`NODE_ALT_M`); without it the
broker makes no ray and nobody can triangulate this node. It is in every detection so that the
broker needs no state and a moving node (an aerostat with a GPS) is placed where it was.

## `nodes/{id}/status`

```json
{"node": "rpi-1", "t": 1760000001.0, "fps": 29.7, "temp_c": 54.2, "clock_offset_ms": -3.1,
 "lat": 42.6573, "lon": 23.3549, "alt_m": 561.5}
```

| Field | Type | Meaning |
|-------|------|---------|
| `node` | string | Node id; must equal the topic `{id}` |
| `t` | number | Unix time in seconds when the status was sent |
| `fps` | number | Processed frames per second (over the last interval) |
| `temp_c` | number, optional | SoC temperature; omitted if unreadable |
| `clock_offset_ms` | number, optional | Local clock minus NTP time; omitted if the query failed |
| `lat`, `lon`, `alt_m` | number, optional | Camera position, as in detections; for maps |

A node counts as connected while its latest `status` is under 15 s old.

## `rays/{id}`

```json
{"node": "rpi-1", "t": 1760000000.123456, "frame": 4711, "conf": 0.82,
 "ox": 4313311.03, "oy": 1862490.36, "oz": 4299961.88, "dx": -0.5775, "dy": 0.4381, "dz": 0.6889,
 "ingest_ms": 1760000000131, "latency_ms": 7.6}
```

A detection as a half-line in WGS84 ECEF: origin `o` (metres) and unit direction `d`. Same formulas
as the node's `src/ecef.py` (tests check they agree). `latency_ms = ingest_ms − t·1000` is network
delay plus the node's clock offset: a quick clock sanity check.

## `nodes/{id}/fixes` and `fixes/{id}`

```json
{"node": "rpi-2", "peer": "rpi-1", "t": 1760000000.12, "lat": 42.6575551, "lon": 23.3550144,
 "alt_m": 569.35, "miss_m": 0.246, "angle_deg": 50.6, "range_m": 29.9, "conf": 0.444}
```

| Field | Type | Meaning |
|-------|------|---------|
| `node`, `peer` | string | The node that computed the fix (larger id) and the other one |
| `t` | number | Mean capture time of the two rays (at most `TRI_SYNC_S` apart) |
| `lat`, `lon`, `alt_m` | number | Midpoint of the shortest segment between the rays |
| `miss_m` | number | Length of that segment: how well the two rays agree |
| `angle_deg` | number | Angle between the rays; near 0 means poor depth |
| `range_m` | number | Distance from `node` |
| `conf` | number | Product of the detections' confidences, reduced as `miss_m` grows |

`fixes/{id}` is the same message after the broker accepted it (`miss_m ≤ 3`, `angle_deg ≥ 2`,
`conf ≥ 0.1`, `node` matches the topic), with `ingest_ms` and `latency_ms` added.

## `fusion/tracks`

```json
{"id": 1, "t": 1760000000.4, "lat": 42.6575551, "lon": 23.3550144, "alt_m": 569.4,
 "e": 9.8, "n": 22.1, "u": 9.4, "ve": -2.1, "vn": 3.6, "vu": 0.2, "speed_mps": 4.18, "heading_deg": 329.9,
 "pred_lat": 42.6575871, "pred_lon": 23.3549890, "pred_alt_m": 569.6, "horizon_s": 1.0,
 "sigma_m": 0.33, "pred_sigma_m": 1.9, "conf": 0.83, "pairs": 1, "hits": 247}
```

| Field | Type | Meaning |
|-------|------|---------|
| `id` | integer | Track id; stays the same while the track lives, counts up from 1 |
| `t` | number | Unix seconds the state is predicted to (now) |
| `lat`, `lon`, `alt_m` | number | Filtered position; `alt_m` in the nodes' reference |
| `e`, `n`, `u` | number | The same in metres east, north, up of fusion's origin (the first fix) |
| `ve`, `vn`, `vu`, `speed_mps`, `heading_deg` | number | Velocity |
| `pred_lat`, `pred_lon`, `pred_alt_m` | number | Where it will be `horizon_s` from now at this velocity |
| `sigma_m`, `pred_sigma_m` | number | 1σ uncertainty of the position and of the prediction |
| `conf` | number | 0–1: certainty (σ), evidence (fixes so far), freshness and fix confidence |
| `pairs`, `hits` | integer | Node pairs that contributed, fixes so far |

A track is published once it has `CONFIRM_HITS` fixes, so one chance crossing (a false detection
meeting another node's ray) is never shown. Flat on purpose: Grafana's MQTT data source makes a
field of every top-level key.

## Open points (proposals, not decisions)

- **Angle frame.** `az`/`el` are computed on the node from pixel, intrinsics and the
  configured mount heading/pitch/roll. Downstream knows the position, not the orientation. On an
  aerostat the heading changes as it turns; that needs a compass/IMU on the node.
- **Altitude reference** is whatever the nodes agree on; a GPS altitude and a hand-measured one
  must not be mixed.
- **Clocks.** Rays are paired by their `t`, so node clocks must agree to well under `TRI_SYNC_S`
  (100 ms by default): chrony/NTP on every host; over a phone hotspot clocks differ by tens of ms. `latency_ms` on `rays/*` shows a clock that drifts.
- **Two cameras, two targets** can cross in "ghost" places; a third node removes them.
- **`status` fields** are a proposal; unavailable values are omitted, not `null`.
- **No schema version field** and no retained online/offline (LWT) signal yet.
