import json
import logging
import math
import os
import signal
import threading
import time

from .config import Config
from .tracker import Tracker
from .transport import open_transport

log = logging.getLogger("edth.fusion")

SUBSCRIBE = ("fixes/+",)  # fixes the broker accepted (EDTH-infra apps/emqx)
FIELDS = ("node", "peer", "t", "lat", "lon", "alt_m", "miss_m", "conf")


def handle(tracker: Tracker, topic: str, raw: bytes, now: float) -> bool:
    """Feed one fix to `tracker`. False (and nothing changes) if it is malformed."""
    if not topic.startswith("fixes/"):
        return False
    try:
        fix = json.loads(raw)
        if not all(math.isfinite(float(fix[k])) for k in FIELDS[2:]):
            return False
        if not (isinstance(fix["node"], str) and isinstance(fix["peer"], str)):
            return False
    except (ValueError, KeyError, TypeError):
        return False
    tracker.on_fix(fix, now)
    return True


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
    )
    cfg = Config.from_env()
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    tracker = Tracker(cfg)
    lock = threading.Lock()
    counts = {"fixes": 0, "bad": 0}

    def on_message(topic, raw):
        with lock:
            ok = handle(tracker, topic, raw, time.time())
        counts["fixes" if ok else "bad"] += 1
        if not ok and counts["bad"] in (1, 10, 100):
            log.warning("event=bad_message topic=%s count=%d", topic, counts["bad"])

    transport = open_transport(cfg, cfg.client_id, SUBSCRIBE, on_message)
    transport.start()
    log.info(
        "event=start version=%s broker=%s:%s dry_run=%s",
        os.environ.get("EDTH_VERSION", "dev"),
        cfg.mqtt_host,
        cfg.mqtt_port,
        cfg.dry_run,
    )
    period = 1.0 / cfg.rate_hz
    next_log = time.monotonic()
    try:
        while not stop.wait(period):
            now = time.time()
            with lock:
                tracker.expire(now)
                tracks = tracker.report(now, now)
            for p in tracks:
                transport.publish("fusion/tracks", p)
            if time.monotonic() >= next_log:
                next_log += 10
                log.info(
                    "event=stats fixes=%d bad=%d tracks=%d",
                    counts["fixes"],
                    counts["bad"],
                    len(tracks),
                )
    finally:
        transport.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
