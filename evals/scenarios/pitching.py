"""Eval scenario: pitch table, nose-scatter, zone/corner flags."""

import traceback

from server.config import PITCH_TABLE
from server.pitching import resolve_pitch, VALID_PITCHES

CATEGORY = "pitching"
WEIGHT = 15


def check_pitch_table_exact():
    assert set(VALID_PITCHES) == {"FB", "CB", "SL", "CH"}, "4 pitch codes"
    want = {"FB": (1.00, 0, 2, 76.0), "CB": (0.75, 2, 18, 57.0),
            "SL": (0.85, 16, 6, 64.6), "CH": (0.70, 4, 10, 53.2)}
    for spec, (scale, brk, drop, velo) in want.items():
        row = PITCH_TABLE[spec]
        assert row["vel_scale"] == scale, "%s scale" % spec
        assert row["break_px"] == brk, "%s break" % spec
        assert row["drop_px"] == drop, "%s drop" % spec
        p = resolve_pitch(spec, 4.0, (0.0, 0.0), 0.0, 7)
        assert p["break_px"] == brk and p["drop_px"] == drop
        assert p["velo_mph"] == velo, "%s velo %r" % (spec, p["velo_mph"])
    low = resolve_pitch("fb", 4.0, (0, 0), 0.0, 1)
    assert low["pitch"] == "FB", "spec is case-insensitive"
    try:
        resolve_pitch("XX", 4.0, (0, 0), 0.0, 1)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown spec must raise ValueError")
    return "FB/CB/SL/CH rows exact, velo 76/57/64.6/53.2"


def check_pitch_scatter():
    base = dict(target=(0.1, -0.2))
    calm = resolve_pitch("FB", 4.0, (0.1, -0.2), 0.0, 7)
    assert calm["scattered"] is False, "steady head: no scatter"
    assert calm["location"] == [0.1, -0.2], "no scatter keeps target"
    edge = resolve_pitch("FB", 4.0, (0.1, -0.2), 0.3, 7)
    assert edge["scattered"] is False, "nose == 0.3Ws: no scatter (strict >)"
    wild = resolve_pitch("FB", 4.0, (0.1, -0.2), 0.31, 7)
    assert wild["scattered"] is True, "nose > 0.3Ws scatters"
    assert wild["location"] != [0.1, -0.2], "scatter moves location"
    again = resolve_pitch("FB", 4.0, (0.1, -0.2), 0.31, 7)
    assert again["location"] == wild["location"], "same seq: same scatter"
    other = resolve_pitch("FB", 4.0, (0.1, -0.2), 0.31, 8)
    assert other["location"] != wild["location"], "seq varies the offset"
    assert base["target"] == (0.1, -0.2)
    return "0.3 boundary strict, deterministic per-seq scatter"


def check_pitch_zone_corner():
    c = resolve_pitch("FB", 4.0, (0.0, 0.0), 0.0, 1)
    assert c["in_zone"] is True and c["corner"] is False, "heart of zone"
    for tgt in ((0.48, 0.0), (-0.48, 0.1), (0.0, 0.47), (0.1, -0.49)):
        p = resolve_pitch("SL", 5.0, tgt, 0.0, 2)
        assert p["in_zone"] is True, "%r in zone" % (tgt,)
        assert p["corner"] is True, "%r on corner" % (tgt,)
    edge = resolve_pitch("FB", 4.0, (0.5, 0.0), 0.0, 1)
    assert edge["in_zone"] is True and edge["corner"] is True, "edge is corner"
    inside = resolve_pitch("FB", 4.0, (0.44, 0.0), 0.0, 1)
    assert inside["in_zone"] is True and inside["corner"] is False
    out = resolve_pitch("CB", 3.0, (0.6, 0.0), 0.0, 1)
    assert out["in_zone"] is False and out["corner"] is False, "outside zone"
    return "zone heart/edge/outside + corner band"


CHECKS = [("pitch_table_exact", 6, check_pitch_table_exact),
          ("pitch_scatter", 5, check_pitch_scatter),
          ("pitch_zone_corner", 4, check_pitch_zone_corner)]


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
