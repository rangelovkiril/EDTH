"""Pixel to bearing. Camera frame: x right, y down, z forward (OpenCV).

World directions are local ENU; az is degrees clockwise from true north,
el is degrees above the horizon. Mount pose: heading is where the optical axis
points (clockwise from north), pitch is positive nose-up, roll is positive
clockwise as seen looking along the optical axis.
"""

import math

import cv2
import numpy as np

# Level camera facing north: x_cam -> east, y_cam -> down, z_cam -> north.
_CAM_TO_ENU = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)


def _rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


class CameraGeometry:
    def __init__(self, K, dist, heading_deg=0.0, pitch_deg=0.0, roll_deg=0.0):
        self.K = np.asarray(K, float)
        self.dist = np.asarray(dist, float)
        # roll about the optical axis (north), then pitch about east, then heading about up.
        self.rotation = (
            _rot_z(-math.radians(heading_deg))
            @ _rot_x(math.radians(pitch_deg))
            @ _rot_y(math.radians(roll_deg))
            @ _CAM_TO_ENU
        )

    @classmethod
    def from_config(cls, cfg, width: int, height: int) -> "CameraGeometry":
        """Use calibrated intrinsics when given, else a pinhole model from the HFOV."""
        if cfg.camera_fx is not None:
            fx = cfg.camera_fx
            fy = cfg.camera_fy or fx
        else:
            fx = fy = (width / 2) / math.tan(math.radians(cfg.camera_hfov_deg) / 2)
        cx = width / 2 if cfg.camera_cx is None else cfg.camera_cx
        cy = height / 2 if cfg.camera_cy is None else cfg.camera_cy
        K = [[fx, 0, cx], [0, fy, cy], [0, 0, 1]]
        return cls(K, cfg.camera_dist, cfg.heading_deg, cfg.pitch_deg, cfg.roll_deg)

    def pixel_to_azel(self, u: float, v: float) -> tuple[float, float]:
        x, y = cv2.undistortPoints(np.array([[[u, v]]], float), self.K, self.dist)[0, 0]
        east, north, up = self.rotation @ np.array([x, y, 1.0])
        az = math.degrees(math.atan2(east, north)) % 360.0
        el = math.degrees(math.atan2(up, math.hypot(east, north)))
        return az, el
