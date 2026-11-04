"""FSM transitions, timeouts, occlusion, idle-reject, frustum pause."""

from conftest import feed
from fixtures.landmarks import (
    DT, frame, base_points, neutral_frames, menu_frames, gate_frames,
    crossed_frames, frustum_gap, low_torso_frames, occlusion_frames,
    idle_sway_frames, swing_sweep_frames, vertical_drift_frames,
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
    trs = feed(fsm, frustum_gap(60))
    assert len(trs) == 1 and trs[0][0] == 60
    assert trs[0][1].event == "out_of_frustum"
    assert fsm.state == PAUSE


def test_low_torso_conf_pauses(fsm_to_menu):
    fsm = fsm_to_menu
    feed(fsm, menu_frames("BAT", 121))
    trs = feed(fsm, low_torso_frames(60))
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
