import pytest

from matchvoice.schema import PITCH_L, PITCH_W
from matchvoice.sim.arcs import ARCS
from matchvoice.sim.engine import Sim

EXPECTED_SCORE = {"comeback": [2, 1], "red_card": [1, 1], "unlucky": [0, 1]}


@pytest.fixture(scope="module", params=list(ARCS))
def match(request):
    return request.param, Sim(request.param, seed=7).run()


def test_final_score_follows_arc(match):
    arc, (_, events, _) = match
    goals = [e for e in events if e.type == "shot" and e.outcome == "goal"]
    assert goals[-1].score == EXPECTED_SCORE[arc] if goals else EXPECTED_SCORE[arc] == [0, 0]
    assert len(goals) == sum(EXPECTED_SCORE[arc])


def test_time_is_monotonic_and_events_numbered(match):
    _, (_, events, _) = match
    assert [e.i for e in events] == list(range(len(events)))
    assert all(a.t <= b.t for a, b in zip(events, events[1:]))


def test_coordinates_stay_on_pitch(match):
    _, (_, events, _) = match
    for e in events:
        assert 0 <= e.x <= PITCH_L and 0 <= e.y <= PITCH_W
        if e.end_x is not None:
            assert 0 <= e.end_x <= PITCH_L and 0 <= e.end_y <= PITCH_W


def test_truth_lists_every_goal(match):
    arc, (_, events, truth) = match
    assert sum(1 for t in truth if t.kind == "goal") == sum(EXPECTED_SCORE[arc])


def test_same_seed_same_match():
    a = Sim("comeback", 3).run()[1]
    b = Sim("comeback", 3).run()[1]
    assert [e.model_dump() for e in a] == [e.model_dump() for e in b]
