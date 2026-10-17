# M.I.G.E.T.

Passive, defensive sensing demo for EDTH Sofia 2026: Raspberry Pi camera nodes
report bearings (azimuth/elevation) to airborne objects over MQTT to an EMQX
cluster. No video leaves the node, and nothing is targeted or controlled.

Start with [`AGENTS.md`](AGENTS.md); the message contract is [`docs/contract.md`](docs/contract.md).

```sh
cd node
uv sync
uv run pytest
uv run python -m edth_node      # needs NODE_ID and MQTT_HOST, see node/AGENTS.md
```
