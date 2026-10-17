import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

import deploy

PI = {"id": "rpi-1", "host": "pi@rpi-1.local", "env": {"NODE_HEADING_DEG": "90"}}
SHARED = {"MQTT_HOST": "mqtt.example.com", "MQTT_PORT": "8883", "MQTT_PASSWORD_RPI_1": "p'w d"}


def test_shipped_pis_json_is_valid():
    pis = deploy.load_pis(deploy.HERE / "pis.json")
    assert [p["id"] for p in pis] == ["rpi-1", "rpi-2"]


@pytest.mark.parametrize(
    "bad",
    [
        "[]",
        '[{"id": "RPI", "host": "h"}]',
        '[{"id": "a", "host": "-oProxyCommand=x"}]',
        '[{"id": "a", "host": "h"}, {"id": "a", "host": "g"}]',
        '[{"id": "a"}]',
    ],
)
def test_pis_json_validation(tmp_path, bad):
    path = tmp_path / "pis.json"
    path.write_text(bad)
    with pytest.raises(ValueError):
        deploy.load_pis(path)


def test_node_env_merges_and_never_contains_passwords():
    text = deploy.node_env(PI, SHARED)
    lines = dict(line.split("=", 1) for line in text.splitlines())
    assert lines["NODE_ID"] == "rpi-1" and lines["MQTT_USERNAME"] == "rpi-1"
    assert lines["NODE_HEADING_DEG"] == "90" and lines["MQTT_HOST"] == "mqtt.example.com"
    assert not any("PASSWORD" in k for k in lines)


def test_password_lookup():
    assert deploy.password_for("rpi-1", SHARED) == "p'w d"
    assert deploy.password_for("rpi-2", {"MQTT_PASSWORD": "x"}) == "x"
    assert deploy.password_for("rpi-2", SHARED) is None


def test_script_is_valid_sh():
    script = deploy.build_script(PI, SHARED, "sha-abc1234", "p'w d")
    subprocess.run(["sh", "-n"], input=script, text=True, check=True)


def stub(path: Path, body: str):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def fake_pi(tmp_path, monkeypatch):
    """A fake Pi: HOME in tmp, stub podman/systemctl/..., and an `ssh` that runs `sh -s` locally."""
    home, bin_ = tmp_path / "home", tmp_path / "bin"
    home.mkdir()
    bin_.mkdir()
    log = tmp_path / "calls.log"
    # podman reads stdin like the real one would; if the script is still on stdin it would eat it.
    stub(
        bin_ / "podman",
        f'echo "podman $*" >> {log}; [ "$1 $2" = "secret create" ] && '
        f'{{ echo "secret=$(cat)" >> {log}; exit 0; }}; cat >/dev/null; '
        '[ "$1 $2" = "image inspect" ] && echo sha256abcdef1234567890; exit 0',
    )
    for name in ("systemctl", "loginctl", "journalctl"):
        stub(bin_ / name, f'echo "{name} $*" >> {log}; exit 0')
    stub(bin_ / "sleep", "exit 0")
    stub(
        bin_ / "ssh",
        f'echo "ssh $*" >> {log}; while [ "${{1#-}}" != "$1" ]; do shift 2; done; '
        'shift; exec sh -c "$1"',
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", f"{bin_}:{os.environ['PATH']}")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    # Never let the generated script touch the real machine: every tool must resolve to a stub.
    for tool in ("ssh", "podman", "systemctl", "loginctl", "journalctl", "sleep"):
        assert shutil.which(tool) == str(bin_ / tool), tool
    assert os.path.expanduser("~") == str(home)
    return home, log, bin_


def test_full_deploy_against_a_fake_pi(fake_pi, tmp_path):
    home, log, bin_ = fake_pi
    pis = tmp_path / "pis.json"
    pis.write_text('[{"id": "rpi-1", "host": "pi@h", "env": {"NODE_HEADING_DEG": "90"}}]')
    deploy_env = tmp_path / "deploy.env"
    deploy_env.write_text("MQTT_HOST=mqtt.example.com\nMQTT_PASSWORD_RPI_1=p'w d\n")

    rc = deploy.main(["--tag", "sha-abc1234", "--pis", str(pis), "--env", str(deploy_env)])

    assert rc == 0
    calls = log.read_text()
    assert "secret=p'w d" in calls  # exact bytes, no trailing newline
    assert "podman pull ghcr.io/rangelovkiril/edth-node:sha-abc1234" in calls
    image = "ghcr.io/rangelovkiril/edth-node"
    assert f"podman tag {image}:sha-abc1234 {image}:latest" in calls
    assert "systemctl --user restart edth-node.service" in calls
    assert calls.index("podman pull") < calls.index("restart")  # the whole script ran, in order
    quadlet = home / ".config/containers/systemd/edth-node.container"
    assert "Secret=edth-mqtt-password" in quadlet.read_text()
    env_file = home / ".config/edth/node.env"
    assert "NODE_ID=rpi-1" in env_file.read_text() and "p'w d" not in env_file.read_text()
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


def test_failure_is_reported(fake_pi, tmp_path):
    home, log, bin_ = fake_pi
    stub(
        bin_ / "systemctl",
        'case "$*" in *is-active*) exit 3;; esac; exit 0',
    )
    pis = tmp_path / "pis.json"
    pis.write_text('[{"id": "rpi-1", "host": "pi@h"}]')
    deploy_env = tmp_path / "deploy.env"
    deploy_env.write_text("MQTT_HOST=h\nMQTT_PASSWORD=x\n")
    assert deploy.main(["--tag", "latest", "--pis", str(pis), "--env", str(deploy_env)]) == 1


def test_dry_run_hides_password_and_does_not_ssh(fake_pi, tmp_path, capsys):
    home, log, bin_ = fake_pi
    deploy_env = tmp_path / "deploy.env"
    deploy_env.write_text("MQTT_HOST=h\nMQTT_PASSWORD=hunter2\n")
    assert deploy.main(["--dry-run", "--tag", "latest", "--env", str(deploy_env)]) == 0
    out = capsys.readouterr().out
    assert "hunter2" not in out and "'***'" in out
    assert not log.exists()
