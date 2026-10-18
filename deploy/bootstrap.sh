#!/usr/bin/env bash
# One-time setup of a Raspberry Pi as an EDTH node. Run as root from a checkout of this repo:
#
#   sudo NODE_ID=rpi-1 MQTT_HOST=... MQTT_USERNAME=... MQTT_PASSWORD=... bash deploy/bootstrap.sh
#
# After this the Pi updates itself: every push to main makes GitHub Actions build and push the
# image, and the Pi's podman-auto-update timer picks it up within a minute. Safe to re-run; re-run it
# after `git pull` to apply a changed quadlet.
#
# Environment:
#   NODE_ID         name of this node (default: rpi-1)
#   MQTT_HOST       broker host; if empty the node runs with DRY_RUN=1 (prints, publishes nothing)
#   MQTT_PORT       default 8883
#   MQTT_TLS        default 1
#   MQTT_USERNAME   default: NODE_ID
#   MQTT_PASSWORD   written to /etc/edth/node.env (mode 600, root only)
#   CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS   default 1280 x 720 at 30; lower them on a Pi 3
#   FORCE_ENV=1     overwrite an existing /etc/edth/node.env
#   GHCR_USER, GHCR_TOKEN   only if the image package is private: a token with read:packages

set -euo pipefail

NODE_ID=${NODE_ID:-rpi-1}
HERE=$(dirname "$(readlink -f "$0")")
ENV_FILE=/etc/edth/node.env

log() { printf '\n== %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root: sudo bash $0"
[[ $(uname -m) == aarch64 ]] || die "this is for a 64-bit Raspberry Pi OS (aarch64), got $(uname -m)"
command -v apt-get >/dev/null || die "needs a Debian-based OS"
[[ $NODE_ID =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "NODE_ID must match [a-z0-9][a-z0-9_-]*"
[[ -f $HERE/edth-node.container ]] || die "run it from a checkout of the repo: edth-node.container is missing"

log "Podman"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends podman ca-certificates >/dev/null
[[ -x /usr/lib/systemd/system-generators/podman-system-generator ]] \
  || die "podman has no quadlet generator; need podman >= 4.4 (have $(podman --version))"
podman --version

log "Persistent journal, so logs survive a reboot"
install -d /var/log/journal /etc/systemd/journald.conf.d
printf '[Journal]\nStorage=persistent\nSystemMaxUse=300M\n' > /etc/systemd/journald.conf.d/edth.conf
systemctl restart systemd-journald

log "Camera devices"
ls /dev/dma_heap /dev/media0 >/dev/null 2>&1 || echo "warning: no camera/ISP device nodes; is the CSI camera connected?"

log "Node configuration: $ENV_FILE"
install -d -m 755 /etc/edth
if [[ -e $ENV_FILE && ${FORCE_ENV:-0} != 1 ]]; then
  echo "exists, leaving it alone (FORCE_ENV=1 to rewrite)"
else
  umask 077
  {
    echo "# This machine's settings for the edth-node container. Not in git."
    echo "# After editing: systemctl restart edth-node"
    echo "NODE_ID=$NODE_ID"
    echo "CAMERA_DEVICE=csi"
    echo "CAMERA_WIDTH=${CAMERA_WIDTH:-1280}"
    echo "CAMERA_HEIGHT=${CAMERA_HEIGHT:-720}"
    echo "CAMERA_FPS=${CAMERA_FPS:-30}"
    echo "# Field of view is read from the camera (Module v1/v2/3/3 Wide). Uncomment to override,"
    echo "# e.g. for an HQ camera or after a calibration:"
    echo "# CAMERA_HFOV_DEG=62.2"
    echo "# Mount pose: heading clockwise from true north, pitch up, roll clockwise (degrees)."
    echo "NODE_HEADING_DEG=0"
    echo "NODE_PITCH_DEG=0"
    echo "NODE_ROLL_DEG=0"
    echo "# Live camera view for demos on the local network (no password!): http://<pi>:8080/"
    echo "# Remove the next line to turn it off. STREAM_ROTATE turns the picture (0, 90, 180, 270)."
    echo "STREAM_PORT=8080"
    echo "STREAM_ROTATE=0"
    if [[ -n ${MQTT_HOST:-} ]]; then
      echo "MQTT_HOST=$MQTT_HOST"
      echo "MQTT_PORT=${MQTT_PORT:-8883}"
      echo "MQTT_TLS=${MQTT_TLS:-1}"
      echo "MQTT_USERNAME=${MQTT_USERNAME:-$NODE_ID}"
      echo "MQTT_PASSWORD=${MQTT_PASSWORD:-}"
    else
      echo "# No broker configured: print detections instead of publishing them."
      echo "# Set MQTT_HOST, MQTT_USERNAME, MQTT_PASSWORD and remove DRY_RUN to go live."
      echo "DRY_RUN=1"
    fi
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "written"
fi

if [[ -n ${GHCR_TOKEN:-} ]]; then
  log "Registry login (private package)"
  printf '%s' "$GHCR_TOKEN" | podman login ghcr.io -u "${GHCR_USER:?set GHCR_USER too}" --password-stdin \
    --authfile /root/.config/containers/auth.json
fi

log "Quadlet and the update timer"
install -d /etc/containers/systemd /etc/systemd/system/podman-auto-update.timer.d
install -m 644 "$HERE/edth-node.container" /etc/containers/systemd/edth-node.container
printf '[Timer]\nOnCalendar=\nOnCalendar=minutely\nRandomizedDelaySec=0\n' \
  > /etc/systemd/system/podman-auto-update.timer.d/edth.conf
# Wi-Fi: wait for the network before starting anything that needs it.
systemctl enable NetworkManager-wait-online.service >/dev/null 2>&1 || true
systemctl daemon-reload
systemctl enable --now podman-auto-update.timer

log "Starting the node (the first start pulls the image, which can take a few minutes)"
systemctl start edth-node.service

log "Done"
systemctl is-active edth-node.service | sed 's/^/edth-node: /'
cat <<NEXT

  node config   $ENV_FILE        (then: sudo systemctl restart edth-node)
  node logs     journalctl -u edth-node -f
  updates       journalctl -u podman-auto-update -f
NEXT
