import urllib.error
import urllib.request

import cv2
import numpy as np
import pytest

from src.config import Config
from src.stream import Mark, Streamer


def fetch(streamer, path):
    return urllib.request.urlopen(f"http://127.0.0.1:{streamer.port}{path}", timeout=5)


def decode(data):
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


@pytest.fixture
def streamer():
    s = Streamer("rpi-1", port=0, rotate=0)
    s.start()
    yield s
    s.stop()


def frame(width=320, height=240):
    f = np.full((height, width, 3), 60, np.uint8)
    f[:, : width // 2] = (200, 30, 30)  # left half blue (BGR), so rotation is visible
    return f


def test_snapshot_is_a_jpeg_of_the_frame(streamer):
    with pytest.raises(urllib.error.HTTPError) as e:
        fetch(streamer, "/snapshot.jpg")
    assert e.value.code == 503  # nothing captured yet

    streamer.update(frame(), [])
    response = fetch(streamer, "/snapshot.jpg")
    data = response.read()
    assert response.headers["Content-Type"] == "image/jpeg" and data[:2] == b"\xff\xd8"
    image = decode(data)
    assert image.shape == (240, 320, 3)
    assert image[120, 40, 0] > 150  # blue on the left, as sent (BGR order is preserved)


def test_rotation_by_query_and_config():
    s = Streamer("rpi-1", port=0, rotate=90)
    s.start()
    try:
        s.update(frame(), [])
        assert decode(fetch(s, "/snapshot.jpg").read()).shape == (320, 240, 3)  # default 90
        assert decode(fetch(s, "/snapshot.jpg?rotate=0").read()).shape == (240, 320, 3)
        assert decode(fetch(s, "/snapshot.jpg?rotate=bogus").read()).shape == (320, 240, 3)
    finally:
        s.stop()
    with pytest.raises(ValueError):
        Streamer("rpi-1", port=0, rotate=45)


def test_detections_are_drawn(streamer):
    streamer.update(frame(), [])
    plain = decode(fetch(streamer, "/snapshot.jpg").read())
    streamer.update(frame(), [Mark(u=240, v=120, conf=0.8, az=123.4, el=5.6)])
    marked = decode(fetch(streamer, "/snapshot.jpg").read())
    assert np.abs(marked.astype(int) - plain.astype(int)).sum() > 10_000
    green = (marked[..., 1] > 200) & (marked[..., 0] < 80) & (marked[..., 2] < 80)
    assert green.sum() > 50  # the circle and label


def test_mjpeg_stream_delivers_multipart_jpegs(streamer):
    streamer.update(frame(), [])
    response = fetch(streamer, "/stream.mjpg")
    assert response.headers["Content-Type"].startswith("multipart/x-mixed-replace")
    head = response.read(400)
    assert head.startswith(b"--edthframe\r\nContent-Type: image/jpeg\r\nContent-Length: ")
    assert b"\xff\xd8" in head
    response.close()


def test_page_and_unknown_paths(streamer):
    page = fetch(streamer, "/").read().decode()
    assert "stream.mjpg" in page and "rpi-1" in page
    assert "rotate=90" in fetch(streamer, "/?rotate=90").read().decode()
    with pytest.raises(urllib.error.HTTPError) as e:
        fetch(streamer, "/etc/passwd")
    assert e.value.code == 404


def test_encoding_is_shared_between_viewers(streamer, monkeypatch):
    calls = []
    real = cv2.imencode
    monkeypatch.setattr(cv2, "imencode", lambda *a, **k: calls.append(1) or real(*a, **k))
    streamer.update(frame(), [])
    for _ in range(5):
        assert streamer.jpeg()
    assert len(calls) == 1  # one frame, five viewers, one encode


def test_stream_config():
    assert Config.from_env({"NODE_ID": "x", "DRY_RUN": "1"}).stream_port is None
    cfg = Config.from_env(
        {"NODE_ID": "x", "DRY_RUN": "1", "STREAM_PORT": "8080", "STREAM_ROTATE": "90"}
    )
    assert (cfg.stream_port, cfg.stream_rotate) == (8080, 90)
    with pytest.raises(ValueError):
        Config.from_env({"NODE_ID": "x", "DRY_RUN": "1", "STREAM_ROTATE": "45"})
