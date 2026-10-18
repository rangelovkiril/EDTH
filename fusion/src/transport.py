"""MQTT, or `topic payload` lines on stdin/stdout for DRY_RUN (the node's dry-run format), so
`sim | fusion` works without a broker."""

import json
import logging
import sys
import threading

import paho.mqtt.client as mqtt

from .config import Config

log = logging.getLogger("edth.transport")


class MqttTransport:
    def __init__(self, cfg: Config, client_id: str, subscribe=(), on_message=None):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        if cfg.mqtt_username:
            self.client.username_pw_set(cfg.mqtt_username, cfg.mqtt_password)
        if cfg.mqtt_tls:
            self.client.tls_set(ca_certs=cfg.mqtt_ca_file)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._subscribe = list(subscribe)
        self.client.on_connect = self._connected
        self.client.on_disconnect = self._disconnected
        self.client.on_connect_fail = lambda c, u: log.warning(
            "event=mqtt_connect_fail broker=%s:%s", self._host, self._port
        )
        self.client.on_message = lambda c, u, m: on_message(m.topic, m.payload)
        self._host, self._port = cfg.mqtt_host, cfg.mqtt_port

    def start(self) -> None:
        self.client.connect_async(self._host, self._port, keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()

    def publish(self, topic: str, payload: dict) -> None:
        self.client.publish(topic, json.dumps(payload, separators=(",", ":")), qos=0)

    def _connected(self, client, userdata, flags, reason_code, properties):
        log.info("event=mqtt_connect rc=%s", reason_code)
        for topic in self._subscribe:
            client.subscribe(topic, qos=0)  # again on every reconnect

    def _disconnected(self, client, userdata, flags, reason_code, properties):
        log.warning("event=mqtt_disconnect rc=%s", reason_code)


class StdioTransport:
    def __init__(self, cfg: Config, client_id: str, subscribe=(), on_message=None):
        self._on_message = on_message
        self._lock = threading.Lock()
        self._reader = threading.Thread(target=self._read, name="stdin", daemon=True)

    def start(self) -> None:
        if self._on_message:
            self._reader.start()

    def stop(self) -> None:
        pass

    def publish(self, topic: str, payload: dict) -> None:
        with self._lock:
            print(f"{topic} {json.dumps(payload, separators=(',', ':'))}", flush=True)

    def _read(self) -> None:
        for line in sys.stdin:
            topic, _, payload = line.strip().partition(" ")
            if payload:
                self._on_message(topic, payload.encode())


def open_transport(cfg: Config, client_id: str, subscribe=(), on_message=None):
    kind = StdioTransport if cfg.dry_run else MqttTransport
    return kind(cfg, client_id, subscribe, on_message)
