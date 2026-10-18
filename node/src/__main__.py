import logging
import os
import signal
import threading
import time

from .camera import open_camera
from .config import Config
from .detector import load_detector
from .geometry import DEFAULT_HFOV_DEG, CameraGeometry
from .payloads import detection_payload
from .publisher import DryRunPublisher, Publisher
from .status import StatusReporter
from .stream import Mark, Streamer

log = logging.getLogger("edth.node")


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
    )
    cfg = Config.from_env()
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    publisher = DryRunPublisher(cfg) if cfg.dry_run else Publisher(cfg)
    status = StatusReporter(publisher, cfg.ntp_server, health_file=cfg.health_file)
    camera = open_camera(cfg.camera_device, cfg.camera_width, cfg.camera_height, cfg.camera_fps)
    detector = load_detector(cfg.detector)
    streamer = (
        Streamer(cfg.node_id, cfg.stream_port, cfg.stream_rotate) if cfg.stream_port else None
    )
    geometry = None
    publisher.start()
    if streamer:
        streamer.start()
    status.start()
    log.info(
        "event=start node=%s version=%s broker=%s:%s detector=%s camera=%s dry_run=%s",
        cfg.node_id,
        os.environ.get("EDTH_VERSION", "dev"),
        cfg.mqtt_host,
        cfg.mqtt_port,
        cfg.detector,
        cfg.camera_device,
        cfg.dry_run,
    )

    frame_no = 0
    rc = 0
    try:
        while not stop.is_set():
            frame = camera.read()
            if frame is None:
                log.error("event=camera_eof node=%s", cfg.node_id)
                rc = 1  # let the supervisor (systemd) restart us
                break
            t = camera.captured_at or time.time()  # sensor time if known, else the read time
            if geometry is None:
                height, width = frame.shape[:2]
                sensor_hfov = getattr(camera, "hfov_deg", None)
                geometry = CameraGeometry.from_config(cfg, width, height, sensor_hfov)
                log.info(
                    "event=camera node=%s sensor=%s size=%dx%d hfov_deg=%s source=%s",
                    cfg.node_id,
                    getattr(camera, "model", cfg.camera_device),
                    width,
                    height,
                    cfg.camera_hfov_deg or sensor_hfov or DEFAULT_HFOV_DEG,
                    "config" if cfg.camera_hfov_deg else "sensor" if sensor_hfov else "default",
                )
            frame_no += 1
            status.tick()
            marks = []
            for d in detector.detect(frame):
                az, el = geometry.pixel_to_azel(d.u, d.v)
                marks.append(Mark(d.u, d.v, d.conf, az, el))
                publisher.publish_detection(
                    detection_payload(cfg.node_id, t, az, el, d.conf, frame_no)
                )
                log.debug(
                    "event=detection node=%s frame=%d az=%.1f el=%.1f conf=%.2f",
                    cfg.node_id,
                    frame_no,
                    az,
                    el,
                    d.conf,
                )
            if streamer:
                streamer.update(frame, marks)
    finally:
        if streamer:
            streamer.stop()
        status.stop()
        publisher.stop()
        camera.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
