# M.I.G.E.T.

Passive, defensive sensing demo for EDTH Sofia 2026: Raspberry Pi camera nodes report bearings
(azimuth/elevation) to airborne objects over MQTT. No video leaves the node, and nothing is
targeted or controlled. The broker and infrastructure live in the `EDTH-infra` repo.

Try it without a camera or a broker:

```sh
cd node
uv sync
uv run pytest
NODE_ID=rpi-1 DRY_RUN=1 CAMERA_DEVICE=/path/to/video.mp4 uv run python -m edth_node
```

Start with [`AGENTS.md`](AGENTS.md); detector authors continue in [`node/AGENTS.md`](node/AGENTS.md).
The message contract is [`docs/contract.md`](docs/contract.md).
