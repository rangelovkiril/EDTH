# Triangulum

Passive multi-camera drone detection and triangulation prototype — EDTH Sofia 2026.

Start with [`AGENTS.md`](AGENTS.md) and [`docs/architecture.md`](docs/architecture.md).
The wire/MQTT contract is [`docs/protocol.md`](docs/protocol.md).

```sh
uv sync                      # Python workspace (ground/tools/protocol)
uv run pytest protocol/python
```
