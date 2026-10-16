"""Reconnectable adapters; only the newest frame is kept (no latency backlog)."""

import logging
import struct
import threading
import time
import zlib
from dataclasses import dataclass

import cv2
import numpy as np
import serial

MAGIC = b"SKYCAM01"
HEADER = struct.Struct("<IIQI")  # payload bytes, sequence, capture uptime us, CRC32
MAX_JPEG = 2_000_000


def decode_clock_reply(buffer, nonce):
    """Ignore old replies/boot output; accept only this request's clock sample."""
    while True:
        start = buffer.find(b"SKYTIME2")
        if start < 0:
            del buffer[: max(0, len(buffer) - 7)]
            return None
        del buffer[:start]
        if len(buffer) < 20:
            return None
        received_nonce, device_us = struct.unpack_from("<IQ", buffer, 8)
        del buffer[:20]
        if received_nonce == nonce:
            return device_us


def clock_offset(start, end, device_us):
    """Offset interval from a timestamp generated between request and reply arrival.

    This measures communication uncertainty; it does not assume symmetric USB delay.
    """
    if end < start:
        raise ValueError("Clock sample reversed")
    return (start + end) / 2 - device_us / 1e6, (end - start) / 2


def decode_packet(buffer, on_invalid=None):
    """Consume a resynchronizing bytearray; return None until a valid JPEG packet."""
    while True:
        start = buffer.find(MAGIC)
        if start < 0:
            del buffer[: max(0, len(buffer) - len(MAGIC) + 1)]
            return None
        if start:
            del buffer[:start]
        if len(buffer) < 28:
            return None
        size, sequence, capture_us, crc = HEADER.unpack_from(buffer, 8)
        if not 4 <= size <= MAX_JPEG:
            del buffer[:8]
            continue
        if len(buffer) < 28 + size:
            return None
        payload = bytes(buffer[28 : 28 + size])
        del buffer[: 28 + size]
        if zlib.crc32(payload) != crc:
            logging.warning("Dropped corrupt camera packet sequence=%s", sequence)
            if on_invalid is not None:
                on_invalid()
            continue
        frame = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
        if frame is not None:
            return frame, sequence, capture_us
        logging.warning("Dropped undecodable camera JPEG sequence=%s bytes=%s", sequence, size)
        if on_invalid is not None:
            on_invalid()


@dataclass
class Frame:
    image: np.ndarray
    timestamp: float  # host monotonic estimate, never device uptime compared across cameras
    uncertainty: float
    sequence: int


