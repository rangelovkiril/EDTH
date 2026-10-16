"""Regenerate protocol/test-vectors/vectors.json from the Python codec."""

import dataclasses
import json
from pathlib import Path

import trwire as w

T = 1_760_700_000_123_456

MESSAGES = {
    "detection_batch_two": w.DetectionBatch(
        node_id=1,
        seq=812,
        flags=w.FLAG_TIME_SYNCED,
        t_capture_us=T,
        frame_id=4512,
        width=320,
        height=240,
        detections=(
            w.Detection(cx_q3=1281, cy_q3=644, w=12, h=9, area=80, conf_u8=204),
            w.Detection(cx_q3=2400, cy_q3=100, w=3, h=2, area=5, conf_u8=51),
        ),
    ),
    "status": w.Status(
        node_id=21,
        seq=65535,
        flags=w.FLAG_TIME_SYNCED,
        uptime_ms=912345,
        sync_age_ms=4200,
        clock_offset_us=-132,
        rtt_us=2310,
        fps_x10=145,
        dropped_frames=3,
        rssi_dbm=-54,
        temp_c=61,
    ),
    "status_never_synced": w.Status(
        node_id=2,
        seq=0,
        flags=0,
        uptime_ms=1000,
        sync_age_ms=w.SYNC_AGE_NEVER,
        clock_offset_us=0,
        rtt_us=0,
        fps_x10=0,
        dropped_frames=0,
        rssi_dbm=0,
        temp_c=w.TEMP_NA,
    ),
    "tsync_req": w.TsyncReq(node_id=2, seq=7, flags=0, t1_us=123_456_789),
    "tsync_resp": w.TsyncResp(node_id=2, seq=7, flags=0, t1_us=123_456_789, t2_us=T, t3_us=T + 85),
}


def main() -> None:
    out = []
    for name, msg in MESSAGES.items():
        fields = dataclasses.asdict(msg)
        if "detections" in fields:
            fields["detections"] = [dict(d) for d in fields["detections"]]
        out.append(
            {"name": name, "kind": type(msg).__name__, "hex": w.encode(msg).hex(), "fields": fields}
        )
    path = Path(__file__).resolve().parents[1] / "test-vectors" / "vectors.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {len(out)} vectors to {path}")


if __name__ == "__main__":
    main()
