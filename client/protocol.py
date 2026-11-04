"""Client-side NDJSON wire protocol (v:1). Mirrors server/protocol.py exactly.

Every message is one JSON object per line with a "t" tag and "v": 1.
C->S: hello select stance swing aim throw pause resume
S->C: state pitch_result hit_result score game_over error
"""

import json

PROTOCOL_VERSION = 1

CLIENT_MSGS = ("hello", "select", "stance", "swing", "aim", "throw",
               "pause", "resume")

SERVER_MSGS = ("state", "pitch_result", "hit_result", "score",
               "game_over", "error")


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


def make_hello():
    return {"t": "hello", "v": PROTOCOL_VERSION}


def make_select(role="BOTH", innings=3):
    return {"t": "select", "role": str(role).upper(), "innings": int(innings)}


def make_stance(held_s):
    return {"t": "stance", "held_s": float(held_s)}


def make_swing(vh_ws, dt_s, slope, crossed):
    return {"t": "swing", "vh_ws": float(vh_ws), "dt_s": float(dt_s),
            "slope": float(slope), "crossed": bool(crossed)}


def make_aim(x, y):
    return {"t": "aim", "x": float(x), "y": float(y)}


def make_throw(pitch, arm_ws=4.0, nose_shift_ws=0.0):
    return {"t": "throw", "pitch": str(pitch),
            "arm_ws": float(arm_ws),
            "nose_shift_ws": float(nose_shift_ws)}


def make_pause():
    return {"t": "pause"}


def make_resume():
    return {"t": "resume"}
