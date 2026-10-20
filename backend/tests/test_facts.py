import pytest

from matchvoice.facts.engine import analyse
from matchvoice.facts.winprob import win_probs
from matchvoice.sim.arcs import ARCS
from matchvoice.sim.engine import Sim


@pytest.fixture(scope="module", params=list(ARCS))
def run(request):
    meta, events, truth = Sim(request.param, seed=7).run()
    return request.param, events, truth, analyse(meta, events)


def test_every_goal_becomes_a_fact_at_the_right_time(run):
    _, _, truth, eng = run
    goals = [f for f in eng.facts if f.kind == "goal"]
    expected = [t for t in truth if t.kind == "goal"]
    assert len(goals) == len(expected)
    for f, t in zip(goals, expected):
        assert abs(f.t - t.t) < 1.0 and f.side == t.side


def test_facts_point_at_real_events(run):
    _, events, _, eng = run
    for f in eng.facts:
        assert f.evidence and all(0 <= i < len(events) for i in f.evidence)
        assert 0.0 <= f.importance <= 1.0


def test_red_card_fact_exists_when_the_arc_has_one(run):
    arc, _, truth, eng = run
    assert len([f for f in eng.facts if f.kind == "red_card"]) == len([t for t in truth if t.kind == "red_card"])


def test_win_probability_ends_at_the_result(run):
    _, events, _, eng = run
    h, d, a = eng.snapshot()["win"]
    sh, sa = eng.score["H"], eng.score["A"]
    assert (h, d, a) == ((1.0, 0.0, 0.0) if sh > sa else (0.0, 1.0, 0.0) if sh == sa else (0.0, 0.0, 1.0))


def test_goal_swings_win_probability_towards_scorer(run):
    _, _, _, eng = run
    for f in (f for f in eng.facts if f.kind == "goal"):
        assert f.data["win_after"] > f.data["win_before"]


def test_comeback_winner_is_the_most_important_moment():
    meta, events, _ = Sim("comeback", 7).run()
    eng = analyse(meta, events)
    top = max(eng.facts, key=lambda f: f.importance)
    assert top.kind == "goal" and {"late", "comeback", "go_ahead"} <= set(top.tags)


def test_win_probs_sum_to_one_and_favour_the_leader():
    h, d, a = win_probs(1, 0, 0.4, 0.4)
    assert abs(h + d + a - 1) < 1e-9 and h > a
