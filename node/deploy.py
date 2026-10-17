#!/usr/bin/env python3
"""Deploy the node container to the Raspberry Pis listed in pis.json, over SSH.

For each Pi it installs the quadlet, writes the env file and the MQTT secret, pulls the image and
restarts the service. Needs on the Pi: podman, systemd, and an SSH login that works without a
password prompt. Settings and passwords come from the gitignored deploy.env.

  ./deploy.py                  deploy the image CI built for the current commit (sha-<7>)
  ./deploy.py --tag latest     or any other tag
  ./deploy.py --only rpi-1     a single Pi
  ./deploy.py --dry-run        print what would run, with passwords hidden
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMAGE = "ghcr.io/rangelovkiril/edth-node"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
HOST_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.@:%-]*$")
TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")


def load_pis(path: Path) -> list[dict]:
    pis = json.loads(path.read_text())
    if not isinstance(pis, list) or not pis:
        raise ValueError(f"{path.name} must be a non-empty JSON array")
    seen = set()
    for pi in pis:
        if not ID_RE.match(str(pi.get("id", ""))):
            raise ValueError(f"bad id in {pi!r}: use lowercase letters, digits, '-' and '_'")
        if not HOST_RE.match(str(pi.get("host", ""))):
            raise ValueError(f"bad host in {pi!r}")
        if pi["id"] in seen:
            raise ValueError(f"duplicate id {pi['id']}")
        seen.add(pi["id"])
        pi.setdefault("env", {})
    return pis


def load_env(path: Path) -> dict[str, str]:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, sep, value = line.partition("=")
            if not sep:
                raise ValueError(f"{path.name}: expected KEY=VALUE, got {line!r}")
            env[key.strip()] = value.strip()
    return env


def password_for(pi_id: str, env: dict[str, str]) -> str | None:
    return env.get("MQTT_PASSWORD_" + pi_id.upper().replace("-", "_")) or env.get("MQTT_PASSWORD")


def node_env(pi: dict, shared: dict[str, str]) -> str:
    merged = {k: v for k, v in shared.items() if not k.startswith("MQTT_PASSWORD")}
    merged.setdefault("MQTT_USERNAME", pi["id"])
    merged.update({k: str(v) for k, v in pi["env"].items()})
    merged["NODE_ID"] = pi["id"]
    for key, value in merged.items():
        if "\n" in value or not re.match(r"^[A-Z][A-Z0-9_]*$", key):
            raise ValueError(f"bad env entry {key!r} for {pi['id']}")
    return "".join(f"{k}={v}\n" for k, v in sorted(merged.items()))


def build_script(pi: dict, shared: dict[str, str], tag: str, password: str | None) -> str:
    """POSIX sh for one Pi. Wrapped in a function so sh has parsed all of it before anything runs,
    and stdin is then detached so podman/systemctl cannot swallow the rest of the script."""
    quadlet = (HERE / "edth-node.container").read_text()
    secret = (
        "podman secret rm edth-mqtt-password >/dev/null 2>&1 || true\n"
        f"printf %s {shlex.quote(password)} | podman secret create edth-mqtt-password - >/dev/null"
        if password
        else "echo 'no MQTT password configured: keeping the existing secret' >&2; "
        "podman secret exists edth-mqtt-password"
    )
    return f"""main() {{
exec </dev/null
set -eu
command -v podman >/dev/null || {{ echo 'podman is missing: sudo apt install -y podman' >&2; exit 10; }}
export XDG_RUNTIME_DIR="${{XDG_RUNTIME_DIR:-/run/user/$(id -u)}}"
export DBUS_SESSION_BUS_ADDRESS="${{DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}}"
loginctl enable-linger "$(id -un)" 2>/dev/null || echo "warn: run once: sudo loginctl enable-linger $(id -un)" >&2
mkdir -p "$HOME/.config/containers/systemd" "$HOME/.config/edth"
cat > "$HOME/.config/containers/systemd/edth-node.container" <<'EDTH_QUADLET'
{quadlet}EDTH_QUADLET
umask 077
cat > "$HOME/.config/edth/node.env" <<'EDTH_ENV'
{node_env(pi, shared)}EDTH_ENV
{secret}
systemctl --user daemon-reload
podman pull {shlex.quote(f"{IMAGE}:{tag}")}
podman tag {shlex.quote(f"{IMAGE}:{tag}")} {IMAGE}:latest
systemctl --user restart edth-node.service
sleep 6
if ! systemctl --user is-active --quiet edth-node.service; then
  journalctl --user -u edth-node.service -n 30 --no-pager >&2 || true
  exit 1
fi
echo "running $(podman image inspect --format '{{{{.Id}}}}' {shlex.quote(f"{IMAGE}:{tag}")} | cut -c1-12) as {pi["id"]}"
}}
main
"""


def current_tag() -> str:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, check=True
    ).stdout.strip()
    return f"sha-{sha[:7]}"


def deploy_one(pi: dict, script: str) -> bool:
    cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
        "-o", "StrictHostKeyChecking=accept-new", pi["host"], "sh -s",
    ]  # fmt: skip
    return subprocess.run(cmd, input=script, text=True).returncode == 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--tag", help="image tag (default: sha-<7> of HEAD)")
    ap.add_argument("--only", nargs="+", metavar="ID", help="deploy only these Pi ids")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pis", type=Path, default=HERE / "pis.json")
    ap.add_argument("--env", type=Path, default=HERE / "deploy.env")
    args = ap.parse_args(argv)

    pis = load_pis(args.pis)
    if args.only:
        unknown = set(args.only) - {p["id"] for p in pis}
        if unknown:
            ap.error(f"unknown id(s): {', '.join(sorted(unknown))}")
        pis = [p for p in pis if p["id"] in args.only]
    shared = load_env(args.env)
    if "MQTT_HOST" not in shared:
        ap.error(f"MQTT_HOST missing: copy deploy.env.example to {args.env.name} and edit it")
    tag = args.tag or current_tag()
    if not TAG_RE.match(tag):
        ap.error(f"bad tag {tag!r}")

    failed = []
    for pi in pis:
        password = password_for(pi["id"], shared)
        print(f"== {pi['id']} ({pi['host']}) <- {IMAGE}:{tag}", flush=True)
        if args.dry_run:
            shown = build_script(pi, shared, tag, "***" if password else None)
            print(shown)
        elif not deploy_one(pi, build_script(pi, shared, tag, password)):
            failed.append(pi["id"])
            print(f"!! {pi['id']} failed", file=sys.stderr)
    if failed:
        print(f"failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
