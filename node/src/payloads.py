"""Message bodies for the contract in docs/. Pure functions: no I/O."""


def detection_payload(node: str, t: float, az: float, el: float, conf: float, frame: int) -> dict:
    az = round(az, 3) % 360.0
    if az >= 360.0:  # rounding a value just below 360
        az = 0.0
    return {
        "node": node,
        "t": round(t, 6),
        "az": az,
        "el": round(max(-90.0, min(90.0, el)), 3),
        "conf": round(max(0.0, min(1.0, conf)), 3),
        "frame": frame,
    }


def status_payload(
    node: str, t: float, fps: float, temp_c: float | None, clock_offset_ms: float | None
) -> dict:
    payload = {"node": node, "t": round(t, 6), "fps": round(fps, 2)}
    # Unavailable values are omitted, not null: EMQX maps absent fields to SQL NULL.
    if temp_c is not None:
        payload["temp_c"] = round(temp_c, 1)
    if clock_offset_ms is not None:
        payload["clock_offset_ms"] = round(clock_offset_ms, 2)
    return payload
