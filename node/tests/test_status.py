import time

from src.config import Config
from src.publisher import DryRunPublisher
from src.status import StatusReporter, read_temp_c


def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_health_file_moves_only_while_frames_flow(tmp_path):
    cfg = Config.from_env({"NODE_ID": "rpi-1", "DRY_RUN": "1"})
    health = tmp_path / "alive"
    reporter = StatusReporter(
        DryRunPublisher(cfg), "127.0.0.1", interval=0.05, ntp_every=1e9, health_file=str(health)
    )
    reporter.start()
    try:
        time.sleep(0.5)
        assert not health.exists()  # no frames yet: not alive
        reporter.tick()
        assert wait_for(health.exists)
        time.sleep(0.2)
        first = health.stat().st_mtime
        time.sleep(0.3)
        assert health.stat().st_mtime == first  # no new frames: the file stops moving
    finally:
        reporter.stop()


def test_missing_thermal_zone_is_none(tmp_path):
    assert read_temp_c(tmp_path / "nope") is None
    f = tmp_path / "temp"
    f.write_text("54200\n")
    assert read_temp_c(f) == 54.2
