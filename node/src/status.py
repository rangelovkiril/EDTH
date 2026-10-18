import logging
import threading
import time
from pathlib import Path

from .clock import ntp_offset_ms
from .payloads import status_payload
from .publisher import Publisher

log = logging.getLogger("edth.status")

THERMAL_ZONE = Path("/sys/class/thermal/thermal_zone0/temp")


def read_temp_c(path: Path = THERMAL_ZONE) -> float | None:
    try:
        return int(path.read_text().strip()) / 1000.0
    except (OSError, ValueError):
        return None


class StatusReporter:
    """Publishes `status` about once a second; the main loop calls `tick()` per frame."""

    def __init__(
        self,
        publisher: Publisher,
        ntp_server: str,
        interval: float = 1.0,
        ntp_every: float = 30.0,
        health_file: str | None = None,
        position: tuple[float, float, float] | None = None,
    ):
        self.publisher = publisher
        self.ntp_server = ntp_server
        self.interval = interval
        self.ntp_every = ntp_every
        self.health_file = health_file
        self.position = position  # a GPS on an aerostat would update this
        self._frames = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="status", daemon=True)
        self._offset: float | None = None

    def tick(self) -> None:
        with self._lock:
            self._frames += 1

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    def _run(self) -> None:
        last = time.monotonic()
        next_ntp = last
        while not self._stop.wait(self.interval):
            now = time.monotonic()
            if now >= next_ntp:
                self._offset = ntp_offset_ms(self.ntp_server)
                next_ntp = now + self.ntp_every
                now = time.monotonic()
            with self._lock:
                frames, self._frames = self._frames, 0
            fps = frames / (now - last)
            last = now
            if frames and self.health_file:
                self._touch_health_file()
            payload = status_payload(
                self.publisher.node, time.time(), fps, read_temp_c(), self._offset, self.position
            )
            self.publisher.publish_status(payload)
            log.info(
                "event=status node=%s fps=%.1f dropped=%d",
                payload["node"],
                fps,
                self.publisher.dropped,
            )

    def _touch_health_file(self) -> None:
        """The container healthcheck looks at this file's age: it only moves while frames flow."""
        try:
            Path(self.health_file).touch()
        except OSError as e:
            log.warning("event=health_file_error path=%s error=%s", self.health_file, e)
