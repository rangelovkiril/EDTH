# infra/ — gateway provisioning and operations

## Purpose
Turn a fresh Raspberry Pi into the gateway with one command, and keep the
whole system observable during the demo. Owner: DevOps.

The gateway provides: Wi-Fi AP for sensors, chrony time master, mosquitto,
`tr-ingest`, `tr-tsyncd`, `tr-pi-node@<id>`, firewall, Ethernet uplink.

## Layout
```
gateway/
  chrony.conf  mosquitto.conf  nftables.conf
  systemd/  tr-ingest.service  tr-tsyncd.service  tr-pi-node@.service
  ap.secrets.example          # TR_SSID / TR_PSK, real file gitignored
ansible/                      # to create
  inventory.ini  site.yml
  roles/ base  ap  chrony  mosquitto  firewall  triangulum
```

## Target platform
- Raspberry Pi OS Bookworm Lite 64-bit (Python 3.11, NetworkManager).
- Code deployed to `/opt/triangulum` (rsync or git checkout), venv via
  `uv venv --system-site-packages` (picamera2 is apt-only), `uv sync`.
- Services run as user `triangulum` (groups: `video`), state in
  `/var/lib/triangulum` (recordings).

## AP (NetworkManager)
```sh
nmcli con add type wifi ifname wlan0 con-name tr-ap autoconnect yes ssid "$TR_SSID" \
  802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 \
  802-11-wireless.powersave 2 \
  ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv6.method disabled \
  wifi-sec.key-mgmt sae wifi-sec.psk "$TR_PSK" wifi-sec.pmf required
```
- Pick the channel after `nmcli dev wifi list` / `iw dev wlan0 scan` at the venue.
- If SAE in AP mode fails on the Pi's Wi-Fi chip: `key-mgmt wpa-psk`, keep
  `pmf required`. Write down which one works.
- `eth0`: static `10.43.0.1/24`, no gateway. Laptop: `10.43.0.2/24`.

## Rules
- **Idempotent.** Running the playbook twice changes nothing the second time.
- Everything on the Pi comes from this directory. No hand edits on the device
  that are not reflected here within the hour.
- Secrets only from gitignored files / Ansible vault.
- During the event: disable apt timers and unattended-upgrades; keep a
  **golden SD image** and a spare card; know the reflash time.
- Firewall per `docs/network.md`: drop everything not listed.

## Observability
- Node health = `tr/v1/status/+` and `tr/v1/ingest/stats` (retained). `trctl`
  (in `tools/`) is the primary live view.
- `journalctl -u 'tr-*' -f` for services; `chronyc clients` / `chronyc tracking`
  for time.
- Optional (P3): Grafana on the laptop (Podman compose) fed from MQTT.

## Done criteria
- Fresh SD card → `ansible-playbook site.yml` → ESP nodes connect, time syncs,
  services up after reboot, without manual steps.
- Reflash procedure and time measured and written here.
