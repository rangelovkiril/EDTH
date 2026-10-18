"""Frame sources. `open_camera` picks one from CAMERA_DEVICE:

  csi        Raspberry Pi camera through libcamera/picamera2 (Camera Module 3, HQ, ...)
  0, 1, ...  a V4L2 device (USB camera)
  <path>     a video file, for development

Every source has `read()` (BGR uint8 frame or None), `close()` and `captured_at`: the Unix time of
the last frame when the source knows it, else None (the caller then uses the time of the read).
A source may also have `hfov_deg`, its horizontal field of view once known (see PiCamera).
"""

import math
import time

import numpy as np


class Camera:
    """V4L2 camera or video file, through OpenCV."""

    captured_at: float | None = None

    def __init__(self, device: str = "0", width: int = 640, height: int = 480):
        import cv2

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


# Horizontal field of view of the whole sensor array, degrees, from the Raspberry Pi datasheets.
# Keyed by libcamera's sensor model. The HQ camera (imx477) is left out: its lens is swappable.
SENSOR_HFOV_DEG = {
    "ov5647": 53.5,  # Camera Module v1
    "imx219": 62.2,  # Camera Module v2
    "imx708": 66.0,  # Camera Module 3
    "imx708_wide": 102.0,  # Camera Module 3 Wide
    "imx708_noir": 66.0,
    "imx708_wide_noir": 102.0,
}


def scaled_hfov_deg(full_hfov_deg: float, array_width: int, crop_width: int) -> float:
    """HFOV of a frame made from `crop_width` of the sensor's `array_width` columns."""
    ratio = min(crop_width / array_width, 1.0)
    return math.degrees(2 * math.atan(ratio * math.tan(math.radians(full_hfov_deg) / 2)))


class PiCamera:
    """Raspberry Pi CSI camera. Needs picamera2 + libcamera (apt: python3-picamera2).

    `model` is the sensor name. `hfov_deg` is the horizontal field of view of the frames being
    delivered (None for a sensor we have no datasheet value for): the sensor mode can crop, so it is
    worked out from the ISP's ScalerCrop of the first frame, not just from the model.
    """

    def __init__(self, width: int = 1280, height: int = 720, fps: float = 30.0):
        try:
            from libcamera import controls
            from picamera2 import Picamera2
        except ImportError as e:
            raise RuntimeError(
                "CAMERA_DEVICE=csi needs picamera2 and libcamera (apt: python3-picamera2); "
                "they are part of the container image"
            ) from e
        self.captured_at: float | None = None
        self.hfov_deg: float | None = None
        self.cam = Picamera2()
        props = self.cam.camera_properties
        self.model: str = props.get("Model", "unknown")
        self._full_hfov = SENSOR_HFOV_DEG.get(self.model)
        self._array_width = (props.get("PixelArraySize") or (0, 0))[0]
        # "RGB888" is laid out B, G, R in memory, which is OpenCV's order.
        config = self.cam.create_video_configuration(
            main={"size": (width, height), "format": "RGB888"},
            controls={"FrameRate": fps},
            buffer_count=4,
        )
        self.cam.configure(config)
        self.cam.start()
        # The targets are far away: fix the focus at infinity rather than let autofocus hunt on sky.
        if "LensPosition" in self.cam.camera_controls:
            self.cam.set_controls({"AfMode": controls.AfModeEnum.Manual, "LensPosition": 0.0})

    def read(self) -> np.ndarray | None:
        request = self.cam.capture_request()
        try:
            frame = np.ascontiguousarray(request.make_array("main"))
            metadata = request.get_metadata()
        finally:
            request.release()
        self.captured_at = _sensor_time_to_unix(metadata.get("SensorTimestamp"))
        crop = metadata.get("ScalerCrop")
        if self.hfov_deg is None and crop and self._full_hfov and self._array_width:
            self.hfov_deg = scaled_hfov_deg(self._full_hfov, self._array_width, crop[2])
        return frame

    def close(self) -> None:
        self.cam.stop()
        self.cam.close()


def _sensor_time_to_unix(stamp_ns: int | None) -> float | None:
    """libcamera's SensorTimestamp is CLOCK_BOOTTIME nanoseconds; return Unix seconds.

    Returns None when the stamp is missing or implausible (the caller falls back to now).
    """
    if stamp_ns is None:
        return None
    age = (time.clock_gettime_ns(time.CLOCK_BOOTTIME) - stamp_ns) / 1e9
    return time.time() - age if 0 <= age < 5 else None


def open_camera(device: str, width: int, height: int, fps: float = 30.0):
    if device == "csi":
        return PiCamera(width, height, fps)
    return Camera(device, width, height)
