"""Eval scenario: live server + client flow, session phase flow, score JSON."""

import os
import socket
import threading
import time
import traceback

from fixtures.landmarks import DT, frame, base_points, neutral_frames, menu_frames
from server.state_machine import TrackingFSM, MENU, STANCE, ACTION, RESOLVE
from server.net import Session, GameServer
from server.protocol import make_score
from client.net import GameClient
from client import protocol as P
from client.main import key_to_event
from client.capture import ReplaySource

CATEGORY = "integration"
WEIGHT = 5

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
PERSON_JPG = os.path.join(ROOT, "models", "person.jpg")


def _wait_for(client, pred, timeout=5.0):
    """Poll until pred(msgs-so-far) is truthy; return all messages seen."""
    seen = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        seen += client.poll_frame()
        if pred(seen):
            return seen
        time.sleep(0.02)
    return seen


def _serve():
    srv = GameServer("127.0.0.1", 0, 3)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    deadline = time.monotonic() + 5.0
    while srv.port == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert srv.port != 0, "server did not bind an OS-picked port"
    return srv, th


def _stop(srv, th):
    try:
        srv._stop.set()
        try:
            wake = socket.create_connection(("127.0.0.1", srv.port), timeout=2)
            wake.close()
        except OSError:
            pass
        th.join(timeout=5)
    finally:
        srv.shutdown()


def _assert_score_json(msg):
    assert msg["t"] == "score", "score tag, %r" % (msg,)
    assert set(("runs", "arcade", "inning", "half")) <= set(msg), "score keys"
    assert set(("away", "home")) <= set(msg["runs"]), "runs keys"
    assert isinstance(msg["arcade"], int), "arcade int"
    assert msg["half"] in ("top", "bottom"), "half value"


def check_int_live_flow():
    srv, th = _serve()
    try:
        client = GameClient()
        client.connect("127.0.0.1", srv.port, timeout=5.0)
        assert client.connected
        # Replay event source works headless (no camera needed).
        replay = ReplaySource(PERSON_JPG)
        still = replay.read_frame()
        assert still is not None and still.ndim == 3, "replay still decodes"
        # hello -> MENU state; select -> STANCE + score JSON.
        client.send_event(P.make_hello())
        seen = _wait_for(client, lambda m: any(
            x.get("t") == "state" and x.get("fsm") == "03_MENU_SELECT" for x in m))
        assert any(x.get("fsm") == "03_MENU_SELECT" for x in seen), "hello->MENU"
        client.send_event(P.make_select("BOTH", 3))
        seen = _wait_for(client, lambda m: any(x.get("t") == "score" for x in m))
        scores = [x for x in seen if x.get("t") == "score"]
        assert scores, "select yields score JSON"
        for s in scores:
            _assert_score_json(s)
        assert scores[-1]["inning"] == 1 and scores[-1]["half"] == "top"
        # Keypress-sample events drive the live game (top half: pitching).
        ctx = {"pitch": "FB", "innings": 3, "pitching": True}
        evs, quit_ = key_to_event("g", ctx)
        assert not quit_ and evs and evs[0]["t"] == "stance"
        for e in evs:
            client.send_event(e)
        evs, _ = key_to_event(" ", ctx)
        assert evs and evs[0]["t"] == "throw", "space throws in pitch half"
        for e in evs:
            client.send_event(e)
        seen = _wait_for(client, lambda m: any(
            x.get("t") in ("pitch_result", "hit_result") for x in m))
        res = [x for x in seen if x.get("t") in ("pitch_result", "hit_result")]
        assert res, "throw resolves pitch/hit result"
        seen2 = _wait_for(client, lambda m: any(x.get("t") == "score" for x in m))
        for s in [x for x in seen2 if x.get("t") == "score"]:
            _assert_score_json(s)
        # Unknown messages get error replies, never a crash or hang.
        client.send_event({"t": "bogus"})
        seen = _wait_for(client, lambda m: any(x.get("t") == "error" for x in m))
        assert any(x.get("t") == "error" for x in seen), "error reply"
        # Pause / resume round-trip over the wire.
        client.send_event(P.make_pause())
        seen = _wait_for(client, lambda m: any(
            x.get("t") == "state" and x.get("fsm") == "07_SYSTEM_PAUSE" for x in m))
        assert any(x.get("fsm") == "07_SYSTEM_PAUSE" for x in seen), "paused"
        client.send_event(P.make_resume())
        seen = _wait_for(client, lambda m: any(
            x.get("t") == "state" and x.get("fsm") != "07_SYSTEM_PAUSE" for x in m))
        assert any(x.get("t") == "state" and x.get("fsm") != "07_SYSTEM_PAUSE"
                   for x in seen), "resumed"
        client.close()
        replay.close()
    finally:
        _stop(srv, th)
    return "port %d: hello/select/keys/pause/error + score JSON" % srv.port


