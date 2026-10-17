# Raspberry Pi node deployment

Rootless Podman + systemd quadlet. CI builds `ghcr.io/rangelovkiril/edth-node`
and deploys over SSH through Tailscale (the Pis are behind NAT).

| File | Goes to |
|------|---------|
| `edth-node.container` | `~/.config/containers/systemd/` |
| `edth-node.env.example` | `~/.config/edth/node.env` (edit, `chmod 600`) |
| `edth-deploy` | `/usr/local/bin/edth-deploy` (root-owned, `chmod 755`) |

## One-time setup on each Pi

```sh
sudo apt install podman chrony tailscale        # chrony: node timestamps need a synced clock
sudo loginctl enable-linger $USER               # start the user service at boot
sudo usermod -aG video $USER                    # camera access
sudo install -m 755 edth-deploy /usr/local/bin/edth-deploy

mkdir -p ~/.config/containers/systemd ~/.config/edth
cp edth-node.container ~/.config/containers/systemd/
install -m 600 edth-node.env.example ~/.config/edth/node.env   # then edit NODE_ID, MQTT_HOST, pose

printf '%s' 'the-mqtt-password' | podman secret create edth-mqtt-password -
podman login ghcr.io --authfile ~/.config/containers/auth.json   # classic PAT, read:packages
systemctl --user daemon-reload
systemctl --user start edth-node
journalctl --user -u edth-node -f
```

## CI deploy key

Generate a key per device and restrict it so it can only run the deploy script:

```sh
ssh-keygen -t ed25519 -N '' -f deploy_key -C "ci-deploy-rpi-1"
# ~/.ssh/authorized_keys on the Pi (one line); from= is the tailnet range:
restrict,from="100.64.0.0/10",command="/usr/local/bin/edth-deploy" ssh-ed25519 AAAA... ci-deploy-rpi-1
```

GitHub Environment `rpi-1` (and `rpi-2`) secrets:

| Secret | Value |
|--------|-------|
| `DEPLOY_SSH_KEY` | private key |
| `DEPLOY_KNOWN_HOSTS` | `ssh-keyscan -t ed25519 <tailnet-name>` output, verified out of band (no TOFU) |
| `DEPLOY_HOST` | tailnet name or IP of the Pi |
| `DEPLOY_USER` | the Linux user running the quadlet |

Repository secrets `TS_OAUTH_CLIENT_ID` and `TS_OAUTH_SECRET`: a Tailscale OAuth client
that may create `tag:ci` auth keys. Tailnet ACL, minimal:

```json
{
  "tagOwners": {"tag:ci": ["autogroup:admin"], "tag:rpi": ["autogroup:admin"]},
  "acls": [{"action": "accept", "src": ["tag:ci"], "dst": ["tag:rpi:22"]}]
}
```

Join each Pi with `sudo tailscale up --advertise-tags=tag:rpi`.

## Alternative without SSH

If Tailscale is not an option, set `AutoUpdate=registry` in the quadlet and enable
`podman-auto-update.timer` (user): the Pi polls GHCR itself. Slower, but needs no
inbound path and no deploy key.
