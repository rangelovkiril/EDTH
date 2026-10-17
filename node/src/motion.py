from dataclasses import dataclass, field

import cv2
import numpy as np

from .detector import Detection


@dataclass
class Track:
    id: int
    center: tuple
    box: tuple
    hits: int = 1
    missed: int = 0
    trail: list = field(default_factory=list)


class MotionDetector:
    """Baseline MOG2 background subtractor with a small nearest-neighbour tracker.

    No aircraft classifier: anything small and persistently moving is reported.
    """

    def __init__(self, threshold=20, min_area=5, max_blobs=30):
        self.threshold = threshold
        self.min_area = min_area
        self.max_blobs = max_blobs
        self.background = cv2.createBackgroundSubtractorMOG2(
            history=200, varThreshold=threshold, detectShadows=False
        )
        self.frames = 0
        self.tracks = []
        self.next_id = 1

    def detect(self, frame: np.ndarray) -> list[Detection]:
        self.frames += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mask = self.background.apply(gray, learningRate=0.015)
        # Do not erode tiny targets. Reject global exposure shifts / camera movement.
        fraction = np.count_nonzero(mask) / mask.size
        boxes = []
        if self.frames > 15 and fraction <= 0.12:
            count, _, stats, centers = cv2.connectedComponentsWithStats(mask)
            for i in range(1, count):
                x, y, w, h, area = stats[i]
                if (
                    self.min_area <= area <= mask.size * 0.015
                    and max(w, h) < max(mask.shape) * 0.25
                ):
                    boxes.append((tuple(map(float, centers[i])), (int(x), int(y), int(w), int(h))))
        if len(boxes) > self.max_blobs:
            boxes = []  # hundreds of blobs: a moving camera or noise, and tracking them stalls us
        self._update_tracks(boxes)
        confirmed = [t for t in self.tracks if t.hits >= 3 and t.missed == 0]
        # Heuristic: confidence grows with persistence, never reaches certainty.
        return [Detection(*t.center, conf=min(0.95, 0.4 + 0.1 * t.hits)) for t in confirmed]

    def _update_tracks(self, boxes):
        # Global nearest-neighbour, one detection per track.
        pairs = sorted(
            (np.linalg.norm(np.array(t.center) - center), ti, bi)
            for ti, t in enumerate(self.tracks)
            for bi, (center, _) in enumerate(boxes)
        )
        used_t, used_b = set(), set()
        for distance, ti, bi in pairs:
            if distance > 65 or ti in used_t or bi in used_b:
                continue
            t = self.tracks[ti]
            t.center, t.box = boxes[bi]
            t.hits += 1
            t.missed = 0
            t.trail = (t.trail + [t.center])[-32:]
            used_t.add(ti)
            used_b.add(bi)
        for ti, t in enumerate(self.tracks):
            if ti not in used_t:
                t.missed += 1
        self.tracks = [t for t in self.tracks if t.missed <= 5]
        for bi, (center, box) in enumerate(boxes):
            if bi not in used_b:
                self.tracks.append(Track(self.next_id, center, box, trail=[center]))
                self.next_id += 1
