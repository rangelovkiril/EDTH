#!/usr/bin/env bash
# Run a Pi from your laptop over SSH. <host> is any name from ~/.ssh/config (no addresses in this repo).
#
#   deploy/pi.sh miget3 bootstrap rpi-2    first-time setup; nothing needs to be installed on the Pi
#   deploy/pi.sh miget3 logs               follow the node's log
#   deploy/pi.sh miget3 status             service state and the last log lines
#   deploy/pi.sh miget3 update             pull the newest image now instead of waiting a minute
#   deploy/pi.sh miget3 restart            after editing /etc/edth/node.env
#   deploy/pi.sh miget3 view               open the live camera view in a browser
#   deploy/pi.sh miget5 hub on|off|logs    run fusion (fixes to tracks) on this Pi as the hub
#   deploy/pi.sh miget3 set NODE_ROLL_DEG=90 STREAM_ROTATE=270     change settings, restart
#   SITE=42.6573,23.3549,560 deploy/pi.sh miget3 place 4.2 -1.8 1.1 heading=95 pitch=20
#                                          put the camera 4.2 m east, 1.8 m south and 1.1 m above
#                                          the site point (SITE: lat,lon,alt), aimed at 95° and 20° up
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
  set)
    [[ $# -ge 1 ]] || die "usage: pi.sh <host> set KEY=VALUE..."
    for kv in "$@"; do
      [[ $kv =~ ^[A-Z][A-Z0-9_]*=[^[:space:]\'\"]*$ ]] || die "not KEY=VALUE without spaces or quotes: $kv"
      [[ $kv =~ ^(MQTT_PASSWORD|VIDEO_TOKEN)= ]] && die "secrets are set by EDTH-infra/scripts, not here"
    done
    scp -q "$HERE/node-env-set.sh" "$host:edth-node-env-set.sh"
    ssh -t "$host" "sudo bash ~/edth-node-env-set.sh $*; rm -f ~/edth-node-env-set.sh"
    ;;
  place)
    [[ $# -ge 3 && -n ${SITE:-} ]] || die "usage: SITE=lat,lon,alt pi.sh <host> place EAST NORTH UP [heading=D] [pitch=D] [roll=D]"
    east=$1 north=$2 up=$3
    shift 3
    mapfile -t pos < <(python3 - "$SITE" "$east" "$north" "$up" <<'PY'
import math, sys
lat0, lon0, alt0 = (float(x) for x in sys.argv[1].split(","))
e, n, u = (float(x) for x in sys.argv[2:5])
m = math.pi / 180 * 6_371_000.0
print(f"NODE_LAT={lat0 + n / m:.7f}")
print(f"NODE_LON={lon0 + e / (m * math.cos(math.radians(lat0))):.7f}")
print(f"NODE_ALT_M={alt0 + u:.2f}")
PY
)
    extra=()
    for kv in "$@"; do
      case $kv in
        heading=*) extra+=("NODE_HEADING_DEG=${kv#*=}") ;;
        pitch=*) extra+=("NODE_PITCH_DEG=${kv#*=}") ;;
        roll=*) extra+=("NODE_ROLL_DEG=${kv#*=}") ;;
        *) die "unknown: $kv (heading=, pitch=, roll=)" ;;
      esac
    done
    exec "$0" "$host" set "${pos[@]}" "${extra[@]}"
    ;;
  hub)
    case ${1:-} in
      on)
        scp -q "$HERE/edth-fusion.container" "$host:"
        ssh -t "$host" 'sudo install -m 644 ~/edth-fusion.container /etc/containers/systemd/ && rm ~/edth-fusion.container \
          && sudo podman pull ghcr.io/rangelovkiril/edth-fusion:latest \
          && sudo systemctl daemon-reload && sudo systemctl restart edth-fusion \
          && systemctl --no-pager status edth-fusion | head -5'
        ;;
      off)
        ssh -t "$host" 'sudo systemctl stop edth-fusion; sudo rm -f /etc/containers/systemd/edth-fusion.container && sudo systemctl daemon-reload'
        ;;
      logs) exec ssh -t "$host" 'journalctl -u edth-fusion -f -o cat' ;;
      *) die "usage: pi.sh <host> hub on|off|logs" ;;
    esac
    ;;
  *) die "unknown command '$cmd' (bootstrap, logs, status, update, restart, view, set, place, hub)" ;;
esac
