import json
from pathlib import Path

import pytest
import trwire as w

VECTORS = json.loads(
    (Path(__file__).resolve().parents[2] / "test-vectors" / "vectors.json").read_text()
)


def _build(v):
    cls = getattr(w, v["kind"])
    fields = dict(v["fields"])
    if "detections" in fields:
        fields["detections"] = tuple(w.Detection(**d) for d in fields["detections"])
    return cls(**fields)


@pytest.mark.parametrize("v", VECTORS, ids=[v["name"] for v in VECTORS])
def test_roundtrip(v):
    msg = _build(v)
    assert w.encode(msg).hex() == v["hex"]
    assert w.decode(bytes.fromhex(v["hex"])) == msg


def test_sizes():
    sizes = {v["name"]: len(bytes.fromhex(v["hex"])) for v in VECTORS}
    assert sizes["detection_batch_two"] == 28 + 2 * 12
    assert sizes["status"] == 32
    assert sizes["tsync_req"] == 16
    assert sizes["tsync_resp"] == 32


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"TR",
        b"XX\x01\x02\x01\x00\x00\x00" + bytes(24),
        b"TR\x09\x02\x01\x00\x00\x00" + bytes(24),
        b"TR\x01\x7f\x01\x00\x00\x00",
        b"TR\x01\x02\x01\x00\x00\x00" + bytes(23),
    ],
)
def test_rejects(data):
    with pytest.raises(w.WireError):
        w.decode(data)


def test_batch_count_bounds():
    good = bytes.fromhex(next(v["hex"] for v in VECTORS if v["name"] == "detection_batch_two"))
    zero = bytearray(good[:28])
    zero[24] = 0
    with pytest.raises(w.WireError):
        w.decode(bytes(zero))
    truncated = good[:-1]
    with pytest.raises(w.WireError):
        w.decode(truncated)


def test_from_px():
    d = w.Detection.from_px(160.125, 80.5, 12, 9, 80, 0.8)
    assert (d.cx, d.cy, d.conf_u8) == (160.125, 80.5, 204)
