# ground/fusion/ — triangulation, tracking, affiliation

## Purpose
Subscribe `tr/v1/det/+` and `tr/v1/friendly/+`, load `config/site.yaml`,
publish `tr/v1/tracks` at `fusion.publish_hz`. Runs on the laptop.

## Pipeline
1. **Ray per detection.** Pixel (raw) → `cv2.undistortPoints` with the node's
   intrinsics (scaled to the batch's `w`/`h`) → unit ray in camera frame →
   world ENU via the node pose. `t = t_us − latency_us`.
   The camera→world rotation lives in `geometry.py` and is the only
   implementation in the repo (`tools/sim` imports it).
2. **Buffer** rays per node for ~2× `assoc_window_ms`. Drop unsynced
   (`synced=false`) if `drop_unsynced`.
3. **Associate.** For each time slice, form candidate sets with one ray per
   node within `assoc_window_ms`; solve least-squares closest point of the rays;
   accept if max ray-to-point distance ≤ `gate_m`. P1: greedy, single target.
   Later: proper multi-target assignment; reject ghost intersections.
   Improvement path: interpolate each node's bearing to a common time instead
   of windowing.
4. **Track.** Constant-velocity Kalman filter in 3D per track; nearest-neighbour
   gating of new fixes; create on an unassigned fix, delete after
   `track_timeout_ms` without updates. `sigma_m` = sqrt of the position
   covariance trace / 3.
5. **Affiliation.** `friendly` if a friendly report is within `friendly_gate_m`
   and `friendly_gate_ms`; else `hostile` once a track has ≥ 3 updates;
   `unknown` before that.

## Rules
- Pure functions for geometry, association and filtering (`geometry.py`,
  `assoc.py`, `kalman.py`) — unit-tested with synthetic rays. MQTT glue only in `main.py`.
- Never read raw packets; input is MQTT JSON only.
- Must run identically on replayed data (`tools/replay`) — no wall-clock logic;
  drive time from message timestamps.
- SIGHUP reloads `site.yaml`.
- Reset all tracks when network time goes backwards (collector reboot,
  `docs/time-sync.md`).
- Log per fix: nodes used, residual, track id. This is the main debug signal.

## Done criteria
- Unit tests: two/three cameras with known poses triangulate a known point
  within 1 cm (noise-free) and within the expected error with noise.
- On a recording of a moving object: one stable track, no ID churn.
- Latency `last_update_us − t_us` reported in the log.
