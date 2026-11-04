"""Innings: 1-1 counts, two-foul K, advances, role-swap, mercy."""

import pytest

from server.game import GameState, Count


def test_count_starts_1_1_and_resets():
    g = GameState(3)
    assert (g.count.balls, g.count.strikes) == (1, 1)
    assert g.count.consec_two_strike_fouls == 0
    g.count.balls = 3
    g.new_batter()
    assert (g.count.balls, g.count.strikes) == (1, 1)
    assert Count().as_dict() == {"balls": 1, "strikes": 1,
                                 "consec_two_strike_fouls": 0}
    with pytest.raises(ValueError):
        GameState(0)


def test_called_ball_walk_and_strikeout():
    g = GameState(3)
    g.count.balls = 3
    ev = g.apply_pitch_call("ball")
    assert ev["event"] == "walk"
    g.count.strikes = 2
    ev = g.apply_pitch_call("strike")
    assert ev["event"] == "strikeout" and g.outs == 1
    with pytest.raises(ValueError):
        g.apply_pitch_call("foul")


def test_two_foul_courtesy_rule():
    g = GameState(3)
    g.count.strikes = 1
    assert g.apply_foul()["event"] == "foul"
    assert g.count.strikes == 2
    assert g.apply_foul()["event"] == "foul_alive"
    assert g.outs == 0 and g.count.strikes == 2
    assert g.apply_foul()["event"] == "strikeout"
    assert g.outs == 1
    assert (g.count.balls, g.count.strikes) == (1, 1)


def test_non_foul_resets_courtesy_counter():
    g = GameState(3)
    g.count.strikes = 2
    assert g.apply_foul()["event"] == "foul_alive"
    assert g.apply_pitch_call("ball")["event"] == "ball"
    assert g.apply_foul()["event"] == "foul_alive"
    assert g.outs == 0


def test_auto_advance_hits():
    g = GameState(3)
    g.half = "bottom"
    assert g.apply_hit("1B")["runs"] == 0
    assert g.bases == [True, False, False]
    g.bases = [True, True, False]
    ev = g.apply_hit("2B")
    assert (ev["runs"], g.bases) == (1, [False, True, True])
    g.bases = [True, True, True]
    ev = g.apply_hit("3B")
    assert (ev["runs"], g.bases) == (3, [False, False, True])
    g.bases = [True, False, True]
    ev = g.apply_hit("HR")
    assert (ev["runs"], g.bases) == (3, [False, False, False])
    assert g.score() == {"away": 0, "home": 7}
    with pytest.raises(ValueError):
        g.apply_hit("XX")


def test_loaded_walk_forces_run():
    g = GameState(3)
    g.bases = [True, True, True]
    g.count.balls = 3
    ev = g.apply_pitch_call("ball")
    assert ev["event"] == "walk" and ev["runs"] == 1
    assert g.score() == {"away": 1, "home": 0}


def test_role_swap_halves():
    g = GameState(3)
    assert g.half == "top" and g.batting == "away"
    g.outs = 3
    g.bases = [True, False, False]
    info = g.swap_half()
    assert info["half"] == "bottom" and g.batting == "home"
    assert g.outs == 0 and g.bases == [False, False, False]
    assert (g.count.balls, g.count.strikes) == (1, 1)
    g.outs = 3
    info = g.swap_half()
    assert info["half"] == "top" and g.inning == 2
    assert g.completed_innings == 1


def test_final_inning_ends_game():
    g = GameState(1)
    g.half = "bottom"
    g.outs = 3
    info = g.swap_half()
    assert info == {"event": "game_over", "reason": "final"}
    assert g.over and g.reason == "final"


def test_mercy_rule_and_nine_run_continues():
    g = GameState(3)
    g.runs_home = 10
    assert g.check_mercy() is False  # needs a completed inning
    g.completed_innings = 1
    assert g.check_mercy() is True
    g.runs_home = 9
    assert g.check_mercy() is False
    g.half = "bottom"
    g.outs = 3
    info = g.swap_half()
    assert info["event"] == "swap" and not g.over and g.inning == 2
    gm = GameState(3)
    gm.half = "bottom"
    gm.outs = 3
    gm.runs_home = 12
    info = gm.swap_half()
    assert info == {"event": "game_over", "reason": "mercy"}
    assert gm.over and gm.reason == "mercy"
