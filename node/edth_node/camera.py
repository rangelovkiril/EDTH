import cv2
import numpy as np


class Camera:
    """Frame source. `device` is a V4L2 index ("0") or a video file path."""

    def __init__(self, device: str = "0", width: int = 640, height: int = 480):
        source = int(device) if device.isdigit() else device
        backend = cv2.CAP_V4L2 if isinstance(source, int) else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(source, backend)
        if not self.cap.isOpened():
            raise RuntimeError(f"cannot open camera {device!r}")
        if isinstance(source, int):
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def read(self) -> np.ndarray | None:
        """Next BGR frame, or None when the source has ended or failed."""
        ok, frame = self.cap.read()
        return frame if ok else None

    def close(self) -> None:
        self.cap.release()
