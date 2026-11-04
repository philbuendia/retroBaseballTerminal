"""Retro Diamond terminal client: camera -> pose -> gestures -> server.

Modes:
  live camera (default)   needs a local terminal (macOS TCC denies
                          background capture; degrades to an error panel)
  --replay <image|video>  headless-friendly file loop, no camera needed
  --keys                  keypress-sample mode, no camera needed:
                          f/c/s/h pitch select, g stance-hold, space
                          swing/throw with sample values, p/r pause/resume,
                          q quit. b/t/y re-select role BAT/PITCH/BOTH.

Run:  .venv/bin/python -m client.main [--server H] [--port P] ...
"""

import argparse
import select
import shutil
import sys
import time

from . import protocol as P
from .net import GameClient
from .capture import open_source
from .pose import PoseEstimator
from .calibration import SilhouetteCalibrator
from .fsm import TrackingFSM, Transition  # noqa: F401
from . import gestures as G
from .render import TerminalRenderer
from .audio import AudioBackend

PITCH_KEYS = {"f": "FB", "c": "CB", "s": "SL", "h": "CH"}

# Sample wire values for --keys mode (mid-range, always valid).
SAMPLE_SWING = {"vh_ws": 5.0, "dt_s": 0.05, "slope": 0.4, "crossed": True}
SAMPLE_THROW = {"arm_ws": 4.5, "nose_shift_ws": 0.0}


def key_to_event(ch, ctx):
    """Pure keypress -> (messages, quit). ctx holds pitch/role/half."""
    ch = ch.lower()
    if ch == "q":
        return [], True
    if ch in PITCH_KEYS:
        ctx["pitch"] = PITCH_KEYS[ch]
        return [], False
    if ch == "g":
        return [P.make_stance(0.6)], False
    if ch == " ":
        if ctx.get("pitching"):
            return [P.make_throw(ctx.get("pitch", "FB"),
                                 SAMPLE_THROW["arm_ws"],
                                 SAMPLE_THROW["nose_shift_ws"])], False
        s = SAMPLE_SWING
        return [P.make_swing(s["vh_ws"], s["dt_s"], s["slope"],
                             s["crossed"])], False
    if ch == "p":
        return [P.make_pause()], False
    if ch == "r":
        return [P.make_resume()], False
    if ch == "b":
        return [P.make_select("BAT", ctx.get("innings", 3))], False
    if ch == "t":
        return [P.make_select("PITCH", ctx.get("innings", 3))], False
    if ch == "y":
        return [P.make_select("BOTH", ctx.get("innings", 3))], False
    return [], False


def _read_keys():
    """Non-blocking stdin read -> list of chars ('' when none)."""
    try:
        if not select.select([sys.stdin], [], [], 0)[0]:
            return []
    except Exception:
        pass  # non-selectable stdin (pipes in tests): fall through to read
    try:
        data = sys.stdin.read(8)
    except OSError:
        return []
    return list(data) if data else []


class _RawTTY:
    """Raw-mode stdin when attached to a real TTY; no-op for pipes."""

    def __enter__(self):
        self._fd = None
        self._old = None
        try:
            import termios
            import tty
            if sys.stdin.isatty():
                self._fd = sys.stdin.fileno()
                self._old = termios.tcgetattr(self._fd)
                tty.setcbreak(self._fd)
        except Exception:
            self._fd = None
        return self

    def __exit__(self, *exc):
        if self._fd is not None:
            try:
                import termios
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)
            except Exception:
                pass


class _Screen:
    """Alternate-screen + hidden cursor for flicker-free live play."""

    def __init__(self, renderer):
        self.renderer = renderer

    def __enter__(self):
        if sys.stdout.isatty():
            self.renderer.enter()
        return self

    def __exit__(self, *exc):
        if sys.stdout.isatty():
            self.renderer.exit()


def build_parser():
    ap = argparse.ArgumentParser(description="Retro Diamond terminal client")
    ap.add_argument("--server", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--replay", default=None,
                    help="image or video file to loop instead of camera")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--keys", action="store_true",
                    help="keypress-sample mode (no camera)")
    ap.add_argument("--innings", type=int, default=3, choices=(3, 6, 9))
    ap.add_argument("--role", default="BOTH", choices=("BAT", "PITCH", "BOTH"))
    ap.add_argument("--tall", action="store_true",
                    help="80x96 full mode (default 80x48)")
    ap.add_argument("--max-frames", type=int, default=0,
                    help="exit after N loop frames (0 = forever)")
    return ap


