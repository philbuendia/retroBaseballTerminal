"""Deterministic 7-state camera tracking finite state machine.

Evaluated every frame (dt ~ 1/60 s). Landmark input per call is either None
(no frame / player out of frustum) or a dict::

    {"points": [(x, y)] * 9, "conf": [float] * 9}

with canonical keypoint order [nose, Lsho, Rsho, Lelb, Relb, Lwri, Rwri,
Lhip, Rhip] in +y-up coordinates (any pixel scale; motion is normalized by
the calibrated shoulder width Ws).

States: 01_UNBOUND -> 02_CALIBRATE -> 03_MENU_SELECT -> 04_STANCE_READY ->
05_ACTION_WINDOW -> 06_PLAY_RESOLVE -> 04_STANCE_READY, plus 07_SYSTEM_PAUSE
reachable from any state (except the RESOLVE physics lock) via the crossed-
wrists hold or the out-of-frustum timeout.
"""

from collections import deque
from dataclasses import dataclass, field

from .config import (KP, CALIBRATE_TIMEOUT_S, MENU_DWELL_S, STANCE_TIMEOUT_S,
                     ACTION_TIMEOUT_S, RESOLVE_TIMEOUT_S, PAUSE_HOLD_S,
                     OUT_OF_FRUSTUM_S, STANCE_GATE_HOLD_S,
                     STANCE_GATE_DIST_WS, CONF_MIN, LOCK_CONF, NOSE_CONF,
                     WRIST_CONF, DWELL_GAP_S, GATE_GAP_S, MENU_AUTO_PICK_S,
                     EXTRAPOLATE_MAX_FRAMES, IDLE_SPEED_WS,
                     ONSET_ARM_S, ONSET_BLIND_FRAMES)

UNBOUND = "01_UNBOUND"
CALIBRATE = "02_CALIBRATE"
MENU = "03_MENU_SELECT"
STANCE = "04_STANCE_READY"
ACTION = "05_ACTION_WINDOW"
RESOLVE = "06_PLAY_RESOLVE"
PAUSE = "07_SYSTEM_PAUSE"

STATES = (UNBOUND, CALIBRATE, MENU, STANCE, ACTION, RESOLVE, PAUSE)

STATE_TIMEOUTS = {
    CALIBRATE: CALIBRATE_TIMEOUT_S,
    MENU: MENU_DWELL_S,
    STANCE: STANCE_TIMEOUT_S,
    ACTION: ACTION_TIMEOUT_S,
    RESOLVE: RESOLVE_TIMEOUT_S,
}

ROLE_BAT = "BAT"
ROLE_PITCH = "PITCH"


@dataclass
class Transition:
    from_state: str
    to_state: str
    event: str
    data: dict = field(default_factory=dict)


