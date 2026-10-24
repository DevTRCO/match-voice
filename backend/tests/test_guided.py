"""Guided live run: window choice, the hard live limits, and the insight logs."""
import dataclasses
import random
import threading
import types
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

from matchvoice.commentary.analyst import CallBudget
from matchvoice.commentary.moments import MomentBuilder
from matchvoice.facts.engine import FactEngine
from matchvoice.pipeline.guided import LEAD_S, TAIL_S, WINDOW_S, guided_live, pick_window
from matchvoice.pipeline.insights import MAX_PER_MINUTE, MIN_SWING_T, SWING_POINTS, InsightFeed
from matchvoice.pipeline.runner import LiveConfig, LiveLimits, LiveUnavailable, Runner
from matchvoice.schema import EventType
from matchvoice.server.app import create_app
from test_pipeline import LIB, fake_llm, run
from test_server import ws_messages

CAP = "match=comeback-7&mode=live&speed=60&paced=false"
INSIGHT_KINDS = {"wp_swing", "momentum", "shots"}


def cfg(tmp_path, limits: LiveLimits | None = None, calls: int = 400) -> LiveConfig:
    return LiveConfig(fake_llm(), CallBudget(calls), "fake", tmp_path, limits=limits or LiveLimits())


def goal_times(bundle) -> list[float]:
    return [e.t for e in bundle.events if e.type == EventType.SHOT and e.outcome == "goal"]


# ---------- window choice ----------
@pytest.mark.parametrize("match", ["comeback-7", "red_card-7", "unlucky-7", "comeback-135"])
def test_window_contains_a_goal_and_is_at_most_sixty_seconds(match):
    b = LIB.bundle(match)
    w = pick_window(b)
    assert w["goal_t"] in [round(t, 1) for t in goal_times(b)]
    assert 0 <= w["start"] < w["goal_t"] <= w["until"] and w["until"] - w["start"] <= WINDOW_S
    assert w["goal_t"] - w["start"] <= LEAD_S + 1 and w["until"] <= b.duration
    assert w["until"] - w["goal_t"] <= TAIL_S + 1  # no frozen tail after the goal


def test_the_window_with_the_most_action_wins_among_several_goals():
    b = LIB.bundle("comeback-7")
    eng, mb, moments = FactEngine(b.meta), None, []
    mb = MomentBuilder(eng)
    for ev in b.events:
        moments += [(m.t, m.priority) for m in mb.feed(ev, eng.ingest(ev))]

    def action(g: float) -> int:
        s = max(0, int(g - LEAD_S))
        return sum(p for t, p in moments if s <= t <= min(g + TAIL_S, s + WINDOW_S))
    best = max(goal_times(b), key=lambda g: (action(g), -g))
    assert pick_window(b)["goal_t"] == round(best, 1)


def test_without_a_goal_the_highest_priority_moment_is_the_anchor():
    b = LIB.bundle("red_card-7")
    quiet = dataclasses.replace(b, events=[e for e in b.events if not (e.type == EventType.SHOT and e.outcome == "goal")])
    w = pick_window(quiet)
    assert w["goal_t"] is None
    red = next(e.t for e in quiet.events if e.type == EventType.CARD and e.card == "red")  # priority 95 beats every other moment here
    assert w["start"] <= red <= w["until"]


def test_a_window_near_the_final_whistle_stays_inside_the_match():
    b = LIB.bundle("comeback-7")
    late = dataclasses.replace(b, events=[e for e in b.events if e.t <= max(goal_times(b)) + 5])
    w = pick_window(late)
    assert w["until"] <= late.duration and w["until"] - w["start"] <= WINDOW_S


def test_guided_live_is_a_valid_fresh_match_id_the_runner_accepts():
    rng = random.Random(3)
    seen = set()
    for _ in range(6):
        g = guided_live(LIB, rng)
        assert g["match"] == f"{g['arc']}-{g['seed']}" and 1 <= g["seed"] <= 999_999
        assert g["window_s"] == g["until"] - g["start"] <= WINDOW_S
        b = LIB.bundle(g["match"])  # same id, same match
        assert goal_times(b) == goal_times(LIB.bundle(g["match"]))
        Runner(b, "live", 1.0, True, LiveConfig(fake_llm(), CallBudget(5)), g["start"], None, g["until"])
        seen.add(g["match"])
    assert len(seen) > 1


