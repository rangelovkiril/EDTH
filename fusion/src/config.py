import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    mqtt_host: str | None = None
    mqtt_port: int = 8883
    mqtt_tls: bool = True
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_ca_file: str | None = None
    client_id: str = "fusion"
    origin: tuple[float, float, float] | None = None  # lat, lon, alt_m; else the first fix
    rate_hz: float = 10.0
    gate_m: float = 4.0  # a fix this close to a track's prediction belongs to it
    confirm_hits: int = 3
    track_timeout_s: float = 2.0
    fix_sigma_m: float = 0.3  # a fix's error on top of half its miss distance
    accel_mps2: float = 4.0  # how hard a target may manoeuvre (process noise)
    initial_speed_mps: float = 10.0
    horizon_s: float = 1.0  # how far ahead `pred_*` looks
    conf_sigma_m: float = 2.0  # position uncertainty at which confidence drops to 1/e
    dry_run: bool = False

    @classmethod
    def from_env(cls, env=None) -> "Config":
        env = os.environ if env is None else env

        def get(name, default=None):
            value = env.get(name)
            return default if value in (None, "") else value

        dry_run = get("DRY_RUN", "0").lower() in ("1", "true", "yes")
        host = get("MQTT_HOST")
        if host is None and not dry_run:
            raise ValueError("MQTT_HOST is required (or set DRY_RUN=1)")
        origin = get("ORIGIN")
        d = cls()
        num = {
            f: type(getattr(d, f))(get(f.upper(), getattr(d, f)))
            for f in (
                "rate_hz", "gate_m", "confirm_hits", "track_timeout_s", "fix_sigma_m",
                "accel_mps2", "initial_speed_mps", "horizon_s", "conf_sigma_m",
            )
        }  # fmt: skip
        return cls(
            mqtt_host=host,
            mqtt_port=int(get("MQTT_PORT", d.mqtt_port)),
            mqtt_tls=get("MQTT_TLS", "1").lower() not in ("0", "false", "no"),
            mqtt_username=get("MQTT_USERNAME"),
            mqtt_password=get("MQTT_PASSWORD"),
            mqtt_ca_file=get("MQTT_CA_FILE"),
            client_id=get("MQTT_CLIENT_ID", d.client_id),
            origin=tuple(float(x) for x in origin.split(",")) if origin else None,
            dry_run=dry_run,
            **num,
        )
