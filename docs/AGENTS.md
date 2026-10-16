# docs/ — specs and design

## Purpose
Human- and agent-readable specs. Code follows docs, not the other way around.

| File | Status | Contents |
|------|--------|----------|
| `protocol.md` | **Normative** | UDP wire format, MQTT topics and JSON, recording format |
| `architecture.md` | Descriptive | Components, data flow, frames, latency budget, failure modes, field version |
| `time-sync.md` | Normative for time handling | Timescale, SNTP phase, `TSYNC` phase, latency calibration |
| `network.md` | Normative for addressing | Subnets, ports, AP security |

## Rules
- English, concise, no marketing language. ASCII diagrams only.
- Changing `protocol.md` is a protocol change: follow root rule 2 (update C,
  Python, test vectors in the same commit).
- Byte layouts are tables with offset, size, type, name, meaning. Keep offsets
  correct — the codecs are checked against them.
- When code and docs disagree, the doc wins until the doc is explicitly changed.
- Pitch-relevant reasoning (why passive sensors, EMCON, field transport) lives in
  `architecture.md` so the pitch can be built from it.
