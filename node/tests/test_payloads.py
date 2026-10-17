import json
from types import SimpleNamespace

import pytest
from jsonschema import ValidationError

from src.config import Config
from src.payloads import detection_payload, status_payload
from src.publisher import Publisher


def test_detection_payload_matches_schema(validate):
    validate("detection", detection_payload("rpi-1", 1760000000.123456789, 123.45678, 12.3, 0.8, 7))


@pytest.mark.parametrize("az", [0.0, -1e-15, 359.9999999, 360.0, 720.5, -0.0004])
def test_az_always_in_range(validate, az):
    payload = detection_payload("rpi-1", 1.0, az, 0.0, 0.5, 0)
    assert 0 <= payload["az"] < 360
    validate("detection", payload)


def test_out_of_range_el_and_conf_are_clamped(validate):
    payload = detection_payload("rpi-1", 1.0, 10.0, 95.0, 1.2, 0)
    assert payload["el"] == 90.0 and payload["conf"] == 1.0
    validate("detection", payload)


@pytest.mark.parametrize("temp,offset", [(54.2, -3.1), (None, None), (0.0, 0.0)])
def test_status_payload_matches_schema(validate, temp, offset):
    payload = status_payload("rpi-1", 1760000001.0, 29.7, temp, offset)
    validate("status", payload)
    assert ("temp_c" in payload) == (temp is not None)
    assert ("clock_offset_ms" in payload) == (offset is not None)


def test_schema_rejects_bad_payloads(validate):
    good = detection_payload("rpi-1", 1.0, 10.0, 5.0, 0.5, 1)
    for bad in (
        {**good, "az": 360.0},
        {**good, "node": "../x"},
        {**good, "extra": 1},
        {k: v for k, v in good.items() if k != "frame"},
    ):
        with pytest.raises(ValidationError):
            validate("detection", bad)


def test_publisher_sends_validated_json_on_node_topic(validate):
    cfg = Config(node_id="rpi-1", mqtt_host="localhost", mqtt_tls=False)
    pub = Publisher(cfg)
    sent = []
    pub.client.publish = lambda topic, payload, qos: (
        sent.append((topic, payload, qos)) or SimpleNamespace(rc=0)
    )
    assert pub.publish_detection(detection_payload("rpi-1", 1.0, 1.0, 2.0, 0.9, 3))
    assert pub.publish_status(status_payload("rpi-1", 1.0, 30.0, None, None))
    (t1, p1, q1), (t2, p2, q2) = sent
    assert (t1, t2) == ("nodes/rpi-1/detections", "nodes/rpi-1/status")
    assert q1 == q2 == 0
    validate("detection", json.loads(p1))
    validate("status", json.loads(p2))


def test_publisher_counts_drops_when_offline():
    pub = Publisher(Config(node_id="rpi-1", mqtt_host="localhost", mqtt_tls=False))
    assert not pub.publish_detection(detection_payload("rpi-1", 1.0, 1.0, 2.0, 0.9, 3))
    assert pub.dropped == 1
