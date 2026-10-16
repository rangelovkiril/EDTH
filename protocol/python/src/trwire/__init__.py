"""Triangulum message protocol v1 codec. Normative spec: docs/protocol.md."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAGIC = b"TR"
VERSION = 1

NODE_COLLECTOR = 100
NODE_GROUND = 110

TYPE_DETECTION_BATCH = 0x01
TYPE_STATUS = 0x02
TYPE_TSYNC_REQ = 0x10
TYPE_TSYNC_RESP = 0x11

FLAG_TIME_SYNCED = 0x01
FLAG_TEST = 0x02

MAX_DETECTIONS = 16
SYNC_AGE_NEVER = 0xFFFFFFFF
TEMP_NA = -128

_HDR = struct.Struct("<2sBBBBH")  # 8
_BATCH = struct.Struct("<QIHHB3x")  # 20
_DET = struct.Struct("<HHHHHBx")  # 12
_STATUS = struct.Struct("<IIiIHHbb2x")  # 24
_TREQ = struct.Struct("<Q")  # 8
_TRESP = struct.Struct("<QQQ")  # 24

assert _HDR.size == 8 and _BATCH.size == 20 and _DET.size == 12
assert _STATUS.size == 24 and _TREQ.size == 8 and _TRESP.size == 24


class WireError(ValueError):
    """Malformed or unsupported datagram."""


@dataclass(frozen=True)
class Detection:
    cx_q3: int
    cy_q3: int
    w: int
    h: int
    area: int
    conf_u8: int

    @classmethod
    def from_px(cls, cx: float, cy: float, w: int, h: int, area: int, conf: float) -> Detection:
        return cls(
            cx_q3=_clamp(round(cx * 8), 0, 0xFFFF),
            cy_q3=_clamp(round(cy * 8), 0, 0xFFFF),
            w=_clamp(w, 0, 0xFFFF),
            h=_clamp(h, 0, 0xFFFF),
            area=_clamp(area, 0, 0xFFFF),
            conf_u8=_clamp(round(conf * 255), 0, 255),
        )

    @property
    def cx(self) -> float:
        return self.cx_q3 / 8

    @property
    def cy(self) -> float:
        return self.cy_q3 / 8

    @property
    def conf(self) -> float:
        return self.conf_u8 / 255


@dataclass(frozen=True)
class DetectionBatch:
    node_id: int
    seq: int
    flags: int
    t_capture_us: int
    frame_id: int
    width: int
    height: int
    detections: tuple[Detection, ...] = field(default_factory=tuple)

    type = TYPE_DETECTION_BATCH


@dataclass(frozen=True)
class Status:
    node_id: int
    seq: int
    flags: int
    uptime_ms: int
    sync_age_ms: int
    clock_offset_us: int
    rtt_us: int
    fps_x10: int
    dropped_frames: int
    rssi_dbm: int
    temp_c: int

    type = TYPE_STATUS

    @property
    def fps(self) -> float:
        return self.fps_x10 / 10


@dataclass(frozen=True)
class TsyncReq:
    node_id: int
    seq: int
    flags: int
    t1_us: int

    type = TYPE_TSYNC_REQ


@dataclass(frozen=True)
class TsyncResp:
    node_id: int
    seq: int
    flags: int
    t1_us: int
    t2_us: int
    t3_us: int

    type = TYPE_TSYNC_RESP


Message = DetectionBatch | Status | TsyncReq | TsyncResp


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


def _hdr(msg: Message) -> bytes:
    return _HDR.pack(MAGIC, VERSION, msg.type, msg.node_id, msg.flags, msg.seq & 0xFFFF)


def encode(msg: Message) -> bytes:
    try:
        if isinstance(msg, DetectionBatch):
            n = len(msg.detections)
            if not 1 <= n <= MAX_DETECTIONS:
                raise WireError(f"detection count {n} outside 1..{MAX_DETECTIONS}")
            body = _BATCH.pack(msg.t_capture_us, msg.frame_id, msg.width, msg.height, n)
            dets = b"".join(
                _DET.pack(d.cx_q3, d.cy_q3, d.w, d.h, d.area, d.conf_u8) for d in msg.detections
            )
            return _hdr(msg) + body + dets
        if isinstance(msg, Status):
            body = _STATUS.pack(
                msg.uptime_ms,
                msg.sync_age_ms,
                msg.clock_offset_us,
                msg.rtt_us,
                msg.fps_x10,
                msg.dropped_frames,
                msg.rssi_dbm,
                msg.temp_c,
            )
            return _hdr(msg) + body
        if isinstance(msg, TsyncReq):
            return _hdr(msg) + _TREQ.pack(msg.t1_us)
        if isinstance(msg, TsyncResp):
            return _hdr(msg) + _TRESP.pack(msg.t1_us, msg.t2_us, msg.t3_us)
    except struct.error as e:
        raise WireError(str(e)) from e
    raise WireError(f"cannot encode {type(msg).__name__}")


def decode(data: bytes) -> Message:
    if len(data) < _HDR.size:
        raise WireError("short datagram")
    magic, version, mtype, node_id, flags, seq = _HDR.unpack_from(data, 0)
    if magic != MAGIC:
        raise WireError("bad magic")
    if version != VERSION:
        raise WireError(f"unsupported version {version}")
    body = memoryview(data)[_HDR.size :]
    common = dict(node_id=node_id, seq=seq, flags=flags)

    if mtype == TYPE_DETECTION_BATCH:
        if len(body) < _BATCH.size:
            raise WireError("short detection batch")
        t_us, frame_id, width, height, count = _BATCH.unpack_from(body, 0)
        if not 1 <= count <= MAX_DETECTIONS:
            raise WireError(f"detection count {count} outside 1..{MAX_DETECTIONS}")
        if len(body) != _BATCH.size + count * _DET.size:
            raise WireError("detection batch length mismatch")
        dets = tuple(
            Detection(*_DET.unpack_from(body, _BATCH.size + i * _DET.size)) for i in range(count)
        )
        return DetectionBatch(
            **common,
            t_capture_us=t_us,
            frame_id=frame_id,
            width=width,
            height=height,
            detections=dets,
        )
    if mtype == TYPE_STATUS:
        _expect(body, _STATUS.size, "status")
        return Status(
            **common,
            **dict(
                zip(
                    (
                        "uptime_ms",
                        "sync_age_ms",
                        "clock_offset_us",
                        "rtt_us",
                        "fps_x10",
                        "dropped_frames",
                        "rssi_dbm",
                        "temp_c",
                    ),
                    _STATUS.unpack(body),
                    strict=True,
                )
            ),
        )
    if mtype == TYPE_TSYNC_REQ:
        _expect(body, _TREQ.size, "tsync request")
        return TsyncReq(**common, t1_us=_TREQ.unpack(body)[0])
    if mtype == TYPE_TSYNC_RESP:
        _expect(body, _TRESP.size, "tsync response")
        t1, t2, t3 = _TRESP.unpack(body)
        return TsyncResp(**common, t1_us=t1, t2_us=t2, t3_us=t3)
    raise WireError(f"unknown type 0x{mtype:02x}")


def _expect(body: memoryview, size: int, what: str) -> None:
    if len(body) != size:
        raise WireError(f"{what}: expected {size} bytes, got {len(body)}")


__all__ = [
    "Detection",
    "DetectionBatch",
    "Status",
    "TsyncReq",
    "TsyncResp",
    "Message",
    "WireError",
    "encode",
    "decode",
    "MAGIC",
    "VERSION",
    "NODE_COLLECTOR",
    "NODE_GROUND",
    "TYPE_DETECTION_BATCH",
    "TYPE_STATUS",
    "TYPE_TSYNC_REQ",
    "TYPE_TSYNC_RESP",
    "FLAG_TIME_SYNCED",
    "FLAG_TEST",
    "MAX_DETECTIONS",
    "SYNC_AGE_NEVER",
    "TEMP_NA",
]
