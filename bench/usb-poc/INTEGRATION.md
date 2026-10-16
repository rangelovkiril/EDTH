# EDTH integration boundary

This directory is a self-contained **USB camera bench**, added alongside the
existing service scaffold. All integration changes are confined to this bench.
It provides a working local hardware demo while gateway/ingest, the ESP-IDF nodes,
and the ground services are developed independently.

## Run

```sh
cd bench/usb-poc
uv sync
uv run skywatch                         # synthetic-image bench
cp config/live.example.json config/live.json
# Edit camera device paths, then:
uv run skywatch --config config/live.json
```

Dashboard: http://127.0.0.1:8000. The Python package uses `src/` layout, bundles its
static assets, and has an independent uv workspace and lockfile. The root uv
workspace and its entry points remain intact. `./run.sh` is a pip/venv fallback.

## Contract boundaries

- This is not the repository's `tr-sim`, `tr-calib`, or `trctl` implementation.
- USB `SKYCAM01`/`SKYTIME2` framing exists entirely between the firmware and host
  adapter in this bench. It is **not** `trwire` v1, `TSYNC`, UDP ingest, or MQTT.
  It is never sent to EDTH ports or topics. The normative wire layout and vectors
  are unchanged.
- Camera capture clocks are mapped to the local host's monotonic clock. This
  does not establish synchronization with the gateway timescale, and the bench
  never claims the EDTH `TIME_SYNCED` flag or the 2 ms node-to-node requirement.
- Stereo calibration and voxel visualization use an explicitly local optical
  frame: x right, y down, z forward. These are not ENU positions and are never
  exported as EDTH tracks. The generic bench geometry is not an implementation
  of the site's yaw/pitch/roll-to-ENU transform.
- Events use host wall-clock time for local display only; they are not EDTH
  timestamped detection records. CSV is a UI event log, not the normative raw
  datagram recording format.
- The Arduino USB sketch is a bench firmware image. It does not replace or
  implement `firmware/esp-node/`'s ESP-IDF/Wi-Fi/detection-on-node design.
- Outputs are unclassified motion candidates. No affiliation assignment,
  tactical track publishing, CoT, or ATAK behavior is implemented here.

## Follow-up work by the owning zones

These are interface gaps, not completed integrations:

1. Firmware: implement the ESP-IDF capture/detection path using `trwire.h` and
   gateway time, then validate it against existing protocol vectors.
2. Fusion: implement and validate the shared ENU geometry from the architecture
   contract. Do not treat this bench's camera-local coordinates as ENU.
3. Tools: once shared geometry is available, use it for the repository's
   simulator and site-calibration workflow. Keep raw-recording replay semantics.
4. Ingest/observability: expose real node health for the production dashboard;
   the bench currently monitors its own local capture processes only.

The original standalone working directory and original firmware backups remain
outside this repository. No physical camera images, serial-specific config,
firmware backups, downloaded SDKs, or credentials are committed.
