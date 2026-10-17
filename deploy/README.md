# Deploying to a Raspberry Pi

Two things only, and nothing in between:

| Who | When | What |
|-----|------|------|
| **You**, `bootstrap.sh` | once per Pi | installs podman, writes this Pi's settings, installs the GitHub runner |
| **GitHub Actions**, `.github/workflows/node.yml` | every push to `main` | tests, builds the arm64 image, pulls it on the Pi, installs the quadlet, restarts, verifies |

There are no deploy scripts to run by hand. `git push` is the deploy.

```
git push ─→ test ─→ build arm64 image ─→ GHCR ─→ deploy job on the Pi's own runner
                                                   ├ podman pull ghcr.io/…/edth-node:sha-<7>
                                                   ├ install deploy/edth-node.container with that exact tag
                                                   ├ systemctl restart edth-node   (blocks until healthy)
                                                   └ check the running image and EDTH_VERSION == the pushed commit
```

The Pi is behind NAT and Actions cannot reach it, so the Pi pulls the work instead: the runner
dials out to GitHub. No inbound port, no SSH key, no VPN.

## Bootstrap

```sh
# on your machine: a registration token, valid for one hour
gh api -X POST repos/rangelovkiril/EDTH/actions/runners/registration-token --jq .token

# on the Pi (the script is in this folder)
sudo RUNNER_TOKEN=<token> NODE_ID=rpi-1 bash bootstrap.sh
# with a broker:   sudo RUNNER_TOKEN=… NODE_ID=rpi-1 MQTT_HOST=… MQTT_USERNAME=… MQTT_PASSWORD=… bash bootstrap.sh
```

Without `MQTT_HOST` the node runs in `DRY_RUN=1`: it uses the camera and detector and writes the
messages to its log instead of a broker. To go live later, edit `/etc/edth/node.env` and
`sudo systemctl restart edth-node`. Re-running the bootstrap is safe; it keeps an existing env
file unless `FORCE_ENV=1`.

What it sets up:

- `podman` (rootful; the quadlet generator is part of it) and a persistent journal.
- `/etc/edth/node.env`, mode 600: node id, camera settings, mount pose, broker. Never in git.
- user `ghrunner` with sudo for exactly `podman`, `systemctl`, `install` and `journalctl`, and the
  Actions runner as a systemd service that restarts itself and starts at boot, labelled `rpi-1`.

## What runs

`edth-node.container` is a rootful Podman quadlet in `/etc/containers/systemd/`:

- **Survives reboots.** The unit is wanted by `multi-user.target` and starts after the network is
  online; the image is already on the Pi, so no network is needed to start. `Restart=always` with no
  start limit.
- **Healthy means frames are flowing.** The node touches `/tmp/edth-alive` while it processes
  frames. If the camera hangs, the healthcheck fails, Podman kills the container, systemd starts it.
  `Notify=healthy` makes the deploy's `systemctl restart` wait for that first good check, so a
  broken build fails the Actions run instead of silently "deploying".
- **Camera.** `--privileged` and the host network: libcamera uses `/dev/media*`, `/dev/v4l-subdev*`
  and `/dev/dma_heap/*`, which renumber between boots. The image carries libcamera and picamera2 from
  Raspberry Pi's apt repo, the same one the host uses.

## Day to day

```sh
journalctl -u edth-node -f          # node logs, including event=start version=<commit>
systemctl status edth-node
sudo podman ps
journalctl -u 'actions.runner.*' -f # runner logs
```

- **Roll back:** re-run the `node` workflow for an older commit from the Actions tab (it deploys
  that commit's image).
- **Change a setting:** edit `/etc/edth/node.env`, then `sudo systemctl restart edth-node`.
- **Another Pi:** run the bootstrap there with its own `NODE_ID`, and add the id to `matrix.pi` in the
  workflow.

## Security notes

- The runner executes whatever the workflow says, as a user that can run `podman` as root, so it is
  effectively root on the Pi. Only pushes to `main` can reach the deploy job. In the repository
  settings (Actions → General) set *Fork pull request workflows* to require approval for all
  outside contributors, because this repository is public.
- Make the `edth-node` package public or leave it private: the deploy job logs in to GHCR with the
  workflow's own token either way.
