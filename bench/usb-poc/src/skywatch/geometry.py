"""Camera coordinates: x right, y down, z forward. All distances are metres."""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class CameraModel:
    K: np.ndarray
    dist: np.ndarray
    center: np.ndarray
    rotation: np.ndarray  # camera to world
    size: tuple[int, int]

    @classmethod
    def from_dict(cls, data):
        model = cls(
            np.asarray(data["K"], float),
            np.asarray(data["dist"], float),
            np.asarray(data["center"], float),
            np.asarray(data["rotation"], float),
            tuple(data["size"]),
        )
        if (
            model.K.shape != (3, 3)
            or model.rotation.shape != (3, 3)
            or model.center.shape != (3,)
            or len(model.size) != 2
            or min(model.size) <= 0
            or model.dist.size not in (4, 5, 8, 12, 14)
            or not all(
                np.isfinite(x).all() for x in (model.K, model.dist, model.center, model.rotation)
            )
            or min(model.K[0, 0], model.K[1, 1]) <= 0
            or not np.allclose(model.rotation.T @ model.rotation, np.eye(3), atol=1e-4)
            or not np.isclose(np.linalg.det(model.rotation), 1, atol=1e-4)
        ):
            raise ValueError("Invalid camera calibration")
        return model

    def ray(self, pixel):
        xy = cv2.undistortPoints(np.asarray(pixel, float).reshape(1, 1, 2), self.K, self.dist)[0, 0]
        direction = self.rotation @ np.array([*xy, 1.0])
        return self.center, direction / np.linalg.norm(direction)

    def project(self, points):
        points = np.asarray(points, float).reshape(-1, 3)
        rotation = self.rotation.T
        rvec, _ = cv2.Rodrigues(rotation)
        pixels, _ = cv2.projectPoints(points, rvec, -rotation @ self.center, self.K, self.dist)
        depth = ((points - self.center) @ self.rotation)[:, 2]
        return pixels.reshape(-1, 2), depth


def triangulate(a, b, pa, pb, max_range=5000.0):
    """Reject weak/behind-camera/inconsistent intersections; no invented range."""
    ca, da = a.ray(pa)
    cb, db = b.ray(pb)
    angle = np.arccos(np.clip(np.dot(da, db), -1, 1))
    if angle < np.deg2rad(0.3) or angle > np.deg2rad(175):
        return None
    distances, *_ = np.linalg.lstsq(np.column_stack((da, -db)), cb - ca, rcond=None)
    if np.min(distances) <= 0 or np.max(distances) > max_range:
        return None
    p1, p2 = ca + distances[0] * da, cb + distances[1] * db
    point = (p1 + p2) / 2
    reprojection = max(
        np.linalg.norm(a.project([point])[0][0] - pa), np.linalg.norm(b.project([point])[0][0] - pb)
    )
    if reprojection > 3:
        return None
    distance = float(np.linalg.norm(point - ca))
    # Approximate one-pixel centroid sensitivity, NOT a statistical confidence interval.
    sensitivity = float(distance / (min(a.K[0, 0], b.K[0, 0]) * np.sin(angle)))
    if sensitivity > distance * 0.5:
        return None
    return {
        "position": point.tolist(),
        "range_m": distance,
        "sensitivity_m": sensitivity,
        "ray_angle_deg": float(np.rad2deg(angle)),
        "reprojection_px": float(reprojection),
    }


class VoxelProjector:
    """Project voxel centres into masks: the inverse of casting motion rays.

    Each camera has one vote per cell. Only simultaneous two-view support survives.
    This is visual-hull evidence, not object identity or guaranteed occupied volume.
    """

    def __init__(self, bounds, resolution=36):
        self.bounds = np.asarray(bounds, float)
        if (
            self.bounds.shape != (3, 2)
            or not np.isfinite(self.bounds).all()
            or np.any(self.bounds[:, 1] <= self.bounds[:, 0])
        ):
            raise ValueError("Voxel bounds must be three increasing finite pairs")
        if not 8 <= resolution <= 64:
            raise ValueError("Voxel resolution must be 8..64")
        self.step = (self.bounds[:, 1] - self.bounds[:, 0]) / resolution
        axes = [
            np.linspace(lo + step / 2, hi - step / 2, resolution)
            for (lo, hi), step in zip(self.bounds, self.step, strict=True)
        ]
        self.points = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
        self.cache = {}

    def reconstruct(self, cameras, masks):
        if len(cameras) < 2:
            return []
        support = np.zeros(len(self.points), np.uint8)
        for index, (camera, mask) in enumerate(zip(cameras, masks, strict=True)):
            if index not in self.cache:
                pixels, depth = camera.project(self.points)
                uv = np.rint(np.clip(pixels, -1e7, 1e7)).astype(int)
                w, h = camera.size
                valid = (
                    (depth > 0)
                    & (uv[:, 0] >= 0)
                    & (uv[:, 0] < w)
                    & (uv[:, 1] >= 0)
                    & (uv[:, 1] < h)
                )
                self.cache[index] = uv, valid
            uv, valid = self.cache[index]
            expanded = cv2.dilate(mask, np.ones((3, 3), np.uint8))
            support[valid] += (expanded[uv[valid, 1], uv[valid, 0]] > 0).astype(np.uint8)
        return self.points[support >= 2][:1500].round(3).tolist()


def demo_models():
    return [
        CameraModel(
            np.array([[554.256, 0, 320], [0, 554.256, 240], [0, 0, 1.0]]),
            np.zeros(5),
            np.array([x, 0.0, 0.0]),
            np.eye(3),
            (640, 480),
        )
        for x in (-1.5, 1.5)
    ]
