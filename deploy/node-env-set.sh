#!/usr/bin/env bash
# Run on the Pi as root by `deploy/pi.sh <host> set|place`: replace KEY=VALUE lines in node.env (an
# empty VALUE removes the key) and restart what reads it.
set -euo pipefail
ENV_FILE=/etc/edth/node.env
for kv in "$@"; do
  key=${kv%%=*}
  sed -i "/^${key}=/d" "$ENV_FILE"
  [[ -n ${kv#*=} ]] && printf '%s\n' "$kv" >> "$ENV_FILE"
done
systemctl restart edth-node
if systemctl is-active --quiet edth-fusion; then systemctl restart edth-fusion; fi
grep -E '^(NODE_|TRI_|STREAM_|VIDEO_PUSH|MQTT_HOST)' "$ENV_FILE" || true
