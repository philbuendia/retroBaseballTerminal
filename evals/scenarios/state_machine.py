"""Eval scenario: tracking FSM transitions, timeouts, occlusion, idle, pause."""

import traceback

from fixtures.landmarks import (
    DT, frame, base_points, with_wrists, repeat, neutral_frames,
    calibrate_frames, menu_frames, gate_frames, crossed_frames,
    frustum_gap, low_torso_frames, occlusion_frames, idle_sway_frames,
    swing_sweep_frames, vertical_drift_frames, full_cycle_frames,
    menu_points, gate_points, crossed_points,
)
from server.state_machine import (
    TrackingFSM, UNBOUND, CALIBRATE, MENU, STANCE, ACTION, RESOLVE, PAUSE,
)

CATEGORY = "state_machine"
WEIGHT = 20


def _feed(fsm, frames, cap=None):
    """Feed frames; return (transitions, frames_consumed)."""
    trs = []
    for i, m in enumerate(frames):
        if cap is not None and i >= cap:
            break
        tr = fsm.update(m, DT)
        if tr is not None:
            trs.append((i + 1, tr))
    return trs, len(frames)


def _to_menu(fsm):
    tr = fsm.update(frame(base_points()), DT)
    assert tr is not None and tr.to_state == CALIBRATE, "UNBOUND->CALIBRATE"
    trs, _ = _feed(fsm, neutral_frames(121))
    assert len(trs) == 1 and trs[0][1].to_state == MENU, "CALIBRATE->MENU, %r" % (trs,)
    return trs[0][0]


def _to_stance(fsm):
    trs, _ = _feed(fsm, menu_frames("BAT", 121))
    assert len(trs) == 1 and trs[0][1].to_state == STANCE, "MENU->STANCE, %r" % (trs,)
    assert trs[0][1].data.get("role") == "BAT", "menu role BAT"
    return trs[0][0]


def _to_action(fsm):
    trs, _ = _feed(fsm, gate_frames(31))
    assert len(trs) == 1 and trs[0][1].to_state == ACTION, "STANCE->ACTION, %r" % (trs,)
    return trs[0][0]


def check_sm_full_cycle():
    fsm = TrackingFSM()
    trs, n = _feed(fsm, full_cycle_frames())
    assert n == 602, "full-cycle stream is 602 frames, got %d" % n
    events = [(tr.from_state, tr.to_state, tr.event) for _, tr in trs]
    want = [(UNBOUND, CALIBRATE, "torso_detected"),
            (CALIBRATE, MENU, "calibrated"),
            (MENU, STANCE, "menu_selected"),
            (STANCE, ACTION, "stance_loaded"),
            (ACTION, RESOLVE, "motion_peak"),
            (RESOLVE, STANCE, "resolve_done")]
    assert events == want, "transition order %r" % (events,)
    at = [i for i, _ in trs]
    # Peak hits on the 5th swing frame; the 7 remaining swing frames already
    # count toward the RESOLVE lock, so it releases at 288 + 241 = 529.
    assert at == [1, 122, 246, 280, 288, 529], "fire frames %r" % (at,)
    assert fsm.state == STANCE, "ends back in STANCE, %s" % fsm.state
    assert fsm.Ws == 1.0, "Ws locks to 1.0, got %r" % (fsm.Ws,)
    return "6 transitions in order at frames %r, Ws=1.0" % (at,)


