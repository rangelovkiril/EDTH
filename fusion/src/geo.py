"""A local East-North-Up frame in metres around an origin (tangent plane, equirectangular): good
to centimetres over a site, about a metre over a few kilometres."""

import math

import numpy as np

M_PER_DEG = math.pi / 180 * 6_371_000.0


class LocalFrame:
    def __init__(self, lat0: float, lon0: float, alt0: float):
        self.lat0, self.lon0, self.alt0 = lat0, lon0, alt0
        self._m_per_deg_lon = M_PER_DEG * math.cos(math.radians(lat0))

    def to_enu(self, lat: float, lon: float, alt: float) -> np.ndarray:
        return np.array(
            [
                (lon - self.lon0) * self._m_per_deg_lon,
                (lat - self.lat0) * M_PER_DEG,
                alt - self.alt0,
            ]
        )

    def to_lla(self, enu) -> tuple[float, float, float]:
        e, n, u = enu
        return self.lat0 + n / M_PER_DEG, self.lon0 + e / self._m_per_deg_lon, self.alt0 + u
