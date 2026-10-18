"""Guards against drift between the node's config and the files under deploy/."""

import re
from pathlib import Path

from src.config import Config

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
CONFIG_SOURCE = (Path(__file__).resolve().parents[1] / "src" / "config.py").read_text()


def test_quadlet_healthcheck_watches_the_file_the_node_touches():
    quadlet = (DEPLOY / "edth-node.container").read_text()
    default = Config.from_env({"NODE_ID": "x", "DRY_RUN": "1"}).health_file
    assert re.search(r"^HealthCmd=.*" + re.escape(default), quadlet, re.M)
    assert "Notify=healthy" in quadlet and "HealthOnFailure=kill" in quadlet
    assert "Restart=always" in quadlet and "WantedBy=multi-user.target" in quadlet
    assert re.search(r"^Image=ghcr\.io/\S+:latest$", quadlet, re.M)  # what auto-update follows
    assert "AutoUpdate=registry" in quadlet
    assert "EnvironmentFile=/etc/edth/node.env" in quadlet


def test_every_key_bootstrap_writes_is_read_by_the_node():
    script = (DEPLOY / "bootstrap.sh").read_text()
    script = script.split("Node configuration")[1].split("Runner user")[0]
    written = set(re.findall(r'echo "([A-Z][A-Z0-9_]*)=', script))
    assert {"NODE_ID", "CAMERA_DEVICE", "CAMERA_WIDTH", "MQTT_HOST", "DRY_RUN"} <= written
    unknown = {key for key in written if f'"{key}"' not in CONFIG_SOURCE}
    assert not unknown, f"bootstrap.sh writes settings the node ignores: {unknown}"
