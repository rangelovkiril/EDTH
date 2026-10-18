"""Simulated nodes: N cameras on a line watching targets fly circles, run from a laptop.

Each simulated node publishes what a real node would (status, detections with its position) and
triangulates against its peers with the real Triangulator. Peer rays come from the broker's
`rays/+` like on a Pi; with DRY_RUN=1 there is no broker, so the rays are computed here instead and
messages are printed as `topic payload` lines.

    DRY_RUN=1 uv run python -m src.sim
    MQTT_HOST=emqx.rangelov.dev MQTT_USERNAME=node MQTT_PASSWORD=… uv run python -m src.sim

Each simulated node has its own MQTT connection with its id as the client id, like a Pi, so the
shared node login works (the broker lets it publish only under `nodes/<client id>/`).
"""

import json
import logging
import math
import os
import random
import signal
import threading
import time
from dataclasses import dataclass, fields

import paho.mqtt.client as mqtt

from .ecef import ray
from .payloads import detection_payload, status_payload
from .triangulate import Ray, Triangulator, ray_from_message

log = logging.getLogger("edth.sim")

M_PER_DEG = math.pi / 180 * 6_371_000.0


@dataclass(frozen=True)
class SimConfig:
    origin: tuple[float, float, float] = (42.6573, 23.3549, 560.0)  # TechArena, TU Sofia
    nodes: int = 2
    baseline_m: float = 30.0
    node_up_m: float = 1.5
    pitch_deg: float = 35.0
    hfov_deg: float = 102.0
    fps: float = 15.0
    targets: int = 1
    noise_deg: float = 0.2
    miss: float = 0.05
    false_per_s: float = 0.5
    scale: float = 1.0  # shrinks the targets' paths: 0.05 for a table-top rig, 0.33 m baseline

    @classmethod
    def from_env(cls, env=None) -> "SimConfig":
        env = os.environ if env is None else env
        d = cls()
        values = {}
        for f in fields(cls):
            raw = env.get(f"SIM_{f.name.upper()}")
            if raw in (None, ""):
                continue
            if f.name == "origin":
                values["origin"] = tuple(float(x) for x in raw.split(","))
            else:
                values[f.name] = type(getattr(d, f.name))(raw)
        return cls(**values)


@dataclass
class SimNode:
    id: str
    enu: tuple[float, float, float]
    position: tuple[float, float, float]  # lat, lon, alt
    triangulator: Triangulator


def enu_to_lla(origin, e, n, u):
    lat0, lon0, alt0 = origin
    return (lat0 + n / M_PER_DEG, lon0 + e / (M_PER_DEG * math.cos(math.radians(lat0))), alt0 + u)


def make_nodes(sim: SimConfig) -> list[SimNode]:
    """Nodes on an east-west line, `baseline_m` apart, all looking north and up."""
    out = []
    for i in range(sim.nodes):
        e = (i - (sim.nodes - 1) / 2) * sim.baseline_m
        node_id = f"sim-{chr(ord('a') + i)}"
        enu = (e, 0.0, sim.node_up_m)
        out.append(SimNode(node_id, enu, enu_to_lla(sim.origin, *enu), Triangulator(node_id)))
    return out


def target_position(k: int, t: float, scale: float = 1.0) -> tuple[float, float, float]:
    """Target `k`: a 10 m circle 25 m north of the line, about 4 m/s, bobbing up and down."""
    w = 0.4 * (1 if k % 2 == 0 else -0.7)
    phase = k * 2.1
    return (
        scale * 10 * math.cos(w * t + phase),
        scale * (25 + 10 * math.sin(w * t + phase)),
        scale * (12 + 4 * k + 3 * math.sin(0.25 * t + phase)),
    )


def bearing(frm, to) -> tuple[float, float]:
    e, n, u = (b - a for a, b in zip(frm, to, strict=True))
    return math.degrees(math.atan2(e, n)) % 360.0, math.degrees(math.atan2(u, math.hypot(e, n)))


def in_view(sim: SimConfig, az: float, el: float) -> bool:
    """A cone around the boresight (north, `pitch_deg` up)."""
    a, e, p = math.radians(az), math.radians(el), math.radians(sim.pitch_deg)
    cos_off = math.cos(e) * math.cos(p) * math.cos(a) + math.sin(e) * math.sin(p)
    return cos_off > math.cos(math.radians(sim.hfov_deg / 2))


