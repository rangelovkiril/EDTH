import os
import re
from dataclasses import dataclass

NODE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class Config:
    node_id: str
    mqtt_host: str | None
    mqtt_port: int = 8883
    mqtt_tls: bool = True
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_ca_file: str | None = None
    camera_device: str = "0"
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: float = 30.0
    camera_hfov_deg: float | None = None
    camera_fx: float | None = None
    camera_fy: float | None = None
    camera_cx: float | None = None
    camera_cy: float | None = None
    camera_dist: tuple[float, ...] = ()
    heading_deg: float = 0.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    position: tuple[float, float, float] | None = None  # lat, lon, alt_m
    triangulate: bool = True
    tri_sync_s: float = 0.1
    tri_max_miss_m: float = 2.0
    tri_min_angle_deg: float = 2.0
    tri_max_range_m: float = 2000.0
    ntp_server: str = "pool.ntp.org"
    detector: str = "motion:MotionDetector"
    dry_run: bool = False
    health_file: str | None = "/tmp/edth-alive"
    stream_port: int | None = None
    stream_rotate: int = 0
    video_push_url: str | None = None
    video_fps: float = 4.0
    video_width: int = 640
    video_token: str | None = None

    @classmethod
    def from_env(cls, env=None) -> "Config":
        env = os.environ if env is None else env

        def get(name, default=None):
            value = env.get(name)
            return default if value in (None, "") else value

        def num(name, kind=float):
            value = get(name)
            return None if value is None else kind(value)

        node_id = get("NODE_ID")
        if node_id is None or not NODE_ID_RE.match(node_id):
            raise ValueError("NODE_ID is required and must match [a-z0-9][a-z0-9_-]*")
        dry_run = get("DRY_RUN", "0").lower() in ("1", "true", "yes")
        host = get("MQTT_HOST")
        if host is None and not dry_run:
            raise ValueError("MQTT_HOST is required (or set DRY_RUN=1)")
        stream_rotate = int(get("STREAM_ROTATE", 0))
        if stream_rotate not in (0, 90, 180, 270):
            raise ValueError("STREAM_ROTATE must be 0, 90, 180 or 270")
        dist = get("CAMERA_DIST", "")
        position = tuple(num(f"NODE_{k}") for k in ("LAT", "LON", "ALT_M"))
        if all(v is None for v in position):
            position = None
        elif any(v is None for v in position):
            raise ValueError("NODE_LAT, NODE_LON and NODE_ALT_M go together: set all or none")
        elif not (-90 <= position[0] <= 90 and -180 <= position[1] <= 180):
            raise ValueError("NODE_LAT must be in [-90, 90] and NODE_LON in [-180, 180]")
        return cls(
            node_id=node_id,
            mqtt_host=host,
            mqtt_port=int(get("MQTT_PORT", 8883)),
            mqtt_tls=get("MQTT_TLS", "1").lower() not in ("0", "false", "no"),
            mqtt_username=get("MQTT_USERNAME"),
            mqtt_password=get("MQTT_PASSWORD"),
            mqtt_ca_file=get("MQTT_CA_FILE"),
            camera_device=get("CAMERA_DEVICE", "0"),
            camera_width=int(get("CAMERA_WIDTH", 640)),
            camera_height=int(get("CAMERA_HEIGHT", 480)),
            camera_fps=float(get("CAMERA_FPS", 30)),
            camera_hfov_deg=num("CAMERA_HFOV_DEG"),
            camera_fx=num("CAMERA_FX"),
            camera_fy=num("CAMERA_FY"),
            camera_cx=num("CAMERA_CX"),
            camera_cy=num("CAMERA_CY"),
            camera_dist=tuple(float(x) for x in dist.split(",") if x.strip()),
            heading_deg=float(get("NODE_HEADING_DEG", 0)),
            pitch_deg=float(get("NODE_PITCH_DEG", 0)),
            roll_deg=float(get("NODE_ROLL_DEG", 0)),
            position=position,
            triangulate=get("TRIANGULATE", "1").lower() not in ("0", "false", "no"),
            tri_sync_s=float(get("TRI_SYNC_S", 0.1)),
            tri_max_miss_m=float(get("TRI_MAX_MISS_M", 2.0)),
            tri_min_angle_deg=float(get("TRI_MIN_ANGLE_DEG", 2.0)),
            tri_max_range_m=float(get("TRI_MAX_RANGE_M", 2000.0)),
            ntp_server=get("NTP_SERVER", "pool.ntp.org"),
            detector=get("DETECTOR", "motion:MotionDetector"),
            dry_run=dry_run,
            health_file=get("HEALTH_FILE", "/tmp/edth-alive"),
            stream_port=num("STREAM_PORT", int),
            stream_rotate=stream_rotate,
            video_push_url=get("VIDEO_PUSH_URL"),
            video_fps=float(get("VIDEO_FPS", 4.0)),
            video_width=int(get("VIDEO_WIDTH", 640)),
            video_token=get("VIDEO_TOKEN"),
        )