def _handle_server_msgs(msgs, audio, log):
    """Audio cues + log lines for inbound server messages."""
    for m in msgs:
        t = m.get("t")
        if t == "hit_result":
            out = m.get("outcome", "OUT")
            log.append("HIT %s %s MPH +%d" % (
                out, m.get("exit", "?"), m.get("arcade_delta", 0)))
            if out == "HR":
                audio.swell()
                audio.jingle()
            elif out != "OUT":
                audio.crack()
        elif t == "pitch_result":
            log.append("PITCH %s %s" % (
                m.get("call", "?"), m.get("count", {})))
            if m.get("call") in ("strike", "swinging_strike"):
                audio.crack()
        elif t == "game_over":
            log.append("GAME OVER %s" % m.get("reason", ""))
            audio.jingle()
        elif t == "error":
            log.append("SERVER: %s" % m.get("msg", "?"))
        elif t == "state" and "pitch" in m:
            audio.whistle()


def maybe_send_stance_edge(client, prev_fsm, cur_fsm):
    """On STANCE->ACTION edge, send stance so the server deals the pitch.

    Without this the camera path never tells the server the batter is
    loaded: no AI pitch arrives and every swing errors out. Returns True
    when a stance event was sent.
    """
    if prev_fsm == "04_STANCE_READY" and cur_fsm == "05_ACTION_WINDOW":
        try:
            client.send_event(P.make_stance(0.6))
        except OSError:
            return False
        return True
    return False


def pick_mode(args):
    """Fit the real terminal: 96/48/24 rows, else None (too small)."""
    if args.tall:
        return "80x96"
    if not sys.stdout.isatty():
        return "80x48"
    try:
        size = shutil.get_terminal_size()
    except Exception:
        return "80x48"
    if size.columns < 80 or size.lines < 24:
        return None
    if size.lines >= 48:
        return "80x48"
    return "80x24"


