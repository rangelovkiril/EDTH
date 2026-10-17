import logging
import socket
import struct
import threading
import time
from pathlib import Path

from .publisher import Publisher, status_payload

log = logging.getLogger("edth.status")

_NTP_EPOCH_OFFSET = 2208988800  # 1900-01-01 to 1970-01-01
THERMAL_ZONE = Path("/sys/class/thermal/thermal_zone0/temp")


def read_temp_c(path: Path = THERMAL_ZONE) -> float | None:
    try:
        return int(path.read_text().strip()) / 1000.0
    except (OSError, ValueError):
        return None


def ntp_offset_ms(server: str, port: int = 123, timeout: float = 1.0) -> float | None:
    """SNTP query. Returns local clock minus server clock in ms, or None on failure."""
    request = b"\x23" + 47 * b"\0"  # LI=0, VN=4, mode=3 (client)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            t0 = time.time()
            sock.sendto(request, (server, port))
            data, _ = sock.recvfrom(512)
            t3 = time.time()
    except OSError:
        return None
    if len(data) < 48:
        return None
    sec2, frac2, sec3, frac3 = struct.unpack("!4I", data[32:48])
    t1 = sec2 - _NTP_EPOCH_OFFSET + frac2 / 2**32  # server receive
    t2 = sec3 - _NTP_EPOCH_OFFSET + frac3 / 2**32  # server transmit
    server_ahead = ((t1 - t0) + (t2 - t3)) / 2
    return -server_ahead * 1000.0


class StatusReporter:
    """Publishes `status` about once a second; the main loop calls `tick()` per frame."""

    def __init__(
        self, publisher: Publisher, ntp_server: str, interval: float = 1.0, ntp_every: float = 30.0
    ):
        self.publisher = publisher
        self.ntp_server = ntp_server
        self.interval = interval
        self.ntp_every = ntp_every
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
            payload = status_payload(
                self.publisher.node, time.time(), fps, read_temp_c(), self._offset
            )
            self.publisher.publish_status(payload)
            log.info(
                "event=status node=%s fps=%.1f dropped=%d",
                payload["node"],
                fps,
                self.publisher.dropped,
            )
