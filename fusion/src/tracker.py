"""Fixes in, tracks with a prediction and a confidence out. No I/O: the caller passes the time.

The nodes have already crossed their rays (each fix is a 3D point from two nodes); all that is
left for the ground is to say which fixes are the same object and to smooth them: a constant
velocity Kalman filter per track.
"""

import logging
import math
from dataclasses import dataclass, field

import numpy as np

from .config import Config
from .geo import LocalFrame

log = logging.getLogger("edth.tracker")


@dataclass(eq=False)
class Track:
    x: np.ndarray  # e, n, u, ve, vn, vu
    P: np.ndarray
    t: float  # time of the state, node clock of the last fix
    seen: float  # local time of the last fix
    id: int = 0  # 0 until confirmed, so published ids count up without gaps
    hits: int = 1
    conf_sum: float = 0.0
    pairs: set = field(default_factory=set)

    @property
    def pos(self) -> np.ndarray:
        return self.x[:3]

    @property
    def vel(self) -> np.ndarray:
        return self.x[3:]


def _transition(dt: float, accel: float):
    F = np.eye(6)
    F[:3, 3:] = np.eye(3) * dt
    q = accel**2
    Q = np.zeros((6, 6))
    Q[:3, :3] = np.eye(3) * q * dt**3 / 3
    Q[:3, 3:] = Q[3:, :3] = np.eye(3) * q * dt**2 / 2
    Q[3:, 3:] = np.eye(3) * q * dt
    return F, Q


def predict(x, P, dt: float, accel: float):
    F, Q = _transition(max(dt, 0.0), accel)
    return F @ x, F @ P @ F.T + Q


class Tracker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.frame = LocalFrame(*cfg.origin) if cfg.origin else None
        self.tracks: list[Track] = []
        self._next_id = 1

    def on_fix(self, fix: dict, now: float) -> Track | None:
        """Add one fix; return its track if that track is confirmed."""
        cfg = self.cfg
        if self.frame is None:
            self.frame = LocalFrame(fix["lat"], fix["lon"], fix["alt_m"])
            log.info(
                "event=origin lat=%.7f lon=%.7f alt=%.1f", fix["lat"], fix["lon"], fix["alt_m"]
            )
        z = self.frame.to_enu(float(fix["lat"]), float(fix["lon"]), float(fix["alt_m"]))
        t = float(fix["t"])
        sigma = cfg.fix_sigma_m + float(fix["miss_m"]) / 2
        R = np.eye(3) * sigma**2

        best, best_d = None, cfg.gate_m
        for tr in self.tracks:
            x, _ = predict(tr.x, tr.P, t - tr.t, cfg.accel_mps2)
            d = float(np.linalg.norm(x[:3] - z))
            if d < best_d:
                best, best_d = tr, d
        if best is None:
            P = np.diag([sigma**2] * 3 + [cfg.initial_speed_mps**2] * 3)
            best = Track(np.concatenate([z, np.zeros(3)]), P, t, now)
            self.tracks.append(best)
        else:
            x, P = predict(best.x, best.P, t - best.t, cfg.accel_mps2)
            H = np.hstack([np.eye(3), np.zeros((3, 3))])
            S = H @ P @ H.T + R
            K = P @ H.T @ np.linalg.inv(S)
            best.x = x + K @ (z - H @ x)
            best.P = (np.eye(6) - K @ H) @ P
            best.t = max(best.t, t)
            best.hits += 1
        best.seen = now
        best.conf_sum += float(fix["conf"])
        best.pairs.add(tuple(sorted((fix["node"], fix["peer"]))))
        if not best.id and best.hits >= cfg.confirm_hits:
            best.id = self._next_id
            self._next_id += 1
            log.info("event=track_new id=%d enu=%s", best.id, np.round(best.pos, 1))
        return best if best.id else None

    def expire(self, now: float) -> None:
        for tr in [t for t in self.tracks if now - t.seen > self.cfg.track_timeout_s]:
            if tr.id:
                log.info("event=track_lost id=%d hits=%d", tr.id, tr.hits)
            self.tracks.remove(tr)

    def report(self, now: float, clock_t: float) -> list[dict]:
        """Every confirmed track, predicted to `clock_t` (the nodes' clock, roughly now)."""
        out = []
        for tr in self.tracks:
            if not tr.id:
                continue
            x, P = predict(tr.x, tr.P, clock_t - tr.t, self.cfg.accel_mps2)
            out.append(self._payload(tr, x, P, now, clock_t))
        return out

    def _payload(self, tr: Track, x, P, now: float, clock_t: float) -> dict:
        cfg = self.cfg
        horizon = cfg.horizon_s
        xp, Pp = predict(x, P, horizon, cfg.accel_mps2)
        sigma = math.sqrt(np.trace(P[:3, :3]) / 3)
        sigma_pred = math.sqrt(np.trace(Pp[:3, :3]) / 3)
        lat, lon, alt = self.frame.to_lla(x[:3])
        plat, plon, palt = self.frame.to_lla(xp[:3])
        ve, vn, vu = (float(v) for v in x[3:])
        # Confidence: how sure the position is, how much evidence there is, how fresh it is.
        conf = (
            math.exp(-sigma / cfg.conf_sigma_m)
            * (1 - math.exp(-tr.hits / 5))
            * math.exp(-(now - tr.seen) / cfg.track_timeout_s)
            * min(1.0, tr.conf_sum / tr.hits * 2)
        )
        r = lambda v, n=2: round(float(v), n)  # noqa: E731
        return {
            "id": tr.id,
            "t": round(clock_t, 3),
            "lat": round(lat, 7),
            "lon": round(lon, 7),
            "alt_m": r(alt),
            "e": r(x[0]),
            "n": r(x[1]),
            "u": r(x[2]),
            "ve": r(ve),
            "vn": r(vn),
            "vu": r(vu),
            "speed_mps": r(math.sqrt(ve * ve + vn * vn + vu * vu)),
            "heading_deg": r(math.degrees(math.atan2(ve, vn)) % 360.0, 1),
            "pred_lat": round(plat, 7),
            "pred_lon": round(plon, 7),
            "pred_alt_m": r(palt),
            "horizon_s": horizon,
            "sigma_m": r(sigma, 3),
            "pred_sigma_m": r(sigma_pred, 3),
            "conf": r(conf, 3),
            "pairs": len(tr.pairs),
            "hits": tr.hits,
        }
