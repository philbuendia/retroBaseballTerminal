"""Eval scenario: arcade counts, baserunning, role-swap, mercy rule."""

import traceback

from server.game import GameState, Count

CATEGORY = "innings"
WEIGHT = 15


def check_inn_count_start():
    g = GameState(3)
    assert (g.count.balls, g.count.strikes) == (1, 1), "PA starts 1-1"
    assert g.count.consec_two_strike_fouls == 0
    g.count.balls = 3
    g.count.strikes = 0
    g.new_batter()
    assert (g.count.balls, g.count.strikes) == (1, 1), "new batter resets 1-1"
    d = Count().as_dict()
    assert d == {"balls": 1, "strikes": 1, "consec_two_strike_fouls": 0}
    try:
        GameState(0)
    except ValueError:
        pass
    else:
        raise AssertionError("innings < 1 must raise ValueError")
    return "1-1 starts + resets"


def check_inn_two_foul_k():
    g = GameState(3)
    g.count.strikes = 1
    ev = g.apply_foul()
    assert ev["event"] == "foul" and g.count.strikes == 2, "foul<2K adds strike"
    ev = g.apply_foul()
    assert ev["event"] == "foul_alive", "first 2K foul stays alive"
    assert g.count.strikes == 2 and g.outs == 0
    ev = g.apply_foul()
    assert ev["event"] == "strikeout", "second 2K foul is a K"
    assert g.outs == 1, "K records an out"
    assert (g.count.balls, g.count.strikes) == (1, 1), "count resets after K"
    return "foul#1 alive, foul#2 consecutive K"


def check_inn_auto_advance():
    g = GameState(3)
    g.half = "bottom"
    ev = g.apply_hit("1B")
    assert ev["runs"] == 0 and g.bases == [True, False, False], "1B empty"
    g.bases = [True, True, False]
    ev = g.apply_hit("2B")
    assert ev["runs"] == 1 and g.bases == [False, True, True], "2B scores R2, R1->3B"
    g.bases = [True, True, True]
    ev = g.apply_hit("3B")
    assert ev["runs"] == 3 and g.bases == [False, False, True], "3B clears"
    g.bases = [True, False, True]
    ev = g.apply_hit("HR")
    assert ev["runs"] == 3 and g.bases == [False, False, False], "HR +2 on"
    assert g.score() == {"away": 0, "home": 7}, "7 runs total, %r" % (g.score(),)
    gw = GameState(3)
    gw.bases = [True, True, True]
    gw.count.balls = 3
    ev = gw.apply_pitch_call("ball")
    assert ev["event"] == "walk" and ev["runs"] == 1, "loaded walk forces run"
    try:
        g.apply_hit("XX")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown outcome must raise ValueError")
    return "1B/2B/3B/HR + loaded walk advances"


def check_inn_role_swap():
    g = GameState(3)
    assert g.half == "top" and g.batting == "away", "humans pitch the top"
    g.outs = 3
    g.bases = [True, False, False]
    info = g.swap_half()
    assert info["half"] == "bottom" and g.batting == "home", "top->bottom"
    assert g.outs == 0 and g.bases == [False, False, False], "half resets"
    assert (g.count.balls, g.count.strikes) == (1, 1)
    g.outs = 3
    info = g.swap_half()
    assert info["half"] == "top" and g.inning == 2, "bottom->next top"
    assert g.completed_innings == 1
    gl = GameState(1)
    gl.half = "bottom"
    gl.outs = 3
    info = gl.swap_half()
    assert info["reason"] == "final" and gl.over, "last inning ends game"
    return "top<->bottom halves, final ends"


def check_inn_mercy():
    g = GameState(3)
    g.runs_home = 10
    assert g.check_mercy() is False, "no mercy mid-first-inning"
    g.completed_innings = 1
    assert g.check_mercy() is True, "10-run lead after an inning"
    g.runs_home = 9
    assert g.check_mercy() is False, "9-run lead continues"
    g.half = "bottom"
    g.outs = 3
    g.runs_home = 9
    info = g.swap_half()
    assert info["event"] == "swap" and not g.over, "9-run lead plays on"
    assert g.inning == 2
    gm = GameState(3)
    gm.half = "bottom"
    gm.outs = 3
    gm.runs_home = 12
    info = gm.swap_half()
    assert info == {"event": "game_over", "reason": "mercy"}, "mercy %r" % (info,)
    assert gm.over and gm.reason == "mercy"
    return "mercy>=10, 9-run lead continues"


CHECKS = [("inn_count_start", 2, check_inn_count_start),
          ("inn_two_foul_k", 3, check_inn_two_foul_k),
          ("inn_auto_advance", 4, check_inn_auto_advance),
          ("inn_role_swap", 3, check_inn_role_swap),
          ("inn_mercy", 3, check_inn_mercy)]


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
