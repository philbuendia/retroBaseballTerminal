"""Pitch resolution: pose-selected pitch types, velocity, break, accuracy.

Pitch table (velocity scale, horizontal break px, vertical drop px):
  FB(1.00, 0, 2)  CB(0.75, 2, 18)  SL(0.85, 16, 6)  CH(0.70, 4, 10).
Nose-shift > 0.3 Ws at release scatters the pitch via a deterministic
sequence hash (stdlib deterministic).
"""

from .config import (PITCH_TABLE, BASE_PITCH_MPH, ARM_PITCH_GAIN,
                     NOSE_SCATTER_WS, ZONE_HALF, CORNER_BAND)

VALID_PITCHES = tuple(PITCH_TABLE)
SCATTER_MAG = 0.6  # normalized units of deterministic scatter


def _scatter_offset(seq):
    """Deterministic pseudo-offset in [-0.3, 0.3]^2 from the pitch sequence."""
    a = (seq * 2654435761 + 40503) % 1000 / 1000.0 - 0.5
    b = (seq * 40503 + 2654435761) % 1000 / 1000.0 - 0.5
    return a * SCATTER_MAG, b * SCATTER_MAG


def _in_zone(x, y):
    return abs(x) <= ZONE_HALF and abs(y) <= ZONE_HALF


def _on_corner(x, y):
    if not _in_zone(x, y):
        return False
    edge = ZONE_HALF - abs(x) <= CORNER_BAND
    return edge or (ZONE_HALF - abs(y) <= CORNER_BAND)


def resolve_pitch(spec, arm, target, nose, seq):
    """Resolve a thrown pitch into velocity, movement, and plate location.

    spec: "FB" | "CB" | "SL" | "CH" (case-insensitive).
    arm: pitching-arm speed in Ws/s (>= 0).
    target: locked reticle (x, y) in normalized units (-1..1).
    nose: lateral nose shift during release, in Ws.
    seq: monotonically increasing pitch sequence number (deterministic).
    """
    key = str(spec).upper()
    if key not in PITCH_TABLE:
        raise ValueError("unknown pitch spec: %r" % (spec,))
    row = PITCH_TABLE[key]
    arm = max(0.0, float(arm))
    velo = round((BASE_PITCH_MPH + arm * ARM_PITCH_GAIN) * row["vel_scale"], 1)
    scattered = float(nose) > NOSE_SCATTER_WS
    tx, ty = float(target[0]), float(target[1])
    if scattered:
        dx, dy = _scatter_offset(int(seq))
        tx, ty = tx + dx, ty + dy
    loc = (round(tx, 3), round(ty, 3))
    return {
        "pitch": key,
        "velo_mph": velo,
        "break_px": row["break_px"],
        "drop_px": row["drop_px"],
        "target": [float(target[0]), float(target[1])],
        "location": [loc[0], loc[1]],
        "scattered": scattered,
        "in_zone": _in_zone(*loc),
        "corner": _on_corner(*loc),
        "seq": int(seq),
    }


# Re-exported for callers that resolve the full pitch->contact chain here.
from .hitting import resolve_contact  # noqa: E402,F401
