"""ScriptedAI: fully deterministic lookup-table opponents.

Tables:
  PITCH_LUT  - AI pitcher selection by sequence + count.
  AIM_LUT    - AI pitcher target cycle around the zone.
  FIELDER_POSITIONS - fixed 8-bit fielder spray angles; balls hit within
    +/-3 deg of a fielder with exit < 100 mph are intercepted.
Triples need |spray| >= 28 deg (corners); billboard HRs need spray in the
fixed scoreboard zone [8, 32] deg.
"""

from .config import CORNER_SPRAY_DEG

PITCH_LUT = ("FB", "FB", "CB", "SL", "FB", "CH", "SL", "CB",
             "FB", "CH", "FB", "SL")

AIM_LUT = ((-0.40, -0.30), (0.40, 0.30), (0.00, 0.00), (-0.40, 0.30),
           (0.40, -0.30), (0.20, 0.00), (-0.20, 0.10), (0.00, -0.35),
           (0.35, 0.10), (-0.10, -0.20), (0.10, 0.35), (-0.35, 0.00))

FIELDER_POSITIONS = (-36.0, -18.0, 0.0, 18.0, 36.0)
FIELDER_HALF_WINDOW = 3.0
FIELDER_EXIT_MAX = 100.0

BILLBOARD_SPRAY_LO = 8.0
BILLBOARD_SPRAY_HI = 32.0


def lut_pitch(seq, balls, strikes):
    """AI pitch pick: deterministic table indexed by seq + count."""
    idx = (int(seq) + int(balls) * 2 + int(strikes)) % len(PITCH_LUT)
    return PITCH_LUT[idx]


def lut_aim(seq):
    """AI pitcher target: deterministic cycle around the zone."""
    return AIM_LUT[int(seq) % len(AIM_LUT)]


def _hash01(seq, salt):
    return ((int(seq) * 1103515245 + int(salt) * 12345) % 1000) / 1000.0


def ai_swing_params(seq):
    """Deterministic AI-batter swing features covering fair/foul/whiff."""
    vh = 3.0 + _hash01(seq, 7) * 4.5          # 3.0..7.5 Ws/s
    dt = (_hash01(seq, 13) * 2.0 - 1.0) * 0.40  # -0.40..0.40 s
    slope = -0.10 + _hash01(seq, 29) * 0.90     # -0.10..0.80
    return {"vh_ws": round(vh, 3), "dt_s": round(dt, 3),
            "slope": round(slope, 3), "crossed": True}


def ai_should_swing(in_zone, strikes, seq):
    """AI take/swing rule: swing in zone, protect at 2K, rare chase."""
    if in_zone:
        return True
    if strikes >= 2:
        return True
    return _hash01(seq, 3) < 0.12  # occasional chase (~12%)


def fielder_intercept(spray_deg, exit_mph):
    """Fixed-zone fielder collision: right-at-'em balls are caught."""
    if exit_mph >= FIELDER_EXIT_MAX:
        return False  # smoked through every zone
    return any(abs(spray_deg - p) <= FIELDER_HALF_WINDOW
               for p in FIELDER_POSITIONS)


def is_corner(spray_deg):
    return abs(spray_deg) >= CORNER_SPRAY_DEG


def billboard_zone(spray_deg):
    return BILLBOARD_SPRAY_LO <= spray_deg <= BILLBOARD_SPRAY_HI


class ScriptedAI:
    """Stateful wrapper: sequence counters + the LUT functions above."""

    def __init__(self):
        self.seq = 0  # pitch sequence (also drives scatter + AI swings)

    def next_pitch(self, count):
        spec = lut_pitch(self.seq, count.balls, count.strikes)
        aim = lut_aim(self.seq)
        return spec, aim

    def decide_swing(self, pitch, count):
        """Return a swing dict, or None for a take."""
        if ai_should_swing(pitch["in_zone"], count.strikes, self.seq):
            return ai_swing_params(self.seq)
        return None

    def field(self, spray_deg, exit_mph):
        return fielder_intercept(spray_deg, exit_mph)
