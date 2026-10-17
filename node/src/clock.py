import socket
import struct
import time

NTP_EPOCH_OFFSET = 2208988800  # 1900-01-01 to 1970-01-01


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
    t1 = sec2 - NTP_EPOCH_OFFSET + frac2 / 2**32  # server receive
    t2 = sec3 - NTP_EPOCH_OFFSET + frac3 / 2**32  # server transmit
    server_ahead = ((t1 - t0) + (t2 - t3)) / 2
    return -server_ahead * 1000.0
