"""Terminal client headless: render frames, synth audio, pose extract."""

import os
import re

import numpy as np
import pytest

from client.render import TerminalRenderer, BLOCK, ESC, FG_CODE, BG_CODE
from client.audio import ChipSynth
from client.pose import PoseEstimator
from client.calibration import SilhouetteCalibrator
from client import gestures as G
from conftest import PERSON_JPG

_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")


def _strip_sgr(s):
    return _SGR_RE.sub("", s)


def test_field_frame_cells_and_zone():
    r = TerminalRenderer("80x48")
    r.render_field({}, view="pitch")
    s = r.to_string()
    rows = [x for x in s.split("\n") if x]
    assert len(rows) == 48
    # Every row is exactly 80 visible cells (half-blocks and/or text chars).
    assert all(len(_strip_sgr(x)) == 80 for x in rows)
    assert "94" in s and "104" in s  # ZONE LBLUE SGR pair
    # Batter view: pitcher + live ball render without errors.
    r.render_field({"ball_progress": 0.5}, view="bat")
    s2 = r.to_string()
    assert len([x for x in s2.split("\n") if x]) == 48
    assert all(len(_strip_sgr(x)) == 80 for x in s2.split("\n") if x)
    r.render_field({"ball_progress": 1.0, "contact_flash": True})
    assert "H0 A0" in _strip_sgr(r.to_string())  # default scoreboard


def test_frame_text_is_legible():
    r = TerminalRenderer("80x48")
    r.render_menu()
    menu = _strip_sgr(r.to_string())
    assert "R E T R O" in menu and "D I A M O N D" in menu
    assert "HOLD TO SELECT" in menu
    r.render_menu(auto_pick_s=5.2)
    assert "AUTO-BAT 5S" in _strip_sgr(r.to_string())
    r.render_field({"runs": {"HOME": 3, "AWAY": 1}, "arcade": 1250,
                    "inning": 2, "half": "bottom",
                    "count": {"balls": 2, "strikes": 1}, "outs": 1})
    field = _strip_sgr(r.to_string())
    assert "H3 A1 I2B" in field
    assert "B2 S1 O1" in field
    assert "1250 PTS" in field
    assert "RETRO" in field  # billboard
    r.render_pause()
    assert "P A U S E D" in _strip_sgr(r.to_string())
    assert "UNCROSS ARMS" in _strip_sgr(r.to_string())


def test_menu_highlight_dwell_and_pause_change_frames():
    r = TerminalRenderer("80x48")
    r.render_menu()
    plain = r.to_string()
    r.render_menu(dwell_side="BAT", dwell_frac=0.5)
    hi = r.to_string()
    assert hi != plain
    r.render_menu(dwell_frac=0.0)
    assert hi != r.to_string()
    r.render_field({})
    before = r.to_string()
    r.render_pause()
    assert r.to_string() != before


def test_alternate_row_dim_and_sgr_budget():
    r = TerminalRenderer("80x48")
    r.render_field({})
    field = r.to_string()
    body = [x for x in field.split("\n") if x]
    for i, row in enumerate(body):
        if i % 2 == 1:
            assert row.startswith(ESC + "[2m")
        else:
            assert "[2m" not in row
    r.render_menu(dwell_side="PITCH", dwell_frac=0.7)
    menu = r.to_string()
    r.render_field({})
    r.render_pause()
    paused = r.to_string()
    for name, s in (("field", field), ("menu", menu), ("pause", paused)):
        for i, row in enumerate(x for x in s.split("\n") if x):
            n = len(set(m.group(0) for m in _SGR_RE.finditer(row)))
            assert n <= 16, "%s row %d: %d SGR codes" % (name, i, n)
    valid = {0, 2} | set(FG_CODE) | set(BG_CODE)
    for m in _SGR_RE.finditer(field + menu + paused):
        for tok in m.group(1).split(";"):
            assert int(tok) in valid


def test_tall_mode_and_bad_mode():
    t = TerminalRenderer("80x96")
    t.render_field({})
    assert len([x for x in t.to_string().split("\n") if x]) == 96
    with pytest.raises(ValueError):
        TerminalRenderer("40x20")


def test_compact_24_mode():
    c = TerminalRenderer("80x24")
    c.render_field({"ball_progress": 0.5}, view="bat")
    s = c.to_string()
    rows = [x for x in s.split("\n") if x]
    assert len(rows) == 24
    assert all(len(_strip_sgr(x)) == 80 for x in rows)
    assert "H0 A0" in _strip_sgr(s)
    c.render_field({}, view="pitch")
    assert "104" in c.to_string()  # zone survives 2x8 cells


def test_screenshots_have_expected_content(tmp_path):
    import screenshot as SH
    shots = SH.capture_all(str(tmp_path))
    assert set(shots) == {"menu", "calibrate", "field_bat", "field_pitch",
                          "field24", "stance", "action", "pause", "nserver"}
    for name, shot in shots.items():
        assert os.path.exists(shot["png"])
        want = 24 if name == "field24" else 48
        assert len(shot["cells"]) == want
    # Batter view uses a rich palette (sky, turf, dirt, skin, chalk...).
    assert len(SH.fg_histogram(shots["field_bat"]["cells"])) >= 6
    # Pitcher view shows the zone frame + glove target colors.
    phist = SH.fg_histogram(shots["field_pitch"]["cells"])
    assert phist.get(12, 0) >= 20  # ZONE LBLUE border cells
    # Compact 24-row mode keeps the scoreboard legible.
    assert "1250 PTS" in _strip_sgr(shots["field24"]["ansi"])
    # Menu title is yellow; highlighted tile is cyan.
    menu_hist = SH.fg_histogram(shots["menu"]["cells"])
    assert menu_hist.get(11, 0) >= 15  # YELLOW title cells
    assert menu_hist.get(6, 0) >= 50  # CYAN highlighted tile
    # Pause + action labels are literally legible in the stream.
    assert "P A U S E D" in _strip_sgr(shots["pause"]["ansi"])
    assert "S W I N G !" in _strip_sgr(shots["action"]["ansi"])


