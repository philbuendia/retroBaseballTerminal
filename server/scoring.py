"""Arcade point awards (deterministic, no I/O)."""

from .config import (HIT_WINDOWS, RUN_POINTS, CORNER_PAINT_K_POINTS,
                     BILLBOARD_POINTS, IMMACULATE_MULT)


def award_hit(outcome):
    """Points for a hit outcome: 1B 100 / 2B 250 / 3B 500 / HR 1000."""
    row = HIT_WINDOWS.get(outcome)
    return row[3] if row else 0


def award_run(runs=1):
    """500 points per run crossing home plate."""
    return RUN_POINTS * max(0, int(runs))


def award_corner_paint_k():
    """300-point bonus for a strikeout on the zone's outer border."""
    return CORNER_PAINT_K_POINTS


def award_billboard():
    """2500-point jackpot for a billboard home run."""
    return BILLBOARD_POINTS


def immaculate_multiplier(active):
    """2x score multiplier when an immaculate inning is active, else 1x."""
    return IMMACULATE_MULT if active else 1


def apply_multiplier(points, active):
    return points * immaculate_multiplier(active)
