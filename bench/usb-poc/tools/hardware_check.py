"""Check live camera health across repeated clock syncs; server must be running."""

import argparse
import json
import statistics
import time
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://127.0.0.1:8000")
parser.add_argument("--duration", type=float, default=30)
args = parser.parse_args()
if args.duration < 1:
    parser.error("--duration must be at least one second")


def read_state():
    with urllib.request.urlopen(args.url + "/api/state", timeout=3) as response:
        return json.load(response)


for _ in range(40):
    state = read_state()
    if state["mode"] != "live":
        raise SystemExit("Hardware validation requires live mode")
    if len(state["cameras"]) >= 2 and all(c["connected"] for c in state["cameras"]):
        break
    time.sleep(0.25)

samples = []
started = time.monotonic()
while time.monotonic() - started < args.duration:
    state = read_state()
    samples.append(state)
    time.sleep(0.25)

timings = [s["pair_timing_ms"] for s in samples if s["pair_timing_ms"] is not None]
result = {
    "duration_s": round(time.monotonic() - started, 2),
    "samples": len(samples),
    "both_online_samples": sum(
        len(s["cameras"]) >= 2 and all(c["connected"] for c in s["cameras"]) for s in samples
    ),
    "processed_frames": samples[-1]["frames_total"] - samples[0]["frames_total"],
    "median_pair_timing_ms": statistics.median(timings) if timings else None,
    "errors": sorted({c["error"] for s in samples for c in s["cameras"] if c["error"]}),
}
Path("data").mkdir(exist_ok=True)
Path("data/final-live-validation.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
if result["both_online_samples"] != len(samples) or result["processed_frames"] < 2:
    raise SystemExit("Hardware health check failed; inspect camera errors and server log")
