"""Arcade inning rules: counts, baserunning, role-swap halves, mercy rule.

Conventions: the human pitches the top half (AI batters, "away" scores) and
bats the bottom half ("home" scores). Arcade points are the human's.
Every plate appearance starts 1-1; the first two-strike foul stays alive
and the second consecutive two-strike foul is a strikeout. A lead >= 10
after a completed inning ends the game immediately.
"""

from dataclasses import dataclass

from .config import (COUNT_START_BALLS, COUNT_START_STRIKES, MAX_BALLS,
                     MAX_STRIKES, MERCY_RUNS)
from .scoring import (award_hit, award_run, award_corner_paint_k,
                      award_billboard, immaculate_multiplier)


@dataclass
class Count:
    balls: int = COUNT_START_BALLS
    strikes: int = COUNT_START_STRIKES
    consec_two_strike_fouls: int = 0

    def reset(self):
        self.balls = COUNT_START_BALLS
        self.strikes = COUNT_START_STRIKES
        self.consec_two_strike_fouls = 0

    def as_dict(self):
        return {"balls": self.balls, "strikes": self.strikes,
                "consec_two_strike_fouls": self.consec_two_strike_fouls}


class GameState:
    def __init__(self, innings=3):
        if int(innings) < 1:
            raise ValueError("innings must be >= 1")
        self.max_innings = int(innings)
        self.inning = 1
        self.half = "top"
        self.outs = 0
        self.bases = [False, False, False]  # 1B, 2B, 3B occupied
        self.count = Count()
        self.runs_away = 0  # AI (bats top)
        self.runs_home = 0  # human (bats bottom)
        self.arcade = 0
        self.over = False
        self.reason = None
        self.completed_innings = 0
        self.pitches_this_half = 0
        self.ks_consec = 0
        self.immaculate_armed = False
        self.multiplier_active = False
        self.batters_faced = 0

    # -- queries ------------------------------------------------------
    @property
    def batting(self):
        return "away" if self.half == "top" else "home"

    @property
    def half_over(self):
        return self.outs >= 3

    def new_batter(self):
        self.count.reset()
        self.batters_faced += 1

    def score(self):
        return {"away": self.runs_away, "home": self.runs_home}

    def lead(self):
        return abs(self.runs_home - self.runs_away)

    def check_mercy(self):
        """True once a completed inning ends with a lead >= 10."""
        return self.completed_innings >= 1 and self.lead() >= MERCY_RUNS

    def to_dict(self):
        return {
            "inning": self.inning, "half": self.half, "outs": self.outs,
            "bases": list(self.bases), "count": self.count.as_dict(),
            "runs": self.score(), "arcade": self.arcade,
            "multiplier": immaculate_multiplier(self.multiplier_active),
            "over": self.over, "reason": self.reason,
        }

    # -- internal helpers ---------------------------------------------
    def _add_runs(self, n):
        if self.half == "top":
            self.runs_away += n
        else:
            self.runs_home += n
        return n

    def _walk_advance(self):
        """Forced-only walk advance. Returns runs scored."""
        b = self.bases
        runs = 1 if (b[0] and b[1] and b[2]) else 0
        n1 = b[0] or b[1]  # forced runner arrives, or unforced R2 stays
        n2 = (b[1] and b[0]) or (b[2] and not (b[0] and b[1]))
        self.bases = [True, bool(n1), bool(n2)]
        return runs

    def _hit_advance(self, outcome):
        """Auto-baserunning advance. Returns runs scored."""
        b = self.bases
        if outcome == "1B":
            runs = (1 if b[2] else 0)
            self.bases = [True, b[0], b[1]]
            return runs
        if outcome == "2B":
            runs = (1 if b[2] else 0) + (1 if b[1] else 0)
            self.bases = [False, True, bool(b[0])]
            return runs
        if outcome == "3B":
            runs = sum(1 for x in b if x)
            self.bases = [False, False, True]
            return runs
        if outcome == "HR":
            runs = sum(1 for x in b if x) + 1
            self.bases = [False, False, False]
            return runs
        return 0

    def _strikeout(self, corner):
        """Record a strikeout; corner-paint bonus only when human pitches."""
        self.outs += 1
        self.ks_consec += 1
        delta = 0
        if self.half == "top" and corner:
            delta += award_corner_paint_k()
        self.arcade += delta
        self.new_batter()
        return {"event": "strikeout", "runs": 0, "arcade_delta": delta,
                "half_over": self.half_over}

    def _maybe_walkoff(self):
        last = self.inning >= self.max_innings
        if self.half == "bottom" and last and self.runs_home > self.runs_away:
            self.over = True
            self.reason = "walkoff"
            return True
        return False

    # -- scoring events -------------------------------------------------
    def apply_pitch_call(self, call, corner=False):
        """Apply a called ball/strike. Returns an event dict."""
        if self.over:
            return {"event": "game_over", "runs": 0, "arcade_delta": 0}
        if call not in ("ball", "strike"):
            raise ValueError("call must be 'ball' or 'strike'")
        self.pitches_this_half += 1
        self.count.consec_two_strike_fouls = 0  # non-foul resets courtesy
        if call == "ball":
            self.count.balls += 1
            if self.count.balls >= MAX_BALLS:
                runs = self._add_runs(self._walk_advance())
                self.ks_consec = 0
                self.new_batter()
                self._maybe_walkoff()
                return {"event": "walk", "runs": runs, "arcade_delta": 0,
                        "half_over": self.half_over}
            return {"event": "ball", "runs": 0, "arcade_delta": 0,
                    "half_over": False}
        self.count.strikes += 1
        if self.count.strikes >= MAX_STRIKES:
            return self._strikeout(corner)
        return {"event": "strike", "runs": 0, "arcade_delta": 0,
                "half_over": False}

    def apply_foul(self):
        """Apply a foul ball incl. the two-foul courtesy rule."""
        if self.over:
            return {"event": "game_over", "runs": 0, "arcade_delta": 0}
        self.pitches_this_half += 1
        if self.count.strikes < 2:
            self.count.strikes += 1
            self.count.consec_two_strike_fouls = 0
            return {"event": "foul", "runs": 0, "arcade_delta": 0,
                    "half_over": False}
        if self.count.consec_two_strike_fouls >= 1:
            return self._strikeout(corner=False)
        self.count.consec_two_strike_fouls += 1
        return {"event": "foul_alive", "runs": 0, "arcade_delta": 0,
                "half_over": False}

    def apply_hit(self, outcome, billboard=False):
        """Apply a batted-ball outcome. Returns an event dict."""
        if self.over:
            return {"event": "game_over", "runs": 0, "arcade_delta": 0}
        if outcome not in ("1B", "2B", "3B", "HR", "OUT"):
            raise ValueError("unknown hit outcome: %r" % (outcome,))
        self.pitches_this_half += 1
        if outcome == "OUT":
            self.outs += 1
            self.ks_consec = 0
            self.new_batter()
            return {"event": "out", "outcome": outcome, "runs": 0,
                    "arcade_delta": 0, "half_over": self.half_over}
        runs = self._add_runs(self._hit_advance(outcome))
        self.ks_consec = 0
        delta = 0
        if self.half == "bottom":  # human is batting: arcade points apply
            mult = immaculate_multiplier(self.multiplier_active)
            delta = (award_hit(outcome) + award_run(runs)) * mult
            if outcome == "HR" and billboard:
                delta += award_billboard() * mult
            self.arcade += delta
        self.new_batter()
        self._maybe_walkoff()
        return {"event": "hit", "outcome": outcome, "runs": runs,
                "arcade_delta": delta, "billboard": bool(billboard),
                "half_over": self.half_over or self.over}

    def swap_half(self):
        """Advance top->bottom or bottom->next top; handles mercy/final."""
        if self.over:
            return {"event": "game_over", "reason": self.reason}
        if self.half == "top":
            if self.outs >= 3 and self.ks_consec >= 3 \
                    and self.pitches_this_half == 9:
                self.immaculate_armed = True
            self.half = "bottom"
            self.multiplier_active = self.immaculate_armed
            self.immaculate_armed = False
        else:
            self.completed_innings += 1
            if self.check_mercy():
                self.over = True
                self.reason = "mercy"
                return {"event": "game_over", "reason": "mercy"}
            if self.inning >= self.max_innings:
                self.over = True
                self.reason = "final"
                return {"event": "game_over", "reason": "final"}
            self.inning += 1
            self.half = "top"
            self.multiplier_active = False
        self.outs = 0
        self.bases = [False, False, False]
        self.count.reset()
        self.pitches_this_half = 0
        self.ks_consec = 0
        return {"event": "swap", "inning": self.inning, "half": self.half,
                "multiplier": immaculate_multiplier(self.multiplier_active)}
