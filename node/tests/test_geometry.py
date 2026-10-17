import math

import pytest

from edth_node.config import Config
from edth_node.geometry import CameraGeometry

W, H, HFOV = 640, 480, 70.0


def geom(**pose):
    cfg = Config(node_id="n", mqtt_host="h", camera_hfov_deg=HFOV, **pose)
    return CameraGeometry.from_config(cfg, W, H)


def test_image_centre_is_the_optical_axis():
    az, el = geom(heading_deg=123.0, pitch_deg=20.0).pixel_to_azel(W / 2, H / 2)
    assert az == pytest.approx(123.0, abs=1e-6)
    assert el == pytest.approx(20.0, abs=1e-6)


def test_right_edge_is_half_hfov_clockwise():
    az, el = geom().pixel_to_azel(W, H / 2)
    assert az == pytest.approx(HFOV / 2, abs=1e-6)
    assert el == pytest.approx(0.0, abs=1e-6)
    az, _ = geom().pixel_to_azel(0, H / 2)
    assert az == pytest.approx(360 - HFOV / 2, abs=1e-6)


def test_up_in_image_is_up_in_sky():
    _, el = geom().pixel_to_azel(W / 2, 0)
    assert el > 0
    _, el = geom().pixel_to_azel(W / 2, H)
    assert el < 0


def test_heading_east_right_of_centre_is_south_of_east():
    az, _ = geom(heading_deg=90.0).pixel_to_azel(W, H / 2)
    assert az == pytest.approx(90.0 + HFOV / 2, abs=1e-6)


def test_pitch_up_moves_horizon_down_in_image():
    el_of_centre = geom(pitch_deg=30.0).pixel_to_azel(W / 2, H / 2)[1]
    el_of_bottom = geom(pitch_deg=30.0).pixel_to_azel(W / 2, H)[1]
    assert el_of_centre == pytest.approx(30.0)
    assert el_of_bottom < el_of_centre


def test_vertical_extent_matches_pinhole():
    f = (W / 2) / math.tan(math.radians(HFOV / 2))
    _, el = geom().pixel_to_azel(W / 2, 0)
    assert el == pytest.approx(math.degrees(math.atan((H / 2) / f)), abs=1e-6)


def test_roll_clockwise_lowers_the_right_side_of_the_image():
    # Rolled clockwise by 90 deg: the image's right edge now points at the ground.
    _, el = geom(roll_deg=90.0).pixel_to_azel(W, H / 2)
    assert el < -30.0
    # and the image's top edge points to the right (east for heading 0).
    az, _ = geom(roll_deg=90.0).pixel_to_azel(W / 2, 0)
    assert 0 < az < 90


def test_zenith_pitch_stays_finite_and_in_range():
    az, el = geom(pitch_deg=90.0).pixel_to_azel(W / 2, H / 2)
    assert el == pytest.approx(90.0)
    assert 0 <= az < 360


def test_calibrated_intrinsics_override_hfov():
    cfg = Config(node_id="n", mqtt_host="h", camera_fx=800.0, camera_cx=300.0, camera_cy=200.0)
    g = CameraGeometry.from_config(cfg, W, H)
    assert g.pixel_to_azel(300, 200) == pytest.approx((0.0, 0.0), abs=1e-9)
    az, _ = g.pixel_to_azel(300 + 800, 200)
    assert az == pytest.approx(45.0, abs=1e-6)
