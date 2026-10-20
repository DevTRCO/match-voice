"""Win probability from a Poisson goal model.

Deliberately simple so it can be explained in one sentence: each side scores
at a rate that blends a league prior with its own expected goals so far, the
rate drops with red cards, and we sum over the remaining time.
"""
from __future__ import annotations

import math
from functools import lru_cache

PRIOR_GOALS_PER_90 = 1.35
PRIOR_WEIGHT_S = 1200.0  # the prior counts as 20 minutes of evidence
KMAX = 8


@lru_cache(maxsize=4096)
def _pmf(lam_x100: int) -> tuple[float, ...]:
    lam = lam_x100 / 100.0
    return tuple(math.exp(-lam) * lam ** k / math.factorial(k) for k in range(KMAX + 1))


def rate_per_s(xg_so_far: float, elapsed_s: float) -> float:
    prior = PRIOR_GOALS_PER_90 / 5400.0
    return (prior * PRIOR_WEIGHT_S + xg_so_far) / (PRIOR_WEIGHT_S + max(elapsed_s, 1.0))


def red_multiplier(own_reds: int, opp_reds: int) -> float:
    return 0.85 ** own_reds * 1.10 ** opp_reds


def win_probs(home_goals: int, away_goals: int, lam_h: float, lam_a: float) -> tuple[float, float, float]:
    """(P home win, P draw, P away win) given the expected goals still to come."""
    ph, pa = _pmf(round(lam_h * 100)), _pmf(round(lam_a * 100))
    home = draw = away = 0.0
    for a, pa_a in enumerate(ph):
        for b, pb_b in enumerate(pa):
            p = pa_a * pb_b
            diff = home_goals + a - (away_goals + b)
            if diff > 0:
                home += p
            elif diff == 0:
                draw += p
            else:
                away += p
    total = home + draw + away
    return home / total, draw / total, away / total


def expected_points(probs: tuple[float, float, float], side: str) -> float:
    h, d, a = probs
    return 3 * h + d if side == "H" else 3 * a + d
