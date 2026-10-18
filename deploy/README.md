# Deploying to a Raspberry Pi

`git push` is the deploy. The Pi is on a private network that GitHub cannot reach, so the Pi pulls:

```
git push ─→ GitHub Actions: test, build arm64 image, push ghcr.io/rangelovkiril/edth-node:latest
                                                            │
Pi: podman-auto-update.timer (every minute) ── sees a new :latest ─→ pulls it, restarts edth-node
                                                   └ if the new container is not healthy: rolls back
```

No runner, no SSH key, no open port. Setup is one command, once per Pi.

## Bootstrap

From your laptop, for any Pi that is in `~/.ssh/config` (nothing but SSH has to exist on the Pi; this
repo holds no addresses):

```sh
deploy/pi.sh miget3 bootstrap rpi-2                                   # prints, no broker
MQTT_HOST=… MQTT_USERNAME=… MQTT_PASSWORD=… deploy/pi.sh miget3 bootstrap rpi-2
deploy/pi.sh miget3 logs | status | update | restart | view          # day to day
```

It asks for the Pi's sudo password. `CAMERA_WIDTH`, `CAMERA_HEIGHT`, `CAMERA_FPS` in your shell are
passed on (lower them on a Pi 3). Or, on the Pi itself, from a checkout of this repository:

```sh
git clone https://github.com/rangelovkiril/EDTH && cd EDTH
sudo NODE_ID=rpi-1 bash deploy/bootstrap.sh                       # camera + detector, prints, no broker
sudo NODE_ID=rpi-1 MQTT_HOST=… MQTT_USERNAME=… MQTT_PASSWORD=… bash deploy/bootstrap.sh   # with a broker
```

It installs podman, writes `/etc/edth/node.env` (mode 600; never in git), installs the quadlet
`edth-node.container`, switches the auto-update timer to every minute and starts the node. The
first start pulls the image, which takes a few minutes over Wi-Fi. Re-run it after `git pull` to apply a
changed quadlet; an existing env file is kept unless `FORCE_ENV=1`.

Without `MQTT_HOST` the node runs with `DRY_RUN=1`. To go live later, edit `/etc/edth/node.env` and
`sudo systemctl restart edth-node`.

If the image package is private, either make it public (GitHub → Packages → `edth-node` → settings) or
pass `GHCR_USER` and `GHCR_TOKEN` (a token with `read:packages`) to the bootstrap.

## What the quadlet gives you

- **Survives reboots.** Wanted by `multi-user.target`, starts once the network is online, and the
  image is already local so no network is needed. `Restart=always`, no start limit.
- **Healthy means frames are flowing.** The node touches `/tmp/edth-alive` while it processes frames. A
  hung camera fails the healthcheck, Podman kills the container, systemd restarts it. This is also how
  auto-update tells a working new image from a broken one.
- **Camera.** `--privileged` and the host network: libcamera uses `/dev/media*`, `/dev/v4l-subdev*` and
  `/dev/dma_heap/*`, which renumber between boots. The image carries libcamera and picamera2 from
  Raspberry Pi's apt repo, the same one the host uses.

## Day to day

```sh
journalctl -u edth-node -f                  # node logs; event=start shows version=<commit>
systemctl status edth-node
journalctl -u podman-auto-update -f         # update checks
sudo systemctl start podman-auto-update     # don't wait for the minute
sudo podman ps
```

- **What is running:** `sudo podman inspect edth-node --format '{{.Config.Labels}}'` includes the
  commit (`org.opencontainers.image.revision`).
- **Roll back:** revert the commit and push; the Pi follows. To stop updates while you test by hand:
  `sudo systemctl disable --now podman-auto-update.timer`.
- **Another Pi:** `deploy/pi.sh <host> bootstrap <its own NODE_ID>`. The camera model needs no setting:
  the node reads it and logs `event=camera sensor=… hfov_deg=… source=sensor`. Only mount pose
  (`NODE_HEADING_DEG`, …) is per Pi, in its `/etc/edth/node.env`.

## Why not deploy over SSH from Actions?

GitHub-hosted runners come from the public internet, and a Pi on a hotspot or LAN has no address
they can reach. The options are a VPN/tunnel on every Pi or a self-hosted runner, and both add a
moving part (and a root-equivalent agent) for no benefit here. The pull model needs nothing but outbound
internet. The deploy keys stored as repository secrets (`RPI1_SSH_KEY`, `RPI2_SSH_KEY`) are not used.

## The hub

One Pi can also run fusion (the thin tracker from fixes to tracks) next to its camera, as the node the
others' fixes come together on:

```sh
deploy/pi.sh miget5 hub on      # installs edth-fusion.container, pulls the image, starts it
deploy/pi.sh miget5 hub logs
deploy/pi.sh miget5 hub off
```

It uses the same broker settings as the node (`/etc/edth/node.env`) with client id `fusion-<hostname>`,
and updates itself like the node. Run fusion in one place only (scale the cluster's `miget/fusion` to
0 while a hub runs), or tracks are published twice.

## Where a camera is and where it looks

Triangulation needs each camera's position and aim. Positions only have to be right **relative to
each other**, so measure them from one point on the site (a floor marking, a corner) in metres and let
`place` turn that into coordinates; `SITE` is that point's `lat,lon,alt` (read it off a satellite map):

```sh
export SITE=42.6573,23.3549,560
deploy/pi.sh miget5 place 0 0 1.2 heading=0 pitch=30            # at the site point, 1.2 m up
deploy/pi.sh miget3 place 6.5 0 1.2 heading=350 pitch=30 roll=90 # 6.5 m east of it, mounted sideways
deploy/pi.sh miget5 set STREAM_ROTATE=270                        # any other non-secret setting
```

`heading` is where the camera looks, clockwise from true north; `pitch` up from level; `roll` if the
camera is turned on its side (the picture shows it: rotate the view with `STREAM_ROTATE`, and set
`roll` so the bearings are right). Both restart the node. Secrets are set by EDTH-infra's scripts
(`mqtt-node-user.sh`, `video-token.sh`).
