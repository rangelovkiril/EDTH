# config/ — site configuration and calibration

## Purpose
Everything geometric about a deployment: origin, node poses, camera
intrinsics, per-node latency. Read by `ground/fusion`, `ground/cot`, `tools/sim`.
Nodes never read this — they send raw pixels.

```
site.example.yaml     committed template, documents the schema
site.yaml             the real deployment (gitignored — copy from the example)
site.sim.yaml         simulator scenario site (committed, synthetic)
calib/node-XX.yaml    intrinsics per camera (committed: they describe hardware)
```

## Schema rules
- Frames and angle conventions: `docs/architecture.md` ("Frames and conventions").
  Do not invent new ones.
- Intrinsics files use OpenCV naming: `camera_matrix` (3×3, row-major list),
  `dist_coeffs` (k1, k2, p1, p2, k3), plus `width`/`height` they were calibrated at.
  If a node streams at a different resolution, fusion scales `fx, fy, cx, cy`.
- Calibration files are produced by `tr-calib` (see `tools/`), not hand-edited.
- Poses: measure position with a tape (cm precision is fine indoors), yaw with
  a reference line or compass app, pitch with a phone inclinometer. Record
  how you measured in a YAML comment — it matters when numbers look wrong.
- Every change to `site.yaml` during the event: also note it in the team chat.
  Fusion reloads config on SIGHUP.

## Done criteria
- `site.example.yaml` stays valid and loads in fusion's config loader test.