def test_crack_peak_and_dtypes():
    synth = ChipSynth()
    crack = synth.crack()
    assert crack.dtype == np.int16
    assert int(np.abs(crack.astype(np.int32)).max()) >= 30000
    assert np.array_equal(synth.crack(), crack)


def test_whistle_frequency_zero_crossing():
    synth = ChipSynth()
    w = synth.whistle()
    assert w.dtype == np.int16
    prod = w[:-1].astype(np.int32) * w[1:].astype(np.int32)
    est = int(np.sum(prod < 0)) / 2.0 / (len(w) / synth.sr)
    assert abs(est - 1320.0) / 1320.0 <= 0.02


def test_jingle_exact_length_and_swell():
    synth = ChipSynth()
    j = synth.jingle()
    assert j.dtype == np.int16 and len(j) == 19404
    assert np.array_equal(synth.jingle(), j)
    s = synth.swell()
    assert s.dtype == np.int16 and len(s) == 26460


def test_pose_extract_person_jpg():
    import cv2
    assert os.path.exists(PERSON_JPG)
    frame = cv2.imread(PERSON_JPG)
    assert frame is not None
    out = PoseEstimator().extract(frame)
    assert out is not None
    assert len(out["points"]) == 9 and len(out["conf"]) == 9
    for x, y in out["points"]:
        assert np.isfinite(x) and np.isfinite(y)
        assert 0.0 <= x <= frame.shape[1]
        assert 0.0 <= y <= frame.shape[0]


def test_pose_extract_none_is_none():
    assert PoseEstimator().extract(None) is None


BATTER_MOV = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "batter.mov")


def _batter_extract(start, count, fn):
    """Stream (points, conf, dt) from batter.mov without buffering frames."""
    import cv2
    assert os.path.exists(BATTER_MOV), "batter.mov (camera view) missing"
    v = cv2.VideoCapture(BATTER_MOV)
    fps = v.get(cv2.CAP_PROP_FPS)
    dt = 1.0 / fps
    est = PoseEstimator()
    v.set(cv2.CAP_PROP_POS_FRAMES, start)
    seen = 0
    for _ in range(count):
        ok, fr = v.read()
        if not ok:
            break
        out = est.extract(fr)
        del fr
        if out is not None:
            fn(out["points"], out["conf"], dt)
            seen += 1
    v.release()
    return seen


def test_batter_mov_close_range_lock():
    cal = SilhouetteCalibrator()
    seen = _batter_extract(0, 350, lambda p, c, dt: cal.update(p, c, dt))
    assert seen > 200, "pose must fire on the real camera view"
    assert cal.locked, "must lock on the real camera view"
    assert cal.close_range is True, "chest-up framing has no hips"
    assert 900.0 <= cal.Ws <= 1400.0, "Ws=%r" % (cal.Ws,)


def test_batter_mov_real_swing_tracked():
    cal = SilhouetteCalibrator()
    _batter_extract(0, 350, lambda p, c, dt: cal.update(p, c, dt))
    assert cal.locked
    sw = G.SwingTracker()
    # Window covers the ~7.7 s real swing (frame ~442 at 57.6 fps).
    _batter_extract(380, 140,
                    lambda p, c, dt: sw.update(cal.norm(p), dt, conf=c))
    assert sw.moved, "the 7.7 s swing must trip the idle gate"
    assert 6.0 <= sw.vh_ws <= 25.0, "peak vh=%r" % (sw.vh_ws,)


def test_calibrator_locks_and_normalizes():
    cal = SilhouetteCalibrator()
    pts = [(0.0, -35.0), (-50.0, 0.0), (50.0, 0.0), (-70.0, 30.0),
           (70.0, 30.0), (-40.0, 50.0), (40.0, 50.0), (-30.0, 80.0),
           (30.0, 80.0)]
    conf = [0.9] * 9
    assert cal.torso_visible(pts, conf) is True
    locked = False
    for _ in range(121):  # 120 x 1/60 sums just under 2.0 s in float
        locked = cal.update(pts, conf, 1.0 / 60.0)
    assert locked and cal.Ws == 100.0
    normed = cal.norm(pts)
    assert abs(normed[1][0] - -0.5) < 1e-9
    assert abs(normed[2][0] - 0.5) < 1e-9


def test_gesture_classifiers():
    pts = [(0.0, 0.35), (-0.5, 0.0), (0.5, 0.0), (-0.7, -0.3), (0.7, -0.3),
           (-0.5, 0.3), (0.5, -0.5), (-0.3, -0.8), (0.3, -0.8)]
    assert G.menu_side(pts) == "BAT"
    assert G.classify_pitch_pose(pts) == "FB"
    cb = [list(p) for p in pts]
    cb[5] = (-0.2, 0.5)
    cb[6] = (0.2, 0.5)
    assert G.classify_pitch_pose(cb) == "CB"
    ch = [list(p) for p in pts]
    ch[5] = (-0.3, -0.8)
    assert G.classify_pitch_pose(ch) == "CH"
    sl = [list(p) for p in pts]
    sl[3] = (-1.3, -0.3)
    sl[4] = (1.3, -0.3)
    assert G.classify_pitch_pose(sl) == "SL"
