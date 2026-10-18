"""Opt-in demo video: push small JPEGs (detections drawn on) to the video relay.

The node is behind NAT (a phone hotspot), so it sends rather than serves: one long chunked HTTPS
POST of multipart JPEGs to `{VIDEO_PUSH_URL}/{node}`, authenticated with the node's MQTT username
and password (the relay checks them against the broker). A few frames per second at 640 px wide is
about 100 kB/s. This is a demo aid and not part of the message contract; nothing goes to the broker.
"""

import base64
import http.client
import logging
import ssl
import threading
import time
from urllib.parse import urlsplit

from .stream import Streamer

log = logging.getLogger("edth.video")

BOUNDARY = "edthframe"


class VideoPusher:
    def __init__(
        self,
        streamer: Streamer,
        url: str,
        node: str,
        username: str | None,
        password: str | None,
        fps: float = 4.0,
        width: int = 640,
        quality: int = 60,
    ):
        parts = urlsplit(url.rstrip("/") + "/" + node)
        if parts.scheme not in ("http", "https"):
            raise ValueError("VIDEO_PUSH_URL must be http(s)://…")
        self.streamer, self.parts, self.fps, self.width, self.quality = (
            streamer, parts, fps, width, quality,
        )  # fmt: skip
        self._auth = None
        if username:
            token = base64.b64encode(f"{username}:{password or ''}".encode()).decode()
            self._auth = "Basic " + token
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="video", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self._push()
            except (OSError, http.client.HTTPException) as e:
                log.warning("event=video_error url=%s error=%s", self.parts.geturl(), e)
            if time.monotonic() - started > 30:
                backoff = 1.0
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 30.0)

    def _connect(self) -> http.client.HTTPConnection:
        host, port = self.parts.hostname, self.parts.port
        if self.parts.scheme == "https":
            ctx = ssl.create_default_context()
            return http.client.HTTPSConnection(host, port, timeout=15, context=ctx)
        return http.client.HTTPConnection(host, port, timeout=15)

    def _push(self) -> None:
        conn = self._connect()
        try:
            conn.putrequest("POST", self.parts.path or "/", skip_accept_encoding=True)
            conn.putheader("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
            conn.putheader("Transfer-Encoding", "chunked")
            if self._auth:
                conn.putheader("Authorization", self._auth)
            conn.endheaders()
            log.info("event=video_push url=%s fps=%s width=%d", self.parts.geturl(), self.fps,
                     self.width)  # fmt: skip
            seq, last = 0, 0.0
            while not self._stop.is_set():
                got = self.streamer.wait_for_frame(seq, timeout=5.0)
                if got is None:
                    continue
                seq = got
                wait = 1.0 / self.fps - (time.monotonic() - last)
                if wait > 0:
                    self._stop.wait(wait)
                last = time.monotonic()
                data = self.streamer.small_jpeg(self.width, self.quality)
                if not data:
                    continue
                part = (
                    (
                        f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\n"
                        f"Content-Length: {len(data)}\r\n\r\n"
                    ).encode()
                    + data
                    + b"\r\n"
                )
                conn.send(f"{len(part):X}\r\n".encode() + part + b"\r\n")
            conn.send(b"0\r\n\r\n")
        finally:
            conn.close()
