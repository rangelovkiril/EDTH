#!/usr/bin/env bash
# One-time setup of a Raspberry Pi as an EDTH node. Run as root, once per Pi:
#
#   sudo RUNNER_TOKEN=<token> NODE_ID=rpi-1 MQTT_HOST=... MQTT_PASSWORD=... bash bootstrap.sh
#
# After this the Pi needs no more manual steps: pushing to main makes GitHub Actions build the image
# and deploy it through the self-hosted runner installed here. Safe to re-run.
#
# Environment:
#   RUNNER_TOKEN    GitHub runner registration token (valid 1 h). Needed on the first run:
#                   gh api -X POST repos/OWNER/REPO/actions/runners/registration-token --jq .token
#   NODE_ID         name of this node and label of its runner (default: rpi-1)
#   MQTT_HOST       broker host; if empty the node runs with DRY_RUN=1 (prints, publishes nothing)
#   MQTT_PORT       default 8883
#   MQTT_TLS        default 1
#   MQTT_USERNAME   default: NODE_ID
#   MQTT_PASSWORD   written to /etc/edth/node.env (mode 600, root only)
#   FORCE_ENV=1     overwrite an existing /etc/edth/node.env
#   REPO            GitHub repository, default rangelovkiril/EDTH

set -euo pipefail

NODE_ID=${NODE_ID:-rpi-1}
REPO=${REPO:-rangelovkiril/EDTH}
RUNNER_USER=ghrunner
RUNNER_DIR=/opt/actions-runner
ENV_FILE=/etc/edth/node.env

log() { printf '\n== %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root: sudo bash $0"
[[ $(uname -m) == aarch64 ]] || die "this is for a 64-bit Raspberry Pi OS (aarch64), got $(uname -m)"
command -v apt-get >/dev/null || die "needs a Debian-based OS"
[[ $NODE_ID =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "NODE_ID must match [a-z0-9][a-z0-9_-]*"

log "Packages: podman"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends podman ca-certificates curl tar >/dev/null
[[ -x /usr/lib/systemd/system-generators/podman-system-generator ]] \
  || die "podman has no quadlet generator; need podman >= 4.4 (have $(podman --version))"
podman --version

log "Persistent journal, so logs survive a reboot"
install -d /var/log/journal /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/edth.conf <<'CONF'
[Journal]
Storage=persistent
SystemMaxUse=300M
CONF
systemctl restart systemd-journald

log "Camera access check"
ls /dev/dma_heap /dev/media0 >/dev/null 2>&1 || echo "warning: no camera/ISP device nodes found; is the CSI camera connected and enabled?"

log "Node configuration: $ENV_FILE"
install -d -m 755 /etc/edth /etc/containers/systemd
if [[ -e $ENV_FILE && ${FORCE_ENV:-0} != 1 ]]; then
  echo "exists, leaving it alone (FORCE_ENV=1 to rewrite)"
else
  umask 077
  {
    echo "# This machine's settings for the edth-node container. Not in git."
    echo "# After editing: systemctl restart edth-node"
    echo "NODE_ID=$NODE_ID"
    echo "CAMERA_DEVICE=csi"
    echo "CAMERA_WIDTH=1280"
    echo "CAMERA_HEIGHT=720"
    echo "CAMERA_FPS=30"
    echo "# Camera Module 3 Wide: 102 deg horizontal (Module 3 standard: 66). Calibrate later."
    echo "CAMERA_HFOV_DEG=102"
    echo "# Mount pose: heading clockwise from true north, pitch up, roll clockwise (degrees)."
    echo "NODE_HEADING_DEG=0"
    echo "NODE_PITCH_DEG=0"
    echo "NODE_ROLL_DEG=0"
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

log "Runner user and sudo rules"
id "$RUNNER_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash "$RUNNER_USER"
# The deploy job pulls the image, installs the quadlet, restarts the unit and reads logs.
cat > /etc/sudoers.d/$RUNNER_USER <<SUDO
$RUNNER_USER ALL=(root) NOPASSWD: /usr/bin/podman, /usr/bin/systemctl, /usr/bin/install, /usr/bin/journalctl
SUDO
chmod 440 /etc/sudoers.d/$RUNNER_USER
visudo -cf /etc/sudoers.d/$RUNNER_USER >/dev/null

log "GitHub Actions runner"
if [[ -f $RUNNER_DIR/.runner ]]; then
  echo "already configured, leaving it alone"
else
  [[ -n ${RUNNER_TOKEN:-} ]] || die "RUNNER_TOKEN is required on the first run"
  version=$(curl -fsSLI -o /dev/null -w '%{url_effective}' https://github.com/actions/runner/releases/latest)
  version=${version##*/v}
  echo "runner $version"
  install -d -o "$RUNNER_USER" -g "$RUNNER_USER" "$RUNNER_DIR"
  curl -fsSL "https://github.com/actions/runner/releases/download/v$version/actions-runner-linux-arm64-$version.tar.gz" \
    | tar -xz -C "$RUNNER_DIR"
  chown -R "$RUNNER_USER:$RUNNER_USER" "$RUNNER_DIR"
  # Avoids needing libicu on a minimal system.
  echo "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1" > "$RUNNER_DIR/.env"
  chown "$RUNNER_USER:$RUNNER_USER" "$RUNNER_DIR/.env"
  sudo -u "$RUNNER_USER" env DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 \
    "$RUNNER_DIR/config.sh" --unattended --replace \
    --url "https://github.com/$REPO" --token "$RUNNER_TOKEN" \
    --name "$NODE_ID" --labels "$NODE_ID" --work _work
  (cd "$RUNNER_DIR" && ./svc.sh install "$RUNNER_USER")
fi
# Restart the runner service whatever happens, and never stop trying.
runner_unit=$(cat "$RUNNER_DIR/.service")
install -d "/etc/systemd/system/$runner_unit.d"
cat > "/etc/systemd/system/$runner_unit.d/restart.conf" <<'CONF'
[Unit]
StartLimitIntervalSec=0

[Service]
Restart=always
RestartSec=10
CONF
systemctl daemon-reload
systemctl enable "$runner_unit" >/dev/null 2>&1
systemctl restart "$runner_unit"

log "Network must be up before the node starts (Wi-Fi)"
systemctl enable NetworkManager-wait-online.service >/dev/null 2>&1 || true

log "Done"
sleep 3
systemctl is-active "$runner_unit" | sed "s/^/runner service: /"
cat <<NEXT

The Pi is ready. The edth-node container is not installed yet: the first run of the deploy job
(push to main) installs the quadlet, pulls the image and starts it. From then on it starts at
every boot by itself.

  node config   $ENV_FILE
  node logs     journalctl -u edth-node -f
  runner logs   journalctl -u $runner_unit -f
NEXT
