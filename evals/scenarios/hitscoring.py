"""Eval scenario: hit table, downgrades, intercepts, arcade bonuses."""

import traceback

from server.config import HIT_WINDOWS
from server.hitting import resolve_hit
from server.game import GameState
from server.scoring import (award_hit, award_run, award_corner_paint_k,
                            award_billboard, immaculate_multiplier)

CATEGORY = "hitscoring"
WEIGHT = 15


def check_hit_table():
    assert HIT_WINDOWS["1B"] == (-5.0, 15.0, 70.0, 100), "1B row"
    assert HIT_WINDOWS["2B"] == (12.0, 24.0, 88.0, 250), "2B row"
    assert HIT_WINDOWS["3B"] == (18.0, 28.0, 98.0, 500), "3B row"
    assert HIT_WINDOWS["HR"] == (25.0, 38.0, 102.0, 1000), "HR row"
    assert resolve_hit(0.0, 70.0, False, False, False)["outcome"] == "1B"
    assert resolve_hit(20.0, 90.0, False, False, False)["outcome"] == "2B"
    assert resolve_hit(20.0, 100.0, False, True, False)["outcome"] == "3B"
    assert resolve_hit(30.0, 105.0, False, False, False)["outcome"] == "HR"
    # Overlap precedence HR > 3B > 2B > 1B: launch 20 corner -> 3B not 2B.
    assert resolve_hit(27.0, 105.0, False, True, False)["outcome"] == "HR"
    # Launch outside every window is an out even when smoked.
    assert resolve_hit(50.0, 110.0, False, False, False)["outcome"] == "OUT"
    bb = resolve_hit(30.0, 105.0, False, False, True)
    assert bb["outcome"] == "HR" and bb["billboard"] is True, "billboard HR"
    plain = resolve_hit(20.0, 90.0, False, True, True)
    assert plain["billboard"] is False, "non-HR never billboard"
    return "4 rows + precedence + billboard flag"


def check_hit_downgrade():
    # HR-class launch short on velo with corners -> one rung to 3B.
    assert resolve_hit(30.0, 100.0, False, True, False)["outcome"] == "3B"
    # Same without corners: 3B rung invalid -> falls to 2B.
    assert resolve_hit(30.0, 100.0, False, False, False)["outcome"] == "2B"
    # 2B-class short -> 1B (single rung, even outside the 1B window).
    assert resolve_hit(20.0, 80.0, False, False, False)["outcome"] == "1B"
    # Exactly one rung: HR-class at 70 mph stays 3B, never cascades.
    assert resolve_hit(30.0, 70.0, False, True, False)["outcome"] == "3B"
    # Overlap launch picks 2B first, then downgrades to 1B on velo.
    assert resolve_hit(13.0, 75.0, False, False, False)["outcome"] == "1B"
    # 1B-class short -> OUT (bottom of the ladder).
    assert resolve_hit(0.0, 60.0, False, False, False)["outcome"] == "OUT"
    return "one-rung downgrade, corner fallthrough, no cascade"


def check_hit_intercept():
    for launch, exit, corner, bb in ((30.0, 105.0, True, True),
                                     (0.0, 70.0, False, False),
                                     (20.0, 90.0, False, False)):
        r = resolve_hit(launch, exit, True, corner, bb)
        assert r["outcome"] == "OUT", "intercept %r must be OUT" % (r,)
        assert r["billboard"] is False, "intercept kills billboard"
    return "fielder intercept always OUT"


def check_hit_bonuses():
    assert award_hit("1B") == 100 and award_hit("2B") == 250
    assert award_hit("3B") == 500 and award_hit("HR") == 1000
    assert award_hit("OUT") == 0
    assert award_run(3) == 1500 and award_run(0) == 0, "500/run"
    assert award_corner_paint_k() == 300
    assert award_billboard() == 2500
    assert immaculate_multiplier(True) == 2
    assert immaculate_multiplier(False) == 1
    # Run bonus inside a hit: HR + 2 aboard = 1000 + 3x500.
    g = GameState(3)
    g.half = "bottom"
    g.bases = [True, True, False]
    ev = g.apply_hit("HR")
    assert ev["runs"] == 3 and ev["arcade_delta"] == 2500, "run bonus %r" % (ev,)
    # Corner-paint K pays only when the human pitches (top half).
    gt = GameState(3)
    gt.count.strikes = 2
    ev = gt.apply_pitch_call("strike", corner=True)
    assert ev["arcade_delta"] == 300, "corner K +300"
    gb = GameState(3)
    gb.half = "bottom"
    gb.count.strikes = 2
    ev = gb.apply_pitch_call("strike", corner=True)
    assert ev["arcade_delta"] == 0, "bottom-half K pays no bonus"
    # Immaculate: 3 Ks on exactly 9 pitches -> 2x next batting half.
    gi = GameState(3)
    for _ in range(3):
        gi.apply_pitch_call("ball")
        gi.apply_pitch_call("strike")
        gi.apply_pitch_call("strike")
    assert gi.pitches_this_half == 9 and gi.outs == 3
    info = gi.swap_half()
    assert info["multiplier"] == 2 and gi.multiplier_active, "armed 2x"
    ev = gi.apply_hit("HR")
    assert ev["arcade_delta"] == 3000, "doubled HR %r" % (ev,)
    return "run/corner/immaculate bonuses pay"


def check_hit_billboard():
    # Billboard HR: +2500 jackpot on top of hit + runs.
    assert award_billboard() == 2500
    g2 = GameState(3)
    g2.half = "bottom"
    ev = g2.apply_hit("HR", billboard=True)
    assert ev["arcade_delta"] == 1000 + 500 + 2500, "billboard %r" % (ev,)
    return "billboard jackpot +2500"


CHECKS = [("hit_table", 4, check_hit_table),
          ("hit_downgrade", 4, check_hit_downgrade),
          ("hit_intercept", 2, check_hit_intercept),
          ("hit_bonuses", 3, check_hit_bonuses),
          ("hit_billboard", 2, check_hit_billboard)]


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