class TrackingFSM:
    """Landmark-driven tracking state machine with timeout/occlusion logic."""

    def __init__(self, rear="R"):
        self.state = UNBOUND
        self.role = None
        self.close_range = False
        self._conf_hist = deque(maxlen=3)
        self.rear = "R" if rear != "L" else "L"
        self.Ws = None  # calibrated shoulder width in input pixels
        self.t_state = 0.0
        self._torso_t = 0.0
        self._dwell_side = None
        self._dwell_t = 0.0
        self._dwell_gap = 0.0
        self._menu_gate_t = 0.0
        self._gate_t = 0.0
        self._gate_gap = 0.0
        self._onset_blind = 0
        self._pause_hold_t = 0.0
        self._out_t = 0.0
        self._cal_samples = []
        # Per-wrist tracking: last known pos/vel in pixels + miss streak.
        self._wpos = {"L": None, "R": None}
        self._wvel = {"L": (0.0, 0.0), "R": (0.0, 0.0)}
        self._miss = {"L": 0, "R": 0}
        self._path_x = []  # lead-wrist x history (pixels) for midline cross
        self._action_vmax = 0.0
        self._action_vh = 0.0
        self._action_moved = False

    # -- helpers ------------------------------------------------------
    def _go(self, to_state, event, data=None):
        tr = Transition(self.state, to_state, event, data or {})
        self.state = to_state
        self.t_state = 0.0
        return tr

    @staticmethod
    def _dist(ax, ay, bx, by):
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

    def _ws_now(self, pts):
        lx, ly = pts[KP["Lsho"]]
        rx, ry = pts[KP["Rsho"]]
        d = self._dist(lx, ly, rx, ry)
        return d if d > 1e-9 else 1.0

    def _ws(self, pts):
        return self.Ws if self.Ws else self._ws_now(pts)

    def _torso_ok(self, lm):
        try:
            conf = list(lm["conf"]) if lm is not None else None
        except (KeyError, TypeError):
            conf = None
        if conf is None:
            conf = [0.0] * 9  # dropped frame decays presence, never holds it
        self._conf_hist.append(conf)
        eff = [max(w[k] for w in self._conf_hist) for k in range(9)]
        for k in ("Lsho", "Rsho"):
            if eff[KP[k]] < LOCK_CONF:
                return False
        hips_ok = all(eff[KP[k]] >= LOCK_CONF for k in ("Lhip", "Rhip"))
        nose_ok = eff[KP["nose"]] >= NOSE_CONF
        if not (hips_ok or nose_ok):
            return False
        self.close_range = not hips_ok
        return True

    def _track_wrists(self, lm, dt):
        """Update wrist pos/vel with <=3-frame extrapolation on occlusion.

        Returns (ok, fail): fail=True on the 4th consecutive missing frame.
        """
        if lm is None:
            return False, False
        pts, conf = lm["points"], lm["conf"]
        fail = False
        for side, key in (("L", "Lwri"), ("R", "Rwri")):
            if conf[KP[key]] >= WRIST_CONF:
                x, y = pts[KP[key]]
                old = self._wpos[side]
                if old is not None and dt > 0:
                    self._wvel[side] = ((x - old[0]) / dt, (y - old[1]) / dt)
                self._wpos[side] = (x, y)
                self._miss[side] = 0
            else:
                self._miss[side] += 1
                if self._miss[side] > EXTRAPOLATE_MAX_FRAMES:
                    fail = True
                elif self._wpos[side] is not None:
                    vx, vy = self._wvel[side]
                    px, py = self._wpos[side]
                    self._wpos[side] = (px + vx * dt, py + vy * dt)
        return True, fail

    def _wrist_speed_ws(self, pts):
        ws = self._ws(pts)
        best = 0.0
        for side in ("L", "R"):
            vx, vy = self._wvel[side]
            sp = self._dist(vx, vy, 0.0, 0.0) / ws
            best = max(best, sp)
        return best

    def _mid_shoulder(self, pts):
        lx, ly = pts[KP["Lsho"]]
        rx, ry = pts[KP["Rsho"]]
        return ((lx + rx) / 2.0, (ly + ry) / 2.0)

    def _fresh_sides(self, conf):
        """Wrist sides with a current confident sample (stacked hands
        occlude one peak, so one fresh side can suffice; geometry
        consistency checks below rule out wild shots)."""
        return [s for s, k in (("L", "Lwri"), ("R", "Rwri"))
                if conf[KP[k]] >= WRIST_CONF]

    def _crossed_hold(self, pts, conf):
        """Wrists crossed on chest: both near chest center and close together."""
        if not self._fresh_sides(conf):
            return False
        ws = self._ws(pts)
        mx, my = self._mid_shoulder(pts)
        cx, cy = mx, my - 0.3 * ws  # chest center, +y up
        lw, rw = pts[KP["Lwri"]], pts[KP["Rwri"]]
        near = (self._dist(lw[0], lw[1], cx, cy) < 0.45 * ws
                and self._dist(rw[0], rw[1], cx, cy) < 0.45 * ws)
        return near and abs(lw[0] - rw[0]) < 0.35 * ws

    def _menu_side(self, pts):
        """Raised-hand menu pick: left wrist up -> BAT, right wrist up -> PITCH."""
        lw, rw = self._wpos["L"], self._wpos["R"]
        if lw is None or rw is None:
            return None
        _, lsy = pts[KP["Lsho"]]
        _, rsy = pts[KP["Rsho"]]
        lup = lw[1] > lsy and self._miss["L"] == 0
        rup = rw[1] > rsy and self._miss["R"] == 0
        if lup and not rup:
            return ROLE_BAT
        if rup and not lup:
            return ROLE_PITCH
        return None

    def _gate_ok(self, pts, conf):
        # Midpoint gate over current confident samples: immune to L/R
        # wrist identity swaps when the hands are adjacent (front view),
        # matching the swing tracker's midpoint. Hands must also be
        # together (both fresh only) so a wide split cannot fake a stance.
        fresh = self._fresh_sides(conf)
        if not fresh:
            return False
        rear = pts[KP["Rsho"]] if self.rear == "R" else pts[KP["Lsho"]]
        ws = self._ws(pts)
        fpts = [pts[KP["Lwri" if s == "L" else "Rwri"]] for s in fresh]
        mx = sum(p[0] for p in fpts) / len(fpts)
        my = sum(p[1] for p in fpts) / len(fpts)
        if self._dist(mx, my, rear[0], rear[1]) > STANCE_GATE_DIST_WS * ws:
            return False
        if len(fpts) == 2:
            lw, rw = fpts
            return self._dist(lw[0], lw[1], rw[0], rw[1]) <= 0.6 * ws
        return True

    # -- public API ---------------------------------------------------
    def force_pause(self):
        """Immediate transition to 07_SYSTEM_PAUSE (None if already there)."""
        if self.state == PAUSE:
            return None
        self._pause_hold_t = 0.0
        return self._go(PAUSE, "force_pause")

    def resume(self):
        """Leave 07_SYSTEM_PAUSE back to 03_MENU_SELECT (None if not paused)."""
        if self.state != PAUSE:
            return None
        self._dwell_side = None
        self._dwell_t = 0.0
        self._dwell_gap = 0.0
        self._menu_gate_t = 0.0
        return self._go(MENU, "resume")

    def update(self, landmarks, dt):
        """Advance the FSM one frame. Returns a Transition or None."""
        dt = min(max(dt, 0.0), 5.0)
        self.t_state += dt
        visible = self._torso_ok(landmarks)
        have = visible and landmarks is not None
        pts = landmarks["points"] if have else None
        conf = landmarks["conf"] if have else None

        # Out-of-frustum tracking (all states).
        if visible:
            self._out_t = 0.0
        else:
            self._out_t += dt
            if (self._out_t > OUT_OF_FRUSTUM_S
                    and self.state not in (UNBOUND, PAUSE)):
                self._pause_hold_t = 0.0
                return self._go(PAUSE, "out_of_frustum")
            if self.state == UNBOUND:
                return None
            if self.state == PAUSE:
                return None
            return None  # frozen mid-gesture until the player returns

        tracked, occluded = self._track_wrists(landmarks, dt)
        if not tracked:
            return None

        # Emergency pause gesture (every state except the RESOLVE lock).
        if self.state != RESOLVE and self.state != PAUSE:
            if self._crossed_hold(pts, conf):
                self._pause_hold_t += dt
                if self._pause_hold_t >= PAUSE_HOLD_S:
                    self._pause_hold_t = 0.0
                    return self._go(PAUSE, "pause_hold")
            else:
                self._pause_hold_t = 0.0

        if self.state == UNBOUND:
            self._cal_samples = []
            return self._go(CALIBRATE, "torso_detected")

        if self.state == CALIBRATE:
            self._cal_samples.append(self._ws_now(pts))
            self._torso_t += dt
            if self._torso_t >= CALIBRATE_TIMEOUT_S:
                ordered = sorted(self._cal_samples)
                self.Ws = ordered[len(ordered) // 2]  # median shoulder width
                self._torso_t = 0.0
                self._dwell_side = None
                self._dwell_t = 0.0
                self._dwell_gap = 0.0
                self._menu_gate_t = 0.0
                return self._go(MENU, "calibrated",
                                {"Ws": self.Ws, "role": None})
            return None

        if self.state == MENU:
            side = self._menu_side(pts)
            if side is not None and side == self._dwell_side:
                self._dwell_t += dt
                self._dwell_gap = 0.0
            elif side is not None:
                self._dwell_side = side
                self._dwell_t = dt
                self._dwell_gap = 0.0
            else:
                # Flicker tolerance: brief gaps pause, long gaps reset.
                self._dwell_gap += dt
                if self._dwell_gap > DWELL_GAP_S:
                    self._dwell_side = None
                    self._dwell_t = 0.0
            if self._dwell_t >= MENU_DWELL_S:
                self.role = self._dwell_side
                self._gate_t = 0.0
                return self._go(STANCE, "menu_selected", {"role": self.role})
            # Stance shortcut: holding a batting stance in the menu is an
            # unambiguous batter declaration (a 2 s dwell on the BAT tile).
            # Pitcher grips never satisfy the shoulder gate (verified in
            # tests), so this cannot misfire for pitchers.
            if self._gate_ok(pts, conf):
                self._menu_gate_t += dt
                self._gate_gap = 0.0
                if self._menu_gate_t >= MENU_DWELL_S:
                    self.role = ROLE_BAT
                    self._gate_t = 0.0
                    return self._go(STANCE, "stance_selected",
                                    {"role": self.role})
            else:
                self._gate_gap += dt
                if self._gate_gap > GATE_GAP_S:
                    self._menu_gate_t = 0.0
            if self.t_state >= MENU_AUTO_PICK_S:
                # Idle backstop: a player who never picks still gets a
                # game (batter default; pause->menu->raise-hand switches).
                self.role = ROLE_BAT
                self._gate_t = 0.0
                return self._go(STANCE, "auto_pick", {"role": self.role})
            return None

        if self.state == STANCE:
            if self._gate_ok(pts, conf):
                self._onset_blind = 0
                self._gate_t += dt
                self._gate_gap = 0.0
                if self._gate_t >= STANCE_GATE_HOLD_S:
                    self._gate_t = 0.0
                    self._path_x = []
                    self._action_vmax = 0.0
                    self._action_moved = False
                    self._miss = {"L": 0, "R": 0}  # fresh window
                    self._wvel = {"L": (0.0, 0.0), "R": (0.0, 0.0)}
                    return self._go(ACTION, "stance_loaded",
                                    {"role": self.role})
            else:
                self._gate_gap += dt
                if self._gate_gap > GATE_GAP_S:
                    self._gate_t = 0.0
                # Swing onset: a held stance whose wrists suddenly go blind
                # is a swing launch (motion blur eats both wrists). Keep
                # last-known velocity/miss streaks: speed proves motion and
                # the streaks bound the blind ride-through in ACTION.
                if (conf[KP["Lwri"]] < WRIST_CONF
                        and conf[KP["Rwri"]] < WRIST_CONF):
                    self._onset_blind += 1
                else:
                    self._onset_blind = 0
                if (self._gate_t >= ONSET_ARM_S
                        and self._onset_blind >= ONSET_BLIND_FRAMES):
                    self._onset_blind = 0
                    self._gate_t = 0.0
                    self._path_x = []
                    self._action_vmax = 0.0
                    self._action_moved = False
                    return self._go(ACTION, "swing_onset",
                                    {"role": self.role})
            if self.t_state >= STANCE_TIMEOUT_S:
                return self._go(MENU, "stance_timeout")
            return None

        if self.state == ACTION:
            if occluded:
                # Blind before any motion = truly gone; blind after real
                # motion = motion blur, ride through on extrapolation
                # (bounded by a 0.5 s both-blind hard cap).
                speed = self._wrist_speed_ws(pts)
                blind_long = min(self._miss["L"], self._miss["R"]) > 30
                if blind_long and self._action_moved:
                    # Blind swing: player present, hands blurred through a
                    # full swing (batter.mov: 25+ blind frames per real
                    # swing). No contact observed -> whiff, not a retry.
                    return self._go(RESOLVE, "blind_swing",
                                    {"vh_ws": 0.0,
                                     "vmax_ws": self._action_vmax,
                                     "role": self.role, "blind": True})
                if blind_long or (not self._action_moved
                                  and speed < IDLE_SPEED_WS):
                    return self._go(STANCE, "occlusion_fail")
            speed = self._wrist_speed_ws(pts)
            if speed >= IDLE_SPEED_WS:
                self._action_moved = True
            self._action_vmax = max(self._action_vmax, speed)
            lead = self._wpos["L"] or self._wpos["R"]
            if lead is not None:
                self._path_x.append(lead[0])
            mx, _ = self._mid_shoulder(pts)
            crossed = any(
                (a - mx) * (b - mx) < 0 or b == mx
                for a, b in zip(self._path_x, self._path_x[1:]))
            peak_passed = (self._action_moved and speed < IDLE_SPEED_WS)
            if crossed and speed >= IDLE_SPEED_WS:
                return self._go(RESOLVE, "motion_peak",
                                 {"vh_ws": speed, "vmax_ws": self._action_vmax,
                                  "role": self.role})
            if peak_passed:
                return self._go(RESOLVE, "motion_peak",
                                 {"vh_ws": self._action_vmax,
                                  "vmax_ws": self._action_vmax,
                                  "role": self.role})
            if self.t_state >= ACTION_TIMEOUT_S:
                if not self._action_moved:
                    return self._go(STANCE, "idle_reject")
                return self._go(STANCE, "action_timeout")
            return None

        if self.state == RESOLVE:
            if self.t_state >= RESOLVE_TIMEOUT_S:
                return self._go(STANCE, "resolve_done", {"role": self.role})
            return None

        if self.state == PAUSE:
            if not self._crossed_hold(pts, conf):
                return self._go(MENU, "unpaused")
            return None

        return None

