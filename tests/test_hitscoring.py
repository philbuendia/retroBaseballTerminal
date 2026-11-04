"""Hit resolution: table, downgrades, intercepts, arcade bonuses."""

import pytest

from server.config import HIT_WINDOWS
from server.hitting import resolve_hit
from server.game import GameState
from server.scoring import (award_hit, award_run, award_corner_paint_k,
                            award_billboard, immaculate_multiplier)


def test_hit_window_rows():
    assert HIT_WINDOWS["1B"] == (-5.0, 15.0, 70.0, 100)
    assert HIT_WINDOWS["2B"] == (12.0, 24.0, 88.0, 250)
    assert HIT_WINDOWS["3B"] == (18.0, 28.0, 98.0, 500)
    assert HIT_WINDOWS["HR"] == (25.0, 38.0, 102.0, 1000)


@pytest.mark.parametrize("launch,exit,corner,bb,want",
                         [(0.0, 70.0, False, False, "1B"),
                          (20.0, 90.0, False, False, "2B"),
                          (20.0, 100.0, True, False, "3B"),
                          (30.0, 105.0, False, False, "HR"),
                          (27.0, 105.0, True, False, "HR"),
                          (50.0, 110.0, False, False, "OUT")])
def test_hit_table_and_precedence(launch, exit, corner, bb, want):
    assert resolve_hit(launch, exit, False, corner, bb)["outcome"] == want


def test_billboard_flag_only_on_hr():
    assert resolve_hit(30.0, 105.0, False, False, True)["billboard"] is True
    assert resolve_hit(20.0, 90.0, False, True, True)["billboard"] is False


@pytest.mark.parametrize("launch,exit,corner,want",
                         [(30.0, 100.0, True, "3B"),
                          (30.0, 100.0, False, "2B"),
                          (20.0, 80.0, False, "1B"),
                          (30.0, 70.0, True, "3B"),
                          (13.0, 75.0, False, "1B"),
                          (0.0, 60.0, False, "OUT")])
def test_one_rung_downgrade(launch, exit, corner, want):
    assert resolve_hit(launch, exit, False, corner, False)["outcome"] == want


@pytest.mark.parametrize("launch,exit,corner,bb",
                         [(30.0, 105.0, True, True),
                          (0.0, 70.0, False, False),
                          (20.0, 90.0, False, False)])
def test_intercept_always_out(launch, exit, corner, bb):
    r = resolve_hit(launch, exit, True, corner, bb)
    assert r["outcome"] == "OUT"
    assert r["billboard"] is False


def test_award_units():
    assert (award_hit("1B"), award_hit("2B"), award_hit("3B"),
            award_hit("HR"), award_hit("OUT")) == (100, 250, 500, 1000, 0)
    assert award_run(3) == 1500 and award_run(0) == 0
    assert award_corner_paint_k() == 300
    assert award_billboard() == 2500
    assert immaculate_multiplier(True) == 2
    assert immaculate_multiplier(False) == 1


def test_run_bonus_inside_hit():
    g = GameState(3)
    g.half = "bottom"
    g.bases = [True, True, False]
    ev = g.apply_hit("HR")
    assert ev["runs"] == 3 and ev["arcade_delta"] == 2500


def test_corner_paint_k_top_half_only():
    gt = GameState(3)
    gt.count.strikes = 2
    assert gt.apply_pitch_call("strike", corner=True)["arcade_delta"] == 300
    gb = GameState(3)
    gb.half = "bottom"
    gb.count.strikes = 2
    assert gb.apply_pitch_call("strike", corner=True)["arcade_delta"] == 0


def test_immaculate_multiplier():
    g = GameState(3)
    for _ in range(3):
        g.apply_pitch_call("ball")
        g.apply_pitch_call("strike")
        g.apply_pitch_call("strike")
    assert g.pitches_this_half == 9 and g.outs == 3
    info = g.swap_half()
    assert info["multiplier"] == 2 and g.multiplier_active
    assert g.apply_hit("HR")["arcade_delta"] == 3000


def test_billboard_jackpot():
    g = GameState(3)
    g.half = "bottom"
    ev = g.apply_hit("HR", billboard=True)
    assert ev["arcade_delta"] == 1000 + 500 + 2500
