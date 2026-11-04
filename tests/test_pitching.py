"""Pitching: table rows, nose scatter, zone/corner flags."""

import pytest

from server.config import PITCH_TABLE
from server.pitching import resolve_pitch, VALID_PITCHES


def test_four_pitch_rows():
    assert set(VALID_PITCHES) == {"FB", "CB", "SL", "CH"}
    assert PITCH_TABLE["FB"] == {"vel_scale": 1.00, "break_px": 0, "drop_px": 2}
    assert PITCH_TABLE["CB"] == {"vel_scale": 0.75, "break_px": 2, "drop_px": 18}
    assert PITCH_TABLE["SL"] == {"vel_scale": 0.85, "break_px": 16, "drop_px": 6}
    assert PITCH_TABLE["CH"] == {"vel_scale": 0.70, "break_px": 4, "drop_px": 10}


@pytest.mark.parametrize("spec,velo,brk,drop",
                         [("FB", 76.0, 0, 2), ("CB", 57.0, 2, 18),
                          ("SL", 64.6, 16, 6), ("CH", 53.2, 4, 10)])
def test_resolve_pitch_rows_exact(spec, velo, brk, drop):
    p = resolve_pitch(spec, 4.0, (0.0, 0.0), 0.0, 7)
    assert p["pitch"] == spec
    assert p["velo_mph"] == velo
    assert p["break_px"] == brk and p["drop_px"] == drop
    assert p["scattered"] is False
    assert p["seq"] == 7


def test_spec_case_insensitive_and_unknown_rejected():
    assert resolve_pitch("fb", 4.0, (0, 0), 0.0, 1)["pitch"] == "FB"
    with pytest.raises(ValueError):
        resolve_pitch("XX", 4.0, (0, 0), 0.0, 1)


def test_nose_scatter_boundary_strict():
    calm = resolve_pitch("FB", 4.0, (0.1, -0.2), 0.0, 7)
    assert calm["scattered"] is False
    assert calm["location"] == [0.1, -0.2]
    edge = resolve_pitch("FB", 4.0, (0.1, -0.2), 0.3, 7)
    assert edge["scattered"] is False
    wild = resolve_pitch("FB", 4.0, (0.1, -0.2), 0.31, 7)
    assert wild["scattered"] is True
    assert wild["location"] != [0.1, -0.2]


def test_scatter_deterministic_per_seq():
    a = resolve_pitch("FB", 4.0, (0.1, -0.2), 0.31, 7)
    b = resolve_pitch("FB", 4.0, (0.1, -0.2), 0.31, 7)
    assert a["location"] == b["location"]
    c = resolve_pitch("FB", 4.0, (0.1, -0.2), 0.31, 8)
    assert c["location"] != a["location"]


@pytest.mark.parametrize("tgt", [(0.48, 0.0), (-0.48, 0.1),
                                 (0.0, 0.47), (0.1, -0.49), (0.5, 0.0)])
def test_corner_band(tgt):
    p = resolve_pitch("SL", 5.0, tgt, 0.0, 2)
    assert p["in_zone"] is True
    assert p["corner"] is True


def test_zone_heart_and_outside():
    heart = resolve_pitch("FB", 4.0, (0.0, 0.0), 0.0, 1)
    assert heart["in_zone"] is True and heart["corner"] is False
    inside = resolve_pitch("FB", 4.0, (0.44, 0.0), 0.0, 1)
    assert inside["in_zone"] is True and inside["corner"] is False
    out = resolve_pitch("CB", 3.0, (0.6, 0.0), 0.0, 1)
    assert out["in_zone"] is False and out["corner"] is False
