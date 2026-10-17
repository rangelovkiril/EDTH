import socket
import struct
import threading
import time

import pytest

from src.clock import NTP_EPOCH_OFFSET, ntp_offset_ms


def fake_ntp_server(skew_s):
    """UDP server whose clock is `skew_s` ahead of ours."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))

    def serve():
        _, addr = sock.recvfrom(512)
        now = time.time() + skew_s + NTP_EPOCH_OFFSET
        sec, frac = int(now), int((now % 1) * 2**32)
        reply = bytearray(48)
        reply[32:48] = struct.pack("!4I", sec, frac, sec, frac)
        sock.sendto(bytes(reply), addr)
        sock.close()

    threading.Thread(target=serve, daemon=True).start()
    return sock.getsockname()[1]


@pytest.mark.parametrize("skew", [0.0, 0.5, -0.25])
def test_offset_sign_and_size(skew):
    offset = ntp_offset_ms("127.0.0.1", port=fake_ntp_server(skew))
    # server ahead by `skew` => local clock is behind => negative offset
    assert offset == pytest.approx(-skew * 1000, abs=20)


def test_unreachable_server_is_none():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    assert ntp_offset_ms("127.0.0.1", port=port, timeout=0.2) is None
    s.close()
