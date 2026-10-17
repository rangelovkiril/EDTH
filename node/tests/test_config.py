import pytest

from edth_node.config import Config


def test_minimal_env():
    cfg = Config.from_env({"NODE_ID": "rpi-1", "MQTT_HOST": "mqtt.example"})
    assert cfg.mqtt_port == 8883 and cfg.mqtt_tls and cfg.camera_dist == ()


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
        }
    )
    assert not cfg.mqtt_tls and cfg.heading_deg == 90 and cfg.camera_fx == 500
    assert cfg.camera_dist == (0.1, -0.2, 0, 0, 0)


@pytest.mark.parametrize(
    "env",
    [
        {"MQTT_HOST": "h"},
        {"NODE_ID": "rpi-1"},
        {"NODE_ID": "a/b", "MQTT_HOST": "h"},
        {"NODE_ID": "a#", "MQTT_HOST": "h"},
        {"NODE_ID": "RPI", "MQTT_HOST": "h"},
    ],
)
def test_invalid_env(env):
    with pytest.raises(ValueError):
        Config.from_env(env)
