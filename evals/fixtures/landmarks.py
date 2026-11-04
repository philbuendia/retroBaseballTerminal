"""Deterministic spec-derived landmark fixtures for tests and evals.

Fixture frame (per BUILD_CONTRACT.md): Ws = 1.0 units, origin at
mid-shoulder, +x pull side, +y up, dt = 1/60 s. Every sequence is built
from closed-form expressions (no RNG of any kind) so results are
bit-identical on every run.

Nominal spec-derived sequence lengths (timeout x 60 Hz):
  120f calibration / menu dwell (2.0 s)
  602f full pipeline budget (120 + 30 + 211 + 241 + margin)
  211f action window (3.5 s + float-boundary frame)
  241f resolve lock (4.0 s + float-boundary frame)
   90f pause hold (1.5 s)
   60f out-of-frustum trip (1.0 s)
   30f stance gate (0.5 s)

Float-boundary note: accumulating dt = 1/60 in binary floating point,
120 steps sum to 1.9999999999999978 (< 2.0), so timeouts firing on
>= fire one frame after the nominal count (121/31/91/211/241), while
the strict out-of-frustum check (> 1.0) trips exactly at 60 steps
(1.0000000000000013 > 1.0). Sequences below use exact nominal counts;
checks assert the measured fire frame explicitly.
"""

import math

DT = 1.0 / 60.0

KP = {"nose": 0, "Lsho": 1, "Rsho": 2, "Lelb": 3, "Relb": 4,
      "Lwri": 5, "Rwri": 6, "Lhip": 7, "Rhip": 8}

COUNTS = {"calibrate": 120, "full_cycle": 602, "action_window": 211,
          "resolve": 241, "pause_hold": 90, "frustum": 60,
          "stance_gate": 30}

CONF_OK = 0.9
CONF_MISS = 0.0
CONF_LOW_TORSO = 0.1


def base_points():
    """Neutral Ws-frame pose: triggers no gate, dwell, or pause gesture."""
    return [(0.0, 0.35), (-0.5, 0.0), (0.5, 0.0),
            (-0.7, -0.3), (0.7, -0.3),
            (-0.4, -0.5), (0.4, -0.5),
            (-0.3, -0.8), (0.3, -0.8)]


def with_wrists(lw, rw):
    pts = base_points()
    pts[KP["Lwri"]] = tuple(lw)
    pts[KP["Rwri"]] = tuple(rw)
    return pts


def menu_points(side="BAT"):
    if side == "BAT":
        return with_wrists((-0.5, 0.3), (0.5, -0.5))
    return with_wrists((-0.5, -0.5), (0.5, 0.3))


def gate_points(rear="R"):
    if rear == "R":
        return with_wrists((0.45, 0.05), (0.55, -0.05))
    return with_wrists((-0.55, -0.05), (-0.45, 0.05))


def crossed_points():
    return with_wrists((-0.1, -0.3), (0.1, -0.3))


def frame(points, conf=CONF_OK, wrist_conf=None, torso_conf=None):
    """One landmark dict {"points", "conf"} (fresh objects every call)."""
    pts = [(float(x), float(y)) for x, y in points]
    c = [float(conf)] * 9
    if wrist_conf is not None:
        c[KP["Lwri"]] = float(wrist_conf)
        c[KP["Rwri"]] = float(wrist_conf)
    if torso_conf is not None:
        for k in ("Lsho", "Rsho", "Lhip", "Rhip"):
            c[KP[k]] = float(torso_conf)
    return {"points": pts, "conf": c}


def repeat(points, n, **kw):
    return [frame(points, **kw) for _ in range(n)]


def neutral_frames(n):
    return repeat(base_points(), n)


def calibrate_frames(n=120):
    """Torso-visible stream for UNBOUND -> CALIBRATE -> MENU."""
    return neutral_frames(n)


def menu_frames(side="BAT", n=121):
    return repeat(menu_points(side), n)


def gate_frames(n=31, rear="R"):
    return repeat(gate_points(rear), n)


def crossed_frames(n=91):
    return repeat(crossed_points(), n)


def frustum_gap(n=60):
    """Out-of-frustum gap: None frames (no torso at all)."""
    return [None] * n


def low_torso_frames(n=60):
    """Out-of-frustum gap via torso conf < 0.6 (camera sees no torso)."""
    return [frame(base_points(), torso_conf=CONF_LOW_TORSO)
            for _ in range(n)]


def occlusion_frames(n, pose_fn=None):
    """Wrist conf 0.0 (occluded) with torso still visible."""
    pose_fn = pose_fn or (lambda: gate_points())
    return [frame(pose_fn(), wrist_conf=CONF_MISS) for _ in range(n)]


def idle_sway_frames(n=211, amp=0.005, period=30):
    """Sub-threshold wrist sway: peak speed amp*2*pi/(period*DT) Ws/s.

    Defaults: 0.005 * 2pi / 0.5 s = 0.063 Ws/s, far below the 1.5 idle bar.
    """
    out = []
    for i in range(n):
        dx = amp * math.sin(2.0 * math.pi * i / period)
        pts = gate_points()
        pts[KP["Lwri"]] = (pts[KP["Lwri"]][0] + dx, pts[KP["Lwri"]][1])
        pts[KP["Rwri"]] = (pts[KP["Rwri"]][0] - dx, pts[KP["Rwri"]][1])
        out.append(frame(pts))
    return out


def swing_sweep_frames(vh_ws=6.0, start_x=0.45, y=0.05, n=12):
    """Constant-speed lead-wrist sweep crossing the torso midline.

    Per-frame step vh_ws * DT gives exactly vh_ws Ws/s every frame.
    Default crosses x = 0 between the 4th and 5th frame.
    """
    out = []
    step = vh_ws * DT
    for i in range(n):
        pts = gate_points()
        pts[KP["Lwri"]] = (start_x - step * (i + 1), y)
        out.append(frame(pts))
    return out


def vertical_drift_frames(speed_ws=1.8, x=0.3, y0=0.05, n=211):
    """Constant vertical drift: always above idle, never crosses midline."""
    out = []
    step = speed_ws * DT
    for i in range(n):
        pts = gate_points()
        pts[KP["Lwri"]] = (x, y0 + step * (i + 1))
        out.append(frame(pts))
    return out


def full_cycle_frames():
    """Exactly 602 frames driving UNBOUND -> ... -> RESOLVE -> STANCE.

    1 (enter CAL) + 124 (calibrated) + 124 (menu pick) + 34 (stance load)
    + 12 (motion peak) + 247 (resolve done) + 60 (settle) = 602.
    """
    seq = []
    seq += neutral_frames(1)
    seq += neutral_frames(124)
    seq += menu_frames("BAT", 124)
    seq += gate_frames(34)
    seq += swing_sweep_frames(6.0, n=12)
    seq += neutral_frames(247)
    seq += neutral_frames(60)
    assert len(seq) == COUNTS["full_cycle"]
    return seq


def swing_path_crossing():
    """Lead-wrist x samples straddling midline x = 0 (check-swing True)."""
    return [0.45 - 0.1 * i for i in range(8)]


def swing_path_hold():
    """Lead-wrist x samples that never reach the midline (check swing)."""
    return [0.45 - 0.01 * i for i in range(8)]


def stance_wrists_ok():
    return [(0.45, 0.05), (0.55, -0.05)], (0.5, 0.0)


def stance_wrists_far():
    return [(1.2, 0.0), (0.55, -0.05)], (0.5, 0.0)