class Source:
    def __init__(self, config):
        self.config = config
        self.latest = None
        self.error = "Waiting for camera"
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.handle = None

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=4)

    def read(self):
        with self.lock:
            return self.latest, self.error

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.capture()
            except Exception as exc:
                if self.stop_event.is_set():
                    break
                with self.lock:
                    # Avoid exposing credentials embedded in RTSP URLs.
                    reason = (
                        str(exc)
                        if self.config["type"] == "serial"
                        and isinstance(exc, (TimeoutError, ValueError))
                        else "check camera connection and permissions"
                    )
                    self.error = f"{type(exc).__name__}: {reason}"
                    self.latest = None
                logging.warning("Camera %s: %s", self.config.get("name", "?"), self.error)
                self.stop_event.wait(1)
            finally:
                if self.handle is not None:
                    if hasattr(self.handle, "release"):
                        self.handle.release()
                    else:
                        self.handle.close()
                    self.handle = None

    def capture(self):
        cfg = self.config
        kind = cfg["type"]
        if kind == "serial":
            self.handle = serial.Serial(
                cfg["source"], cfg.get("baud", 921600), timeout=0.1, write_timeout=1
            )
            self.handle.dtr = True
            self.handle.rts = False
            self.stop_event.wait(1)
            self.handle.reset_input_buffer()
        else:
            source = cfg["source"]
            if kind == "stream":
                self.handle = cv2.VideoCapture(
                    source,
                    cv2.CAP_FFMPEG,
                    [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000],
                )
            else:
                self.handle = cv2.VideoCapture(source)
            if not self.handle.isOpened():
                raise OSError("Cannot open video source")
            self.handle.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if kind == "usb":
                self.handle.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.get("width", 640))
                self.handle.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.get("height", 480))
        sequence = 0
        sync_time, offset, clock_uncertainty = 0.0, 0.0, 0.0
        while not self.stop_event.is_set():
            if kind == "serial" and time.monotonic() - sync_time > 5:
                samples = []
                for _ in range(3):
                    nonce = time.monotonic_ns() & 0xFFFFFFFF
                    t0 = time.monotonic()
                    self.handle.write(b"T" + struct.pack("<I", nonce))
                    reply = bytearray()
                    device_us = None
                    while device_us is None and time.monotonic() - t0 < 0.75:
                        if self.stop_event.is_set():
                            return
                        reply.extend(self.handle.read(max(1, min(self.handle.in_waiting, 65536))))
                        device_us = decode_clock_reply(reply, nonce)
                    t1 = time.monotonic()
                    if device_us is None:
                        raise TimeoutError("Clock reply missing; update skycam firmware")
                    samples.append(clock_offset(t0, t1, device_us))
                offset, clock_uncertainty = min(samples, key=lambda sample: sample[1])
                sync_time = time.monotonic()
            start = time.monotonic()
            if kind == "serial":
                # One outstanding request per camera; firmware returns a recent captured frame.
                self.handle.write(b"F")
                buffer = bytearray()
                received_bytes = 0
                packet = None
                retries = 0

                def retry_frame():
                    nonlocal retries
                    retries += 1
                    if retries <= 3:
                        self.handle.write(b"F")

                while (
                    packet is None and time.monotonic() - start < 3 and not self.stop_event.is_set()
                ):
                    chunk = self.handle.read(max(1, min(self.handle.in_waiting, 65536)))
                    received_bytes += len(chunk)
                    buffer.extend(chunk)
                    packet = decode_packet(buffer, on_invalid=retry_frame)
                if self.stop_event.is_set():
                    return
                if packet is None:
                    expected = (
                        HEADER.unpack_from(buffer, 8)[0]
                        if buffer.startswith(MAGIC) and len(buffer) >= 28
                        else None
                    )
                    raise TimeoutError(
                        f"No camera packet (received {received_bytes}, "
                        f"buffered {len(buffer)}, expected {expected})"
                    )
                image, sequence, capture_us = packet
            else:
                ok, image = self.handle.read()
                if not ok:
                    if kind == "file":
                        self.handle.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    raise OSError("Video disconnected")
                sequence += 1
            end = time.monotonic()
            if kind == "serial":
                timestamp = capture_us / 1e6 + offset
                # Add 100 ppm drift allowance and 40 ms exposure/readout allowance.
                # This is estimated synchronization, not a hardware trigger or timing guarantee.
                uncertainty = (
                    clock_uncertainty
                    + 0.0001 * (end - sync_time)
                    + cfg.get("exposure_uncertainty_s", 0.04)
                )
                if timestamp > end + clock_uncertainty or timestamp < end - 1:
                    raise ValueError("Camera timestamp outside acquisition window")
            else:
                timestamp = (start + end) / 2
                uncertainty = cfg.get("timing_uncertainty_s", 10.0)
            frame = Frame(image, timestamp, uncertainty, sequence)
            with self.lock:
                self.latest, self.error = frame, None
            fps = cfg.get("fps", 10)
            self.stop_event.wait(max(0, 1 / fps - (time.monotonic() - start)))


def demo_frame(model, t):
    """Synthetic pixels enter the SAME detector as real frames; no canned detections."""
    w, h = model.size
    image = np.zeros((h, w, 3), np.uint8)
    image[:] = np.linspace([99, 65, 40], [175, 135, 85], h).astype(np.uint8)[:, None, :]
    for cx, cy in [(100, 120), (440, 80), (290, 320)]:
        cv2.ellipse(image, (cx, cy), (75, 12), 0, 0, 360, (166, 140, 112), -1)
    # Known 3D trajectory is used ONLY to render images, never supplied to detection/fusion.
    point = [7 * np.sin(t * 0.22), -2 + 1.3 * np.sin(t * 0.41), 28 + 4 * np.sin(t * 0.13)]
    uv, _ = model.project([point])
    x, y = np.rint(uv[0]).astype(int)
    silhouette = np.array(
        [[-13, 0], [-3, -2], [0, -9], [3, -2], [13, 0], [3, 2], [3, 6], [0, 4], [-3, 6], [-3, 2]]
    )
    cv2.fillPoly(image, [silhouette + [x, y]], (26, 31, 36))
    return image
