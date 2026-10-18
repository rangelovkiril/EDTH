# M.I.G.E.T. — agent guide (root)

**Intent.** This is a *passive, defensive sensing* demo for EDTH Sofia 2026. Cameras on
Raspberry Pi nodes look at the sky and report **bearings (azimuth/elevation) to airborne
objects** so that people on the ground can be warned. Nothing here targets anything, controls a
weapon, or acts on the world: the system only observes and publishes numbers. Prototype scale:
a yard, a toy drone or a thrown ball.

## What this repo is

The computation is spread out: each Pi detects, turns pixels into bearings and crosses its rays with
its peers' into 3D fixes; the broker's rule engine turns detections into rays and validates fixes;
a thin `fusion/` on the ground only associates fixes and Kalman-filters them into tracks with a
prediction and a confidence. Details: [`docs/contract.md`](docs/contract.md), "Who computes what".

```
node: camera → detector → az/el ─→ detections ─→ broker rule: ECEF ray ─→ rays/+ ─→ every node
node: own rays × peers' rays ─→ fixes ─→ broker rule: validate ─→ fusion: tracks ─→ Grafana
```

The broker, cluster, TLS, database and Grafana live in the separate **EDTH-infra** repo.
Do not add infrastructure here.

| Path | What |
|------|------|
| `node/` | the node program and its tests; start with [`node/AGENTS.md`](node/AGENTS.md) |
| `fusion/` | the thin ground side: fixes → tracks; [`fusion/AGENTS.md`](fusion/AGENTS.md) |
| `docs/contract.md`, `docs/*.schema.json` | the message contract (normative) |
| `.github/workflows/node.yml` | test, then build and push the arm64 image on push to `main` |
| `.github/workflows/fusion.yml` | the same for fusion (amd64 + arm64) |
| `deploy/` | one-time Pi bootstrap and the quadlet; the Pi then updates itself |

## Contract in one table

| Topic | Payload |
|-------|---------|
| `nodes/{id}/detections` | `{"node","t","az","el","conf","frame"}` plus `lat`/`lon`/`alt_m` — one message per detection, QoS 0 |
| `nodes/{id}/status` | `{"node","t","fps"}` plus optional `temp_c`, `clock_offset_ms`, `lat`/`lon`/`alt_m` — about 1 Hz |
| `rays/{id}` | broker rule: the detection as an ECEF ray `{"node","t","conf","ox".."dz","ingest_ms","latency_ms"}` |
| `nodes/{id}/fixes`, `fixes/{id}` | node: where its ray crosses a peer's `{"node","peer","t","lat","lon","alt_m","miss_m","angle_deg","range_m","conf"}`; broker republishes accepted ones |
| `fusion/tracks` | `{"id","t","lat","lon","alt_m",…,"pred_lat","pred_lon","pred_alt_m","sigma_m","conf",…}` — per track per step |

`t` is Unix seconds at frame capture. `az` is degrees clockwise from true north, [0, 360);
`el` is degrees above the horizon, [-90, 90]. Details and ranges: [`docs/contract.md`](docs/contract.md).
Changing a payload means updating the schemas, `docs/contract.md`, `node/` and its tests in the
same commit, and telling whoever runs the broker.

## Rules

1. **Stay in your lane.** Detector authors touch only the files listed in `node/AGENTS.md`.
   Changes to publishing, status, geometry or config go through the platform owner.
2. **Secrets stay out of git.** Passwords and keys come from the environment; commit only `*.example`.
3. **Demo first.** A working end-to-end path beats completeness. Prefer simple, observable code.
4. **Tests must pass:** `uv run pytest && uv run ruff check .` in `node/` and in `fusion/`.
5. **Python:** 3.11+, `uv`, `ruff`, `pytest`.

## Git

- Conventional Commits, scope = area: `feat(node): ...`, `fix(detector): ...`.
- Short imperative subject. No body, or one short line of *why*.
- No `Co-Authored-By` or "Generated with ..." trailers.
- `main` must always work. Small commits.

## Open questions

Written down, not decided.

1. **`az`/`el` frame and node pose.** Assumed: computed on the node from pixel, intrinsics and
   the configured mount heading/pitch/roll. Fusion knows each node's position (from `status`), not its
   orientation; on an aerostat the heading drifts and needs a compass/IMU.
2. **`status` field names/units** are a proposal (`fps`, `temp_c`, `clock_offset_ms`).
3. **Cameras:** `miget5` (Pi 5) has a Camera Module 3 Wide (imx708_wide), `miget3` (Pi 3B) a Camera
   Module v2 (imx219), both on CSI; USB cameras work through V4L2. The node takes the HFOV (102° / 62.2°)
   from the sensor's datasheet value and the crop of the mode in use, not from a calibration. Untested
   on the Pi 3 yet, including whether it keeps up at 1280x720.
4. **NTP egress** (UDP 123) from the Pis; without it `clock_offset_ms` is omitted.
5. **Online/offline signal:** retained LWT on `status`, and a schema `version` field.
6. **Project name:** repo history says "Triangulum", the brief says "M.I.G.E.T.".
7. **Pi deployment** is pull-based (`podman auto-update` on the Pi), because the Pi is on a private
   network. The `RPI*_SSH_KEY` secrets are unused; SSH-from-Actions needs a tunnel or VPN.
8. **Untested on real hardware:** the container image on a Pi (the camera code itself was run on one),
   and surviving a reboot.
