"""Eval scenario: headless terminal render, synth audio, pose extract."""

import os
import re
import traceback

import numpy as np

from client.render import TerminalRenderer, BLOCK, ESC, FG_CODE, BG_CODE
from client.audio import ChipSynth
from client.pose import PoseEstimator
import screenshot as SH

CATEGORY = "terminal_client"
WEIGHT = 10

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
PERSON_JPG = os.path.join(ROOT, "models", "person.jpg")

_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")


def _sgr_seqs(row):
    return set(m.group(0) for m in _SGR_RE.finditer(row))


def _plain(s):
    return _SGR_RE.sub("", s)


def check_term_render():
    r = TerminalRenderer("80x48")
    r.render_field({}, view="pitch")
    field = r.to_string()
    rows = field.split("\n")
    body = [x for x in rows if x]
    assert len(body) == 48, "80x48 mode emits 48 rows, got %d" % len(body)
    # Every row is exactly 80 visible cells (half-blocks and/or text chars).
    assert all(len(_plain(x)) == 80 for x in body), "80 cells per row"
    # Strike-zone box: ZONE (LBLUE=12) SGR pair 94/104 in pitcher view.
    assert "94" in field and "104" in field, "zone-box SGR present"
    # Batter view renders the same frame contract with a live ball.
    r.render_field({"ball_progress": 0.5}, view="bat")
    bat = r.to_string()
    assert len([x for x in bat.split("\n") if x]) == 48
    assert all(len(_plain(x)) == 80 for x in bat.split("\n") if x)
    # Legibility: overlay text survives as literal characters in the stream.
    r.render_menu()
    menu_plain = _plain(r.to_string())
    assert "R E T R O" in menu_plain, "menu title legible"
    assert "HOLD TO SELECT" in menu_plain, "menu hint legible"
    r.render_field({"runs": {"HOME": 3, "AWAY": 1}, "arcade": 1250,
                    "inning": 2, "half": "bottom",
                    "count": {"balls": 2, "strikes": 1}, "outs": 1})
    score = _plain(r.to_string())
    assert "H3 A1 I2B" in score, "score line legible, got tail: %r" % score[-200:]
    assert "1250 PTS" in score, "arcade line legible"
    # Server-case scoreboard keys (lowercase away/home) also render.
    r.render_field({"runs": {"home": 5, "away": 2}, "half": "top"})
    assert "H5 A2" in _plain(r.to_string()), "live scoreboard keys render"
    # Compact 24-row mode keeps its contract on stock terminals.
    c = TerminalRenderer("80x24")
    c.render_field({"ball_progress": 0.5}, view="bat")
    s24 = c.to_string()
    assert len([x for x in s24.split("\n") if x]) == 24, "24 rows"
    assert all(len(_plain(x)) == 80 for x in s24.split("\n") if x)
    # Screenshots: capture every screen, check pixel stats, save PNGs.
    shots = SH.capture_all()
    assert set(shots) == {"menu", "calibrate", "field_bat", "field_pitch",
                          "field24", "stance", "action", "pause",
                          "nserver"}, "9 screens shot"
    for name, shot in shots.items():
        assert os.path.exists(shot["png"]), "%s png saved" % name
        want = 24 if name == "field24" else 48
        assert len(shot["cells"]) == want, "%s cell rows" % name
    assert len(SH.fg_histogram(shots["field_bat"]["cells"])) >= 6, \
        "batter view uses >=6 palette colors"
    phist = SH.fg_histogram(shots["field_pitch"]["cells"])
    assert phist.get(12, 0) >= 20, "pitcher view shows zone frame"
    menu_hist = SH.fg_histogram(shots["menu"]["cells"])
    assert menu_hist.get(11, 0) >= 15, "yellow title cells present"
    assert menu_hist.get(6, 0) >= 50, "cyan highlighted tile present"
    assert "P A U S E D" in _plain(shots["pause"]["ansi"]), "pause legible"
    assert "1250 PTS" in _plain(shots["field24"]["ansi"]), "24-mode board"
    # Menu tile highlight + dwell bar change the emitted frame.
    r.render_menu()
    plain = r.to_string()
    r.render_menu(dwell_side="BAT", dwell_frac=0.5)
    hi = r.to_string()
    assert hi != plain, "tile highlight changes frame"
    r.render_menu(dwell_frac=0.0)
    nodwell = r.to_string()
    assert hi != nodwell, "dwell bar changes frame"
    # PAUSE overlay changes the emitted frame.
    r.render_field({})
    before = r.to_string()
    r.render_pause()
    after = r.to_string()
    assert after != before, "PAUSE overlay changes frame"
    # Alternate-row scanline dim: odd rows start with SGR 2, even rows lack it.
    for i, row in enumerate(body):
        if i % 2 == 1:
            assert row.startswith(ESC + "[2m"), "row %d must dim" % i
        else:
            assert "[2m" not in row, "row %d must not dim" % i
    # At most 16 distinct SGR codes per row on every frame type.
    for name, s in (("field", field), ("menu", hi), ("pause", after)):
        for i, row in enumerate(x for x in s.split("\n") if x):
            n = len(_sgr_seqs(row))
            assert n <= 16, "%s row %d uses %d SGR codes" % (name, i, n)
    # Palette discipline: every SGR param is reset/dim or a 16-color code.
    valid = {0, 2} | set(FG_CODE) | set(BG_CODE)
    for m in _SGR_RE.finditer(field + hi + after):
        for tok in m.group(1).split(";"):
            assert int(tok) in valid, "SGR param %r outside palette" % tok
    # Tall mode doubles the rows.
    t = TerminalRenderer("80x96")
    t.render_field({})
    assert len([x for x in t.to_string().split("\n") if x]) == 96
    try:
        TerminalRenderer("40x20")
    except ValueError:
        pass
    else:
        raise AssertionError("bad mode must raise ValueError")
    return "fp-views+zone+legible-text+9-screenshots+highlight+dwell+pause"


