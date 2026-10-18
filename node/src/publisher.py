import json
import logging

import paho.mqtt.client as mqtt

from .config import Config

log = logging.getLogger("edth.publisher")


class Publisher:
    """Thread-safe MQTT publisher. QoS 0, no queueing: stale detections are dropped offline."""

    def __init__(self, cfg: Config):
        self.node = cfg.node_id
        self.dropped = 0
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cfg.node_id)
        if cfg.mqtt_username:
            self.client.username_pw_set(cfg.mqtt_username, cfg.mqtt_password)
        if cfg.mqtt_tls:
            self.client.tls_set(ca_certs=cfg.mqtt_ca_file)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self._host, self._port = cfg.mqtt_host, cfg.mqtt_port
        self._subscriptions: dict = {}

    def subscribe(self, topic: str, handler) -> None:
        """`handler(topic, payload_bytes)` runs on the MQTT thread; kept across reconnects."""
        self._subscriptions[topic] = handler
        if self.client.is_connected():
            self.client.subscribe(topic, qos=0)

    def start(self) -> None:
        self.client.connect_async(self._host, self._port, keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()

    @property
    def connected(self) -> bool:
        return self.client.is_connected()

    def publish(self, kind: str, payload: dict) -> bool:
        topic = f"nodes/{self.node}/{kind}"
        info = self.client.publish(topic, json.dumps(payload, separators=(",", ":")), qos=0)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            self.dropped += 1
            return False
        return True

    def publish_detection(self, payload: dict) -> bool:
        return self.publish("detections", payload)

    def publish_status(self, payload: dict) -> bool:
        return self.publish("status", payload)

    def publish_fix(self, payload: dict) -> bool:
        return self.publish("fixes", payload)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        log.info("event=mqtt_connect node=%s rc=%s", self.node, reason_code)
        for topic in self._subscriptions:
            client.subscribe(topic, qos=0)

    def _on_message(self, client, userdata, message):
        for pattern, handler in self._subscriptions.items():
            if mqtt.topic_matches_sub(pattern, message.topic):
                handler(message.topic, message.payload)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        log.warning("event=mqtt_disconnect node=%s rc=%s", self.node, reason_code)


class DryRunPublisher:
    """Same interface as Publisher, but prints each message as `topic payload` on stdout."""

    dropped = 0
    connected = True

    def __init__(self, cfg: Config):
        self.node = cfg.node_id

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def publish(self, kind: str, payload: dict) -> bool:
        print(f"nodes/{self.node}/{kind} {json.dumps(payload, separators=(',', ':'))}", flush=True)
        return True

    def publish_detection(self, payload: dict) -> bool:
        return self.publish("detections", payload)

    def publish_status(self, payload: dict) -> bool:
        return self.publish("status", payload)

    def publish_fix(self, payload: dict) -> bool:
        return self.publish("fixes", payload)

    def subscribe(self, topic: str, handler) -> None:
        pass  # nothing arrives in a dry run