def check_int_phase_flow():
    # Client-side tracking: calibrate -> menu via landmark frames.
    fsm = TrackingFSM()
    tr = fsm.update(frame(base_points()), DT)
    assert tr is not None and tr.to_state == "02_CALIBRATE", "calibrate"
    for m in neutral_frames(121):
        tr = fsm.update(m, DT) or tr
    assert fsm.state == MENU, "menu, got %s" % fsm.state
    for m in menu_frames("BAT", 121):
        tr = fsm.update(m, DT) or tr
    assert fsm.state == STANCE and fsm.role == "BAT", "stance BAT"
    # Server session: menu -> stance -> action -> resolve -> swap.
    s = Session(3)
    r = s.handle({"t": "hello", "v": 1})
    assert r[0]["fsm"] == "03_MENU_SELECT" and s.phase == "03_MENU_SELECT"
    r = s.handle({"t": "select", "role": "BOTH", "innings": 3})
    assert s.phase == STANCE, "select->STANCE"
    _assert_score_json([x for x in r if x["t"] == "score"][0])
    r = s.handle({"t": "stance", "held_s": 0.6})
    assert s.phase == ACTION, "stance->ACTION"
    r = s.handle({"t": "throw", "pitch": "FB", "arm_ws": 4.0,
                  "nose_shift_ws": 0.0})
    assert s.phase == RESOLVE, "throw->RESOLVE"
    kinds = {x["t"] for x in r}
    assert kinds >= {"score"} and kinds & {"pitch_result", "hit_result"}, \
        "resolve replies %r" % (kinds,)
    for x in r:
        if x["t"] == "score":
            _assert_score_json(x)
    r = s.update(4.0)
    assert s.phase == STANCE, "resolve timeout->STANCE"
    # Swap to the batting half: force 3 top-half outs, then swap.
    for _ in range(3):
        s.game.count.strikes = 2
        s.game.apply_pitch_call("strike")
    assert s.game.half_over
    replies = []
    s._manage_half_end(replies)
    assert s.game.half == "bottom", "swapped to bottom"
    # Batting half: stance deals a pitch, swing resolves a hit + score.
    r = s.handle({"t": "stance", "held_s": 0.6})
    assert s.phase == ACTION and s.pending_pitch is not None, "pitch dealt"
    r = s.handle({"t": "swing", "vh_ws": 5.0, "dt_s": 0.05,
                  "slope": 0.4, "crossed": True})
    kinds = {x["t"] for x in r}
    assert "hit_result" in kinds and "score" in kinds, "swing %r" % (kinds,)
    for x in r:
        if x["t"] == "score":
            _assert_score_json(x)
    assert make_score(s.game)["half"] == "bottom"
    return "calibrate->menu->stance->action->resolve->swap + scores"


CHECKS = [("int_live_flow", 3, check_int_live_flow),
          ("int_phase_flow", 2, check_int_phase_flow)]


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
