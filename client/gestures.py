"""Gesture measurement on normalized (+y up, Ws units) landmarks.

Trackers are fed one frame at a time and expose the wire-ready numbers
the server's resolve_* functions need. Canonical keypoint order:
[nose, Lsho, Rsho, Lelb, Relb, Lwri, Rwri, Lhip, Rhip].
"""

import math

KP = {"nose": 0, "Lsho": 1, "Rsho": 2, "Lelb": 3, "Relb": 4,
      "Lwri": 5, "Rwri": 6, "Lhip": 7, "Rhip": 8}

MENU_DWELL_S = 2.0
STANCE_GATE_DIST_WS = 0.5
STANCE_GATE_HOLD_S = 0.5
PAUSE_HOLD_S = 1.5
IDLE_SPEED_WS = 1.5
NOSE_SCATTER_WS = 0.3


def _dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def mid_shoulder(pts):
    lx, ly = pts[KP["Lsho"]]
    rx, ry = pts[KP["Rsho"]]
    return ((lx + rx) / 2.0, (ly + ry) / 2.0)


def crossed_midline(path_x, mid_x):
    """True if a wrist-x path crossed the torso midline."""
    for a, b in zip(path_x, path_x[1:]):
        if (a - mid_x) * (b - mid_x) < 0 or b == mid_x:
            return True
    return False


def stance_gate_ok(wrists, shoulder, dist_ws=STANCE_GATE_DIST_WS):
    """Both wrists within dist_ws of the rear shoulder (positions only)."""
    sx, sy = shoulder
    for wx, wy in wrists:
        if _dist(wx, wy, sx, sy) > dist_ws:
            return False
    return True


def menu_side(pts):
    """Raised-hand pick: left wrist up -> BAT, right wrist up -> PITCH."""
    lwx, lwy = pts[KP["Lwri"]]
    rwx, rwy = pts[KP["Rwri"]]
    _, lsy = pts[KP["Lsho"]]
    _, rsy = pts[KP["Rsho"]]
    lup, rup = lwy > lsy, rwy > rsy
    if lup and not rup:
        return "BAT"
    if rup and not lup:
        return "PITCH"
    return None


def crossed_hold(pts):
    """Wrists crossed on chest (pause gesture)."""
    mx, my = mid_shoulder(pts)
    cx, cy = mx, my + 0.3  # chest center, +y up... shoulders sit above chest
    # NOTE: +y up means chest is BELOW mid-shoulder: use my - 0.3*Ws.
    cy = my - 0.3
    lw = pts[KP["Lwri"]]
    rw = pts[KP["Rwri"]]
    near = (_dist(lw[0], lw[1], cx, cy) < 0.45
            and _dist(rw[0], rw[1], cx, cy) < 0.45)
    return near and abs(lw[0] - rw[0]) < 0.35


def elbow_flare(pts):
    """Mean horizontal elbow-vs-shoulder spread in Ws (slider pose cue)."""
    lsx, _ = pts[KP["Lsho"]]
    rsx, _ = pts[KP["Rsho"]]
    lex, _ = pts[KP["Lelb"]]
    rex, _ = pts[KP["Relb"]]
    return (abs(lex - lsx) + abs(rex - rsx)) / 2.0


def classify_pitch_pose(pts):
    """Pre-throw pose -> pitch code (FB/CB/SL/CH).

    CB: both wrists above nose. SL: elbows flared wide. CH: non-throwing
    (left) wrist parked on the hip. Default: FB (hands together at chest).
    """
    lwx, lwy = pts[KP["Lwri"]]
    rwx, rwy = pts[KP["Rwri"]]
    _, nosey = pts[KP["nose"]]
    if lwy > nosey and rwy > nosey:
        return "CB"
    if elbow_flare(pts) > 0.55:
        return "SL"
    lhx, lhy = pts[KP["Lhip"]]
    if _dist(lwx, lwy, lhx, lhy) < 0.35:
        return "CH"
    return "FB"


class DwellTracker:
    """2-second dwell-to-select. update(side, dt) -> locked side or None."""

    def __init__(self, dwell_s=MENU_DWELL_S):
        self.dwell_s = dwell_s
        self.side = None
        self.t = 0.0

    @property
    def frac(self):
        if self.side is None:
            return 0.0
        return min(1.0, self.t / self.dwell_s)

    def update(self, side, dt):
        if side is not None and side == self.side:
            self.t += dt
        elif side is not None:
            self.side = side
            self.t = dt
        else:
            self.side = None
            self.t = 0.0
        if self.side is not None and self.t >= self.dwell_s:
            pick, self.side, self.t = self.side, None, 0.0
            return pick
        return None


class SwingTracker:
    """Wrist-trajectory swing capture -> wire-ready swing{...} numbers.

    Feed normalized frames during the action window; result() returns
    (vh_ws, dt_s, slope, crossed). dt_s here is swing duration; the
    caller maps contact timing to the server's dt_s at resolve time.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self._path = []  # (x, y, t) lead-wrist samples
        self._vmax = 0.0
        self._t = 0.0
        self._moved = False

    def update(self, pts, dt):
        dt = max(dt, 1e-6)
        self._t += dt
        lw = pts[KP["Lwri"]]
        rw = pts[KP["Rwri"]]
        lead = lw if abs(lw[0]) >= abs(rw[0]) else rw
        if self._path:
            px, py, _ = self._path[-1]
            v = _dist(lead[0], lead[1], px, py) / dt
            self._vmax = max(self._vmax, v)
            if v >= IDLE_SPEED_WS:
                self._moved = True
        self._path.append((lead[0], lead[1], self._t))

    @property
    def moved(self):
        return self._moved

    @property
    def vh_ws(self):
        return self._vmax

    def result(self, pts):
        if len(self._path) < 2:
            return (0.0, 0.0, 0.0, False)
        x0, y0, t0 = self._path[0]
        x1, y1, t1 = self._path[-1]
        mx, _ = mid_shoulder(pts)
        slope = (y1 - y0) / (abs(x1 - x0) + 1e-6)
        slope = max(-2.0, min(2.0, slope))
        return (self._vmax, max(t1 - t0, 0.0), slope,
                crossed_midline([p[0] for p in self._path], mx))


class ThrowTracker:
    """Throw capture -> (arm_ws, nose_shift_ws) for throw{...}."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._vmax = 0.0
        self._prev = None
        self._nose0 = None
        self._nose_shift = 0.0
        self._moved = False

    def update(self, pts, dt, throwing="R"):
        dt = max(dt, 1e-6)
        key = KP["Rwri"] if throwing == "R" else KP["Lwri"]
        w = pts[key]
        if self._prev is not None:
            v = _dist(w[0], w[1], self._prev[0], self._prev[1]) / dt
            self._vmax = max(self._vmax, v)
            if v >= IDLE_SPEED_WS:
                self._moved = True
        self._prev = w
        nose = pts[KP["nose"]]
        if self._nose0 is None:
            self._nose0 = nose
        self._nose_shift = max(
            self._nose_shift, abs(nose[0] - self._nose0[0]))

    @property
    def moved(self):
        return self._moved

    def result(self):
        return (self._vmax, self._nose_shift)


class PauseTracker:
    """Crossed-wrists hold -> True once held PAUSE_HOLD_S."""

    def __init__(self, hold_s=PAUSE_HOLD_S):
        self.hold_s = hold_s
        self.t = 0.0

    @property
    def frac(self):
        return min(1.0, self.t / self.hold_s)

    def update(self, pts, dt):
        if crossed_hold(pts):
            self.t += dt
            return self.t >= self.hold_s
        self.t = 0.0
        return False
