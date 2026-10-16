# Triangulum — agent guide (root)

Passive multi-camera detection and triangulation of low-flying aerial targets
(Shahed/Geran-class threat model), built as a prototype for **EDTH Sofia 2026**.
Cheap camera nodes report 2D detections with precise timestamps; a gateway
collects them; a ground station triangulates, tracks, tags friendlies and
publishes tracks to ATAK via Cursor on Target.

Prototype scale: a room or a yard, a toy drone or a thrown ball as the target.
Every design decision should still have a clear story for the field version
(see `docs/architecture.md`, section "Field version").

## Read first

1. This file.
2. `docs/protocol.md` — **normative** wire + MQTT contract. Anything that
   crosses a zone boundary is defined there.
3. The `AGENTS.md` of the zone you are working in.

## Hardware

| Qty | Device | Role |
|-----|--------|------|
| 2 | Seeed XIAO ESP32S3 Sense (camera) | Sensor nodes `1`, `2` |
| 1 | Raspberry Pi | Gateway: Wi-Fi AP, time master, ingest, MQTT, uplink |
| 1–2 | Camera on the Pi (CSI and/or USB) | Sensor nodes `21`, `22` |
| 1 | Laptop | Ground station: fusion, CoT, ATAK/WinTAK, dashboards |

## Architecture

```
[ESP node 1] ─┐  Wi-Fi AP (UDP)
[ESP node 2] ─┼──────────────────→ [Gateway RPi] ── Ethernet ──→ [Ground laptop]
[Pi cam 21/22] (localhost UDP) ──→   ingest → MQTT              fusion → tracks
                                     chrony (time master)        cot → ATAK
```

## Zone map

Each zone has its own `AGENTS.md`. **Work inside one zone per task.**

| Path | Zone | Language | Owner |
|------|------|----------|-------|
| `docs/` | Specs and design docs | Markdown | all (protocol: lead) |
| `protocol/` | Wire protocol codecs (C + Python) + test vectors | C, Python | lead |
| `config/` | Site config: node poses, calibration | YAML | fusion + calib |
| `firmware/esp-node/` | ESP32-S3 camera node firmware | C (ESP-IDF) | firmware |
| `sensors/pi-node/` | Raspberry Pi camera node | Python | sensors |
| `gateway/ingest/` | UDP ingest → MQTT, recorder, time-sync responder | Python | DevOps |
| `infra/` | Gateway OS provisioning, AP, chrony, MQTT, services | Ansible, config | DevOps (Kiril) |
| `ground/fusion/` | Triangulation, tracking, IFF gating | Python | fusion |
| `ground/cot/` | Tracks → Cursor on Target → ATAK | Python | fusion / DevOps |
| `tools/` | Replay, simulator, calibration, `trctl` status CLI | Python | shared |

Fill in owner names in this table once the team is fixed.

## Hard rules

1. **Stay in your zone.** If you need a change in another zone, describe it
   (issue, chat, or a note in your commit) instead of editing it yourself.
2. **The protocol is the contract.** Never change a message layout in one place
   only. A wire change updates, in the same commit: `docs/protocol.md`,
   `protocol/c/trwire.h`, `protocol/python`, and regenerated test vectors.
   Incompatible changes bump `version`.
3. **Time.** All absolute timestamps are integer **microseconds since the Unix
   epoch, UTC, on the gateway's timescale**, named `t_*_us`. Stamp at capture,
   never at receive, when capture time exists. Use monotonic clocks for
   durations and as the local base for capture stamps.
4. **Units and frames.** Metres, seconds, degrees in configs/JSON. World frame
   is local **ENU** (x east, y north, z up) around the site origin. Camera
   frame is OpenCV (x right, y down, z forward). See `docs/architecture.md`.
5. **Replayable.** Every component downstream of ingest must run on recorded
   data without hardware. Never break `tools` replay.
6. **No secrets in git.** Wi-Fi passphrases and keys live in gitignored files
   with a committed `*.example` next to them.
7. **Demo first.** A working end-to-end path beats completeness. Prefer simple,
   observable code. Log one structured line per event with `node`/`seq`.
8. **Python**: 3.11+, uv workspace (root `pyproject.toml`), `ruff` for
   lint/format, `pytest` for tests. Each package uses the `src/` layout.

## Milestones

- **P0** — one ESP node → ingest → MQTT visible; SNTP time sync; raw recording.
- **P1** — all cameras live; fusion triangulates a single target; tracks on MQTT.
- **P2** — CoT into ATAK/WinTAK; friendly gating; `trctl` status view;
  end-to-end latency measured.
- **P3** — simulator with many targets; custom time sync (`TSYNC`); SAPIENT
  output as a stretch goal.

## Network and ports (summary — details in `docs/network.md`)

| What | Where |
|------|-------|
| AP subnet (sensors) | `10.42.0.0/24`, gateway `10.42.0.1` |
| Uplink (Ethernet) | `10.43.0.0/24`, gateway `10.43.0.1`, laptop `10.43.0.2` |
| Ingest | UDP `5600` on gateway |
| Time sync (`TSYNC`) | UDP `5601` on gateway |
| NTP (chrony) | UDP `123` on gateway |
| MQTT | TCP `1883` on gateway |
| CoT out | UDP multicast `239.2.3.1:6969` (ATAK SA default) |

## Git

- Conventional Commits, scope = zone: `feat(fusion): ...`, `fix(firmware): ...`,
  `chore(infra): ...`, `docs(protocol): ...`.
- Short imperative subject. No body, or one short line of *why*. Never restate
  the diff.
- No `Co-Authored-By` or "Generated with ..." trailers.
- `main` must always be demoable. Small commits.
