from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class Track:
    id: int
    center: tuple
    box: tuple
    hits: int = 1
    missed: int = 0
    trail: list = field(default_factory=list)


class MotionDetector:
    def __init__(self):
        self.background = cv2.createBackgroundSubtractorMOG2(
            history=200, varThreshold=20, detectShadows=False
        )
        self.frames = 0
        self.tracks = []
        self.next_id = 1

    def process(self, frame, threshold=20, min_area=5):
        self.frames += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.background.setVarThreshold(threshold)
        mask = self.background.apply(gray, learningRate=0.015)
        # Do not erode tiny targets. Reject global exposure shifts / camera movement.
        fraction = np.count_nonzero(mask) / mask.size
        suppressed = self.frames <= 15 or fraction > 0.12
        boxes = []
        if suppressed:
            mask[:] = 0
        else:
            count, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
            clean = np.zeros_like(mask)
            for i in range(1, count):
                x, y, w, h, area = stats[i]
                if min_area <= area <= mask.size * 0.015 and max(w, h) < max(mask.shape) * 0.25:
                    boxes.append((tuple(map(float, centers[i])), (int(x), int(y), int(w), int(h))))
                    clean[labels == i] = 255
            mask = clean
        # Global nearest-neighbour, one detection per track. No aircraft classifier.
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
        confirmed = [t for t in self.tracks if t.hits >= 3 and t.missed == 0]
        # Only persistent current tracks contribute to volume evidence.
        accepted = np.zeros_like(mask)
        for t in confirmed:
            x, y, w, h = t.box
            accepted[y : y + h, x : x + w] = mask[y : y + h, x : x + w]
        return accepted, confirmed, suppressed