def test_the_endpoint_returns_the_documented_shape_and_a_new_match_each_time(tmp_path):
    with TestClient(create_app(live=cfg(tmp_path, LiveLimits(75, 150)))) as c:
        a, b = c.get("/api/guided-live").json(), c.get("/api/guided-live").json()
        assert set(a) == {"match", "arc", "seed", "start", "until", "window_s", "goal_t", "fresh", "runs_left"}
        assert a["runs_left"] == 150 and a["fresh"] is False and a["match"] != b["match"]
        assert c.get("/api/guided-live").json()["runs_left"] == 150  # asking for a window starts no run
    with TestClient(create_app(live_error=LiveUnavailable("no_key", "x"))) as c:
        assert c.get("/api/guided-live").json()["runs_left"] is None


def test_the_endpoint_uses_the_injected_random_source():
    with TestClient(create_app(rng=random.Random(9))) as c1, TestClient(create_app(rng=random.Random(9))) as c2:
        assert c1.get("/api/guided-live").json() == c2.get("/api/guided-live").json()


# ---------- run length cap ----------
def test_a_live_run_longer_than_the_cap_is_refused_on_both_transports(tmp_path):
    with TestClient(create_app(live=cfg(tmp_path, LiveLimits(max_seconds=75)))) as c:
        long = ws_messages(c, f"{CAP}&start=100&until=176")
        assert long[0]["k"] == "error" and long[0]["code"] == "bad_request" and "75" in long[0]["message"]
        r = c.get(f"/sse?{CAP}&start=100&until=176")
        assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_request"
        assert c.get("/api/health").json()["live"]["runs_left"] is None  # refused requests used nothing


def test_a_live_run_without_until_is_refused_when_the_cap_is_set(tmp_path):
    with TestClient(create_app(live=cfg(tmp_path, LiveLimits(max_seconds=75)))) as c:
        msg = ws_messages(c, CAP)[0]
        assert msg["code"] == "bad_request" and "until" in msg["message"]
        assert c.get(f"/sse?{CAP}").status_code == 400


def test_a_run_of_exactly_the_cap_is_accepted_and_replay_is_not_capped(tmp_path):
    with TestClient(create_app(live=cfg(tmp_path, LiveLimits(max_seconds=75)))) as c:
        msgs = ws_messages(c, f"{CAP}&start=100&until=175")
        assert msgs[0]["k"] == "hello" and msgs[0]["until"] == 175 and msgs[-1]["k"] == "end"
        assert ws_messages(c, "match=comeback-7&mode=replay&speed=600&paced=false")[-1]["k"] == "end"


def test_without_a_cap_nothing_changes(tmp_path):
    with TestClient(create_app(live=cfg(tmp_path))) as c:
        assert ws_messages(c, f"{CAP}&start=100&until=2000")[0]["k"] == "hello"


