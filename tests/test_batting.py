"""Batting: stance gate, exit velo, spray, launch, contact windows."""

import pytest

from fixtures.landmarks import stance_wrists_ok, stance_wrists_far
from server.kinematics import (
    exit_velocity_mph, spray_angle_deg, launch_angle_deg,
    launch_angle_from_slope, crossed_midline, stance_gate_ok, is_idle,
)
from server.hitting import resolve_contact
from server.pitching import resolve_pitch


def test_stance_gate_hold_and_distance():
    wrists, sh = stance_wrists_ok()
    assert stance_gate_ok(wrists, sh, 0.5) is True
    assert stance_gate_ok(wrists, sh, 5.0) is True
    assert stance_gate_ok(wrists, sh, 0.49) is False
    far, sh = stance_wrists_far()
    assert stance_gate_ok(far, sh, 0.5) is False


def test_stance_gate_boundary_inclusive():
    assert stance_gate_ok([(1.0, 0.0), (0.5, 0.0)], (0.5, 0.0), 0.5) is True
    assert stance_gate_ok([(1.01, 0.0), (0.5, 0.0)], (0.5, 0.0), 0.5) is False


@pytest.mark.parametrize("vh,want", [(2.0, 65.0), (5.0, 90.0), (8.0, 115.0),
                                     (3.5, 77.5), (6.5, 102.5)])
def test_exit_velocity_mapping(vh, want):
    assert abs(exit_velocity_mph(vh) - want) <= 0.5


def test_exit_velocity_clamps():
    assert exit_velocity_mph(0.0) == 65.0
    assert exit_velocity_mph(-3.0) == 65.0
    assert exit_velocity_mph(8.01) == 115.0
    assert exit_velocity_mph(99.0) == 115.0


def test_idle_threshold():
    assert is_idle(1.49) is True
    assert is_idle(1.5) is False
    assert is_idle(6.0) is False


def test_spray_sign_and_cone():
    assert spray_angle_deg(-0.1) > 0
    assert spray_angle_deg(0.1) < 0
    assert abs(spray_angle_deg(0.0)) == 0.0
    assert spray_angle_deg(-0.25) == 45.0
    assert spray_angle_deg(0.25) == -45.0
    assert spray_angle_deg(-9.0) == 45.0
    assert spray_angle_deg(9.0) == -45.0
    assert abs(spray_angle_deg(-0.1) - 18.0) < 1e-9


def test_launch_angle_and_clamp():
    assert launch_angle_deg(0.0, 0.0, 1.0) == 5.0
    assert launch_angle_deg(0.0, 1.0, 1.0) == 45.0
    assert launch_angle_deg(0.0, -1.0, 1.0) == -15.0
    assert launch_angle_deg(0.0, 0.25, 1.0) == 15.0
    assert launch_angle_deg(0.0, 0.5, 0.0) == 0.0
    assert launch_angle_from_slope(0.0) == 5.0
    assert launch_angle_from_slope(2.0) == 45.0
    assert launch_angle_from_slope(-2.0) == -15.0


def test_crossed_midline():
    assert crossed_midline([], 0.0) is False
    assert crossed_midline([0.4, -0.1], 0.0) is True
    assert crossed_midline([0.4, 0.1], 0.0) is False
    assert crossed_midline([0.0], 0.0) is True


def _pitch():
    return resolve_pitch("FB", 4.0, (0.0, 0.0), 0.0, 1)


def _swing(**kw):
    d = {"vh_ws": 5.0, "dt_s": 0.05, "slope": 0.4, "crossed": True}
    d.update(kw)
    return d


def test_contact_fair_and_foul_windows():
    fair = resolve_contact(_pitch(), _swing())
    assert fair["contact"] and not fair["foul"] and fair["reason"] == "fair"
    assert (fair["exit_mph"], fair["launch_deg"]) == (90.0, 21.0)
    assert resolve_contact(_pitch(), _swing(dt_s=0.25))["foul"] is False
    assert resolve_contact(_pitch(), _swing(dt_s=-0.25))["foul"] is False
    foul = resolve_contact(_pitch(), _swing(dt_s=0.30))
    assert foul["contact"] and foul["foul"] and foul["reason"] == "foul_tip"
    assert resolve_contact(_pitch(), _swing(dt_s=0.40))["foul"] is True
    assert resolve_contact(_pitch(), _swing(dt_s=-0.40))["foul"] is True


def test_contact_whiff_check_idle():
    whiff = resolve_contact(_pitch(), _swing(dt_s=0.41))
    assert not whiff["contact"] and whiff["reason"] == "whiff"
    check = resolve_contact(_pitch(), _swing(crossed=False))
    assert not check["contact"] and check["reason"] == "check_swing"
    idle = resolve_contact(_pitch(), _swing(vh_ws=1.0))
    assert not idle["contact"] and idle["reason"] == "idle"


def test_contact_spray_follows_timing():
    assert resolve_contact(_pitch(), _swing(dt_s=-0.1))["spray_deg"] > 0
    assert resolve_contact(_pitch(), _swing(dt_s=0.1))["spray_deg"] < 0
