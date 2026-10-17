import logging
import signal
import threading
import time

from .camera import Camera
from .config import Config
from .detectors.motion import MotionDetector
from .geometry import CameraGeometry
from .publisher import Publisher, detection_payload
from .status import StatusReporter

log = logging.getLogger("edth.node")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"
    )
    cfg = Config.from_env()
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    publisher = Publisher(cfg)
    status = StatusReporter(publisher, cfg.ntp_server)
    camera = Camera(cfg.camera_device, cfg.camera_width, cfg.camera_height)
    detector = MotionDetector()  # swap in another Detector here
    geometry = None
    publisher.start()
    status.start()
    log.info("event=start node=%s broker=%s:%d", cfg.node_id, cfg.mqtt_host, cfg.mqtt_port)

    frame_no = 0
    rc = 0
    try:
        while not stop.is_set():
            frame = camera.read()
            if frame is None:
                log.error("event=camera_eof node=%s", cfg.node_id)
                rc = 1  # let the supervisor (systemd) restart us
                break
            t = time.time()  # closest we get to capture time over V4L2
            if geometry is None:
                height, width = frame.shape[:2]
                geometry = CameraGeometry.from_config(cfg, width, height)
            frame_no += 1
            status.tick()
            for d in detector.detect(frame):
                az, el = geometry.pixel_to_azel(d.u, d.v)
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
    finally:
        status.stop()
        publisher.stop()
        camera.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