def run(args):
    mode = pick_mode(args)
    if mode is None:
        sys.stdout.write("TERMINAL TOO SMALL: need 80x24, "
                         "resize and rerun.\n")
        return 2
    renderer = TerminalRenderer(mode=mode)
    audio = AudioBackend(enabled=not args.no_audio)
    client = GameClient()
    try:
        client.connect(args.server, args.port)
    except OSError as exc:
        renderer.clear()
        renderer.render_message("NO SERVER", "%s:%d %s" % (
            args.server, args.port, exc))
        sys.stdout.write(renderer.to_string())
        return 2
    client.send_event(P.make_hello())
    client.send_event(P.make_select(args.role, args.innings))

    source = None
    pose = None
    if not args.keys:
        try:
            source = open_source(args.replay, args.camera)
        except (FileNotFoundError, ValueError) as exc:
            renderer.clear()
            renderer.render_message("BAD REPLAY", str(exc)[:28])
            sys.stdout.write(renderer.to_string())
            return 2
        if not source.ok:
            renderer.clear()
            renderer.render_message("NO CAMERA",
                                    getattr(source, "error", "")[:28])
            renderer.text("USE --REPLAY OR --KEYS", 34, 172 - 8)
            sys.stdout.write(renderer.to_string())
            return 1
        pose = PoseEstimator()

    cal = SilhouetteCalibrator()
    fsm = TrackingFSM()
    dwell = G.DwellTracker()
    swing = G.SwingTracker()
    throw = G.ThrowTracker()
    ctx = {"pitch": "FB", "innings": args.innings, "pitching": False,
           "ball": None, "flash": 0.0}
    log = []
    last = time.monotonic()
    frames = 0
    with _RawTTY(), _Screen(renderer):
        while True:
            now = time.monotonic()
            dt = min(now - last, 0.25)
            last = now

            msgs = client.poll_frame()
            _handle_server_msgs(msgs, audio, log)
            for m in msgs:
                t = m.get("t", "")
                if t == "state" and "pitch" in m:
                    ctx["ball"] = 0.0  # pitch away: animate the ball
                elif t in ("pitch_result", "hit_result"):
                    ctx["ball"] = None
                    if t == "hit_result":
                        ctx["flash"] = 1.0
            if ctx["ball"] is not None:
                ctx["ball"] = min(1.0, ctx["ball"] + dt / 0.45)
            ctx["flash"] = max(0.0, ctx["flash"] - dt * 2.0)
            state = client.latest_state or {}
            half = state.get("half", "")
            ctx["pitching"] = (half == "top")
            fsm_hint = state.get("fsm", "")
            view = dict(state)
            view["ball_progress"] = ctx["ball"]
            view["contact_flash"] = ctx["flash"] > 0.3
            view["fp"] = "pitch" if ctx["pitching"] else "bat"

            if args.keys:
                quit_ = False
                for ch in _read_keys():
                    out, quit_ = key_to_event(ch, ctx)
                    for m in out:
                        try:
                            client.send_event(m)
                        except OSError:
                            pass
                    if quit_:
                        break
                if quit_:
                    break
                renderer.render_field(view, view=view["fp"])
                renderer.render_message(
                    "KEYS P:%s %s" % (ctx["pitch"],
                                      "PITCH" if ctx["pitching"] else "BAT"),
                    (log[-1] if log else "G STANCE SPC HIT")[0:28])
            else:
                prev_fsm = fsm.state
                frame = source.read_frame()
                if frame is None and isinstance(
                        getattr(source, "drops", None), int):
                    pass  # drop counted inside the source; keep looping
                lm = None
                normed = None
                if frame is not None:
                    try:
                        lm = pose.extract(frame)
                    except Exception as exc:  # model errors -> panel
                        renderer.clear()
                        renderer.render_message("POSE FAIL", str(exc)[:28])
                        sys.stdout.write(renderer.to_string())
                        return 3
                    if lm is not None:
                        cal.update(lm["points"], lm["conf"], dt)
                        normed = cal.norm(lm["points"])
                        # +y-up dict for the FSM (norm flips y already).
                        fsm.update({"points": normed, "conf": lm["conf"]},
                                   dt)
                renderer.render_field(view, view=view["fp"])
                if not cal.locked:
                    renderer.render_calibrate(cal.progress)
                elif fsm.state == "03_MENU_SELECT":
                    side = G.menu_side(normed) if normed else None
                    pick = dwell.update(side, dt)
                    if pick:
                        role = "BAT" if pick == "BAT" else "PITCH"
                        try:
                            client.send_event(
                                P.make_select(role, args.innings))
                        except OSError:
                            pass
                    renderer.render_menu(dwell_frac=dwell.frac,
                                         dwell_side=side)
                elif fsm.state == "07_SYSTEM_PAUSE":
                    renderer.render_pause()
                    try:
                        client.send_event(P.make_pause())
                    except OSError:
                        pass
                else:
                    if log:
                        renderer.render_message(fsm_hint or fsm.state,
                                                log[-1][0:28])
                    else:
                        renderer.render_message(fsm_hint or fsm.state,
                                                "CAM %dX%d %dFPS %dDROP" % (
                                                    source.width,
                                                    source.height,
                                                    int(source.fps),
                                                    source.drops))
                # Gesture -> wire events on FSM transitions.
                if normed is not None:
                    if fsm.state == "04_STANCE_READY":
                        swing.reset()
                        throw.reset()
                        ctx["pitch"] = G.classify_pitch_pose(normed)
                    elif fsm.state == "05_ACTION_WINDOW":
                        if ctx["pitching"]:
                            throw.update(normed, dt, conf=lm["conf"])
                        else:
                            swing.update(normed, dt, conf=lm["conf"])
                    elif fsm.state == "06_PLAY_RESOLVE":
                        try:
                            if ctx["pitching"]:
                                arm, nose = throw.result()
                                client.send_event(P.make_throw(
                                    ctx["pitch"], max(arm, 2.0), nose))
                            else:
                                vh, dts, slope, crossed = swing.result(
                                    normed)
                                client.send_event(P.make_swing(
                                    vh, min(dts, 0.4), slope, crossed))
                        except OSError:
                            pass
                        throw.reset()
                        swing.reset()
                maybe_send_stance_edge(client, prev_fsm, fsm.state)
                for ch in _read_keys():  # q quits, p pauses from keyboard
                    if ch.lower() == "q":
                        frames = args.max_frames or frames
                        break
                    if ch.lower() == "p":
                        try:
                            client.send_event(P.make_pause())
                        except OSError:
                            pass

            renderer.present()
            frames += 1
            if args.max_frames and frames >= args.max_frames:
                break
            time.sleep(0.005)

    client.close()
    audio.close()
    if source is not None:
        source.close()
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
