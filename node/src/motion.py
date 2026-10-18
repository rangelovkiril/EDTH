from dataclasses import dataclass

import cv2
import numpy as np

from .detector import Detection


@dataclass
class Track:
    """One moving blob, filtered with a constant-velocity alpha-beta filter (a steady-state Kalman).

    Positions and velocities are pixels and pixels per frame.
    """

    id: int
    x: np.ndarray  # filtered position
    birth: np.ndarray  # where it was first seen
    v: np.ndarray = None  # velocity
    seen: tuple = (0.0, 0.0)  # the last measured centre, which is what gets reported
    hits: int = 1
    missed: int = 0

    def __post_init__(self):
        if self.v is None:
            self.v = np.zeros(2)

    def predicted(self) -> np.ndarray:
        return self.x + self.v

    @property
    def speed(self) -> float:
        return float(np.hypot(*self.v))


class MotionDetector:
    """MOG2 background subtraction, then a tracker that reports only fast, travelling blobs.

    No aircraft classifier. Each blob becomes a track with a position and a velocity; a new blob is
    matched to where a track is predicted to be, so a fast target that jumps far between frames
    keeps its track (a track seen only once has no velocity yet and gets the wider `acquire` gate).
    A track is reported once it has been seen `min_hits` frames in a row, moves faster than
    `min_speed` and has travelled `min_travel` from where it started: flicker and things that
    shuffle on the spot never are. At most `max_reports` per frame, fastest first.
    Distances are fractions of the frame width, so they hold at any resolution.
    """

    ALPHA, BETA = 0.85, 0.5  # gains of the alpha-beta filter: trust the measurement, adapt fast

    def __init__(
        self,
        threshold=20,
        min_area=5,
        max_blobs=30,
        min_hits=3,
        min_speed=0.005,
        min_travel=0.04,
        gate=0.08,
        acquire=0.2,
        max_missed=2,
        max_reports=3,
    ):
        self.threshold = threshold
        self.min_area = min_area
        self.max_blobs = max_blobs
        self.min_hits = min_hits
        self.min_speed = min_speed
        self.min_travel = min_travel
        self.gate = gate
        self.acquire = acquire
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
            and np.hypot(*(t.x - t.birth)) >= self.min_travel * width
        ]
        moving.sort(key=lambda t: t.speed, reverse=True)
        # Heuristic: confidence grows with persistence, never reaches certainty.
        return [
            Detection(*t.seen, conf=min(0.95, 0.4 + 0.1 * t.hits))
            for t in moving[: self.max_reports]
        ]

    def _update_tracks(self, centers: list[tuple], width: int) -> None:
        # Global nearest-neighbour against the predicted positions, one blob per track. The gate
        # widens with speed, so a target that speeds up between frames is not lost.
        pairs = sorted(
            (float(np.hypot(*(np.array(c) - t.predicted()))), ti, ci)
            for ti, t in enumerate(self.tracks)
            for ci, c in enumerate(centers)
        )
        used_t, used_c = set(), set()
        for distance, ti, ci in pairs:
            t = self.tracks[ti]
            # a track seen once has no velocity yet: a wider gate lets a fast target be acquired
            gate = self.acquire * width if t.hits == 1 else self.gate * width + 1.5 * t.speed
            if ti in used_t or ci in used_c or distance > gate:
                continue
            z = np.array(centers[ci])
            p = t.predicted()
            r = z - p
            t.x = p + self.ALPHA * r
            t.v = t.v + self.BETA * r
            t.seen = centers[ci]
            t.hits += 1
            t.missed = 0
            used_t.add(ti)
            used_c.add(ci)
        for ti, t in enumerate(self.tracks):
            if ti not in used_t:
                t.x = t.predicted()  # coast on the velocity through a missed frame
                t.missed += 1
        self.tracks = [t for t in self.tracks if t.missed <= self.max_missed]
        for ci, c in enumerate(centers):
            if ci not in used_c:
                z = np.array(c)
                self.tracks.append(Track(self.next_id, z, z.copy(), seen=c))
                self.next_id += 1
