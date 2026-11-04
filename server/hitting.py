"""Contact and hit resolution (deterministic, no I/O).

Contact windows on timing error dt (|swing_time - ideal_time|):
  |dt| <= 0.25 s -> fair contact; 0.25 < |dt| <= 0.40 -> foul;
  beyond -> whiff. No midline cross -> check swing (pitch is called).
  Hand speed < 1.5 Ws/s -> idle, no swing.

Hit precedence on angle overlap: HR > 3B > 2B > 1B > OUT; a fielder
intercept is always an OUT. Exit velocity below the class minimum
downgrades exactly one rung on the OUT < 1B < 2B < 3B < HR ladder
(a downgrade landing on 3B without the corner condition falls to 2B).
"""

from .config import FAIR_DT_S, FOUL_DT_S, IDLE_SPEED_WS, HIT_WINDOWS
from .kinematics import (exit_velocity_mph, spray_angle_deg,
                         launch_angle_from_slope)


def resolve_contact(pitch, swing):
    """Resolve a swing against a pitch.

    pitch: dict from pitching.resolve_pitch (uses in_zone for takes).
    swing: dict {vh_ws, dt_s, slope, crossed}.
    Returns contact, foul, exit_mph, launch_deg, spray_deg, reason.
    """
    vh = float(swing.get("vh_ws", 0.0))
    dt = float(swing.get("dt_s", 0.0))
    slope = float(swing.get("slope", 0.0))
    crossed = bool(swing.get("crossed", False))
    result = {"contact": False, "foul": False, "exit_mph": 0.0,
              "launch_deg": 0.0, "spray_deg": 0.0, "reason": ""}
    if not crossed:
        result["reason"] = "check_swing"
        return result
    if vh < IDLE_SPEED_WS:
        result["reason"] = "idle"
        return result
    adt = abs(dt)
    if adt > FOUL_DT_S:
        result["reason"] = "whiff"
        return result
    result["contact"] = True
    result["exit_mph"] = round(exit_velocity_mph(vh), 1)
    result["launch_deg"] = round(launch_angle_from_slope(slope), 1)
    result["spray_deg"] = round(spray_angle_deg(dt), 1)
    if adt > FAIR_DT_S:
        result["foul"] = True
        result["reason"] = "foul_tip"
    else:
        result["reason"] = "fair"
    return result


_LADDER = ("OUT", "1B", "2B", "3B", "HR")


def _candidate(launch, corner):
    if HIT_WINDOWS["HR"][0] <= launch <= HIT_WINDOWS["HR"][1]:
        return "HR"
    if corner and HIT_WINDOWS["3B"][0] <= launch <= HIT_WINDOWS["3B"][1]:
        return "3B"
    if HIT_WINDOWS["2B"][0] <= launch <= HIT_WINDOWS["2B"][1]:
        return "2B"
    if HIT_WINDOWS["1B"][0] <= launch <= HIT_WINDOWS["1B"][1]:
        return "1B"
    return "OUT"


def resolve_hit(launch, exit, intercept, corner, billboard):
    """Resolve a fair ball into an outcome.

    launch: launch angle deg; exit: exit velocity mph; intercept: fielder
    caught it; corner: ball lands in a corner zone; billboard: HR struck
    the flashing scoreboard graphic.
    """
    if intercept:
        outcome = "OUT"
    else:
        outcome = _candidate(launch, corner)
        if outcome != "OUT":
            lo, hi, need, _pts = HIT_WINDOWS[outcome]
            if exit < need:
                idx = _LADDER.index(outcome) - 1
                outcome = _LADDER[idx]
                if outcome == "3B" and not corner:
                    outcome = "2B"
    return {
        "outcome": outcome,
        "launch": launch,
        "exit": exit,
        "billboard": bool(outcome == "HR" and billboard),
    }
