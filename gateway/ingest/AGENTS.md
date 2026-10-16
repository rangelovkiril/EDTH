# gateway/ingest/ — UDP ingest, recorder, time-sync responder

## Purpose
Two small, boring, reliable services on the gateway.

**`tr-ingest`** — UDP `:5600` → validate/decode with `trwire` → publish JSON
to MQTT per `docs/protocol.md` §3 → append raw datagram to the recording.
**`tr-tsyncd`** — UDP `:5601` → answer `TSYNC_REQ` with `TSYNC_RESP` (§2.5).

## Rules
- Never parse bytes by hand — only `trwire.decode`.
- `rx_us` from kernel RX timestamps (`SO_TIMESTAMPNS`), not from Python time.
  Same for `t2_us` in `tr-tsyncd`; `t3_us` immediately before `sendto`.
- Bad datagrams: count in stats, log once per source per 10 s, never crash.
- Track `seq` per node; count gaps (with wraparound) in `tr/v1/ingest/stats`.
- MQTT must never block the UDP path: paho `loop_start()`, publish
  non-blocking; if the broker is down, keep recording and keep counting.
- Recording: `recordings/<start>.jsonl` (format in protocol §4), line-buffered,
  rotate per process start. Path configurable (`--record-dir`).
- `tr-tsyncd` must be minimal and fast: no MQTT, no logging per packet.
- Config by CLI flags with env overrides (`TR_MQTT_HOST`, `TR_RECORD_DIR`, ...).

## Layout
```
src/tr_ingest/main.py      tr-ingest entry point
src/tr_ingest/tsyncd.py    tr-tsyncd entry point
src/tr_ingest/mqtt_json.py message → JSON (pure, unit-tested)
tests/
```

## Done criteria
- `tools` replay of a recording reproduces the same MQTT JSON (test).
- Runs under systemd (units in `infra/`), restarts on failure, logs to journald.
- Handles 4 nodes × 30 fps of batches with < 5% CPU on the Pi.
