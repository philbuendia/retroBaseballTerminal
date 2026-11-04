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


def test_stance_rearms_from_menu_without_reset():
    # Regression: after a stance timeout the session sat in MENU and
    # every later stance errored, so the (AI) pitcher never threw again.
    s = Session(3)
    s.handle({"t": "hello", "v": 1})
    s.handle({"t": "select", "role": "BOTH", "innings": 3})
    assert s.phase == "04_STANCE_READY"
    game_before = s.game
    s.update(10.5)  # STANCE_TIMEOUT_S
    assert s.phase == "03_MENU_SELECT"
    r = s.handle({"t": "stance", "held_s": 0.6})
    assert s.phase == "05_ACTION_WINDOW"  # re-arm flows into the pitch
    assert s.game is game_before, "re-arm must not reset the game"
    assert r[0].get("event") == "rearm"
    # ... and the re-armed session resolves the pitch normally.
    r = s.handle({"t": "throw", "pitch": "FB", "arm_ws": 4.0,
                  "nose_shift_ws": 0.0})
    assert s.phase == "06_PLAY_RESOLVE"
    assert {x["t"] for x in r} & {"pitch_result", "hit_result"}


def test_ai_pitch_arrives_after_stance_then_swing_resolves():
    # Bottom-half camera flow: stance deals the AI pitch, swing resolves it.
    s = Session(3)
    s.handle({"t": "hello", "v": 1})
    s.handle({"t": "select", "role": "BOTH", "innings": 3})
    s.game.half = "bottom"  # bottom half: player bats vs AI pitcher
    r = s.handle({"t": "stance", "held_s": 0.6})
    assert s.phase == "05_ACTION_WINDOW"
    assert s.pending_pitch is not None, "AI pitcher must deal on stance"
    assert any("pitch" in x for x in r), "stance reply carries the pitch"
    r = s.handle({"t": "swing", "vh_ws": 5.0, "dt_s": 0.05,
                  "slope": 0.4, "crossed": True})
    assert {x["t"] for x in r} & {"pitch_result", "hit_result"}


def test_stance_edge_sends_once_on_load():
    from client.main import maybe_send_stance_edge

    class FakeClient:
        def __init__(self):
            self.sent = []

        def send_event(self, m):
            self.sent.append(m)

    c = FakeClient()
    assert maybe_send_stance_edge(c, "04_STANCE_READY",
                                  "05_ACTION_WINDOW") is True
    assert [m["t"] for m in c.sent] == ["stance"]
    assert c.sent[0]["held_s"] >= 0.5
    # No other transition may emit stance (no duplicate pitches).
    for prev, cur in (("04_STANCE_READY", "04_STANCE_READY"),
                      ("05_ACTION_WINDOW", "05_ACTION_WINDOW"),
                      ("05_ACTION_WINDOW", "06_PLAY_RESOLVE"),
                      ("03_MENU_SELECT", "04_STANCE_READY")):
        assert maybe_send_stance_edge(c, prev, cur) is False
    assert len(c.sent) == 1


def test_select_edge_sends_fsm_role_once():
    from client.main import maybe_send_select_edge

    class FakeClient:
        def __init__(self):
            self.sent = []

        def send_event(self, m):
            self.sent.append(m)

    c = FakeClient()
    assert maybe_send_select_edge(c, "03_MENU_SELECT", "04_STANCE_READY",
                                  "PITCH", 6) is True
    assert [(m["t"], m.get("role"), m.get("innings")) for m in c.sent] == [
        ("select", "PITCH", 6)]
    assert maybe_send_select_edge(c, "03_MENU_SELECT", "04_STANCE_READY",
                                  None, 3) is True
    assert c.sent[-1]["role"] == "BAT"  # safe default, never empty
    for prev, cur in (("03_MENU_SELECT", "03_MENU_SELECT"),
                      ("04_STANCE_READY", "05_ACTION_WINDOW")):
        assert maybe_send_select_edge(c, prev, cur, "BAT", 3) is False
    assert len(c.sent) == 2
