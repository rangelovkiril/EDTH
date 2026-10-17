# M.I.G.E.T. — agent guide (root)

**Intent.** This is a *passive, defensive sensing* demo for EDTH Sofia 2026. Cameras on
Raspberry Pi nodes look at the sky and report **bearings (azimuth/elevation) to airborne
objects** so that people on the ground can be warned. Nothing here targets anything, controls a
weapon, or acts on the world: the system only observes and publishes numbers. Prototype scale:
a yard, a toy drone or a thrown ball.

## What this repo is

One Python program, `node/`, that runs on each Pi: camera → detector → az/el → MQTT.

```
camera → detector → pixel to az/el → MQTT (TLS) ──→ broker (EDTH-infra repo) ──→ dashboards
```

The broker, cluster, TLS, database and Grafana live in the separate **EDTH-infra** repo.
Do not add infrastructure here.

| Path | What |
|------|------|
| `node/` | the node program and its tests; start with [`node/AGENTS.md`](node/AGENTS.md) |
| `docs/contract.md`, `docs/*.schema.json` | the message contract (normative) |
| `.github/workflows/node.yml` | test, build the arm64 image, push to GHCR |
| `node/deploy.py`, `node/pis.json` | deploy the image to the Pis |

## Contract in one table

| Topic | Payload |
|-------|---------|
| `nodes/{id}/detections` | `{"node","t","az","el","conf","frame"}` — one message per detection, QoS 0 |
| `nodes/{id}/status` | `{"node","t","fps"}` plus optional `temp_c`, `clock_offset_ms` — about 1 Hz |

`t` is Unix seconds at frame capture. `az` is degrees clockwise from true north, [0, 360);
`el` is degrees above the horizon, [-90, 90]. Details and ranges: [`docs/contract.md`](docs/contract.md).
Changing a payload means updating the schemas, `docs/contract.md`, `node/` and its tests in the
same commit, and telling whoever runs the broker.

## Rules

1. **Stay in your lane.** Detector authors touch only the files listed in `node/AGENTS.md`.
   Changes to publishing, status, geometry or config go through the platform owner.
2. **Secrets stay out of git.** Passwords and keys come from the environment; commit only `*.example`.
3. **Demo first.** A working end-to-end path beats completeness. Prefer simple, observable code.
4. **Tests must pass:** `cd node && uv run pytest && uv run ruff check .`.
5. **Python:** 3.11+, `uv`, `ruff`, `pytest`.

## Git

- Conventional Commits, scope = area: `feat(node): ...`, `fix(detector): ...`.
- Short imperative subject. No body, or one short line of *why*.
- No `Co-Authored-By` or "Generated with ..." trailers.
- `main` must always work. Small commits.

## Open questions

Written down, not decided.

1. **`az`/`el` frame and node pose.** Assumed: computed on the node from pixel, intrinsics and
   the configured mount heading/pitch/roll. Nobody downstream knows the pose.
2. **`status` field names/units** are a proposal (`fps`, `temp_c`, `clock_offset_ms`).
3. **Camera:** USB (V4L2, default) or CSI (needs libcamera and more device access).
4. **NTP egress** (UDP 123) from the Pis; without it `clock_offset_ms` is omitted.
5. **Online/offline signal:** retained LWT on `status`, and a schema `version` field.
6. **Project name:** repo history says "Triangulum", the brief says "M.I.G.E.T.".
7. **Pi deployment** is `node/deploy.py` over SSH (from a machine that can reach the Pis).
   Deploying from CI would need a network path to the Pis (VPN/tailnet); not set up.
8. **Untested on real hardware:** the Pi camera path, the arm64 image and `deploy.py` on a real Pi
   (it is tested against stubs).
