"""FSM transitions, timeouts, occlusion, idle-reject, frustum pause."""

from conftest import feed
from fixtures.landmarks import (
    DT, frame, base_points, with_wrists, repeat, neutral_frames,
    menu_frames, gate_frames, crossed_frames, frustum_gap,
    low_torso_frames, occlusion_frames, idle_sway_frames,
    swing_sweep_frames, vertical_drift_frames,
    full_cycle_frames, gate_points,
)
from server.state_machine import (
    TrackingFSM, UNBOUND, CALIBRATE, MENU, STANCE, ACTION, RESOLVE, PAUSE,
)


def _to_action():
    fsm = TrackingFSM()
    fsm.update(frame(base_points()), DT)
    feed(fsm, neutral_frames(121))
    feed(fsm, menu_frames("BAT", 121))
    feed(fsm, gate_frames(31))
    assert fsm.state == ACTION
    return fsm


def test_full_cycle_order_and_frames():
    fsm = TrackingFSM()
    seq = full_cycle_frames()
    assert len(seq) == 602
    trs = feed(fsm, seq)
    assert [(t.from_state, t.to_state, t.event) for _, t in trs] == [
        (UNBOUND, CALIBRATE, "torso_detected"),
        (CALIBRATE, MENU, "calibrated"),
        (MENU, STANCE, "menu_selected"),
        (STANCE, ACTION, "stance_loaded"),
        (ACTION, RESOLVE, "motion_peak"),
        (RESOLVE, STANCE, "resolve_done")]
    assert [i for i, _ in trs] == [1, 122, 246, 280, 288, 529]
    assert fsm.state == STANCE
    assert fsm.Ws == 1.0


def test_calibration_boundary():
    fsm = TrackingFSM()
    fsm.update(frame(base_points()), DT)
    assert feed(fsm, neutral_frames(120)) == []
    assert fsm.state == CALIBRATE
    tr = fsm.update(frame(base_points()), DT)
    assert tr is not None and tr.event == "calibrated"
    assert fsm.state == MENU
    assert fsm.Ws == 1.0


def test_menu_dwell_picks_role(fsm_to_menu):
    fsm = fsm_to_menu
    trs = feed(fsm, menu_frames("PITCH", 121))
    assert len(trs) == 1 and trs[0][1].data["role"] == "PITCH"
    assert fsm_to_menu.role == "PITCH"


def test_menu_dwell_resets_without_raise(fsm_to_menu):
    fsm = fsm_to_menu
    assert feed(fsm, menu_frames("BAT", 60)) == []
    assert feed(fsm, neutral_frames(10)) == []  # hand drops: dwell resets
    trs = feed(fsm, menu_frames("BAT", 121))
    assert len(trs) == 1 and fsm.state == STANCE


def test_stance_timeout_returns_to_menu(fsm_to_menu):
    fsm = fsm_to_menu
    feed(fsm, menu_frames("BAT", 121))
    assert fsm.state == STANCE
    trs = feed(fsm, neutral_frames(600))
    assert len(trs) == 1 and trs[0] == (600, trs[0][1])
    assert trs[0][1].event == "stance_timeout"
    assert fsm.state == MENU


def test_action_timeout_when_moved_without_cross():
    fsm = _to_action()
    trs = feed(fsm, vertical_drift_frames(1.8, n=211))
    assert len(trs) == 1 and trs[0][0] == 211
    assert trs[0][1].event == "action_timeout"
    assert fsm.state == STANCE


def test_resolve_lock_releases_after_4s():
    fsm = _to_action()
    peak_at = None
    for i, m in enumerate(swing_sweep_frames(6.0, n=12), start=1):
        if fsm.update(m, DT) is not None:
            peak_at = i
            break
    assert peak_at == 5
    trs = feed(fsm, neutral_frames(241))
    assert len(trs) == 1 and trs[0][0] == 241
    assert trs[0][1].event == "resolve_done"
    assert fsm.state == STANCE


def test_occlusion_extrapolates_3_frames():
    fsm = _to_action()
    assert feed(fsm, occlusion_frames(3)) == []
    assert fsm.state == ACTION
    assert fsm.update(frame(gate_points()), DT) is None


def test_occlusion_fails_on_4th_frame():
    fsm = _to_action()
    trs = feed(fsm, occlusion_frames(4))
    assert len(trs) == 1 and trs[0][0] == 4
    assert trs[0][1].event == "occlusion_fail"
    assert fsm.state == STANCE


