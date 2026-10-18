"""Optional live view of the camera over HTTP, for demos on the local network.

Off unless STREAM_PORT is set. Only the node's own LAN can see it; there is no authentication, and
nothing here goes to the MQTT broker (the contract still carries no pixels).

  /               a page with the live picture
  /stream.mjpg    motion JPEG, opens in a browser, VLC, ffplay
  /snapshot.jpg   one JPEG
  add ?rotate=90 (or 180, 270) to turn the picture, e.g. when the camera is mounted sideways
"""

import logging
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np

log = logging.getLogger("edth.stream")

BOUNDARY = "edthframe"
ROTATIONS = {
    0: None,
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}
PAGE = """<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{node}</title>
<style>html,body{{margin:0;height:100%;background:#111;color:#ddd;font:14px sans-serif}}
img{{display:block;max-width:100%;max-height:calc(100% - 28px);margin:auto}}
p{{margin:0;padding:6px 10px}}</style>
<p>{node} &middot; passive camera view, bearings are drawn on detections</p>
<img src="stream.mjpg{query}" alt="camera">
"""


@dataclass(frozen=True)
class Mark:
    """A detection to draw: pixel position, confidence and the bearing the node published."""

    u: float
    v: float
    conf: float
    az: float
    el: float


class Streamer:
    def __init__(
        self, node: str, port: int | None, rotate: int = 0, quality: int = 70, max_fps: float = 15
    ):
        if rotate not in ROTATIONS:
            raise ValueError(f"rotate must be one of {sorted(ROTATIONS)}")
        self.node, self.rotate, self.quality, self.max_fps = node, rotate, quality, max_fps
        self._cond = threading.Condition()
        self._seq = 0
        self._frame: np.ndarray | None = None
        self._marks: list[Mark] = []
        self._cache: tuple[int, int, bytes] | None = None  # (seq, rotate, jpeg), shared by viewers
        self._stopped = False
        self._server = None  # no port: frames only for the video pusher, no local server
        if port is not None:
            self._server = ThreadingHTTPServer(("0.0.0.0", port), _make_handler(self))
            self._server.daemon_threads = True
            self._thread = threading.Thread(
                target=self._server.serve_forever, name="stream", daemon=True
            )

    @property
    def port(self) -> int | None:
        return self._server.server_address[1] if self._server else None

    def start(self) -> None:
        if self._server:
            self._thread.start()
            log.info("event=stream_start node=%s port=%d rotate=%d", self.node, self.port,
                     self.rotate)  # fmt: skip

    def stop(self) -> None:
        with self._cond:
            self._stopped = True
            self._cond.notify_all()
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    def update(self, frame: np.ndarray, marks: list[Mark]) -> None:
        """Called by the main loop per frame; keeps references only, no copying or encoding."""
        with self._cond:
            self._frame, self._marks, self._seq = frame, marks, self._seq + 1
            self._cond.notify_all()

    def wait_for_frame(self, after_seq: int, timeout: float = 5.0) -> int | None:
        """Block until a frame newer than `after_seq` exists; its seq, or None on stop/timeout."""
        with self._cond:
            self._cond.wait_for(lambda: self._stopped or self._seq > after_seq, timeout)
            return None if self._stopped or self._seq <= after_seq else self._seq

    def jpeg(self, rotate: int | None = None) -> bytes | None:
        rotate = self.rotate if rotate is None else rotate
        with self._cond:
            frame, marks, seq = self._frame, self._marks, self._seq
            if frame is None:
                return None
            if self._cache and self._cache[:2] == (seq, rotate):
                return self._cache[2]
        image = _render(frame, marks, rotate)
        ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
        data = buf.tobytes() if ok else None
        if data:
            with self._cond:
                self._cache = (seq, rotate, data)
        return data

    def small_jpeg(self, width: int, quality: int) -> bytes | None:
        """The current frame with its marks, scaled down to `width`, for sending off the device."""
        with self._cond:
            frame, marks = self._frame, self._marks
        if frame is None:
            return None
        image = _render(frame, marks, self.rotate)
        h, w = image.shape[:2]
        if w > width:
            image = cv2.resize(image, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes() if ok else None


def _render(frame: np.ndarray, marks: list[Mark], rotate: int) -> np.ndarray:
    image = frame.copy()
    for m in marks:
        centre = (int(m.u), int(m.v))
        cv2.circle(image, centre, 16, (0, 255, 0), 2, cv2.LINE_AA)
        label = f"az {m.az:.0f} el {m.el:.0f} c{m.conf:.2f}"
        cv2.putText(image, label, (centre[0] + 20, centre[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 255, 0), 2, cv2.LINE_AA)  # fmt: skip
    code = ROTATIONS[rotate]
    return image if code is None else cv2.rotate(image, code)


def _rotate_from(query: dict, default: int) -> int:
    try:
        value = int(query.get("rotate", [default])[0])
    except ValueError:
        return default
    return value if value in ROTATIONS else default


def _make_handler(streamer: Streamer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # the node's own logs stay clean
            log.debug("event=stream_http %s", fmt % args)

        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)
            rotate = _rotate_from(query, streamer.rotate)
            if url.path == "/":
                suffix = f"?rotate={rotate}" if "rotate" in query else ""
                self._send(200, "text/html; charset=utf-8",
                           PAGE.format(node=streamer.node, query=suffix).encode())  # fmt: skip
            elif url.path == "/snapshot.jpg":
                data = streamer.jpeg(rotate)
                if data is None:
                    self._send(503, "text/plain", b"no frame yet")
                else:
                    self._send(200, "image/jpeg", data, cache="no-store")
            elif url.path == "/stream.mjpg":
                self._stream(rotate)
            else:
                self._send(404, "text/plain", b"not found")

        def _send(self, code: int, ctype: str, body: bytes, cache: str | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if cache:
                self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(body)

        def _stream(self, rotate: int):
            self.send_response(200)
            self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            seq, last = 0, 0.0
            try:
                while True:
                    seq = streamer.wait_for_frame(seq)
                    if seq is None:
                        if streamer._stopped:
                            return
                        seq = 0
                        continue
                    wait = 1.0 / streamer.max_fps - (time.monotonic() - last)
                    if wait > 0:
                        time.sleep(wait)
                    last = time.monotonic()
                    data = streamer.jpeg(rotate)
                    if data is None:
                        continue
                    self.wfile.write(
                        f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\n"
                        f"Content-Length: {len(data)}\r\n\r\n".encode()
                        + data
                        + b"\r\n"
                    )
            except (BrokenPipeError, ConnectionResetError):
                return  # the viewer went away

    return Handler