def check_sm_timeouts():
    # STANCE 10.0 s -> MENU (600 frames, no gate held).
    fsm = TrackingFSM()
    _to_menu(fsm)
    _to_stance(fsm)
    trs, _ = _feed(fsm, neutral_frames(600))
    assert len(trs) == 1 and trs[0][1].event == "stance_timeout", "stance timeout %r" % (trs,)
    assert trs[0][0] == 600, "stance timeout fires on frame 600, got %d" % trs[0][0]
    assert fsm.state == MENU
    # ACTION moved-but-no-cross 3.5 s -> STANCE action_timeout (211 frames).
    fsm = TrackingFSM()
    _to_menu(fsm)
    _to_stance(fsm)
    _to_action(fsm)
    trs, _ = _feed(fsm, vertical_drift_frames(1.8, n=211))
    assert len(trs) == 1 and trs[0][1].event == "action_timeout", "action timeout %r" % (trs,)
    assert trs[0][0] == 211, "action timeout fires on frame 211, got %d" % trs[0][0]
    # RESOLVE 4.0 s -> STANCE resolve_done (241 frames).
    fsm = TrackingFSM()
    _to_menu(fsm)
    _to_stance(fsm)
    _to_action(fsm)
    # Feed the sweep only until the peak so the RESOLVE clock starts clean.
    peak_at = None
    for i, m in enumerate(swing_sweep_frames(6.0, n=12), start=1):
        tr = fsm.update(m, DT)
        if tr is not None:
            assert tr.event == "motion_peak", "swing must peak, %r" % (tr,)
            peak_at = i
            break
    assert peak_at == 5, "motion peak on swing frame 5, got %r" % (peak_at,)
    trs, _ = _feed(fsm, neutral_frames(241))
    assert len(trs) == 1 and trs[0][1].event == "resolve_done", "resolve done %r" % (trs,)
    assert trs[0][0] == 241, "resolve fires on frame 241, got %d" % trs[0][0]
    # MENU dwell tolerates a 0.2 s flicker gap but resets on a 0.66 s gap.
    fsm = TrackingFSM()
    _to_menu(fsm)
    seq = menu_frames("BAT", 60) + neutral_frames(12) + menu_frames("BAT", 70)
    trs, _ = _feed(fsm, seq)
    assert [t.event for _, t in trs] == ["menu_selected"], "gap dwell %r" % (trs,)
    fsm = TrackingFSM()
    _to_menu(fsm)
    seq = menu_frames("BAT", 60) + neutral_frames(40) + menu_frames("BAT", 70)
    trs, _ = _feed(fsm, seq)
    assert trs == [], "long gap must reset dwell, %r" % (trs,)
    # MENU stance shortcut: 2 s held stance declares BAT without a raise.
    fsm = TrackingFSM()
    _to_menu(fsm)
    pts = with_wrists((0.3, -0.1), (0.5, -0.15))
    trs, _ = _feed(fsm, repeat(pts, 121))
    assert [t.event for _, t in trs] == ["stance_selected"], "shortcut %r" % (trs,)
    assert fsm.role == "BAT"
    # MENU idle backstop: auto-pick BAT at 8 s, exactly once.
    fsm = TrackingFSM()
    _to_menu(fsm)
    trs, _ = _feed(fsm, neutral_frames(490))
    assert [t.event for _, t in trs] == ["auto_pick"], "auto-pick %r" % (trs,)
    assert fsm.role == "BAT" and fsm.state == STANCE
    return "stance@600 action@211 resolve@241 swing-peak@5 dwell-gap shortcut auto-pick"


def check_sm_occlusion():
    # 3-frame wrist dropout is extrapolated: no transition, tracking alive.
    fsm = TrackingFSM()
    _to_menu(fsm)
    _to_stance(fsm)
    _to_action(fsm)
    trs, _ = _feed(fsm, occlusion_frames(3))
    assert trs == [], "3-frame occlusion must not transition, %r" % (trs,)
    assert fsm.state == ACTION, "still in ACTION after 3-frame gap"
    tr = fsm.update(frame(gate_points()), DT)
    assert tr is None, "recovery frame must not transition"
    # 4th consecutive missing frame fails back to STANCE.
    fsm = TrackingFSM()
    _to_menu(fsm)
    _to_stance(fsm)
    _to_action(fsm)
    trs, _ = _feed(fsm, occlusion_frames(4))
    assert len(trs) == 1, "4-frame occlusion must transition once, %r" % (trs,)
    assert trs[0][0] == 4 and trs[0][1].event == "occlusion_fail", "occlusion fail %r" % (trs,)
    assert fsm.state == STANCE
    # Blur ride-through: misses after real motion do not fail (0.5 s cap).
    fsm = TrackingFSM()
    _to_menu(fsm)
    _to_stance(fsm)
    _to_action(fsm)
    sweep = [frame(with_wrists((0.45 + i * 0.05, 0.05),
                               (0.55 + i * 0.05, 0.05))) for i in range(6)]
    trs, _ = _feed(fsm, sweep)
    assert trs == [] and fsm.state == ACTION
    trs, _ = _feed(fsm, occlusion_frames(6))
    assert trs == [] and fsm.state == ACTION, "blur must ride, %r" % (trs,)
    # 0.5 s both-blind cap after real motion resolves a blind swing
    # (batter.mov blurs both wrists for 25+ frames per real swing).
    trs, _ = _feed(fsm, occlusion_frames(30))
    assert [t.event for _, t in trs] == ["blind_swing"], "cap %r" % (trs,)
    assert fsm.state == RESOLVE and trs[0][1].data["blind"] is True
    # Swing onset: 0.2 s hold arms, 3 blind frames fire; a 4-frame
    # brush through the gate does not arm.
    fsm = TrackingFSM()
    _to_menu(fsm)
    _to_stance(fsm)
    trs, _ = _feed(fsm, gate_frames(12))
    assert trs == [] and fsm.state == STANCE, "hold must arm, %r" % (trs,)
    trs, _ = _feed(fsm, occlusion_frames(3))
    assert ([t.event for _, t in trs] == ["swing_onset"]
            and fsm.state == ACTION), "onset %r" % (trs,)
    fsm = TrackingFSM()
    _to_menu(fsm)
    _to_stance(fsm)
    trs, _ = _feed(fsm, gate_frames(4))
    assert trs == []
    trs, _ = _feed(fsm, occlusion_frames(8))
    assert trs == [] and fsm.state == STANCE, "unprimed %r" % (trs,)
    return ("3f extrapolated, 4th fails; blur rides after motion, 0.5s "
            "blind-swing cap; onset arms at 0.15s hold + 3 blind")


