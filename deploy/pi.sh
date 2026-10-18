#!/usr/bin/env bash
# Run a Pi from your laptop over SSH. <host> is any name from ~/.ssh/config (no addresses in this repo).
#
#   deploy/pi.sh miget3 bootstrap rpi-2    first-time setup; nothing needs to be installed on the Pi
#   deploy/pi.sh miget3 logs               follow the node's log
#   deploy/pi.sh miget3 status             service state and the last log lines
#   deploy/pi.sh miget3 update             pull the newest image now instead of waiting a minute
#   deploy/pi.sh miget3 restart            after editing /etc/edth/node.env
#   deploy/pi.sh miget3 view               open the live camera view in a browser
#
# `bootstrap`, `update` and `restart` use sudo on the Pi and ask for its password here (ssh -t).
# `bootstrap` passes on whichever of these are set in your shell: MQTT_HOST MQTT_PORT MQTT_TLS
# MQTT_USERNAME MQTT_PASSWORD CAMERA_WIDTH CAMERA_HEIGHT CAMERA_FPS GHCR_USER GHCR_TOKEN FORCE_ENV.
# They travel in a mode-600 temporary file, not on a command line, and are deleted afterwards.

set -euo pipefail

HERE=$(dirname "$(readlink -f "$0")")
PASS_THROUGH=(MQTT_HOST MQTT_PORT MQTT_TLS MQTT_USERNAME MQTT_PASSWORD
  CAMERA_WIDTH CAMERA_HEIGHT CAMERA_FPS GHCR_USER GHCR_TOKEN FORCE_ENV)

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
[[ $# -ge 2 ]] || { sed -n '2,/^$/{s/^# \{0,1\}//;p}' "$0"; exit 2; }
host=$1 cmd=$2
shift 2

case $cmd in
  bootstrap)
    node_id=${1:?usage: pi.sh <host> bootstrap <node-id>}
    local_env=$(mktemp)
    trap 'rm -f "$local_env"' EXIT
    printf 'NODE_ID=%q\n' "$node_id" > "$local_env"
    for name in "${PASS_THROUGH[@]}"; do
      [[ -n ${!name:-} ]] && printf '%s=%q\n' "$name" "${!name}" >> "$local_env"
    done
    ssh "$host" 'rm -rf ~/edth-deploy && mkdir -p ~/edth-deploy && umask 077 && : > ~/edth-deploy/.env'
    scp -q "$HERE/bootstrap.sh" "$HERE/edth-node.container" "$host:edth-deploy/"
    scp -q "$local_env" "$host:edth-deploy/.env"
    ssh -t "$host" 'sudo bash -c "set -a; . ~/edth-deploy/.env; set +a; bash ~/edth-deploy/bootstrap.sh"; rm -rf ~/edth-deploy'
    ;;
  logs) exec ssh -t "$host" 'journalctl -u edth-node -f -o cat' ;;
  status) ssh "$host" 'systemctl --no-pager status edth-node | head -12; journalctl -u edth-node -n 15 --no-pager -o cat' ;;
  update) exec ssh -t "$host" 'sudo systemctl start podman-auto-update && journalctl -u podman-auto-update -n 8 --no-pager -o cat' ;;
  restart) exec ssh -t "$host" 'sudo systemctl restart edth-node' ;;
  view)
    address=$(ssh -G "$host" | awk '$1 == "hostname" {print $2}')
    url=http://$address:8080/
    echo "$url"
    command -v xdg-open >/dev/null && xdg-open "$url" || true
    ;;
  *) die "unknown command '$cmd' (bootstrap, logs, status, update, restart, view)" ;;
esac
