"""Pure batting/pitching kinematic mappings (deterministic, no I/O).

All functions operate in shoulder-width-normalized units (Ws) unless noted.
Fixture frame: Ws = 1.0, origin mid-shoulder, +x pull side, +y up.
"""

from .config import (VH_MIN_WS, VH_MAX_WS, EXIT_MIN_MPH, EXIT_MAX_MPH,
                     LAUNCH_MIN_DEG, LAUNCH_MAX_DEG, SPRAY_MAX_DEG,
                     FAIR_DT_S, STANCE_GATE_DIST_WS, STANCE_GATE_HOLD_S)


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def exit_velocity_mph(vh):
    """Map hand speed Vh (Ws/s, clamped to [2,8]) to exit velo 65..115 mph."""
    v = clamp(vh, VH_MIN_WS, VH_MAX_WS)
    return EXIT_MIN_MPH + (v - VH_MIN_WS) / (VH_MAX_WS - VH_MIN_WS) * (
        EXIT_MAX_MPH - EXIT_MIN_MPH)


def spray_angle_deg(dt):
    """Contact timing -> spray angle across the 90-degree fair cone.

    dt = swing_time - ideal_time (s): negative (early) pulls the ball (+),
    positive (late) goes oppo (-). Clamped to [-45, +45] deg.
    """
    t = clamp(dt, -FAIR_DT_S, FAIR_DT_S)
    return -t / FAIR_DT_S * SPRAY_MAX_DEG


def launch_angle_deg(y0, y1, Ws):
    """Wrist-path vertical slope -> launch angle in [-15, +45] deg.

    y0 = wrist height at swing start, y1 = height at contact, same units as
    Ws. Flat swing -> ~5 deg line drive; upward arc -> fly ball; downward
    chop -> grounder.
    """
    if Ws <= 0:
        return 0.0
    slope = (y1 - y0) / Ws
    return clamp(slope * 40.0 + 5.0, LAUNCH_MIN_DEG, LAUNCH_MAX_DEG)


def launch_angle_from_slope(slope):
    """launch_angle_deg for a precomputed (dy / Ws) slope (Ws = 1.0 frame)."""
    return launch_angle_deg(0.0, slope, 1.0)


def crossed_midline(path, mid):
    """True if an x-position sequence touches or straddles midline x=mid."""
    pts = list(path)
    if not pts:
        return False
    for p in pts:
        if p == mid:
            return True
    for a, b in zip(pts, pts[1:]):
        if (a - mid) * (b - mid) < 0:
            return True
    return False


def _dist(ax, ay, bx, by):
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def stance_gate_ok(wrists, sh, held):
    """Batting stance gate: every wrist within 0.5 Ws of the rear shoulder.

    wrists: sequence of (x, y); sh: rear-shoulder (x, y); all in Ws units
    (fixture frame). held: seconds the pose has been held (>= 0.5 required).
    """
    if held < STANCE_GATE_HOLD_S:
        return False
    sx, sy = sh
    for w in wrists:
        if _dist(w[0], w[1], sx, sy) > STANCE_GATE_DIST_WS:
            return False
    return True


def is_idle(vh, threshold=1.5):
    """True if hand speed is below the idle-reject threshold (Ws/s)."""
    return vh < threshold
