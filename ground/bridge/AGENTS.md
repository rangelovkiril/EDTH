# ground/bridge/ — ground ESP → MQTT

## Purpose
`tr-bridge` runs on the ground host. It receives raw messages from the ground
ESP, records them, decodes them with `trwire` and publishes JSON to MQTT per
`docs/protocol.md` §3.

## Open question
How messages get from the ground ESP to this process is undecided (root
`AGENTS.md`). Structure the code so the transport is one small adapter:

```
src/tr_bridge/source.py     Source interface: yields (rx_host_us, bytes); stub/file source until decided
src/tr_bridge/publish.py    message → JSON (pure, unit-tested), MQTT publish, stats
src/tr_bridge/record.py     raw JSONL recorder (protocol §4)
src/tr_bridge/main.py       tr-bridge entry point: source → record → decode → publish
```
`tools` replay and the simulator reuse `publish.py` and the decode path.

## Rules
- Never parse bytes by hand — only `trwire.decode`.
- Record before decoding: a message that fails to decode is still recorded.
- Bad messages: count in `tr/v1/bridge/stats`, log once per node per 10 s, never crash.
- Track `seq` per node; count gaps with wraparound.
- MQTT must never block receiving: paho `loop_start()`; if the broker is down,
  keep recording and counting.
- `rx_host_us` is host clock; never mix it with network time.
- Config by CLI flags with env overrides (`TR_MQTT_HOST`, `TR_RECORD_DIR`, ...).

## Done criteria
- Replaying a recording reproduces the same MQTT JSON (test).
- Stats show per-node rx counts and gaps.
