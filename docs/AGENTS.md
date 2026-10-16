# docs/ — specs and design

## Purpose
Human- and agent-readable specs. Code follows docs, not the other way around.

| File | Status | Contents |
|------|--------|----------|
| `protocol.md` | **Normative** | Message format, MQTT topics and JSON, recording format |
| `architecture.md` | Descriptive | Components, data flow, frames, failure modes |
| `time-sync.md` | Normative for time handling | Network timescale, `TSYNC`, capture stamps |
| `radio.md` | Normative for ESP-NOW | Channel, peers, encryption, node IDs |

## Rules
- English, concise, no marketing language. ASCII diagrams only.
- Changing `protocol.md` is a protocol change: follow root rule 2 (update C,
  Python, test vectors in the same commit).
- Byte layouts are tables with offset, size, type, name, meaning. Keep offsets
  correct — the codecs are checked against them.
- When code and docs disagree, the doc wins until the doc is explicitly changed.
- Undecided items are listed as open questions in the root `AGENTS.md`, not
  filled in with guesses.