# ---------- daily cap ----------
class Day:
    def __init__(self):
        self.now = datetime(2026, 10, 21, 23, 59, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


def test_the_daily_cap_counts_starts_refuses_with_a_code_and_resets_at_midnight_utc(tmp_path):
    day = Day()
    limits = LiveLimits(max_seconds=75, runs_per_day=2, clock=day)
    with TestClient(create_app(live=cfg(tmp_path, limits))) as c:
        q = f"{CAP}&start=100&until=130"
        assert c.get("/api/health").json()["live"]["runs_left"] == 2
        for left in (1, 0):
            assert ws_messages(c, q)[0]["k"] == "hello"
            assert c.get("/api/health").json()["live"]["runs_left"] == left
        live = c.get("/api/health").json()["live"]
        assert live["available"] is False and live["code"] == "no_runs_today" and live["reason"] and live["runs_per_day"] == 2
        msg = ws_messages(c, q)[0]
        assert msg["k"] == "error" and msg["code"] == "no_runs_today" and msg["message"]
        r = c.get(f"/sse?{q}")
        assert r.status_code == 429 and r.json()["detail"]["code"] == "no_runs_today"
        assert c.get("/api/guided-live").json()["runs_left"] == 0
        assert ws_messages(c, "match=comeback-7&mode=replay&speed=600&paced=false")[-1]["k"] == "end"  # a recording needs no run
        day.now += timedelta(minutes=2)  # 00:01 UTC the next day
        assert c.get("/api/health").json()["live"]["runs_left"] == 2
        assert ws_messages(c, q)[0]["k"] == "hello"


def test_a_refused_request_does_not_use_up_a_run(tmp_path):
    with TestClient(create_app(live=cfg(tmp_path, LiveLimits(max_seconds=75, runs_per_day=1)))) as c:
        for bad in ("match=nope&mode=live&until=130", f"{CAP}&until=300", f"{CAP}&start=abc&until=130", CAP):
            assert ws_messages(c, bad)[0]["k"] == "error"
        assert c.get("/api/health").json()["live"]["runs_left"] == 1


def test_the_call_budget_is_still_the_final_guard(tmp_path):
    spent = LiveConfig(fake_llm(), CallBudget(2, used=2), "fake", tmp_path, limits=LiveLimits(75, 5))
    with TestClient(create_app(live=spent)) as c:
        assert ws_messages(c, f"{CAP}&start=100&until=130")[0]["code"] == "no_budget"
        assert c.get("/api/health").json()["live"]["runs_left"] == 5  # refused by the budget before a run was counted


def test_concurrent_starts_can_never_exceed_the_cap():
    limits = LiveLimits(runs_per_day=50)
    granted, refused = [], []

    def go() -> None:
        try:
            limits.claim_run()
            granted.append(1)
        except LiveUnavailable as exc:
            assert exc.code == "no_runs_today"
            refused.append(1)
    threads = [threading.Thread(target=go) for _ in range(400)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(granted) == 50 and len(refused) == 350 and limits.runs_left == 0


def test_caps_off_means_unlimited():
    limits = LiveLimits()
    for _ in range(1000):
        limits.claim_run()
    limits.check_span(0, None)
    assert limits.runs_left is None


# ---------- insight logs ----------
@pytest.fixture(scope="module")
def live_msgs(tmp_path_factory):
    c = LiveConfig(fake_llm(), CallBudget(400), "fake", tmp_path_factory.mktemp("insight"))
    return run(Runner(LIB.bundle("comeback-7"), "live", 60.0, paced=False, live=c))


def insights(msgs: list[dict]) -> list[dict]:
    return [m for m in msgs if m["k"] == "log" and m["step"] == "insight"]


def test_insights_use_the_existing_log_shape(live_msgs):
    found = insights(live_msgs)
    assert found and {m["d"]["kind"] for m in found} <= INSIGHT_KINDS
    for m in found:
        assert m["agent"] == "facts" and m["m"] is None and m["msg"] and m["at"] <= m["t"]
        assert m["d"]["ev"] and all(isinstance(i, int) for i in m["d"]["ev"])


def test_a_goal_swings_the_win_probability_and_the_numbers_are_the_engines(live_msgs):
    swings = [m for m in insights(live_msgs) if m["d"]["kind"] == "wp_swing"]
    assert swings
    b = LIB.bundle("comeback-7")
    for m in swings:
        d = m["d"]
        idx = next(i for i, e in enumerate(b.events) if e.i == d["ev"][0])
        i = 0 if d["side"] == "H" else 2
        was, now = (round(100 * FactEngineAt(b, idx + k).win_probs()[i]) for k in (0, 1))
        assert (d["before"], d["after"]) == (was, now) and abs(now - was) >= SWING_POINTS and d["delta"] == now - was
        assert f"{was}%" in m["msg"] and f"{now}%" in m["msg"]
    goal_evs = {e.i for e in b.events if e.type == EventType.SHOT and e.outcome == "goal"}
    assert goal_evs & {m["d"]["ev"][0] for m in swings}


def FactEngineAt(bundle, n: int) -> FactEngine:
    """The engine after the first n events."""
    eng = FactEngine(bundle.meta)
    for ev in bundle.events[:n]:
        eng.ingest(ev)
    return eng


def test_no_swing_is_reported_in_the_first_minutes_unless_a_goal_or_red_card_caused_it(live_msgs, tmp_path):
    b = LIB.bundle("unlucky-7")  # an early shot makes the win probability jump here: real engine output, but noise
    msgs = run(Runner(b, "live", 60.0, paced=False, live=cfg(tmp_path)))
    assert not [m for m in insights(msgs) if m["d"]["kind"] == "wp_swing" and m["at"] < MIN_SWING_T]


def test_insights_are_rare_and_never_repeat(live_msgs):
    found = insights(live_msgs)
    keys = [(m["d"]["kind"], tuple(m["d"]["ev"])) for m in found]
    assert len(keys) == len(set(keys)) and len({m["msg"] for m in found}) == len(found)
    for m in found:
        in_minute = [x for x in found if m["at"] - 60 < x["at"] <= m["at"]]
        assert len(in_minute) <= MAX_PER_MINUTE


def test_insights_see_no_future(tmp_path):
    full_cfg, cut_cfg = cfg(tmp_path), cfg(tmp_path)
    b = LIB.bundle("comeback-7")
    goal = goal_times(b)[0]
    full = insights(run(Runner(b, "live", 60.0, paced=False, live=full_cfg)))
    cut = insights(run(Runner(b, "live", 60.0, paced=False, live=cut_cfg, start=0.0, until=goal + 1)))
    assert cut and all(m["at"] <= goal + 1 for m in cut)
    assert cut == [m for m in full if m["at"] <= goal + 1]  # a run that stops here says exactly what the long run said by then
    assert not [m for m in cut if m["at"] > goal + 1]


def test_a_resumed_run_does_not_report_the_catch_up_stretch(tmp_path):
    b = LIB.bundle("comeback-7")
    goal = goal_times(b)[0]
    msgs = run(Runner(b, "live", 60.0, paced=False, live=cfg(tmp_path), start=goal + 5, until=goal + 120))
    assert all(m["at"] >= goal + 5 for m in insights(msgs))


def test_replay_streams_have_no_insights_and_insights_never_change_the_lines(tmp_path, monkeypatch):
    """Two live runs, with the insight feed on and off. The first version of this test took the shared `live_msgs` run and compared it with a fresh one:
    the model call of a live run is timed on the wall clock, `latency x speed` moves the moment its analysis is ready, and under a loaded machine
    (the full suite) the two runs saw different latencies, so a `say` or `voice` message differed by a few hundredths of a second. The clock of the
    call is pinned here, so the only difference left is the insight feed."""
    replay = run(Runner(LIB.bundle("comeback-7"), "replay", 30.0, paced=False))
    assert not insights(replay)
    monkeypatch.setattr("matchvoice.commentary.analyst.time", types.SimpleNamespace(perf_counter=lambda: 0.0))  # a model call takes no time
    on = run(Runner(LIB.bundle("comeback-7"), "live", 60.0, paced=False, live=cfg(tmp_path / "on")))
    assert insights(on)
    monkeypatch.setattr(InsightFeed, "observe", lambda *a, **k: [])
    off = run(Runner(LIB.bundle("comeback-7"), "live", 60.0, paced=False, live=cfg(tmp_path / "off")))
    assert not insights(off)
    def keep(msgs):  # frames and lines whole; logs without their wall-clock stamps
        return [(m["agent"], m["step"], m["m"], m["msg"]) if m["k"] == "log" else m
                for m in msgs if m["k"] in ("f", "say", "voice", "end") or (m["k"] == "log" and m["step"] != "insight")]
    # same frames, lines and logs, only the insight logs differ. Two analyst calls run on threads, so the order of
    # their log lines may swap between runs: compare those as sorted lists, and the frames in order.
    a, b = keep(on), keep(off)
    assert [m for m in a if isinstance(m, dict) and m["k"] == "f"] == [m for m in b if isinstance(m, dict) and m["k"] == "f"]
    assert sorted(map(repr, a)) == sorted(map(repr, b))


def test_analyst_from_cannot_reach_back_past_the_run_cap(tmp_path):
    """A fresh id has no cache: resuming moments from kick-off would start model calls for the whole match before start."""
    with TestClient(create_app(live=cfg(tmp_path, LiveLimits(75, 150)))) as c:
        start, until = 3000, 3070
        far = ws_messages(c, f"match=comeback-4243&mode=live&start={start}&until={until}&speed=600&analyst_from=0")
        assert far[0]["code"] == "bad_request" and "analyst_from" in far[0]["message"]
        near = ws_messages(c, f"match=comeback-4243&mode=live&start={start}&until={until}&speed=600&analyst_from={start - 60}")
        assert near[0]["k"] == "hello"
