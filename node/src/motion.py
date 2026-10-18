from dataclasses import dataclass

import cv2
import numpy as np

from .detector import Detection

# Constant-velocity model in pixels, one step per frame: state (x, y, vx, vy), measured (x, y).
F = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]], float)
H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], float)
# Piecewise-constant acceleration between frames, per unit of acceleration variance.
_G = np.array([[0.5, 0, 1, 0], [0, 0.5, 0, 1]], float).T
Q_UNIT = _G @ _G.T


def _inv2(S: np.ndarray) -> np.ndarray:
    """Inverse of a 2x2 covariance; np.linalg.inv costs more than the rest of the tracker."""
    a, b, c, d = S[0, 0], S[0, 1], S[1, 0], S[1, 1]
    return np.array([[d, -b], [-c, a]]) / (a * d - b * c)


@dataclass
class Track:
    """One blob, followed by a Kalman filter. Pixels and pixels per frame."""

    id: int
    s: np.ndarray  # state x, y, vx, vy
    P: np.ndarray  # its covariance
    birth: np.ndarray  # where it was first seen
    seen: tuple  # the last measured centre, which is what gets reported
    hits: int = 1
    missed: int = 0

    def predict(self, Q: np.ndarray) -> None:
        self.s = F @ self.s
        self.P = F @ self.P @ F.T + Q

    def innovation(self, z: np.ndarray, R: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Measurement residual and its covariance."""
        return z - H @ self.s, H @ self.P @ H.T + R

    def update(self, z: np.ndarray, R: np.ndarray) -> None:
        r, S = self.innovation(z, R)
        K = self.P @ H.T @ _inv2(S)
        self.s = self.s + K @ r
        self.P = (np.eye(4) - K @ H) @ self.P

    @property
    def speed(self) -> float:
        return float(np.hypot(self.s[2], self.s[3]))


class MotionDetector:
    """MOG2 background subtraction, then a Kalman tracker that reports only fast, travelling blobs.

    No aircraft classifier. Each blob becomes a track with a position, a velocity and their
    uncertainty. A new blob joins the track whose prediction it falls inside, measured in that
    track's own uncertainty (Mahalanobis distance): a fresh track, whose velocity could be anything
    up to `max_speed`, accepts a blob far away, so a fast target is caught on its second frame; a
    settled track accepts only blobs near its prediction, so noise does not hijack it. `accel` is
    how hard a target may change velocity between frames (a thrown ball, a turning drone).

    A track is reported once it has been seen `min_hits` frames in a row, moves faster than
    `min_speed` and has travelled `min_travel` from where it started: flicker and things that
    shuffle on the spot never are. At most `max_reports` per frame, fastest first. Speeds and
    distances are fractions of the frame width (per frame), so they hold at any resolution.
    """

    def __init__(
        self,
        threshold=20,
        min_area=3,
        max_blobs=30,
        min_hits=4,
        min_speed=0.005,
        min_travel=0.04,
        max_speed=0.25,
        accel=0.01,
        pixel_sigma=1.5,
        gate_chi2=16.0,
        max_missed=2,
        max_reports=3,
    ):
        self.threshold = threshold
        self.min_area = min_area
        self.max_blobs = max_blobs
        self.min_hits = min_hits
        self.min_speed = min_speed
        self.min_travel = min_travel
        self.max_speed = max_speed
        self.accel = accel
        self.pixel_sigma = pixel_sigma
        self.gate_chi2 = gate_chi2  # 2 degrees of freedom: 16 keeps 99.97% of true matches
        self.max_missed = max_missed
        self.max_reports = max_reports
        self.background = cv2.createBackgroundSubtractorMOG2(
            history=200, varThreshold=threshold, detectShadows=False
        )
        self.frames = 0
        self.tracks: list[Track] = []
        self.next_id = 1

    def detect(self, frame: np.ndarray) -> list[Detection]:
        self.frames += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mask = self.background.apply(gray, learningRate=0.015)
        # Do not erode tiny targets. Reject global exposure shifts / camera movement.
        fraction = np.count_nonzero(mask) / mask.size
        centers = []
        if self.frames > 15 and fraction <= 0.12:
            count, _, stats, cents = cv2.connectedComponentsWithStats(mask)
            for i in range(1, count):
                x, y, w, h, area = stats[i]
                if (
                    self.min_area <= area <= mask.size * 0.015
                    and max(w, h) < max(mask.shape) * 0.25
                ):
                    centers.append(tuple(map(float, cents[i])))
        if len(centers) > self.max_blobs:
            centers = []  # hundreds of blobs: a moving camera or noise, and tracking them stalls us
        width = frame.shape[1]
        self._update_tracks(centers, width)
        moving = [
            t
            for t in self.tracks
            if t.hits >= self.min_hits
            and t.missed == 0
            and t.speed >= self.min_speed * width
            and np.hypot(*(t.s[:2] - t.birth)) >= self.min_travel * width
        ]
        moving.sort(key=lambda t: t.speed, reverse=True)
        # Heuristic: confidence grows with persistence, never reaches certainty.
        return [
            Detection(*t.seen, conf=min(0.95, 0.4 + 0.1 * t.hits))
            for t in moving[: self.max_reports]
        ]

    def _update_tracks(self, centers: list[tuple], width: int) -> None:
        Q = Q_UNIT * (self.accel * width) ** 2
        R = np.eye(2) * self.pixel_sigma**2
        for t in self.tracks:
            t.predict(Q)
        # Global nearest neighbour by Mahalanobis distance, one blob per track.
        pairs = []
        if centers:
            Z = np.array(centers)
            for ti, t in enumerate(self.tracks):
                r = Z - H @ t.s  # every blob's residual against this track at once
                d2 = np.einsum("ni,ij,nj->n", r, _inv2(t.P[:2, :2] + R), r)
                pairs += [(float(d2[ci]), ti, ci) for ci in np.flatnonzero(d2 <= self.gate_chi2)]
        used_t, used_c = set(), set()
        for _, ti, ci in sorted(pairs):
            if ti in used_t or ci in used_c:
                continue
            t = self.tracks[ti]
            t.update(np.array(centers[ci]), R)
            t.seen = centers[ci]
            t.hits += 1
            t.missed = 0
            used_t.add(ti)
            used_c.add(ci)
        for ti, t in enumerate(self.tracks):
            if ti not in used_t:
                t.missed += 1  # coasts on its prediction, growing less certain
        # A blob seen once and then not again was noise: only a confirmed track may coast.
        self.tracks = [
            t
            for t in self.tracks
            if t.missed == 0 or (t.hits >= self.min_hits and t.missed <= self.max_missed)
        ]
        v0 = (self.max_speed * width / 2) ** 2  # unknown velocity: within max_speed at 2 sigma
        for ci, c in enumerate(centers):
            if ci not in used_c:
                z = np.array(c)
                P = np.diag([R[0, 0], R[1, 1], v0, v0])
                s = np.array([z[0], z[1], 0.0, 0.0])
                self.tracks.append(Track(self.next_id, s, P, z.copy(), c))
                self.next_id += 1
