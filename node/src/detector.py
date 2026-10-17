import importlib
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


def load_detector(spec: str) -> Detector:
    """Instantiate `module:Class`; a bare module name is looked up inside src.

    `motion:MotionDetector` -> src.motion.MotionDetector (no constructor arguments).
    """
    module_name, _, class_name = spec.partition(":")
    if not class_name:
        raise ValueError(f"DETECTOR must look like module:Class, got {spec!r}")
    if "." not in module_name:
        module_name = f"src.{module_name}"
    return getattr(importlib.import_module(module_name), class_name)()
