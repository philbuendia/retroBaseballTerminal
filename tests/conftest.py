"""Shared pytest fixtures: path bootstrap, live server, frame helpers."""

import os
import socket
import sys
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "evals"))

from fixtures.landmarks import DT, frame, base_points  # noqa: E402

PERSON_JPG = os.path.join(ROOT, "models", "person.jpg")


def feed(fsm, frames):
    """Feed frames to an FSM; return list of (1-based index, Transition)."""
    out = []
    for i, m in enumerate(frames, start=1):
        tr = fsm.update(m, DT)
        if tr is not None:
            out.append((i, tr))
    return out


@pytest.fixture()
def fsm_to_menu():
    """Fresh TrackingFSM driven UNBOUND -> CALIBRATE -> MENU."""
    from fixtures.landmarks import neutral_frames
    from server.state_machine import TrackingFSM, MENU
    fsm = TrackingFSM()
    fsm.update(frame(base_points()), DT)
    feed(fsm, neutral_frames(121))
    assert fsm.state == MENU
    return fsm


@pytest.fixture()
def live_server():
    """GameServer on an OS-picked port; yields (host, port); clean teardown."""
    from server.net import GameServer
    srv = GameServer("127.0.0.1", 0, 3)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    deadline = time.monotonic() + 5.0
    while srv.port == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert srv.port != 0
    yield "127.0.0.1", srv.port
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


def wait_for(client, pred, timeout=5.0):
    seen = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        seen += client.poll_frame()
        if pred(seen):
            return seen
        time.sleep(0.02)
    return seen
