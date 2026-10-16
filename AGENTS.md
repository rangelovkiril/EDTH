# Triangulum — agent guide (root)

Passive multi-camera detection and triangulation of low-flying aerial targets
(Shahed/Geran-class threat model), built as a prototype for **EDTH Sofia 2026**.
ESP32-S3 camera nodes report 2D detections with precise timestamps to a
collector node; the collector relays them to a ground node; ground software
triangulates, tracks, tags friendlies and publishes tracks to ATAK via
Cursor on Target.

Prototype scale: a room or a yard, a toy drone or a thrown ball as the target.

## Read first

1. This file, including **Open questions** below.
2. `docs/protocol.md` — **normative** message contract.
3. The `AGENTS.md` of the zone you are working in.

## Hardware

All radio nodes are ESP32-S3. Radio communication happens only between them.

| Qty | Device | Role |
|-----|--------|------|
| N (2+) | Seeed XIAO ESP32S3 Sense (camera) | Observer nodes |
| 1 | ESP32-S3 | Collector: gathers observer traffic, time master |
| 1 | ESP32-S3 | Ground node: receives from the collector |
| 1 | Laptop | Ground host: bridge, fusion, CoT, tools |

## Architecture

```
[observer 1] ─┐
[observer 2] ─┼─ ESP-NOW ─→ [collector] ── sky↔ground link (TBD) ──→ [ground ESP] ── (TBD) ──→ [ground host]
[observer N] ─┘             time master                                                       bridge → MQTT
                                                                                              fusion → tracks
                                                                                              cot → ATAK
```

## Open questions (do not decide these inside a zone)

1. **Sky↔ground link** between collector and ground ESP: transport, rate, and
   what exactly is forwarded.
2. **Ground ESP ↔ ground host** interface.
3. Whether the ground ESP takes part in time sync.

Until decided, code on either side of these links stays behind an interface
with a stub implementation. Decisions are recorded here and in `docs/`.

## Zone map

Each zone has its own `AGENTS.md`. **Work inside one zone per task.**

| Path | Zone | Language | Owner |
|------|------|----------|-------|
| `docs/` | Specs and design docs | Markdown | |
| `protocol/` | Message codecs (C + Python) + test vectors | C, Python | |
| `config/` | Site config: node poses, calibration | YAML | |
| `firmware/components/` | Shared ESP-IDF components: ESP-NOW link, time sync | C | |
| `firmware/observer/` | Camera node firmware | C (ESP-IDF) | |
| `firmware/collector/` | Collector firmware | C (ESP-IDF) | |
| `firmware/ground/` | Ground node firmware | C (ESP-IDF) | |
| `ground/bridge/` | Ground ESP → decode → MQTT, raw recorder | Python | |
| `ground/fusion/` | Triangulation, tracking, IFF gating | Python | |
| `ground/cot/` | Tracks → Cursor on Target → ATAK | Python | |
| `tools/` | Replay, simulator, calibration, `trctl` status CLI | Python | |

Fill in owners once the team is fixed.

## Hard rules

1. **Stay in your zone.** If you need a change in another zone, describe it
   (issue, chat, or a note in your commit) instead of editing it yourself.
2. **The protocol is the contract.** Never change a message layout in one place
   only. A wire change updates, in the same commit: `docs/protocol.md`,
   `protocol/c/trwire.h`, `protocol/python`, and regenerated test vectors.
   Incompatible changes bump `version`.
3. **Time.** All absolute timestamps are integer **microseconds on the network
   timescale** (the collector's clock, see `docs/time-sync.md`), named `t_*_us`.
   Stamp at capture, never at receive, when capture time exists. Ground-host
   clock values are named `*_host_us` and never mixed with network time.
4. **Units and frames.** Metres, seconds, degrees in configs/JSON. World frame
   is local **ENU** (x east, y north, z up) around the site origin. Camera
   frame is OpenCV (x right, y down, z forward). See `docs/architecture.md`.
5. **Replayable.** Everything on the ground host must run on recorded data
   without hardware. Never break `tools` replay.
6. **No secrets in git.** ESP-NOW keys and similar live in gitignored files
   with a committed `*.example` next to them.
7. **Demo first.** A working end-to-end path beats completeness. Prefer simple,
   observable code. Log one structured line per event with `node`/`seq`.
8. **Python**: 3.11+, uv workspace (root `pyproject.toml`), `ruff`, `pytest`,
   `src/` layout. **Firmware**: ESP-IDF, one pinned version (`firmware/IDF_VERSION`).

## Milestones

- **P0** — one observer → collector over ESP-NOW; time sync working; status visible
  on the collector's serial log.
- **P1** — sky↔ground and ground host paths decided and working; detections on MQTT;
  raw recording.
- **P2** — all observers live; fusion triangulates a single target; tracks on MQTT.
- **P3** — CoT into ATAK/WinTAK; friendly gating; `trctl`; simulator with many targets.

## Ground host

| What | Where |
|------|-------|
| MQTT | `localhost:1883` (mosquitto) |
| CoT out | UDP multicast `239.2.3.1:6969` (ATAK SA default) |

## Git

- Conventional Commits, scope = zone: `feat(fusion): ...`, `fix(observer): ...`,
  `docs(protocol): ...`.
- Short imperative subject. No body, or one short line of *why*. Never restate
  the diff.
- No `Co-Authored-By` or "Generated with ..." trailers.
- `main` must always be demoable. Small commits.