def check_term_audio():
    synth = ChipSynth()
    crack = synth.crack()
    assert crack.dtype == np.int16, "crack int16"
    peak = int(np.abs(crack.astype(np.int32)).max())
    assert peak >= 30000, "crack peak %d" % peak
    whistle = synth.whistle()
    assert whistle.dtype == np.int16
    prod = whistle[:-1].astype(np.int32) * whistle[1:].astype(np.int32)
    crossings = int(np.sum(prod < 0))
    est_hz = crossings / 2.0 / (len(whistle) / synth.sr)
    assert abs(est_hz - 1320.0) / 1320.0 <= 0.02, \
        "whistle %.1f Hz vs 1320 mean" % est_hz
    jingle = synth.jingle()
    assert jingle.dtype == np.int16
    assert len(jingle) == 19404, "jingle len %d" % len(jingle)
    swell = synth.swell()
    assert swell.dtype == np.int16 and len(swell) == 26460
    # Deterministic: identical buffers on repeat calls.
    assert np.array_equal(synth.crack(), crack), "crack deterministic"
    assert np.array_equal(synth.jingle(), jingle), "jingle deterministic"
    return "crack peak %d, whistle %.1f Hz, jingle 19404" % (peak, est_hz)


def check_term_pose():
    assert os.path.exists(PERSON_JPG), "models/person.jpg missing"
    import cv2
    frame = cv2.imread(PERSON_JPG)
    assert frame is not None, "person.jpg must decode"
    est = PoseEstimator()
    out = est.extract(frame)
    assert out is not None, "extract must return landmarks"
    assert len(out["points"]) == 9, "9 landmarks, got %d" % len(out["points"])
    assert len(out["conf"]) == 9, "9 confidences"
    for x, y in out["points"]:
        assert np.isfinite(x) and np.isfinite(y), "finite points"
        assert 0.0 <= x <= frame.shape[1] and 0.0 <= y <= frame.shape[0]
    assert est.extract(None) is None, "None frame -> None"
    hi = sum(1 for c in out["conf"] if c >= 0.6)
    # Real camera view: batter.mov must calibrate (close-range, no hips)
    # and track the genuine ~7.7 s swing with a sane peak speed.
    mov = os.path.join(ROOT, "batter.mov")
    assert os.path.exists(mov), "batter.mov (camera view) missing"
    from client.calibration import SilhouetteCalibrator
    from client import gestures as G
    cal = SilhouetteCalibrator()
    v = cv2.VideoCapture(mov)
    fps = v.get(cv2.CAP_PROP_FPS)
    dt = 1.0 / fps
    for _ in range(300):
        ok, fr = v.read()
        if not ok:
            break
        out = est.extract(fr)
        if out is not None:
            cal.update(out["points"], out["conf"], dt)
    assert cal.locked, "no Ws lock on the real camera view"
    assert cal.close_range is True, "batter.mov framing has no hips"
    assert 900.0 <= cal.Ws <= 1400.0, "Ws=%r" % (cal.Ws,)
    sw = G.SwingTracker()
    v.set(cv2.CAP_PROP_POS_FRAMES, 380)
    for _ in range(140):
        ok, fr = v.read()
        if not ok:
            break
        out = est.extract(fr)
        if out is not None:
            sw.update(cal.norm(out["points"]), dt, conf=out["conf"])
    v.release()
    assert sw.moved, "real swing missed the idle gate"
    assert 6.0 <= sw.vh_ws <= 25.0, "swing peak vh=%r" % (sw.vh_ws,)
    return ("9 landmarks on person.jpg, %d/9 conf>=0.6; batter.mov locks "
            "Ws=%.0f close-range, swing peak %.1f Ws/s"
            % (hi, cal.Ws, sw.vh_ws))


CHECKS = [("term_render", 4, check_term_render),
          ("term_audio", 3, check_term_audio),
          ("term_pose", 3, check_term_pose)]


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
