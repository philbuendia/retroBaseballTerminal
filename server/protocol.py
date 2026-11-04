"""NDJSON wire protocol (v:1): message constructors and parsing.

Every message is one JSON object per line with a "t" tag. Unknown "t"
values get an error{msg} reply, never a crash.
C->S: hello select stance swing aim throw pause resume
S->C: state pitch_result hit_result score game_over error
"""

import json

from .config import PROTOCOL_VERSION

CLIENT_MSGS = ("hello", "select", "stance", "swing", "aim", "throw",
               "pause", "resume")


def parse_line(line):
    """Parse one NDJSON line into a dict. Raises ValueError if malformed."""
    try:
        msg = json.loads(line)
    except (ValueError, TypeError) as exc:
        raise ValueError("bad json: %s" % exc)
    if not isinstance(msg, dict) or "t" not in msg:
        raise ValueError("message must be an object with a 't' tag")
    return msg


def encode(msg):
    out = {"v": PROTOCOL_VERSION}
    out.update(msg)
    return json.dumps(out, separators=(",", ":")) + "\n"


def make_state(fsm, game=None, extra=None):
    body = {"t": "state", "fsm": fsm}
    if game is not None:
        body.update(game.to_dict())
    if extra:
        body.update(extra)
    return body


def make_pitch_result(call, count, pitch=None, extra=None):
    body = {"t": "pitch_result", "call": call, "count": count.as_dict()}
    if pitch is not None:
        body["pitch"] = pitch
    if extra:
        body.update(extra)
    return body


def make_hit_result(outcome, launch, exit, runs, arcade_delta, extra=None):
    body = {"t": "hit_result", "outcome": outcome, "launch": launch,
            "exit": exit, "runs": runs, "arcade_delta": arcade_delta}
    if extra:
        body.update(extra)
    return body


def make_score(game):
    d = game.to_dict()
    return {"t": "score", "runs": d["runs"], "arcade": d["arcade"],
            "inning": d["inning"], "half": d["half"]}


def make_game_over(reason, game):
    d = game.to_dict()
    return {"t": "game_over", "reason": reason, "runs": d["runs"],
            "arcade": d["arcade"]}


def make_error(msg):
    return {"t": "error", "msg": str(msg)}
