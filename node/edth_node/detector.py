from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Detection:
    """One object in a frame: pixel centre (x right, y down) and confidence in [0, 1]."""

    u: float
    v: float
    conf: float


class Detector(Protocol):
    def detect(self, frame: np.ndarray) -> list[Detection]:
        """`frame` is a BGR uint8 image. Return zero or more detections."""
        ...
