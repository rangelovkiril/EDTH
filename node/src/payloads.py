"""Message bodies for the contract in docs/. Pure functions: no I/O."""


def detection_payload(
    node: str,
    t: float,
    az: float,
    el: float,
    conf: float,
    frame: int,
    position: tuple[float, float, float] | None = None,
) -> dict:
    az = round(az, 3) % 360.0
    if az >= 360.0:  # rounding a value just below 360
        az = 0.0
    payload = {
        "node": node,
        "t": round(t, 6),
        "az": az,
        "el": round(max(-90.0, min(90.0, el)), 3),
        "conf": round(max(0.0, min(1.0, conf)), 3),
        "frame": frame,
    }
    # With the position in every detection the broker can turn it into a ray on its own, and a
    # moving node (an aerostat) is placed where it was at that frame.
    if position is not None:
        payload.update(_position(position))
    return payload


def _position(position: tuple[float, float, float]) -> dict:
    lat, lon, alt_m = position
    return {"lat": round(lat, 7), "lon": round(lon, 7), "alt_m": round(alt_m, 2)}


def status_payload(
    node: str,
    t: float,
    fps: float,
    temp_c: float | None,
    clock_offset_ms: float | None,
    position: tuple[float, float, float] | None = None,
) -> dict:
    payload = {"node": node, "t": round(t, 6), "fps": round(fps, 2)}
    # Unavailable values are omitted, not null: EMQX maps absent fields to SQL NULL.
    if temp_c is not None:
        payload["temp_c"] = round(temp_c, 1)
    if clock_offset_ms is not None:
        payload["clock_offset_ms"] = round(clock_offset_ms, 2)
    if position is not None:
        payload.update(_position(position))
    return payload
