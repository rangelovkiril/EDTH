# Message contract

Passive sensing only: nodes publish bearings to airborne objects. Schemas in
[the `*.schema.json` files](.) are normative; this page explains them.

## Topics

| Topic | Publisher | QoS | Retained | Rate |
|-------|-----------|-----|----------|------|
| `nodes/{id}/detections` | node `{id}` | 0 | no | per detection |
| `nodes/{id}/status` | node `{id}` | 0 | no | ≈1 Hz |
| `detections/clean/{id}` | EMQX rule `det_accept` | 0 | no | per accepted detection |
| `detections/rejected/{id}` | EMQX rule `det_reject` | 0 | no | per rejected detection |

`{id}` matches `^[a-z0-9][a-z0-9_-]*$` (e.g. `rpi-1`) and equals the MQTT client id.

## `nodes/{id}/detections`

```json
{"node": "rpi-1", "t": 1760000000.123456, "az": 123.456, "el": 12.345, "conf": 0.82, "frame": 4711}
```

| Field | Type | Meaning |
|-------|------|---------|
| `node` | string | Node id; must equal the topic `{id}` |
| `t` | number | Unix time in seconds at frame capture, node clock |
| `az` | number | Degrees clockwise from true north, [0, 360) |
| `el` | number | Degrees above the horizon, [-90, 90] |
| `conf` | number | Detector confidence, [0, 1] |
| `frame` | integer | Node-local frame counter; several detections may share one |

One message per detection. No video or pixels are sent.

## `nodes/{id}/status`

```json
{"node": "rpi-1", "t": 1760000001.0, "fps": 29.7, "temp_c": 54.2, "clock_offset_ms": -3.1}
```

| Field | Type | Meaning |
|-------|------|---------|
| `node` | string | Node id; must equal the topic `{id}` |
| `t` | number | Unix time in seconds when the status was sent |
| `fps` | number | Processed frames per second (over the last interval) |
| `temp_c` | number, optional | SoC temperature; omitted if unreadable |
| `clock_offset_ms` | number, optional | Local clock minus NTP time; omitted if the query failed |

A node counts as connected while its latest `status` is under 15 s old.

## Broker-side topics

`detections/clean/{id}` carries the accepted payload plus `ingest_ms` (broker time)
and `latency_ms = ingest_ms − t·1000`. `detections/rejected/{id}` carries the
original fields (`node` renamed `claimed_node`; missing fields stay missing) plus
`reason`: `low_conf`, `range` or `node_mismatch`.

## Open points (proposals, not decisions)

- **Angle frame.** `az`/`el` are computed on the node from pixel, intrinsics and the
  configured mount heading/pitch/roll. Nobody downstream knows the pose.
- **`status` fields** are a proposal; omitting `temp_c`/`clock_offset_ms` when unavailable is an
  extension so a node without sensors or NTP still reports. (Omitted, not `null`: EMQX
  turns an absent field into SQL NULL, but passes JSON `null` to Postgres as the string `"null"`.)
- **`t` accuracy** is only as good as the node clock; chrony/NTP must run on the host.
- **No schema version field** and no retained online/offline (LWT) signal yet.
