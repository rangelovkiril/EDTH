# tools/ — replay, simulator, calibration, status CLI

## Purpose
Shared tooling that lets everyone work without the physical setup.
Each tool is a module in `src/tr_tools/` with its own entry point.

| Command | Module | Does |
|---------|--------|------|
| `tr-replay` | `replay.py` | Sends a raw recording (`protocol.md` §4) to an ingest port with original timing; `--speed`, `--loop`, `--from/--to` |
| `tr-sim` | `sim.py` | Synthetic targets → projected through `config/site.sim.yaml` cameras → `DETECTION_BATCH` with `FLAG_TEST`, sent to ingest |
| `tr-calib` | `calib.py` | Checkerboard intrinsics from captured images → `config/calib/node-XX.yaml` |
| `trctl` | `trctl.py` | Live terminal view: nodes (age, fps, sync, rssi, temp, gaps), tracks, latency |

## Rules
- Build packets only with `trwire`. Project points only with
  `tr_fusion.geometry` — the simulator must use the same math as fusion, or a
  sim test proves nothing.
- Simulator noise model is explicit and configurable: pixel noise, time
  offset per node, pose error (deg), detection dropout, false alarms, many
  targets. These are the knobs used to show robustness in the pitch.
- `trctl` is read-only: MQTT subscribe only. Highlight in red: status older
  than 3 s, unsynced nodes, seq gaps rising.
- Replay must keep working with every recording in `recordings/` — it is the
  team's test harness and the demo fallback.

## Done criteria
- `tr-sim` with 3 nodes and 1 target → fusion produces a track matching ground truth.
- `trctl` shows all live nodes during the demo.