def test_idle_reject_static():
    fsm = _to_action()
    assert feed(fsm, gate_frames(210)) == []
    tr = fsm.update(frame(gate_points()), DT)
    assert tr is not None and tr.event == "idle_reject"
    assert fsm.state == STANCE


def test_idle_reject_subthreshold_sway():
    fsm = _to_action()
    trs = feed(fsm, idle_sway_frames(211))
    assert len(trs) == 1 and trs[0][1].event == "idle_reject"


def test_frustum_gap_pauses(fsm_to_menu):
    fsm = fsm_to_menu
    feed(fsm, menu_frames("BAT", 121))
    # 2-frame presence release, then the 1.0 s trip fires on gap frame 62.
    trs = feed(fsm, frustum_gap(63))
    assert len(trs) == 1 and trs[0][0] == 62
    assert trs[0][1].event == "out_of_frustum"
    assert fsm.state == PAUSE


def test_low_torso_conf_pauses(fsm_to_menu):
    fsm = fsm_to_menu
    feed(fsm, menu_frames("BAT", 121))
    # 3-frame presence release + 1.0 s out-of-frustum trip.
    trs = feed(fsm, low_torso_frames(64))
    assert len(trs) == 1 and trs[0][1].event == "out_of_frustum"


def test_pause_hold_and_release(fsm_to_menu):
    fsm = fsm_to_menu
    feed(fsm, menu_frames("BAT", 121))
    assert feed(fsm, crossed_frames(90)) == []
    tr = fsm.update(frame(crossed_frames(1)[0]["points"]), DT)
    assert tr is not None and tr.event == "pause_hold"
    assert fsm.state == PAUSE
    tr = fsm.update(frame(base_points()), DT)
    assert tr is not None and tr.event == "unpaused"
    assert fsm.state == MENU


def test_force_pause_and_resume(fsm_to_menu):
    fsm = fsm_to_menu
    assert fsm.force_pause() is not None and fsm.state == PAUSE
    assert fsm.force_pause() is None
    assert fsm.resume() is not None and fsm.state == MENU
    assert fsm.resume() is None


def test_resolve_ignores_pause_gesture():
    fsm = _to_action()
    for m in swing_sweep_frames(6.0, n=12):
        fsm.update(m, DT)
    assert fsm.state == RESOLVE
    assert feed(fsm, crossed_frames(91)) == []
    assert fsm.state == RESOLVE


def test_menu_auto_pick_bat_after_idle(fsm_to_menu):
    fsm = fsm_to_menu
    trs = feed(fsm, neutral_frames(490))
    assert [t.event for _, t in trs] == ["auto_pick"]
    assert fsm.state == STANCE and fsm.role == "BAT"


def test_menu_stance_shortcut_picks_bat(fsm_to_menu):
    fsm = fsm_to_menu
    # Hands held at/below shoulder height: no tile dwell, stance hold only.
    pts = with_wrists((0.3, -0.1), (0.5, -0.15))
    trs = feed(fsm, repeat(pts, 121))
    assert [t.event for _, t in trs] == ["stance_selected"]
    assert fsm.state == STANCE and fsm.role == "BAT"


def test_menu_pitch_grips_do_not_shortcut(fsm_to_menu):
    grips = [
        with_wrists((0.0, -0.55), (0.1, -0.6)),    # FB hands at chest
        with_wrists((-0.2, 1.3), (0.2, 1.3)),      # CB overhead
        with_wrists((-0.45, -1.1), (0.3, -0.4)),   # CH hand on hip
    ]
    wide = base_points()
    wide[3] = (-1.3, -0.2)
    wide[4] = (1.3, -0.2)
    wide[5] = (-1.0, -0.6)
    wide[6] = (1.0, -0.6)
    grips.append(wide)                             # SL flared
    for pts in grips:
        fsm = TrackingFSM()
        fsm.update(frame(base_points()), DT)
        feed(fsm, neutral_frames(121))
        assert fsm.state == MENU
        # No grip may declare the player a batter (FB chest-hold reads as
        # a pause pose instead, which is also acceptable here).
        for _, tr in feed(fsm, repeat(pts, 130)):
            assert tr.to_state != STANCE, tr.event
        assert fsm.role is None


def test_menu_dwell_tolerates_brief_gap(fsm_to_menu):
    fsm = fsm_to_menu
    seq = menu_frames("BAT", 60) + neutral_frames(12) + menu_frames("BAT", 70)
    trs = feed(fsm, seq)
    assert [t.event for _, t in trs] == ["menu_selected"]
    assert fsm.role == "BAT"


