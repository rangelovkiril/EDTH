import pytest

from src.config import Config, hardware_id


def test_minimal_env():
    cfg = Config.from_env({"NODE_ID": "rpi-1", "MQTT_HOST": "mqtt.example"})
    assert cfg.mqtt_port == 8883 and cfg.mqtt_tls and cfg.camera_dist == ()
    assert cfg.position is None


def test_full_env():
    cfg = Config.from_env(
        {
            "NODE_ID": "rpi-2",
            "MQTT_HOST": "h",
            "MQTT_PORT": "1883",
            "MQTT_TLS": "0",
            "NODE_HEADING_DEG": "90",
            "CAMERA_DIST": "0.1, -0.2,0,0,0",
            "CAMERA_FX": "500",
            "NODE_LAT": "42.6977",
            "NODE_LON": "23.3219",
            "NODE_ALT_M": "560.5",
        }
    )
    assert not cfg.mqtt_tls and cfg.heading_deg == 90 and cfg.camera_fx == 500
    assert cfg.camera_dist == (0.1, -0.2, 0, 0, 0)
    assert cfg.position == (42.6977, 23.3219, 560.5)


def test_node_id_defaults_to_the_board_serial(tmp_path):
    serial = tmp_path / "serial-number"
    serial.write_bytes(b"000000008584F1F2\x00")
    assert hardware_id([tmp_path / "missing", serial]) == "pi-8584f1f2"
    cfg = Config.from_env({"MQTT_HOST": "h"}, default_id=lambda: "pi-8584f1f2")
    assert cfg.node_id == "pi-8584f1f2"
    assert Config.from_env({"NODE_ID": "cam-a", "MQTT_HOST": "h"}).node_id == "cam-a"
    assert hardware_id([tmp_path / "missing"]) is None


@pytest.mark.parametrize(
    "env",
    [
        {"MQTT_HOST": "h", "NODE_ID": ""},
        {"NODE_ID": "rpi-1"},
        {"NODE_ID": "a/b", "MQTT_HOST": "h"},
        {"NODE_ID": "a#", "MQTT_HOST": "h"},
        {"NODE_ID": "RPI", "MQTT_HOST": "h"},
        {"NODE_ID": "rpi-1", "MQTT_HOST": "h", "NODE_LAT": "42", "NODE_LON": "23"},
        {"NODE_ID": "r", "MQTT_HOST": "h", "NODE_LAT": "91", "NODE_LON": "0", "NODE_ALT_M": "0"},
    ],
)
def test_invalid_env(env):
    with pytest.raises(ValueError):
        Config.from_env(env, default_id=lambda: None)