def check_sm_idle_reject():
    # Static ACTION window for 211 frames -> idle_reject. The idle stream
    # holds the gate pose (zero wrist velocity); jumping to a neutral pose
    # would be a 50+ Ws/s fling, i.e. a swing, not idleness.
    fsm = TrackingFSM()
    _to_menu(fsm)
    _to_stance(fsm)
    _to_action(fsm)
    trs, _ = _feed(fsm, gate_frames(210))
    assert trs == [], "no transition before 3.5 s, %r" % (trs,)
    tr = fsm.update(frame(gate_points()), DT)
    assert tr is not None and tr.event == "idle_reject", "idle reject, %r" % (tr,)
    assert fsm.state == STANCE
    # Sub-threshold sway (< 1.5 Ws/s) also rejects as idle.
    fsm = TrackingFSM()
    _to_menu(fsm)
    _to_stance(fsm)
    _to_action(fsm)
    trs, _ = _feed(fsm, idle_sway_frames(211))
    assert len(trs) == 1 and trs[0][1].event == "idle_reject", "sway idle %r" % (trs,)
    return "static@211 + sway both idle_reject"


def check_sm_frustum_pause():
    # None frames x63 (2-frame release + ~1.0 s) -> PAUSE from STANCE.
    fsm = TrackingFSM()
    _to_menu(fsm)
    _to_stance(fsm)
    trs, _ = _feed(fsm, frustum_gap(63))
    assert len(trs) == 1 and trs[0][1].event == "out_of_frustum", "frustum %r" % (trs,)
    assert trs[0][0] == 62 and fsm.state == PAUSE
    # Low torso conf behaves identically.
    fsm = TrackingFSM()
    _to_menu(fsm)
    _to_stance(fsm)
    trs, _ = _feed(fsm, low_torso_frames(64))
    assert len(trs) == 1 and trs[0][1].event == "out_of_frustum", "low-torso %r" % (trs,)
    # Crossed-wrists 1.5 s hold -> PAUSE (91 frames), release -> MENU.
    fsm = TrackingFSM()
    _to_menu(fsm)
    _to_stance(fsm)
    trs, _ = _feed(fsm, crossed_frames(91))
    assert len(trs) == 1 and trs[0][1].event == "pause_hold", "pause hold %r" % (trs,)
    assert trs[0][0] == 91, "pause hold fires on frame 91, got %d" % trs[0][0]
    tr = fsm.update(frame(base_points()), DT)
    assert tr is not None and tr.event == "unpaused" and fsm.state == MENU
    # force_pause / resume semantics.
    tr = fsm.force_pause()
    assert tr is not None and fsm.state == PAUSE
    assert fsm.force_pause() is None, "force_pause idempotent in PAUSE"
    tr = fsm.resume()
    assert tr is not None and fsm.state == MENU
    assert fsm.resume() is None, "resume no-op outside PAUSE"
    # RESOLVE physics lock ignores the pause gesture.
    fsm = TrackingFSM()
    _to_menu(fsm)
    _to_stance(fsm)
    _to_action(fsm)
    _feed(fsm, swing_sweep_frames(6.0, n=12))
    assert fsm.state == RESOLVE
    trs, _ = _feed(fsm, crossed_frames(91))
    assert trs == [], "RESOLVE must ignore pause hold, %r" % (trs,)
    assert fsm.state == RESOLVE
    return "frustum@60 lowconf@60 hold@91 resume-ok lock-immune"


CHECKS = [("sm_full_cycle", 5, check_sm_full_cycle),
          ("sm_timeouts", 5, check_sm_timeouts),
          ("sm_occlusion", 4, check_sm_occlusion),
          ("sm_idle_reject", 3, check_sm_idle_reject),
          ("sm_frustum_pause", 3, check_sm_frustum_pause)]


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