def test_menu_dwell_resets_on_long_gap(fsm_to_menu):
    fsm = fsm_to_menu
    seq = menu_frames("BAT", 60) + neutral_frames(40) + menu_frames("BAT", 70)
    assert feed(fsm, seq) == []
    assert fsm.state == MENU and fsm.role is None


def test_action_static_blindness_fails():
    fsm = _to_action()
    trs = feed(fsm, occlusion_frames(4))
    assert [t.event for _, t in trs] == ["occlusion_fail"]
    assert fsm.state == STANCE


def test_action_rides_blur_after_real_motion():
    fsm = _to_action()
    # +x lateral motion at 3 Ws/s: latches moved, never crosses midline.
    sweep = [frame(with_wrists((0.45 + i * 0.05, 0.05),
                               (0.55 + i * 0.05, 0.05))) for i in range(6)]
    assert feed(fsm, sweep) == []
    assert fsm.state == ACTION
    assert feed(fsm, occlusion_frames(6)) == []  # blur: ride through
    assert fsm.state == ACTION
    # 0.5 s both-blind cap after real motion: a completed blind swing
    # (batter.mov blurs both wrists for 25+ frames per real swing), so
    # this resolves as a whiff instead of failing back to STANCE.
    trs = feed(fsm, occlusion_frames(30))
    assert [t.event for _, t in trs] == ["blind_swing"]
    assert fsm.state == RESOLVE
    assert trs[0][1].data["vh_ws"] == 0.0
    assert trs[0][1].data["blind"] is True


def _to_stance():
    fsm = TrackingFSM()
    fsm.update(frame(base_points()), DT)
    feed(fsm, neutral_frames(121))
    feed(fsm, menu_frames("BAT", 121))
    assert fsm.state == STANCE
    return fsm


def test_swing_onset_after_hold():
    fsm = _to_stance()
    # 0.2 s hold arms onset (below the 0.5 s stance_loaded bar).
    assert feed(fsm, gate_frames(12)) == []
    assert fsm.state == STANCE
    # Wrists go blind = swing launch (motion blur), not a freeze.
    trs = feed(fsm, occlusion_frames(3))
    assert [t.event for _, t in trs] == ["swing_onset"]
    assert fsm.state == ACTION


def test_onset_requires_armed_hold():
    fsm = _to_stance()
    # 4-frame brush through the gate does not arm onset.
    assert feed(fsm, gate_frames(4)) == []
    assert feed(fsm, occlusion_frames(8)) == []
    assert fsm.state == STANCE


def test_onset_requires_clean_hold():
    fsm = _to_stance()
    # Fragmented hold: 12 gate-ok frames scattered in runs of 3 arms
    # the timer (0.2 s) but no clean 6-frame run precedes the blind
    # run, so a passing shadow is not mistaken for a swing launch.
    for _ in range(4):
        assert feed(fsm, gate_frames(3)) == []
        assert feed(fsm, neutral_frames(2)) == []
    assert feed(fsm, occlusion_frames(3)) == []
    assert fsm.state == STANCE


def test_real_batter_mov_swing_resolves():
    import os
    import cv2
    from client.pose import PoseEstimator
    from client.calibration import SilhouetteCalibrator
    mov = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "batter.mov")
    assert os.path.exists(mov), "batter.mov (camera view) missing"
    fsm = TrackingFSM()
    fsm.update(frame(base_points()), DT)
    feed(fsm, neutral_frames(121))
    feed(fsm, menu_frames("BAT", 121))
    feed(fsm, gate_frames(31))
    assert fsm.state == ACTION
    est = PoseEstimator()
    cal = SilhouetteCalibrator()
    v = cv2.VideoCapture(mov)
    fps = v.get(cv2.CAP_PROP_FPS)
    dt = 1.0 / fps
    for _ in range(300):  # lock Ws on the real view first
        ok, fr = v.read()
        out = est.extract(fr) if ok else None
        if out is not None:
            cal.update(out["points"], out["conf"], dt)
    assert cal.locked
    v.set(cv2.CAP_PROP_POS_FRAMES, 400)  # real swing window (~7.7 s)
    resolved = False
    for _ in range(140):
        ok, fr = v.read()
        if not ok:
            break
        out = est.extract(fr)
        if out is None:
            continue
        tr = fsm.update({"points": cal.norm(out["points"]),
                         "conf": out["conf"]}, dt)
        if tr is not None and tr.event == "motion_peak":
            resolved = True
            break
    v.release()
    assert resolved, "the real 7.7 s swing must resolve the window"
    assert fsm.state == RESOLVE
