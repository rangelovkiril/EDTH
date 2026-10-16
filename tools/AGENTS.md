# tools/ — replay, simulator, calibration, status CLI

## Purpose
Shared tooling that lets everyone work without the physical setup.
Each tool is a module in `src/tr_tools/` with its own entry point.

| Command | Module | Does |
|---------|--------|------|
| `tr-replay` | `replay.py` | Feeds a raw recording (`protocol.md` §4) through the bridge's decode path into MQTT with original timing; `--speed`, `--loop`, `--from/--to` |
| `tr-sim` | `sim.py` | Synthetic targets → projected through `config/site.sim.yaml` cameras → `DETECTION_BATCH` with `FLAG_TEST` → bridge decode path → MQTT |
| `tr-calib` | `calib.py` | Checkerboard intrinsics from captured images → `config/calib/node-XX.yaml` |
| `trctl` | `trctl.py` | Live terminal view: nodes (age, fps, sync, rssi, temp, gaps), tracks, latency |

## Rules
- Build messages only with `trwire`. Reuse the bridge's decode/publish code
  (`tr_bridge`), don't duplicate it. Project points only with
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
