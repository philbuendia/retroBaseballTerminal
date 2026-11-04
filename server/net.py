"""TCP NDJSON game server: sessions, 60 Hz state broadcast, rule wiring.

One Session per connection owns a GameState, a ScriptedAI, and a session
phase (mirroring the 7 tracking-FSM states, driven by client gesture
events). The server broadcasts state{fsm,...} at 60 Hz and answers every
client event with pitch_result / hit_result / score / game_over messages.
"""

import socket
import threading
import time

from .config import (DEFAULT_HOST, DEFAULT_PORT, DEFAULT_INNINGS, STATE_HZ,
                     STANCE_TIMEOUT_S, ACTION_TIMEOUT_S, RESOLVE_TIMEOUT_S,
                     STANCE_GATE_HOLD_S)
from .state_machine import (UNBOUND, CALIBRATE, MENU, STANCE, ACTION,
                            RESOLVE, PAUSE)
from .pitching import resolve_pitch
from .hitting import resolve_contact, resolve_hit
from .game import GameState
from .ai import ScriptedAI, is_corner, billboard_zone
from .protocol import (PROTOCOL_VERSION, parse_line, encode, make_state,
                       make_pitch_result, make_hit_result, make_score,
                       make_game_over, make_error)


class Session:
    """Per-connection game session (not thread-safe; one thread owns it)."""

    def __init__(self, innings=DEFAULT_INNINGS):
        self.game = GameState(innings)
        self.ai = ScriptedAI()
        self.phase = UNBOUND
        self.role = "BOTH"
        self.aim = [0.0, 0.0]
        self.pending_pitch = None
        self.prev_phase = MENU
        self.t_phase = 0.0

    # -- helpers ------------------------------------------------------
    def state_msg(self, extra=None):
        return make_state(self.phase, self.game, extra)

    def _set_phase(self, phase):
        self.phase = phase
        self.t_phase = 0.0

    def _manage_half_end(self, replies):
        g = self.game
        if g.over:
            replies.append(make_game_over(g.reason, g))
            return
        if g.half_over:
            info = g.swap_half()
            if info.get("event") == "game_over":
                replies.append(make_game_over(info["reason"], g))
            else:
                replies.append(make_score(g))

    def _ai_pitch_for_batter(self):
        spec, aim = self.ai.next_pitch(self.game.count)
        seq = self.ai.seq
        arm = 3.5 + (seq % 5) * 0.7
        nose = 0.45 if seq % 9 == 8 else 0.0
        return resolve_pitch(spec, arm, aim, nose, seq)

    def _resolve_swing(self, pitch, swing):
        """Resolve a swing vs a pitch; returns reply messages."""
        g = self.game
        replies = []
        contact = resolve_contact(pitch, swing)
        if contact["foul"]:
            ev = g.apply_foul()
            self.ai.seq += 1
            replies.append(make_pitch_result("foul", g.count, pitch,
                                             {"event": ev["event"]}))
        elif contact["contact"]:
            spray, exit = contact["spray_deg"], contact["exit_mph"]
            intercept = self.ai.field(spray, exit)
            corner = is_corner(spray)
            bb = billboard_zone(spray)
            hit = resolve_hit(contact["launch_deg"], exit, intercept,
                              corner, bb)
            ev = g.apply_hit(hit["outcome"], billboard=hit["billboard"])
            self.ai.seq += 1
            replies.append(make_hit_result(
                hit["outcome"], contact["launch_deg"], exit, ev["runs"],
                ev["arcade_delta"],
                {"spray": spray, "intercept": intercept, "corner": corner,
                 "billboard": hit["billboard"]}))
        elif contact["reason"] == "whiff":
            ev = g.apply_pitch_call("strike", corner=False)
            self.ai.seq += 1
            replies.append(make_pitch_result("swinging_strike", g.count,
                                             pitch, {"event": ev["event"]}))
        else:  # check_swing / idle: umpire calls the pitch by location
            call = "strike" if pitch["in_zone"] else "ball"
            ev = g.apply_pitch_call(call, corner=pitch["corner"])
            self.ai.seq += 1
            replies.append(make_pitch_result(call, g.count, pitch,
                                             {"event": ev["event"],
                                              "reason": contact["reason"]}))
        replies.append(make_score(g))
        self._manage_half_end(replies)
        return replies

    # -- event handling -----------------------------------------------
    def handle(self, msg):
        """Handle one decoded client message; returns reply messages."""
        t = msg.get("t")
        g = self.game
        if t == "hello":
            if msg.get("v", PROTOCOL_VERSION) != PROTOCOL_VERSION:
                return [make_error("protocol v mismatch; want %d"
                                   % PROTOCOL_VERSION)]
            self._set_phase(MENU)
            return [self.state_msg()]
        if t == "select":
            role = str(msg.get("role", "BOTH")).upper()
            if role not in ("BAT", "PITCH", "BOTH"):
                return [make_error("unknown role: %r" % (role,))]
            try:
                innings = int(msg.get("innings", self.game.max_innings))
                game = GameState(innings)
            except (ValueError, TypeError):
                return [make_error("bad innings value")]
            self.game = game
            g = game
            self.role = role
            self.pending_pitch = None
            self._set_phase(STANCE)
            return [self.state_msg(), make_score(g)]
        if t == "stance":
            rearmed = False
            if self.phase == MENU:
                # Re-arm after a timeout (or a no-select client flow)
                # without resetting the game, then handle as a stance.
                self.pending_pitch = None
                self._set_phase(STANCE)
                rearmed = True
            if self.phase != STANCE:
                return [make_error("stance only valid in STANCE_READY")]
            held = float(msg.get("held_s", 0.0))
            if held < STANCE_GATE_HOLD_S:
                return [make_error("stance gate needs >= %.1fs hold"
                                   % STANCE_GATE_HOLD_S)]
            self._set_phase(ACTION)
            if g.half == "bottom" and not g.over:
                self.pending_pitch = self._ai_pitch_for_batter()
                extra = {"pitch": self.pending_pitch}
                if rearmed:
                    extra["event"] = "rearm"
                return [self.state_msg(extra)]
            if rearmed:
                return [self.state_msg({"event": "rearm"})]
            return [self.state_msg()]
        if t == "swing":
            if g.over:
                return [make_game_over(g.reason, g)]
            if g.half != "bottom":
                return [make_error("swing only valid in the batting half")]
            if self.phase != ACTION or self.pending_pitch is None:
                return [make_error("swing needs a live pitch (stance first)")]
            try:
                swing = {"vh_ws": float(msg["vh_ws"]),
                         "dt_s": float(msg["dt_s"]),
                         "slope": float(msg["slope"]),
                         "crossed": bool(msg["crossed"])}
            except (KeyError, TypeError, ValueError):
                return [make_error("swing needs vh_ws/dt_s/slope/crossed")]
            pitch = self.pending_pitch
            self.pending_pitch = None
            self._set_phase(RESOLVE)
            return self._resolve_swing(pitch, swing)
        if t == "aim":
            try:
                self.aim = [float(msg["x"]), float(msg["y"])]
            except (KeyError, TypeError, ValueError):
                return [make_error("aim needs x/y")]
            return [self.state_msg({"aim": self.aim})]
        if t == "throw":
            if g.over:
                return [make_game_over(g.reason, g)]
            if g.half != "top":
                return [make_error("throw only valid in the pitching half")]
            if self.phase == STANCE:
                self._set_phase(ACTION)  # grip-then-throw in one motion
            if self.phase != ACTION:
                return [make_error("throw only valid in STANCE/ACTION")]
            try:
                spec = msg["pitch"]
                arm = float(msg.get("arm_ws", 4.0))
                nose = float(msg.get("nose_shift_ws", 0.0))
            except (KeyError, TypeError, ValueError):
                return [make_error("throw needs pitch/arm_ws/nose_shift_ws")]
            try:
                pitch = resolve_pitch(spec, arm, self.aim, nose, self.ai.seq)
            except ValueError as exc:
                return [make_error(str(exc))]
            self._set_phase(RESOLVE)
            swing = self.ai.decide_swing(pitch, g.count)
            if swing is None:  # AI takes: umpire calls it by location
                call = "strike" if pitch["in_zone"] else "ball"
                ev = g.apply_pitch_call(call, corner=pitch["corner"])
                self.ai.seq += 1
                replies = [make_pitch_result(call, g.count, pitch,
                                             {"event": ev["event"],
                                              "ai": "take"}),
                           make_score(g)]
                self._manage_half_end(replies)
                return replies
            return self._resolve_swing(pitch, swing)
        if t == "pause":
            if self.phase != PAUSE:
                self.prev_phase = self.phase
                self._set_phase(PAUSE)
            return [self.state_msg()]
        if t == "resume":
            self._set_phase(self.prev_phase
                             if self.prev_phase != PAUSE else MENU)
            return [self.state_msg()]
        return [make_error("unknown message type: %r" % (t,))]

    def update(self, dt):
        """Age phase timeouts; returns follow-up messages (may be empty)."""
        if self.phase in (UNBOUND, PAUSE, CALIBRATE, MENU):
            return []
        self.t_phase += dt
        g = self.game
        if self.phase == STANCE and self.t_phase >= STANCE_TIMEOUT_S:
            self.pending_pitch = None
            self._set_phase(MENU)
            return [self.state_msg({"event": "stance_timeout"})]
        if self.phase == ACTION and self.t_phase >= ACTION_TIMEOUT_S:
            pitch = self.pending_pitch
            self.pending_pitch = None
            self._set_phase(STANCE)
            if pitch is not None and g.half == "bottom" and not g.over:
                call = "strike" if pitch["in_zone"] else "ball"
                ev = g.apply_pitch_call(call, corner=pitch["corner"])
                self.ai.seq += 1
                replies = [make_pitch_result(call, g.count, pitch,
                                             {"event": ev["event"],
                                              "reason": "action_timeout"}),
                           make_score(g)]
                self._manage_half_end(replies)
                return replies
            return [self.state_msg({"event": "action_timeout"})]
        if self.phase == RESOLVE and self.t_phase >= RESOLVE_TIMEOUT_S:
            self._set_phase(STANCE)
            return [self.state_msg({"event": "resolve_done"})]
        return []


