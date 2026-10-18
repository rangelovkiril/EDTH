# fusion — the thin ground side: fixes to tracks

The nodes have already crossed their bearings into 3D points (`fixes`), and the broker has
validated them (see [`../docs/contract.md`](../docs/contract.md), "Who computes what"). All this
service does is decide which fixes are the same object and smooth them: nearest-neighbour
association and a constant-velocity Kalman filter per track. Out comes `fusion/tracks` with a
position, a velocity, a prediction `HORIZON_S` ahead, its uncertainty and a confidence.

Passive: it only reads numbers and publishes numbers.

## Quick start

```sh
cd fusion
uv sync
uv run pytest
```

With a broker that runs the rules (EDTH-infra `apps/emqx`), simulated nodes from `../node` and
this service make the whole chain:

```sh
(cd ../node && MQTT_HOST=… MQTT_USERNAME=… MQTT_PASSWORD=… uv run python -m src.sim)
MQTT_HOST=… MQTT_USERNAME=… MQTT_PASSWORD=… uv run python -m src
```

## Files

| File | What |
|------|------|
| `src/tracker.py` | association, Kalman filter, confidence; no I/O |
| `src/geo.py` | lat/lon/alt ↔ local east-north-up around the origin |
| `src/__main__.py`, `transport.py`, `config.py` | MQTT (or stdio with `DRY_RUN=1`), main loop, settings |

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `MQTT_HOST`, `MQTT_PORT`, `MQTT_TLS`, `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_CA_FILE` | –, `8883`, `1` | as on the node |
| `MQTT_CLIENT_ID` | `fusion` | |
| `DRY_RUN` | `0` | read `fixes/…` lines from stdin, print tracks |
| `ORIGIN` | first fix | `lat,lon,alt_m` for the `e`/`n`/`u` fields |
| `RATE_HZ` | `10` | tracks published per second |
| `GATE_M` | `4` | a fix this close to a track's prediction belongs to it |
| `CONFIRM_HITS` | `3` | fixes before a track is published |
| `TRACK_TIMEOUT_S` | `2` | drop a track with no fixes for this long |
| `FIX_SIGMA_M` | `0.3` | a fix's error on top of half its `miss_m` |
| `ACCEL_MPS2` | `4` | how hard a target may manoeuvre (process noise) |
| `HORIZON_S` | `1` | how far ahead the prediction looks |
| `CONF_SIGMA_M` | `2` | position uncertainty at which confidence falls to 1/e |

## Before you push

```sh
uv run ruff check . && uv run ruff format . && uv run pytest
```

Pushing to `main` builds `ghcr.io/rangelovkiril/edth-fusion` (amd64 and arm64).