def frame_detections(sim: SimConfig, node: SimNode, t: float, frame: int) -> list[dict]:
    out = []
    for k in range(sim.targets):
        az, el = bearing(node.enu, target_position(k, t, sim.scale))
        if in_view(sim, az, el) and random.random() > sim.miss:
            az += random.gauss(0, sim.noise_deg)
            el += random.gauss(0, sim.noise_deg)
            out.append((az, el, random.uniform(0.6, 0.95)))
    if random.random() < sim.false_per_s / sim.fps:
        az, el = random.gauss(0, 30) % 360, random.uniform(5, 60)
        if in_view(sim, az, el):
            out.append((az, el, random.uniform(0.3, 0.6)))
    return [detection_payload(node.id, t, az, el, c, frame, node.position) for az, el, c in out]


def broker_ray(det: dict) -> Ray:
    """What the broker's rule makes of a detection (see EDTH-infra apps/emqx)."""
    o, d = ray(det["lat"], det["lon"], det["alt_m"], det["az"], det["el"])
    return Ray(det["node"], det["t"], o, d, det["conf"])


class Sim:
    """All nodes in one process; `publish(topic, payload)` is the only way out."""

    def __init__(self, sim: SimConfig, publish, local_rays: bool):
        self.sim = sim
        self.nodes = make_nodes(sim)
        self.publish = publish
        self.local_rays = local_rays
        self.frame = 0

    def step(self, t: float) -> None:
        self.frame += 1
        for node in self.nodes:
            for det in frame_detections(self.sim, node, t, self.frame):
                self.publish(f"nodes/{node.id}/detections", det)
                own = broker_ray(det)
                for fix in node.triangulator.add_own(own):
                    self.publish(f"nodes/{node.id}/fixes", fix)
                if self.local_rays:
                    self.on_ray(own)

    def on_ray(self, peer: Ray) -> None:
        if peer.node not in {n.id for n in self.nodes}:
            return  # a real node's ray: crossing it with a made-up one gives a made-up fix
        for node in self.nodes:
            if node.id != peer.node:
                for fix in node.triangulator.add_peer(peer):
                    self.publish(f"nodes/{node.id}/fixes", fix)

    def status(self, t: float) -> None:
        for node in self.nodes:
            payload = status_payload(node.id, t, self.sim.fps, 50.0, 0.0, node.position)
            self.publish(f"nodes/{node.id}/status", payload)


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
    )
    sim_cfg = SimConfig.from_env()
    dry_run = os.environ.get("DRY_RUN", "0").lower() in ("1", "true", "yes")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    lock = threading.Lock()
    sim = Sim(sim_cfg, None, local_rays=dry_run)
    clients: dict[str, mqtt.Client] = {}
    if dry_run:

        def publish(topic, payload):
            print(f"{topic} {json.dumps(payload, separators=(',', ':'))}", flush=True)

    else:

        def on_message(c, u, m):
            try:
                peer = ray_from_message(json.loads(m.payload))
            except (ValueError, KeyError, TypeError):
                return
            with lock:
                sim.on_ray(peer)

        for i, node in enumerate(sim.nodes):
            clients[node.id] = _connect(node.id, on_message if i == 0 else None)

        def publish(topic, payload):
            client = clients[topic.split("/")[1]]
            client.publish(topic, json.dumps(payload, separators=(",", ":")), qos=0)

    sim.publish = publish
    log.info("event=start nodes=%s targets=%d fps=%s", [n.id for n in sim.nodes], sim_cfg.targets,
             sim_cfg.fps)  # fmt: skip
    next_status = time.monotonic()
    try:
        while not stop.wait(1 / sim_cfg.fps):
            with lock:
                sim.step(time.time())
                if time.monotonic() >= next_status:
                    next_status += 1.0
                    sim.status(time.time())
    finally:
        for client in clients.values():
            client.disconnect()
            client.loop_stop()
    return 0


def _connect(client_id: str, on_ray=None) -> mqtt.Client:
    """One node's connection; the one given `on_ray` also hears every node's rays."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    if os.environ.get("MQTT_USERNAME"):
        client.username_pw_set(os.environ["MQTT_USERNAME"], os.environ.get("MQTT_PASSWORD"))
    if os.environ.get("MQTT_TLS", "1").lower() not in ("0", "false", "no"):
        client.tls_set(ca_certs=os.environ.get("MQTT_CA_FILE") or None)

    def on_connect(c, u, f, rc, p):
        log.info("event=mqtt_connect node=%s rc=%s", client_id, rc)
        if on_ray:
            c.subscribe("rays/+")

    client.on_connect = on_connect
    client.on_message = on_ray
    client.connect_async(os.environ["MQTT_HOST"], int(os.environ.get("MQTT_PORT", 8883)), 30)
    client.loop_start()
    return client


if __name__ == "__main__":
    raise SystemExit(main())