class GameServer:
    """Blocking TCP server; one thread per client, 60 Hz state ticks."""

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT,
                 innings=DEFAULT_INNINGS):
        self.host = host
        self.port = port
        self.innings = innings
        self._sock = None
        self._stop = threading.Event()
        self._threads = []

    def serve_forever(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self.port = self._sock.getsockname()[1]
        self._sock.listen(8)
        self._sock.settimeout(0.2)
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            th = threading.Thread(target=self._client_thread,
                                  args=(conn,), daemon=True)
            th.start()
            self._threads.append(th)

    def shutdown(self):
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass

    def _send(self, conn, msg):
        conn.sendall(encode(msg).encode("utf-8"))

    def _client_thread(self, conn):
        session = Session(self.innings)
        conn.settimeout(1.0 / STATE_HZ)
        buf = b""
        last_tick = time.monotonic()
        try:
            while not self._stop.is_set():
                try:
                    chunk = conn.recv(65536)
                except socket.timeout:
                    chunk = None
                if chunk == b"":
                    break  # client disconnected
                if chunk:
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        text = line.decode("utf-8", "replace").strip()
                        if not text:
                            continue
                        try:
                            msg = parse_line(text)
                        except ValueError as exc:
                            self._send(conn, make_error(str(exc)))
                            continue
                        try:
                            replies = session.handle(msg)
                        except Exception as exc:  # never crash on input
                            replies = [make_error("handler: %s" % exc)]
                        for r in replies:
                            self._send(conn, r)
                now = time.monotonic()
                if now - last_tick >= 1.0 / STATE_HZ:
                    dt = now - last_tick
                    last_tick = now
                    for r in session.update(dt):
                        self._send(conn, r)
                    self._send(conn, session.state_msg())
        except (OSError, BrokenPipeError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass
