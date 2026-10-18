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
from dataclasses import dataclass

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


@dataclass(frozen=True)
class Sensor:
    hfov_deg: float  # horizontal field of view of the whole array, from the datasheet
    array: tuple[int, int]  # pixel array, columns x rows
    binned: tuple[int, int]  # the 2x2-binned sensor mode, which still sees the whole array


# Keyed by libcamera's sensor model. The HQ camera (imx477) is left out: its lens is swappable.
SENSORS = {
    "ov5647": Sensor(53.5, (2592, 1944), (1296, 972)),  # Camera Module v1
    "imx219": Sensor(62.2, (3280, 2464), (1640, 1232)),  # Camera Module v2
    "imx708": Sensor(66.0, (4608, 2592), (2304, 1296)),  # Camera Module 3
    "imx708_wide": Sensor(102.0, (4608, 2592), (2304, 1296)),  # Camera Module 3 Wide
    "imx708_noir": Sensor(66.0, (4608, 2592), (2304, 1296)),
    "imx708_wide_noir": Sensor(102.0, (4608, 2592), (2304, 1296)),
}


def scaled_hfov_deg(full_hfov_deg: float, array_width: int, crop_width: float) -> float:
    """HFOV of a frame made from `crop_width` of the sensor's `array_width` columns."""
    ratio = min(crop_width / array_width, 1.0)
    return math.degrees(2 * math.atan(ratio * math.tan(math.radians(full_hfov_deg) / 2)))


class PiCamera:
    """Raspberry Pi CSI camera. Needs picamera2 + libcamera (apt: python3-picamera2).

    `model` is the sensor name. `hfov_deg` is the horizontal field of view of the frames being
    delivered (None for a sensor we have no datasheet value for). The camera runs the binned mode
    that sees the whole array: left to itself libcamera picks one that crops the middle (1920x1080
    on a v2, 1536x864 on a Camera Module 3). The HFOV follows from that mode and the frame's aspect,
    and from the ISP's ScalerCrop of the first frame where the platform reports it. Modes come from
    the table, not from picamera2's `sensor_modes`: listing those configures the full-resolution
    mode, which runs a Pi 5 out of camera memory.
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
        self.sensor = SENSORS.get(self.model)
        self._crop_seen = False
        extra = {}
        if self.sensor and width <= self.sensor.binned[0] and height <= self.sensor.binned[1]:
            extra["sensor"] = {"output_size": self.sensor.binned, "bit_depth": 10}
            array_w, array_h = self.sensor.array
            self._set_hfov(min(array_w, array_h * width / height))  # the ISP trims to our aspect
        # "RGB888" is laid out B, G, R in memory, which is OpenCV's order.
        config = self.cam.create_video_configuration(
            main={"size": (width, height), "format": "RGB888"},
            controls={"FrameRate": fps},
            buffer_count=4,
            **extra,
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
        if crop and not self._crop_seen:
            self._crop_seen = True
            self._set_hfov(crop[2])
        return frame

    def _set_hfov(self, crop_width: float) -> None:
        if self.sensor:
            self.hfov_deg = scaled_hfov_deg(self.sensor.hfov_deg, self.sensor.array[0], crop_width)

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
