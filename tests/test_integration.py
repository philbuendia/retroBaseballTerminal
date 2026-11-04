"""Integration: live server + GameClient, session phase flow, score JSON."""

from conftest import feed, wait_for, PERSON_JPG
from fixtures.landmarks import DT, frame, base_points, neutral_frames, menu_frames
from server.state_machine import TrackingFSM
from server.net import Session
from client.net import GameClient
from client import protocol as P
from client.main import key_to_event
from client.capture import ReplaySource


def _assert_score_json(msg):
    assert msg["t"] == "score"
    assert set(("runs", "arcade", "inning", "half")) <= set(msg)
    assert set(("away", "home")) <= set(msg["runs"])
    assert isinstance(msg["arcade"], int)
    assert msg["half"] in ("top", "bottom")


def test_live_hello_select_and_score(live_server):
    host, port = live_server
    c = GameClient()
    c.connect(host, port, timeout=5.0)
    try:
        assert c.connected
        c.send_event(P.make_hello())
        seen = wait_for(c, lambda m: any(
            x.get("t") == "state" and x.get("fsm") == "03_MENU_SELECT" for x in m))
        assert any(x.get("fsm") == "03_MENU_SELECT" for x in seen)
        c.send_event(P.make_select("BOTH", 3))
        seen = wait_for(c, lambda m: any(x.get("t") == "score" for x in m))
        scores = [x for x in seen if x.get("t") == "score"]
        assert scores
        for s in scores:
            _assert_score_json(s)
        assert scores[-1]["inning"] == 1 and scores[-1]["half"] == "top"
    finally:
        c.close()


def test_live_key_events_resolve_and_pause(live_server):
    host, port = live_server
    c = GameClient()
    c.connect(host, port, timeout=5.0)
    try:
        c.send_event(P.make_hello())
        wait_for(c, lambda m: any(x.get("t") == "state" for x in m))
        c.send_event(P.make_select("BOTH", 3))
        wait_for(c, lambda m: any(x.get("t") == "score" for x in m))
        ctx = {"pitch": "FB", "innings": 3, "pitching": True}
        evs, quit_ = key_to_event("g", ctx)
        assert not quit_ and evs[0]["t"] == "stance"
        for e in evs:
            c.send_event(e)
        evs, _ = key_to_event(" ", ctx)
        assert evs[0]["t"] == "throw"
        for e in evs:
            c.send_event(e)
        seen = wait_for(c, lambda m: any(
            x.get("t") in ("pitch_result", "hit_result") for x in m))
        assert any(x.get("t") in ("pitch_result", "hit_result") for x in seen)
        seen = wait_for(c, lambda m: any(x.get("t") == "score" for x in m))
        for s in [x for x in seen if x.get("t") == "score"]:
            _assert_score_json(s)
        c.send_event({"t": "bogus"})
        seen = wait_for(c, lambda m: any(x.get("t") == "error" for x in m))
        assert any(x.get("t") == "error" for x in seen)
        c.send_event(P.make_pause())
        seen = wait_for(c, lambda m: any(
            x.get("t") == "state" and x.get("fsm") == "07_SYSTEM_PAUSE" for x in m))
        assert any(x.get("fsm") == "07_SYSTEM_PAUSE" for x in seen)
        c.send_event(P.make_resume())
        seen = wait_for(c, lambda m: any(
            x.get("t") == "state" and x.get("fsm") != "07_SYSTEM_PAUSE" for x in m))
        assert any(x.get("t") == "state" and x.get("fsm") != "07_SYSTEM_PAUSE"
                   for x in seen)
    finally:
        c.close()


def test_replay_source_reads_still():
    rs = ReplaySource(PERSON_JPG)
    try:
        fr = rs.read_frame()
        assert fr is not None and fr.ndim == 3
        assert rs.fps == 60.0
    finally:
        rs.close()


def test_key_to_event_map():
    ctx = {"pitch": "FB", "innings": 3, "pitching": False}
    assert key_to_event("q", ctx) == ([], True)
    assert key_to_event("z", ctx) == ([], False)
    evs, _ = key_to_event(" ", dict(ctx))
    assert evs[0]["t"] == "swing"
    evs, _ = key_to_event(" ", {"pitch": "SL", "innings": 3, "pitching": True})
    assert evs[0] == {"t": "throw", "pitch": "SL", "arm_ws": 4.5,
                      "nose_shift_ws": 0.0}
    ctx2 = dict(ctx)
    key_to_event("c", ctx2)
    assert ctx2["pitch"] == "CB"


def test_phase_flow_calibrate_to_swap():
    fsm = TrackingFSM()
    tr = fsm.update(frame(base_points()), DT)
    assert tr is not None and tr.to_state == "02_CALIBRATE"
    feed(fsm, neutral_frames(121))
    assert fsm.state == "03_MENU_SELECT"
    feed(fsm, menu_frames("BAT", 121))
    assert fsm.state == "04_STANCE_READY" and fsm.role == "BAT"

    s = Session(3)
    assert s.handle({"t": "hello", "v": 1})[0]["fsm"] == "03_MENU_SELECT"
    r = s.handle({"t": "select", "role": "BOTH", "innings": 3})
    assert s.phase == "04_STANCE_READY"
    _assert_score_json([x for x in r if x["t"] == "score"][0])
    s.handle({"t": "stance", "held_s": 0.6})
    assert s.phase == "05_ACTION_WINDOW"
    r = s.handle({"t": "throw", "pitch": "FB", "arm_ws": 4.0,
                  "nose_shift_ws": 0.0})
    assert s.phase == "06_PLAY_RESOLVE"
    kinds = {x["t"] for x in r}
    assert kinds & {"pitch_result", "hit_result"} and "score" in kinds
    s.update(4.0)
    assert s.phase == "04_STANCE_READY"

    for _ in range(3):
        s.game.count.strikes = 2
        s.game.apply_pitch_call("strike")
    replies = []
    s._manage_half_end(replies)
    assert s.game.half == "bottom"

    r = s.handle({"t": "stance", "held_s": 0.6})
    assert s.phase == "05_ACTION_WINDOW" and s.pending_pitch is not None
    r = s.handle({"t": "swing", "vh_ws": 5.0, "dt_s": 0.05,
                  "slope": 0.4, "crossed": True})
    kinds = {x["t"] for x in r}
    assert "hit_result" in kinds and "score" in kinds
    for x in r:
        if x["t"] == "score":
            _assert_score_json(x)
