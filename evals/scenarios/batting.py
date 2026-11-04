"""Eval scenario: batting kinematics and contact windows."""

import traceback

from fixtures.landmarks import stance_wrists_ok, stance_wrists_far
from server.kinematics import (
    exit_velocity_mph, spray_angle_deg, launch_angle_deg,
    launch_angle_from_slope, crossed_midline, stance_gate_ok, is_idle,
)
from server.hitting import resolve_contact
from server.pitching import resolve_pitch

CATEGORY = "batting"
WEIGHT = 20


def _close(a, b, tol=0.5):
    return abs(a - b) <= tol


def check_bat_stance_gate():
    wrists, sh = stance_wrists_ok()
    assert stance_gate_ok(wrists, sh, 0.5) is True, "0.5Ws + 0.5s holds"
    assert stance_gate_ok(wrists, sh, 2.0) is True, "longer hold holds"
    assert stance_gate_ok(wrists, sh, 0.49) is False, "0.49s must fail"
    far, sh = stance_wrists_far()
    assert stance_gate_ok(far, sh, 0.5) is False, "far wrist must fail"
    # Inclusive 0.5 Ws boundary: exactly 0.5 passes, just over fails.
    assert stance_gate_ok([(1.0, 0.0), (0.5, 0.0)], (0.5, 0.0), 0.5) is True
    assert stance_gate_ok([(1.01, 0.0), (0.5, 0.0)], (0.5, 0.0), 0.5) is False
    return "0.5Ws/0.5s inclusive boundaries hold"


def check_bat_exit_velo():
    assert _close(exit_velocity_mph(2.0), 65.0), "Vh 2.0 -> 65 mph"
    assert _close(exit_velocity_mph(5.0), 90.0), "Vh 5.0 -> 90 mph"
    assert _close(exit_velocity_mph(8.0), 115.0), "Vh 8.0 -> 115 mph"
    assert _close(exit_velocity_mph(3.5), 77.5), "linear midpoint 77.5"
    assert exit_velocity_mph(0.0) == 65.0, "clamp low to 65"
    assert exit_velocity_mph(99.0) == 115.0, "clamp high to 115"
    assert is_idle(1.49) is True and is_idle(1.5) is False, "idle at 1.5"
    return "65/90/115 mph +-0.5, clamped, linear"


def check_bat_spray_sign():
    assert spray_angle_deg(-0.1) > 0, "early swing pulls (+)"
    assert spray_angle_deg(0.1) < 0, "late swing goes oppo (-)"
    assert abs(spray_angle_deg(0.0)) == 0.0, "perfect timing is straight"
    assert spray_angle_deg(-0.25) == 45.0, "full early -> +45"
    assert spray_angle_deg(0.25) == -45.0, "full late -> -45"
    assert spray_angle_deg(-9.0) == 45.0, "clamp +45"
    assert spray_angle_deg(9.0) == -45.0, "clamp -45"
    assert abs(spray_angle_deg(-0.1) - 18.0) < 1e-9, "linear scale"
    return "sign + 90-degree cone +-45 clamp"


def check_bat_launch_clamp():
    assert launch_angle_deg(0.0, 0.0, 1.0) == 5.0, "flat -> 5 deg"
    assert launch_angle_deg(0.0, 1.0, 1.0) == 45.0, "big uppercut clamps 45"
    assert launch_angle_deg(0.0, -1.0, 1.0) == -15.0, "chop clamps -15"
    assert launch_angle_deg(0.0, 0.25, 1.0) == 15.0, "slope 0.25 -> 15"
    assert launch_angle_deg(0.0, 0.5, 0.0) == 0.0, "Ws<=0 -> 0.0"
    assert launch_angle_from_slope(0.0) == 5.0, "slope helper consistent"
    assert launch_angle_from_slope(2.0) == 45.0
    assert launch_angle_from_slope(-2.0) == -15.0
    return "[-15,+45] clamp, flat 5 deg, Ws<=0 safe"


def check_bat_contact_windows():
    pitch = resolve_pitch("FB", 4.0, (0.0, 0.0), 0.0, 1)

    def sw(**kw):
        d = {"vh_ws": 5.0, "dt_s": 0.05, "slope": 0.4, "crossed": True}
        d.update(kw)
        return d

    fair = resolve_contact(pitch, sw())
    assert fair["contact"] and not fair["foul"] and fair["reason"] == "fair"
    assert fair["exit_mph"] == 90.0 and fair["launch_deg"] == 21.0
    edge = resolve_contact(pitch, sw(dt_s=0.25))
    assert edge["contact"] and not edge["foul"], "|dt|=0.25 still fair"
    foul = resolve_contact(pitch, sw(dt_s=0.30))
    assert foul["contact"] and foul["foul"] and foul["reason"] == "foul_tip"
    edge2 = resolve_contact(pitch, sw(dt_s=0.40))
    assert edge2["foul"], "|dt|=0.40 still foul"
    whiff = resolve_contact(pitch, sw(dt_s=0.41))
    assert not whiff["contact"] and whiff["reason"] == "whiff"
    check = resolve_contact(pitch, sw(crossed=False))
    assert not check["contact"] and check["reason"] == "check_swing"
    idle = resolve_contact(pitch, sw(vh_ws=1.0))
    assert not idle["contact"] and idle["reason"] == "idle"
    early_pull = resolve_contact(pitch, sw(dt_s=-0.1))
    assert early_pull["spray_deg"] > 0, "early contact pulls"
    return "fair/foul/whiff/check/idle + edges 0.25/0.40"


CHECKS = [("bat_stance_gate", 4, check_bat_stance_gate),
          ("bat_exit_velo", 4, check_bat_exit_velo),
          ("bat_spray_sign", 4, check_bat_spray_sign),
          ("bat_launch_clamp", 4, check_bat_launch_clamp),
          ("bat_contact_windows", 4, check_bat_contact_windows)]


def run():
    earned, failed, details = 0, [], {}
    for cid, pts, fn in CHECKS:
        try:
            detail = fn() or "ok"
            earned += pts
            details[cid] = {"points": pts, "earned": pts,
                            "status": "pass", "detail": detail}
        except AssertionError as exc:
            failed.append(cid)
            details[cid] = {"points": pts, "earned": 0,
                            "status": "fail", "detail": str(exc)}
        except Exception:
            failed.append(cid)
            details[cid] = {"points": pts, "earned": 0,
                            "status": "error",
                            "detail": traceback.format_exc()[-2000:]}
    return {"category": CATEGORY, "earned": earned, "possible": WEIGHT,
            "failed": failed, "checks": details}
