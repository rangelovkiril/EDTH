# M.I.G.E.T. — agent guide (root)

**Intent.** This is a *passive, defensive sensing* demo for EDTH Sofia 2026. Cameras
on Raspberry Pi nodes look at the sky and report **bearings (azimuth/elevation) to
airborne objects** so that people on the ground can be warned. Nothing here
targets anything, controls a weapon, or acts on the world: the system only
observes and publishes numbers. Prototype scale: a yard, a toy drone or a thrown
ball.

## Demo model

1–2 Raspberry Pi camera nodes publish **detections** (no video) over MQTT to an
**EMQX cluster on Exoscale**. Validation, routing, storage and dashboards live in
the broker and infra, not in custom backend code.

```
[rpi-1] ─┐  MQTT/TLS 8883           ┌─ rule det_accept ─→ Postgres + detections/clean/{id}
[rpi-2] ─┴─────────────→ [EMQX] ────┼─ rule det_reject ─→ detections/rejected/{id}
 camera → detector → az/el          └─ rule status_sink ─→ Postgres ─→ Grafana
```

## Contract and topic map

Normative text: [`docs/contract.md`](docs/contract.md). Schemas: `docs/`.

| Topic | Direction | Payload |
|-------|-----------|---------|
| `nodes/{id}/detections` | node → broker, QoS 0 | `{"node","t","az","el","conf","frame"}` |
| `nodes/{id}/status` | node → broker, QoS 0, ≈1 Hz | `{"node","t","fps","temp_c","clock_offset_ms"}` |
| `detections/clean/{id}` | broker → subscribers | accepted detections, normalised |
| `detections/rejected/{id}` | broker → subscribers | rejected detections + `reason` |

One message per detection; several may share a `frame`. A change to a payload
updates `docs/contract.md`, `docs/`, `node/` and `infra/emqx/` in the same
commit.

## Where things live

| Path | What | Who edits |
|------|------|-----------|
| `node/` | RPi node software (Python 3.11+) | platform; see `node/AGENTS.md` |
| `node/src/edth_node/camera.py`, `detectors/` | frame source and detector | detector teammates |
| `infra/rpi/` | Podman quadlet, deploy script | platform |
| `infra/emqx/` | EMQX CRD, rules, authn/ACL | platform; see `infra/emqx/AGENTS.md` |
| `infra/grafana/`, `infra/sql/` | dashboards, Postgres schema | platform |
| `docs/` | contract and schemas | whoever changes the wire |
| `.github/workflows/node.yml` | build arm64 image, deploy to Pis | platform |

Each zone has its own `AGENTS.md`; work inside one zone per task.

## Rules

1. **Secrets stay out of git.** Passwords, tokens and keys live in gitignored files
   or secret stores, with a committed `*.example` beside them.
2. **Time.** `t` is Unix seconds (float), taken at frame capture on the node.
   Nodes must run NTP/chrony; `clock_offset_ms` in `status` exposes drift.
3. **Angles.** `az` is degrees clockwise from true north in [0, 360); `el` is
   degrees above the horizon in [-90, 90].
4. **Demo first.** A working end-to-end path beats completeness. Prefer simple,
   observable code.
5. **Python:** 3.11+, `uv`, `ruff`, `pytest`, `src/` layout.

## Git

- Conventional Commits, scope = zone: `feat(node): ...`, `fix(emqx): ...`.
- Short imperative subject. No body, or one short line of *why*.
- No `Co-Authored-By` or "Generated with ..." trailers.
- `main` must always be demoable. Small commits.

## Open questions

Written down, not decided. Confirm before building on them.

1. **Load balancer:** assumed L4 (TLS passthrough, certificate on EMQX). If it terminates TLS
   instead, mTLS is impossible and nothing else changes. Default: username/password per node.
2. **`az`/`el` frame and node pose.** Assumed: computed on the node from pixel, intrinsics and
   the configured mount heading/pitch/roll.
3. **`status` field names/units** are a proposal (`fps`, `temp_c`, `clock_offset_ms`); the last two
   are omitted when unavailable.
4. **Tailscale** on the Pis (CI reaches them through it); needs a Tailscale account.
5. **Camera:** USB (V4L2, default) or CSI (needs more device passthrough in the quadlet).
6. **EMQX version and licence.** Config is written for Operator 3.x / EMQX 6.x (tested on 6.3.2).
   6.x is free for **one node**; a multi-node cluster needs a licence key.
7. **Exoscale:** is DBaaS Postgres available in `bg-sof-1`? Real hostnames and the DNS name for the
   TLS certificate are placeholders in `infra/emqx/`.
8. **Project name:** repo history says "Triangulum", the brief says "M.I.G.E.T.".
9. **NTP egress** (UDP 123) from the Pis; without it `clock_offset_ms` is omitted.
10. **Online/offline signal:** retained LWT on `status`, and a schema `version` field.
11. **Untested on real hardware:** the Pi camera path, the Tailscale/SSH deploy and the Exoscale
    NLB. Everything else is covered by `node/tests` and `infra/emqx/test/run.sh`.
