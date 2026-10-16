# firmware/ — ESP32-S3 firmware

## Purpose
Three ESP-IDF applications sharing common components:

| App | Node ID | Does |
|-----|---------|------|
| `observer/` | 1–19 | Camera, detection, timestamps, sends to collector |
| `collector/` | 100 | Receives from observers, time master, relays towards ground |
| `ground/` | 110 | Receives from collector, hands off to the ground host |
| `components/` | — | `tr_link` (ESP-NOW), `tr_timesync` (master + client) |

## Rules
- **ESP-IDF**, one version for the whole team, written in `firmware/IDF_VERSION`
  when the toolchain is set up. Do not mix versions.
- Messages only via `protocol/c/trwire.h`. Never redefine message structs.
- Radio rules: `docs/radio.md`. Time rules: `docs/time-sync.md`.
- Shared configuration fragments, applied to every app:
  - `network.defaults` (committed): channel, collector MAC, observer MAC list.
  - `espnow.keys` (gitignored, from `espnow.keys.example`): PMK/LMK.
- Build one board:
  ```sh
  idf.py -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;../network.defaults;../espnow.keys;nodes/node-01.defaults" \
    build flash monitor
  ```
  Delete `sdkconfig` when switching node files, or the old values stick.
- Never block a receive callback: copy into a queue, process in a task.
- Every node sends `STATUS` at 1 Hz.
- The collector↔ground link and ground↔host interface are open questions:
  keep them behind a `tr_uplink` / `tr_host` interface with a stub until decided.

## Done criteria (per app)
- Builds from a clean checkout with the command above.
- Measured numbers (fps, latency, sync error) written in the app's `AGENTS.md`.
