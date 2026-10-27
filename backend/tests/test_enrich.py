"""Phase 2 of docs/PLAN-DATA.md: event enrichment without tracking (DATA-MODEL 3.3, 3.4, 4.1 to 4.5).

Rules are tested on small hand-made event lists (exact, no luck) and the gates on real matches."""
import copy
import hashlib
import math
import random
from pathlib import Path

import orjson
import pytest

from matchvoice.config import ROOT
from matchvoice.schema import Event, EventType, MatchMeta, Role
from matchvoice.sim.arcs import ARCS
from matchvoice.sim.engine import Sim
from matchvoice.sim.micro import enrich as E
from matchvoice.sim.micro.__main__ import DEMO, write_enriched
from matchvoice.sim.micro.report import INSERT_WINDOW, arrival_bounds, measure

DATA = ROOT / "data" / "matches"
T = EventType


@pytest.fixture(scope="module")
def runs():
    out = {}
    for mid in DEMO:
        arc, seed = mid.rsplit("-", 1)
        meta, events, _ = Sim(arc, int(seed)).run()
        out[mid] = (meta, events, E.enrich(meta, events))
    return out


@pytest.fixture(scope="module")
def many():
    """Twelve seeds of every arc, for invariants that must hold everywhere."""
    out = {}
    for arc in ARCS:
        for seed in range(1, 13):
            meta, events, _ = Sim(arc, seed).run()
            out[(arc, seed)] = (meta, events, E.enrich(meta, events))
    return out


@pytest.fixture(scope="module")
def meta() -> MatchMeta:
    return Sim("comeback", 7).run()[0]


@pytest.fixture
def ctx(meta):
    return E.Context(meta, [])


class Fixed:
    """A random source that always returns the same number."""

    def __init__(self, v: float):
        self.v = v

    def random(self) -> float:
        return self.v

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self.v

    def gauss(self, mu: float, sigma: float) -> float:
        return mu


# ---------- hand-made events ----------

def ev(i: int, t: float, typ: EventType, player: str = "H10", team: str = "H", x: float = 50.0, y: float = 34.0, **kw) -> Event:
    return Event(i=i, t=t, period=1, clock="1", type=typ, team=team, player=player, x=x, y=y, **kw)


def pas(i: int, t: float, player: str, x: float, y: float, ex: float, ey: float, receiver: str | None = None, kmh: float = 72.0,
        team: str = "H", **kw) -> Event:
    return ev(i, t, T.PASS, player, team, x, y, end_x=ex, end_y=ey, length=round(math.hypot(ex - x, ey - y), 1), ball_speed=kmh,
              outcome="complete" if receiver else "incomplete", receiver=receiver, **kw)


def shot(i: int, t: float, player: str, x: float, y: float, outcome: str = "goal", end_y: float = 34.0, team: str = "H", **kw) -> Event:
    return ev(i, t, T.SHOT, player, team, x, y, end_x=105.0 if team == "H" else 0.0, end_y=end_y, outcome=outcome, xg=0.2,
              shot_speed=100.0, body_part="foot", keeper="A1", **kw)


def kickoff(i: int = 0, player: str = "H10") -> Event:
    return ev(i, 0.0, T.KICKOFF, player, "H", 52.5, 34.0)


def end(i: int, t: float) -> Event:
    return ev(i, t, T.PERIOD_END, None, "H", 50.0, 34.0, outcome="full_time")


def rows_of(meta: MatchMeta, events: list[Event]) -> dict[int, dict]:
    return {r["eid"]: r for r in E.enrich(meta, events).rows}


def act(event: Event, **kw) -> E.Act:
    a = E._act_of(event)
    for k, v in kw.items():
        setattr(a, k, v)
    return a


# ---------- ids, order, determinism ----------

def test_eid_scheme_unique_and_increasing(many):
    for meta, events, res in many.values():
        eids = [r["eid"] for r in res.rows]
        assert eids == sorted(set(eids))
        assert all(r["eid"] == 16 * r["i"] + r["k"] and 0 <= r["k"] <= 15 for r in res.rows)
        assert all(r["k"] == 0 for r in res.rows if r["type"] in ("shot", "foul", "interception"))
        assert res.stats.overflow == 0


def test_time_never_goes_backwards_along_eid(many):
    for meta, events, res in many.values():
        ts = [r["t"] for r in res.rows]
        assert all(b >= a - 1e-9 for a, b in zip(ts, ts[1:]))


def test_every_row_sits_in_the_gap_after_its_event(many):
    for meta, events, res in many.values():
        for r in res.rows:
            assert events[r["i"]].t - 1e-9 <= r["t"]
            if r["i"] + 1 < len(events):
                assert r["t"] <= events[r["i"] + 1].t + 1e-9


def test_same_input_same_rows(runs):
    meta, events, res = runs["comeback-135"]
    again = E.enrich(copy.deepcopy(meta), copy.deepcopy(events))
    assert orjson.dumps(again.rows) == orjson.dumps(res.rows)


def test_window_gives_the_same_rows_and_eids_as_the_full_run(runs):
    meta, events, res = runs["comeback-135"]
    for t0, t1 in [(4379.0, 4402.0), (0.0, 120.0), (2650.0, 2900.0), (5700.0, 99999.0)]:
        win = E.enrich(meta, events, t0, t1)
        want = [r for r in res.rows if t0 <= r["t"] <= t1]
        assert orjson.dumps(win.rows) == orjson.dumps(want)
        assert win.stats.segments < res.stats.segments or t1 > 5000


def test_a_segment_depends_only_on_itself(runs):
    meta, events, res = runs["red_card-7"]
    ctx = E.Context(meta, events)
    starts = E.segment_starts(events)
    lo, hi = starts[20], starts[21]
    solo = E.enrich_segment(ctx, E.Stats(), lo, hi)
    assert orjson.dumps(solo) == orjson.dumps([r for r in res.rows if lo <= r["i"] < hi])


def test_segments_start_at_every_restart(runs):
    meta, events, _ = runs["comeback-7"]
    starts = E.segment_starts(events)
    assert starts[0] == 0
    for i in starts[1:]:
        assert events[i].type is T.KICKOFF or events[i].set_piece in ("throw_in", "goal_kick", "free_kick", "corner")
    restarts = [e.i for e in events if e.type is T.KICKOFF or e.set_piece in ("throw_in", "goal_kick", "free_kick", "corner")]
    assert starts == restarts


def test_enrichment_does_not_touch_the_skeleton_or_the_profiles():
    for arc in ARCS:
        meta, events, truth = Sim(arc, 3).run()
        before = (meta.model_dump_json(), [e.model_dump_json() for e in events])
        E.enrich(meta, events)
        assert (meta.model_dump_json(), [e.model_dump_json() for e in events]) == before


def test_demo_data_is_what_the_code_writes(tmp_path):
    for mid in DEMO:
        path, _ = write_enriched(mid, tmp_path)
        assert path.read_bytes() == (DATA / mid / "enriched.jsonl").read_bytes(), mid


def test_skeleton_files_of_the_demo_matches_are_unchanged():
    golden = {  # same values as test_profile.GOLDEN
        "comeback-7": "58d68e06f5ad3de5d9356b94a47aeb43b5e1f8dc00a2223068b44d6b9acf6b41",
        "red_card-7": "4eec489e407210f9402c9c9888a23073e47ab4a1223acd6ae8360c6d6e620645",
        "unlucky-7": "b0421c0b3a6498eed1f0b09331cac4c4d1ef4183271d8fb81aabfc0e82586f6b",
        "red_card-11": "4b91c137e20388c7b9c9937e675150fde5d13a8391a7c714993815cd5e7bcaa6",
    }
    for mid, want in golden.items():
        assert hashlib.sha256((DATA / mid / "events.jsonl").read_bytes()).hexdigest() == want


def test_segment_stream_is_named_and_not_the_simulations(runs):
    # a changed seed in the name changes the rows; the simulation's own generator is never drawn from (the skeleton hashes prove it)
    meta, events, res = runs["comeback-7"]
    other = meta.model_copy(update={"seed": 8})
    assert orjson.dumps(E.enrich(other, events).rows) != orjson.dumps(res.rows)


# ---------- arrival retiming (3.3) ----------

def test_arrival_inside_the_bounds_everywhere(many):
    for meta, events, res in many.values():
        n, bad = arrival_bounds(events, res.rows)
        assert n > 1000 and bad == 0


def test_arrival_flagged_lands_0_25_to_0_55_before_the_next_action():
    rng = random.Random(1)
    for _ in range(200):
        t_arr, sq = E._arrival(rng, 1.0, 8.0, 5.0, flagged=True)
        assert not sq and 5.0 - 0.55 - 1e-9 <= t_arr <= 5.0 - 0.25 + 1e-9


def test_arrival_flagged_but_impossible_falls_back_to_the_physics():
    rng = random.Random(2)
    t_arr, _ = E._arrival(rng, 1.0, 2.0, 5.0, flagged=True)  # the ball cannot hang until 4.5
    assert 1.0 <= t_arr <= 2.0


def test_arrival_not_flagged_stays_clear_of_the_first_time_line():
    rng = random.Random(3)
    for _ in range(200):
        t_arr, _ = E._arrival(rng, 1.0, 8.0, 5.0, flagged=False)
        assert 5.0 - t_arr >= 0.6 and t_arr >= 1.0


def test_arrival_forced_first_time_when_the_gap_is_small():
    rng = random.Random(4)
    t_arr, sq = E._arrival(rng, 4.6, 10.0, 5.0, flagged=False)
    assert not sq and 4.6 <= t_arr <= 4.75 and 5.0 - t_arr < 0.6


def test_arrival_squeezed_is_reported():
    t_arr, sq = E._arrival(random.Random(5), 4.9, 10.0, 5.0, flagged=False)
    assert sq and t_arr == 4.9


def test_flight_limits_per_height():
    base = dict(kind="pass", ev=None, before=0, anchor=0, team="H", period=1, actor="H1", x0=0, y0=0, x1=40, y1=0, t=10.0, flight=2.0)
    ground = E.Act(height="ground", **base)
    assert E._hi_phys(ground) == pytest.approx(10.0 + 40 / 8.0)  # slows to an average of 8 m/s
    lofted = E.Act(height="lofted", **base)
    assert E._hi_phys(lofted) == pytest.approx(10.0 + min(3.8, 40 / 5.0))
    driven = E.Act(height="driven", **base)
    assert E._hi_phys(driven) == pytest.approx(10.0 + 2.5)
    short = E.Act(height="lofted", **{**base, "x1": 12, "flight": 0.6})
    assert E._hi_phys(short) == pytest.approx(10.0 + 12 / 5.0)  # a short lofted ball does not hang for 3.8 s
    assert E.MAX_HANG_S == pytest.approx(3.8)


def test_first_time_chance_per_next_action(ctx):
    cross = act(pas(0, 0, "H1", 90, 5, 98, 30, "H2"), ptype="cross")
    head = act(shot(1, 3, "H2", 98, 30).model_copy(update={"body_part": "head"}))
    assert E._p_first(head, cross) == 1.0  # a header from a cross is always first time when physics allow
    assert E._p_first(head, act(pas(0, 0, "H1", 50, 30, 60, 30, "H2"), ptype="short")) == E.P_FIRST["shot"]
    assert E._p_first(act(pas(2, 3, "H2", 60, 30, 70, 30, "H3")), cross) == E.P_FIRST["pass"]
    assert E._p_first(act(ev(3, 3, T.CARRY, "H2", x=60, y=30, end_x=66, end_y=30, length=6.0, speed=18.0)), cross) == 0.0
    assert E._p_first(None, cross) == 0.0
    assert 0.15 <= E.P_FIRST["pass"] <= 0.25 and 0.15 <= E.P_FIRST["shot"] <= 0.25


def test_first_time_flag_is_the_gap_between_receipt_and_next_action(many):
    n_ft = n_slow = 0
    for meta, events, res in many.values():
        rows = res.rows
        last_receipt: dict[str, dict] = {}
        for r in rows:
            if r["type"] == "receipt":
                last_receipt[r["player"]] = r
            elif r["type"] in ("pass", "shot") and ("player" in r or r["k"] == 0):
                actor = r.get("player") or events[r["i"]].player
                rc = last_receipt.pop(actor, None)
                if rc is None:
                    assert not r["first_time"]
                    continue
                inbetween = [x for x in rows if rc["eid"] < x["eid"] < r["eid"] and x["type"] == "carry" and
                             (x.get("player") or events[x["i"]].player) == actor]
                if inbetween:
                    assert not r["first_time"]
                    continue
                assert r["first_time"] == (r["t"] - rc["t"] < E.FIRST_TIME_S), (r["eid"], r["t"] - rc["t"])
                n_ft += r["first_time"]
                n_slow += not r["first_time"]
    assert n_ft > 20 and n_slow > 2000


def test_first_time_never_for_the_first_action_of_a_segment(many):
    for meta, events, res in many.values():
        firsts = {e.i for e in events if e.type is T.KICKOFF or e.set_piece in ("throw_in", "goal_kick", "free_kick", "corner")}
        for r in res.rows:
            if r["k"] == 0 and r["i"] in firsts and r["type"] in ("pass", "shot"):
                assert not r["first_time"]


# ---------- pass type and height (4.2) ----------

@pytest.fixture
def tctx(meta):
    c = E.Context(meta, [])
    c.opp_line_ax = lambda team, ax0, t: 70.0  # the opponent's last line at 70 m
    return c


def ptype(ctx, event, first_time=False, events=None, **kw):
    if events is not None:
        ctx.events = events
    a = act(event, **kw)
    return E._pass_type(ctx, 0, a, first_time)


def test_set_piece_passes_take_the_set_piece_name_first(tctx):
    for sp in ("corner", "free_kick", "throw_in", "goal_kick"):
        # these would also be crosses or switches by geometry; the set piece wins
        assert ptype(tctx, pas(0, 0, "H1", 80, 2, 96, 30, "H2", set_piece=sp)) == sp


def test_first_pass_after_a_kickoff_is_a_kickoff_pass(tctx):
    assert ptype(tctx, pas(1, 0, "H10", 52.5, 34, 60, 30, "H9"), after_kickoff=True) == "kickoff"


def test_cross(tctx):
    assert ptype(tctx, pas(0, 0, "H1", 80, 5, 95, 30, "H2")) == "cross"
    assert ptype(tctx, pas(0, 0, "H1", 80, 64, 95, 38, "H2")) == "cross"  # the other flank
    assert ptype(tctx, pas(0, 0, "H1", 65, 5, 95, 30, "H2")) != "cross"  # starts before x 70
    assert ptype(tctx, pas(0, 0, "H1", 80, 20, 95, 30, "H2")) != "cross"  # starts inside the box width
    assert ptype(tctx, pas(0, 0, "H1", 80, 5, 85, 30, "H2")) != "cross"  # ends outside the box


def test_cross_needs_a_length_of_15_m(tctx):
    # a tap from the wide channel into the box corner is not a cross (4.2): it was one at any length before
    assert ptype(tctx, pas(0, 0, "H1", 85, 13.0, 85.5, 13.8, "H2")) != "cross"  # 0.9 m
    assert ptype(tctx, pas(0, 0, "H1", 85, 13.0, 90, 16.0, "H2")) != "cross"  # 5.8 m, ends in the box
    assert ptype(tctx, pas(0, 0, "H1", 85, 13.0, 95, 24.0, "H2")) not in ("cross", "lay_off")  # 14.9 m
    assert ptype(tctx, pas(0, 0, "H1", 85, 13.0, 95, 25.0, "H2")) == "cross"  # 15.6 m
    assert E.CROSS_MIN_LEN_M == 15.0


def test_cut_back(tctx):
    assert ptype(tctx, pas(0, 0, "H1", 96, 18, 88, 34, "H2")) == "cut_back"
    assert ptype(tctx, pas(0, 0, "H1", 96, 30, 88, 34, "H2")) != "cut_back"  # in front of the six-yard box
    assert ptype(tctx, pas(0, 0, "H1", 96, 18, 100, 34, "H2")) != "cut_back"  # not backwards


def test_switch(tctx):
    assert ptype(tctx, pas(0, 0, "H1", 50, 5, 52, 48, "H2")) == "switch"
    assert ptype(tctx, pas(0, 0, "H1", 50, 5, 52, 44, "H2")) != "switch"  # 39 m across
    assert ptype(tctx, pas(0, 0, "H1", 50, 5, 52, 46, "H2", kmh=72.0)) == "switch"


def test_through_ball_needs_the_end_beyond_the_last_line(tctx):
    # line at 70 m; the end must be 10 m past it and the pass at least 40 m long
    assert ptype(tctx, pas(0, 0, "H1", 35, 34, 82, 34, "H2")) == "through"
    assert ptype(tctx, pas(0, 0, "H1", 35, 34, 79, 34, "H2")) != "through"  # 9 m past the line
    assert ptype(tctx, pas(0, 0, "H1", 50, 34, 82, 34, "H2")) != "through"  # past the line, but only 32 m long
    assert ptype(tctx, pas(0, 0, "H1", 50, 34, 75, 34, "H2")) == "short"  # the old rule called this one through
    assert ptype(tctx, pas(0, 0, "H1", 35, 34, 69, 34, "H2")) != "through"  # stops short of the line
    assert ptype(tctx, pas(0, 0, "H1", 72, 34, 85, 34, "H2")) != "through"  # played from beyond the line
    assert ptype(tctx, pas(0, 0, "H1", 80, 34, 60, 34, "H2")) != "through"  # backwards


def test_through_ball_line_comes_from_the_opponents_plan(meta):
    c = E.Context(meta, [])
    line = c.opp_line_ax("H", 50.0, 10.0)
    plan = meta.teams["A"].tactics
    assert line == pytest.approx(105 - (plan.line_height + 0.25 * ((105 - 50.0) - 52.5)))
    assert c.opp_line_ax("A", 50.0, 10.0) == pytest.approx(
        105 - (meta.teams["H"].tactics.line_height + 0.25 * ((105 - 50.0) - 52.5)))


def test_through_ball_line_follows_the_posture(meta):
    # after a shift the plan in force changes the line (here: the home side chases from the 61st minute)
    shifts = [s for s in meta.teams["H"].postures if s.posture == "chase"]
    assert shifts
    c = E.Context(meta, [])
    before = c.opp_line_ax("A", 50.0, 10.0)
    after = c.opp_line_ax("A", 50.0, shifts[0].t + 1)
    assert after != before


def test_clearance_after_winning_the_ball_or_from_the_own_box(tctx):
    win = ev(0, 99.5, T.INTERCEPTION, "H3", x=20, y=30)
    p = pas(1, 100.0, "H3", 20, 30, 54, 40, "H4")  # 35.4 m
    assert ptype(tctx, p, events=[win, p]) == "clearance"
    late = ev(0, 90.0, T.INTERCEPTION, "H3", x=20, y=30)  # more than 2 s ago
    assert ptype(tctx, p, events=[late, p]) != "clearance"
    far = ev(0, 99.5, T.INTERCEPTION, "H3", x=30, y=30)  # not within 3 m
    assert ptype(tctx, p, events=[far, p]) != "clearance"
    short = pas(1, 100.0, "H3", 20, 30, 40, 36, "H4")  # 20.9 m
    assert ptype(tctx, short, events=[win, short]) != "clearance"
    box = pas(1, 100.0, "H3", 10, 34, 45, 40, "H4", under_pressure=True)  # a defender in the own box under pressure
    assert ptype(tctx, box, events=[box]) == "clearance"
    calm = pas(1, 100.0, "H3", 10, 34, 45, 40, "H4")
    assert ptype(tctx, calm, events=[calm]) != "clearance"
    mid = pas(1, 100.0, "H7", 10, 34, 45, 40, "H4", under_pressure=True)  # H7 is a midfielder
    assert ptype(tctx, mid, events=[mid]) != "clearance"


def test_back_pass(tctx):
    assert ptype(tctx, pas(0, 0, "H1", 60, 34, 50, 34, "H2")) == "back"
    assert ptype(tctx, pas(0, 0, "H1", 60, 34, 56.9, 34, "H2")) == "back"  # more than 3 m back
    assert ptype(tctx, pas(0, 0, "H1", 60, 34, 57, 34, "H2")) == "short"  # exactly 3 m is not


def test_lay_off_needs_a_first_time_touch(tctx):
    p = pas(0, 0, "H1", 60, 34, 66, 34, "H2")
    assert ptype(tctx, p, first_time=True) == "lay_off"
    assert ptype(tctx, p, first_time=False) == "short"
    assert ptype(tctx, pas(0, 0, "H1", 50, 34, 62, 34, "H2"), first_time=True) == "short"  # 12 m


def test_long_and_short_by_length(tctx):
    assert ptype(tctx, pas(0, 0, "H1", 20, 34, 52, 34, "H2")) == "long"  # 32 m
    assert ptype(tctx, pas(0, 0, "H1", 20, 34, 51.9, 34, "H2")) == "short"
    assert ptype(tctx, pas(0, 0, "H1", 40, 34, 55, 38, "H2")) == "short"


def test_type_priority_cross_before_through_before_back(tctx):
    # a wide ball into the box beyond the line is a cross, not a through ball
    assert ptype(tctx, pas(0, 0, "H1", 80, 5, 95, 30, "H2")) == "cross"
    # a 40 m switch beyond the line is a switch
    assert ptype(tctx, pas(0, 0, "H1", 62, 4, 75, 50, "H2")) == "switch"


def test_height_rules():
    for t in ("cross", "switch", "clearance", "goal_kick", "corner"):
        assert E._height(Fixed(0.99), t, 30.0, 40.0) == "lofted"
    assert E._height(Fixed(0.99), "goal_kick", 20.0, 40.0) == "ground"  # a short goal kick is rolled out (the live scene's; no plain one is this short)
    assert E._height(Fixed(0.99), "short", 25.0, 70.0) == "driven"
    assert E._height(Fixed(0.99), "short", 17.9, 80.0) == "ground"
    assert E._height(Fixed(0.99), "short", 25.0, 69.9) == "ground"
    assert E._height(Fixed(0.99), "free_kick", 10.0, 50.0) == "ground"


def test_long_ball_loft_probability_rises_from_0_3_to_0_8():
    for length, p in [(32, 0.3), (41, 0.55), (50, 0.8), (60, 0.8)]:
        assert E._height(Fixed(p - 0.001), "long", length, 50.0) == "lofted"
        assert E._height(Fixed(p + 0.001), "long", length, 50.0) == "ground"


def test_pass_mix_fields_are_in_their_enums(many):
    for meta, events, res in many.values():
        for r in res.rows:
            if r["type"] == "pass":
                assert r["pass_type"] in {"corner", "free_kick", "throw_in", "goal_kick", "kickoff", "cross", "cut_back", "switch",
                                          "through", "clearance", "back", "lay_off", "long", "short"}
                assert r["height"] in ("ground", "driven", "lofted")
                assert r["body_part"] in ("left_foot", "right_foot", "head", "other")
                assert r["technique"] in ("inswing", "outswing", "straight", "chip")
                assert r["pressure"] == {"under": r["pressure"]["under"]}
                if r["height"] == "lofted" and r["k"] == 0:
                    assert r["pass_type"] in ("cross", "switch", "clearance", "goal_kick", "corner", "long")


def test_pass_type_is_a_function_of_the_pass_not_of_the_row_order(runs):
    meta, events, res = runs["comeback-7"]
    for r in res.rows:
        if r["type"] == "pass" and r["k"] == 0:
            e = events[r["i"]]
            if e.set_piece:
                assert r["pass_type"] == e.set_piece


# ---------- target, foot, technique ----------

def test_target_is_the_receiver_for_completed_passes(runs):
    meta, events, res = runs["comeback-7"]
    by_eid = {r["eid"]: r for r in res.rows}
    for e in events:
        if e.type is T.PASS and e.outcome == "complete":
            assert by_eid[16 * e.i]["target"] == e.receiver


def test_target_of_an_incomplete_pass_is_a_teammate_on_the_pitch(runs):
    meta, events, res = runs["red_card-7"]
    by_eid = {r["eid"]: r for r in res.rows}
    n = 0
    for e in events:
        if e.type is T.PASS and e.outcome != "complete":
            t = by_eid[16 * e.i]["target"]
            assert t[0] == e.team and t != e.player
            n += 1
    assert n > 100


def test_nearest_mate_by_formation_anchor_and_sent_off_players(meta):
    c = E.Context(meta, [])
    slot = c.slots["H"][5]  # a midfielder
    pid, sx, sy = slot[0].id, slot[1], slot[2]
    assert c.nearest_mate("H", 10, sx, sy, exclude="H1") == pid
    assert c.nearest_mate("H", 10, sx, sy, exclude=pid) != pid
    c.red = {pid: 5}
    assert c.nearest_mate("H", 10, sx, sy, exclude="H1") != pid  # sent off at event 5
    assert c.nearest_mate("H", 4, sx, sy, exclude="H1") == pid  # still on at event 4
    gk = c.slots["H"][0]
    assert c.nearest_mate("H", 10, gk[1], gk[2], exclude="H2") == "H1"  # deep in the own area the keeper is an option
    assert c.nearest_mate("H", 10, 40.0, gk[2], exclude="H2") != "H1"


def test_foot_rule(meta):
    c = E.Context(meta, [])
    c.players["H5"] = c.players["H5"].model_copy(update={"foot": "R", "weak_foot": 2})
    c.players["H6"] = c.players["H6"].model_copy(update={"foot": "both", "weak_foot": 5})
    # weak foot probability (5 - 2) * 0.04 = 0.12 when the target is straight ahead or on the strong side
    assert E._foot_for(c, Fixed(0.11), "H5", 0.0) == "left_foot"
    assert E._foot_for(c, Fixed(0.13), "H5", 0.0) == "right_foot"
    assert E._foot_for(c, Fixed(0.11), "H5", 20.0) == "left_foot"
    # reversed when the angle favours the weak foot (8 m or more to the left for a right-footer)
    assert E._foot_for(c, Fixed(0.5), "H5", -8.0) == "left_foot"
    assert E._foot_for(c, Fixed(0.89), "H5", -8.0) == "right_foot"
    assert E._foot_for(c, Fixed(0.5), "H5", -7.9) == "right_foot"
    # two-footed: whichever side the ball goes
    assert E._foot_for(c, Fixed(0.5), "H6", -20.0) == "left_foot"
    assert E._foot_for(c, Fixed(0.5), "H6", 20.0) == "right_foot"


def delivery(meta, foot: str, y0: float, ptype: str = "corner") -> dict:
    c = E.Context(meta, [])
    c.players["H5"] = c.players["H5"].model_copy(update={"foot": foot, "weak_foot": 5 if foot == "both" else 2})
    x0 = 104.5 if ptype == "corner" else 85.0
    a = act(pas(0, 0.0, "H5", x0, y0, 97.0, 34.0, "H6"), ptype=ptype, height="lofted", t_arr=2.0)
    return E._pass_fields(c, Fixed(0.99), a, False)  # 0.99: always the preferred foot


def test_inswing_when_the_foot_is_opposite_to_the_side(meta):
    assert delivery(meta, "R", 0.0)["technique"] == "inswing"  # right foot from the left side
    assert delivery(meta, "R", 68.0)["technique"] == "outswing"
    assert delivery(meta, "L", 0.0)["technique"] == "outswing"
    assert delivery(meta, "L", 68.0)["technique"] == "inswing"
    assert delivery(meta, "R", 0.0)["delivery"] == "inswing"
    assert delivery(meta, "R", 8.0, "cross")["technique"] == "inswing"


def test_corner_target_zone(meta):
    c = E.Context(meta, [])
    def zone(y0, ex, ey):
        a = act(pas(0, 0.0, "H5", 104.5, y0, ex, ey, "H6"), ptype="corner", height="lofted", t_arr=2.0)
        return E._pass_fields(c, Fixed(0.99), a, False)["target_zone"]
    assert zone(0.0, 100.0, 30.0) == "near_post"  # from the left, the near post is on the low-y side
    assert zone(0.0, 100.0, 38.0) == "far_post"
    assert zone(68.0, 100.0, 38.0) == "near_post"
    assert zone(0.0, 100.0, 34.5) == "six_yard"
    assert zone(0.0, 95.0, 34.5) == "penalty_spot"
    assert zone(0.0, 85.0, 34.5) == "edge"


def test_set_piece_fields_on_passes(runs):
    meta, events, res = runs["comeback-135"]
    by_eid = {r["eid"]: r for r in res.rows}
    seen = set()
    for e in events:
        if e.type is not T.PASS or not e.set_piece:
            continue
        r = by_eid[16 * e.i]
        seen.add(e.set_piece)
        ax0, ay0 = E._att(e.team, e.period, e.x, e.y)
        ax1, _ = E._att(e.team, e.period, e.end_x, e.end_y)
        if e.set_piece == "corner":
            assert r["delivery"] in ("inswing", "outswing") and r["delivery"] == r["technique"]
            assert r["target_zone"] in ("near_post", "six_yard", "penalty_spot", "far_post", "edge")
        elif e.set_piece == "free_kick":
            assert r["direct"] is False and r["distance_m"] == pytest.approx(math.hypot(105 - ax0, 34 - ay0), abs=0.06)
        elif e.set_piece == "throw_in":
            assert r["long"] == (e.length > 20)
        else:
            assert r["short"] == (ax1 < 35.0)
    assert seen == {"corner", "free_kick", "throw_in", "goal_kick"}


# ---------- kick rows carry no outcome ----------

RECEIPT_FORBIDDEN = {"hold_s", "first_time", "next_t", "outcome", "assist", "assist_eid"}  # the gap to the next action is a lookahead (0.1)


def test_through_balls_per_team_stay_in_the_4_2_range(runs):
    for mid, (meta, events, res) in runs.items():
        for side in ("H", "A"):
            n = sum(1 for r in res.rows if r["type"] == "pass" and r["team"] == side and r["pass_type"] == "through")
            assert 1 <= n <= 8, (mid, side, n)


def test_kick_rows_carry_no_outcome_data(many):
    forbidden = {"outcome", "assist", "assist_eid", "receiver", "touch", "facing", "hold_s", "pass_eid"}
    for meta, events, res in many.values():
        for r in res.rows:
            if r["type"] == "pass":
                assert not forbidden & set(r), r["eid"]


def test_outcome_fields_only_on_resolution_rows(many):
    for meta, events, res in many.values():
        for r in res.rows:
            if r["type"] == "receipt":
                assert {"touch", "facing", "pass_eid"} <= set(r)
            elif r["type"] not in ("take_on", "shot", "interception"):
                assert "outcome" not in r and "touch" not in r and "facing" not in r
        assert all("assist_eid" in r for r in res.rows if r["type"] == "shot")


def test_t_arr_is_the_only_future_looking_number_on_a_pass(runs):
    # it is the flight time of a ball that is already in the air; nothing else on the row depends on the resolution
    meta, events, res = runs["comeback-135"]
    keys = set()
    for r in res.rows:
        if r["type"] == "pass" and not r.get("implicit"):
            keys |= set(r)
    base = {"eid", "i", "k", "t", "type", "team", "target", "pass_type", "height", "body_part", "technique", "pressure", "first_time",
            "t_arr", "ball_speed", "delivery", "target_zone", "distance_m", "direct", "long", "short"}
    assert keys <= base


# ---------- receipts ----------

def test_one_receipt_for_every_completed_pass_at_its_arrival(runs):
    for mid, (meta, events, res) in runs.items():
        by_eid = {r["eid"]: r for r in res.rows}
        completed = [r for r in res.rows if r["type"] == "pass" and (r["k"] == 0 and events[r["i"]].outcome == "complete" or r.get("implicit"))]
        receipts = [r for r in res.rows if r["type"] == "receipt"]
        assert len(receipts) == len(completed)
        for rc in receipts:
            p = by_eid[rc["pass_eid"]]
            assert rc["t"] == p["t_arr"] and rc["player"] == p["target"] and rc["eid"] > p["eid"]
            assert rc["touch"] in ("control", "chest", "head") and rc["facing"] in ("forward", "side", "own_goal")
            assert not RECEIPT_FORBIDDEN & set(rc), rc["eid"]


def test_receipt_is_at_the_end_point_of_the_pass(runs):
    meta, events, res = runs["comeback-7"]
    by_eid = {r["eid"]: r for r in res.rows}
    for rc in res.rows:
        if rc["type"] == "receipt" and by_eid[rc["pass_eid"]]["k"] == 0:
            e = events[rc["i"]]
            assert (rc["x"], rc["y"]) == (e.end_x, e.end_y)


def test_receipt_pressure_is_unset_until_tracking(runs):
    # the skeleton has no flag for a receiver, and the next action's flag is a lookahead (0.1): the receipt must not copy it
    for meta, events, res in runs.values():
        receipts = [r for r in res.rows if r["type"] == "receipt"]
        assert receipts and all(r["pressure"] == {"under": None} for r in receipts)


def test_receipt_facing_and_under_ignore_the_next_action(ctx):
    inc = act(pas(1, 1.0, "H9", 40.0, 30.0, 52.0, 30.0, "H8"), complete=True, target="H8", ptype="short", height="ground")
    nexts = [act(pas(2, 5.0, "H8", 52.0, 30.0, 60.0, 30.0, "H7", under_pressure=True)),  # forward, under pressure
             act(pas(2, 5.0, "H8", 52.0, 30.0, 40.0, 30.0, "H9")),  # back
             act(ev(2, 5.0, T.TACKLE, "A3", "A", 52.0, 30.0)), None]
    for u in (0.05, 0.4, 0.8, 0.99):
        got = []
        for nxt in nexts:
            inc.nxt = nxt
            r = E._receipt(ctx, Fixed(u), inc)
            got.append((r["facing"], r["pressure"]))
        assert all(g == got[0] for g in got), (u, got)


def test_receipt_facing_does_not_foretell_a_loss(runs):
    # before: 77 percent of the receipts facing the own goal were followed by a loss (3 percent base rate)
    lost = ours = 0
    n_og = lost_og = 0
    for meta, events, res in runs.values():
        for rc in res.rows:
            if rc["type"] != "receipt":
                continue
            nxt = next((x for x in events[rc["i"] + 1:] if x.type in (T.PASS, T.CARRY, T.SHOT, T.TACKLE, T.INTERCEPTION)), None)
            if nxt is None:
                continue
            loss = nxt.team != rc["team"]
            lost += loss
            ours += 1
            if rc["facing"] == "own_goal":
                n_og += 1
                lost_og += loss
    assert n_og > 100 and lost_og / n_og < 3 * lost / ours + 0.02, (n_og, lost_og, lost, ours)


def test_header_into_a_header_is_a_head_touch(runs):
    for meta, events, res in runs.values():
        by_eid = {r["eid"]: r for r in res.rows}
        heads = [r for r in res.rows if r["type"] == "shot" and r["body_part"] == "head" and r["first_time"] and r["assist_eid"]]
        for s in heads:
            rc = next((r for r in res.rows if r["type"] == "receipt" and r["pass_eid"] == s["assist_eid"]), None)
            if rc is not None and rc["player"] == events[s["i"]].player:
                assert rc["touch"] == "head"


# ---------- gap repair (3.4) ----------

def build(meta, *events):
    return rows_of(meta, [*events])


def base_chain(second: Event, t_end: float = 30.0) -> list[Event]:
    return [kickoff(), pas(1, 0.1, "H10", 52.5, 34.0, 70.0, 30.0, "H9"), second, end(3, t_end)]


def test_implicit_pass_when_the_actor_changes(meta):
    rows = build(meta, *base_chain(shot(2, 5.0, "H11", 80.0, 36.0)))
    pass_row = rows[16 * 1]
    receipt = rows[16 * 1 + 1]
    imp = rows[16 * 1 + 2]
    assert receipt["type"] == "receipt" and receipt["player"] == "H9"
    assert imp["type"] == "pass" and imp["implicit"] is True and imp["player"] == "H9" and imp["target"] == "H11"
    assert (imp["x"], imp["y"], imp["end_x"], imp["end_y"]) == (70.0, 30.0, 80.0, 36.0)
    assert imp["length"] == pytest.approx(math.hypot(10, 6), abs=0.05)
    assert rows[16 * 1 + 3]["type"] == "receipt" and rows[16 * 1 + 3]["player"] == "H11"
    assert receipt["t"] < imp["t"] < imp["t_arr"] <= 5.0 - 0.25 + 1e-9
    assert rows[16 * 2]["assist_eid"] == imp["eid"] and rows[16 * 1 + 3]["pass_eid"] == imp["eid"]
    assert pass_row["target"] == "H9"


def test_implicit_carry_when_the_ball_moved_over_2_m(meta):
    rows = build(meta, *base_chain(shot(2, 5.0, "H9", 76.0, 30.0)))
    car = rows[16 * 1 + 2]
    assert car["type"] == "carry" and car["implicit"] is True and car["player"] == "H9"
    assert car["distance_m"] == 6.0 and car["progress_m"] == 6.0 and car["into_box"] is False
    assert car["t"] + car["duration_s"] <= 5.0 + 1e-9 and car["t"] >= rows[16 * 1 + 1]["t"]
    assert rows[16 * 2]["assist_eid"] == 16 * 1  # the pass before the carry still set it up
    assert rows[16 * 2]["first_time"] is False


def test_no_repair_when_the_ball_moved_2_m_or_less(meta):
    rows = build(meta, *base_chain(shot(2, 5.0, "H9", 71.9, 30.0)))
    assert not any(r.get("implicit") for r in rows.values())
    rows = build(meta, *base_chain(shot(2, 5.0, "H9", 72.1, 30.0)))
    assert sum(bool(r.get("implicit")) for r in rows.values()) == 1


def test_implicit_carry_into_the_box_is_marked(meta):
    rows = build(meta, *base_chain(shot(2, 5.0, "H9", 92.0, 34.0)))
    car = next(r for r in rows.values() if r.get("implicit"))
    assert car["type"] == "carry" and car["into_box"] is True


def test_no_repair_across_a_restart(meta):
    # a restart begins a new segment: the throw-in taker is not "the previous holder's team-mate with a jump"
    events = [kickoff(), pas(1, 0.1, "H10", 52.5, 34.0, 70.0, 30.0, "H9"), ev(2, 4.0, T.FOUL, "A3", "A", 70.0, 30.0, outcome="free_kick"),
              pas(3, 20.0, "H5", 60.0, 34.0, 70.0, 34.0, "H6", set_piece="free_kick"), end(4, 40.0)]
    assert not any(r.get("implicit") for r in rows_of(meta, events).values())


def test_jump_that_leaves_no_time_is_listed_not_invented(meta):
    events = base_chain(shot(2, 2.3, "H11", 104.0, 36.0))
    res = E.enrich(meta, events)
    assert not any(r.get("implicit") for r in res.rows)
    assert res.stats.unrepaired == [{"before": 2, "kind": "ipass", "length_m": pytest.approx(34.5, abs=0.1), "available_s": pytest.approx(1.3, abs=0.1)}]
    shot_row = next(r for r in res.rows if r["type"] == "shot")
    assert shot_row["assist_eid"] is None and shot_row["first_time"] is False


def test_carry_that_cannot_be_run_is_listed(meta):
    res = E.enrich(meta, base_chain(shot(2, 3.0, "H9", 102.0, 30.0)))  # 32 m in under 2 s
    assert [u["kind"] for u in res.stats.unrepaired] == ["icarry"]
    assert not any(r.get("implicit") for r in res.rows)


def test_chain_times_stay_inside_the_gap(many):
    for meta, events, res in many.values():
        for r in res.rows:
            if r.get("implicit"):
                nxt = events[r["i"] + 1]
                assert r["t"] < nxt.t
                if r["type"] == "pass":
                    assert r["t_arr"] <= nxt.t - E.MIN_GAP_S + 1e-6


def test_repair_count_of_the_insert_match(runs):
    meta, events, res = runs["comeback-135"]
    s = res.stats
    assert (s.implicit_passes, s.implicit_carries, len(s.unrepaired)) == (3, 0, 0)  # DATA-MODEL 3.4: 3 actor changes without a pass


# ---------- the insert (comeback-135, goal at 71') ----------

def test_insert_build_up(runs):
    meta, events, res = runs["comeback-135"]
    by_eid = {r["eid"]: r for r in res.rows}
    sw, lg, imp, rc3, sh = by_eid[16 * 1481], by_eid[16 * 1482], by_eid[23714], by_eid[23715], by_eid[16 * 1483]
    assert sw["pass_type"] == "switch" and sw["height"] == "lofted" and events[1481].length == 53.6
    assert abs(events[1481].end_y - events[1481].y) == pytest.approx(49.5, abs=0.05)
    assert lg["pass_type"] == "long" and events[1482].length == 41.1
    assert imp["implicit"] and imp["player"] == "H7" and imp["target"] == "H10" and imp["length"] == 18.3
    assert imp["pass_type"] == "short"  # 1.5 m past A's planned last line (78.5 m) and 18 m long: under the 10 m / 40 m through rule it is short
    assert rc3["player"] == "H10" and rc3["pass_eid"] == 23714
    assert sh["assist_eid"] == 23714
    assert by_eid[23713]["player"] == "H7" and by_eid[16 * 1481 + 1]["player"] == "H4"


def test_insert_has_seven_touches_and_the_interception_is_a_contested_ball(runs):
    meta, events, res = runs["comeback-135"]
    lo, hi = INSERT_WINDOW
    touches = [r for r in res.rows if r["type"] in ("pass", "carry", "shot", "receipt") and lo <= r["t"] <= hi]
    assert [(r["type"], r["eid"]) for r in touches] == [
        ("pass", 16 * 1481), ("receipt", 16 * 1481 + 1), ("pass", 16 * 1482), ("receipt", 23713), ("pass", 23714),
        ("receipt", 23715), ("shot", 16 * 1483)]
    ic = next(r for r in res.rows if r["eid"] == 16 * 1479)
    assert ic["type"] == "interception" and ic["pass_eid"] == 16 * 1478 and ic["contest_s"] > 0.25


# ---------- shots (4.4) ----------

def shot_act(meta, event: Event, **kw):
    c = E.Context(meta, [])
    a = act(event, **kw)
    return c, a


def test_shot_placement_across_the_goal(meta):
    for team, end_y, want_y in [("H", 31.0, 0.66), ("H", 37.0, 6.66), ("A", 31.0, 6.66), ("A", 37.0, 0.66)]:
        e = shot(1, 5.0, "H9" if team == "H" else "A9", 90.0 if team == "H" else 15.0, 34.0, end_y=end_y, team=team)
        c, a = shot_act(meta, e)
        out = E._shot_fields(c, Fixed(0.5), a)
        assert out["placement"]["y"] == pytest.approx(want_y, abs=0.01), (team, end_y)


def test_shot_placement_zone_and_which_shots_have_one(meta):
    def f(outcome, end_y=34.0, rng=0.5):
        c, a = shot_act(meta, shot(1, 5.0, "H9", 90.0, 34.0, outcome=outcome, end_y=end_y))
        return E._shot_fields(c, Fixed(rng), a)
    assert f("goal", 30.4, 0.0)["placement"] == {"y": 0.15, "z": 0.15, "zone": "low_left"}  # clamped inside the posts
    assert f("goal", 36.0, 1.0)["placement"]["zone"] == "high_right"
    assert f("goal", 34.0, 0.5)["placement"]["zone"] in ("low_centre", "high_centre")
    assert f("saved", 34.0, 0.5)["placement"]["z"] == 0.9  # saved shots are biased low
    assert f("post", 20.0)["placement"]["y"] == 0.0 and f("post", 50.0)["placement"]["y"] == 7.32
    assert "placement" not in f("off_target") and "placement" not in f("blocked")
    for o in ("goal", "saved", "post"):
        p = f(o, 34.0, 0.99)["placement"]
        assert 0.0 <= p["y"] <= 7.32 and 0.0 <= p["z"] <= 2.44


def test_shot_body_part_and_technique(meta):
    c = E.Context(meta, [])
    c.players["H9"] = c.players["H9"].model_copy(update={"foot": "R", "weak_foot": 2})
    lofted = act(pas(0, 0, "H1", 70, 5, 90, 34, "H9"), height="lofted")
    def fields(e: Event, **kw):
        return E._shot_fields(c, Fixed(0.99), act(e, **kw))
    head = shot(1, 5.0, "H9", 90.0, 34.0).model_copy(update={"body_part": "head"})
    assert fields(head)["body_part"] == "head" and fields(head)["technique"] == "header"
    assert fields(shot(1, 5.0, "H9", 90.0, 34.0).model_copy(update={"body_part": "other"}))["body_part"] == "other"
    foot = shot(1, 5.0, "H9", 90.0, 34.0)
    assert fields(foot)["body_part"] == "right_foot" and fields(foot)["technique"] == "placed"
    assert fields(foot, first_time=True, incoming=lofted)["technique"] == "volley"
    assert fields(foot, first_time=True, incoming=act(pas(0, 0, "H1", 70, 5, 90, 34, "H9"), height="ground"))["technique"] == "placed"
    assert fields(foot, incoming=lofted)["technique"] == "placed"  # not first time: no volley
    fast = foot.model_copy(update={"shot_speed": 120.0})
    assert fields(fast)["technique"] == "driven"
    fk = shot(1, 5.0, "H9", 85.0, 34.0, set_piece="free_kick")
    out = fields(fk)
    assert out["direct"] is True and out["distance_m"] == 20.0 and out["technique"] == "driven"  # 0.99: no curl for a non-taker
    c.players["H9"] = c.players["H9"].model_copy(update={"traits": ["set_piece_taker"]})
    assert E._shot_fields(c, Fixed(0.5), act(fk))["technique"] == "curled"
    c.players["H8"] = c.players["H8"].model_copy(update={"role": Role.INVERTED_WINGER, "foot": "R"})
    edge = shot(1, 5.0, "H8", 86.0, 46.0)
    assert E._shot_fields(c, Fixed(0.99), act(edge))["technique"] == "curled"  # 19.2 m out, off centre
    assert E._shot_fields(c, Fixed(0.99), act(shot(1, 5.0, "H8", 99.0, 46.0)))["technique"] != "curled"


def test_assist_rules(meta):
    def assist(shot_t: float, mid_carry: bool = False):
        events = [kickoff(), pas(1, 0.1, "H10", 52.5, 34.0, 70.0, 30.0, "H9")]
        n = 2
        if mid_carry:
            events.append(ev(n, 3.0, T.CARRY, "H9", x=70.0, y=30.0, end_x=76.0, end_y=30.0, length=6.0, speed=18.0))
            n += 1
            x = 76.0
        else:
            x = 70.0
        events += [shot(n, shot_t, "H9", x, 30.0), end(n + 1, shot_t + 30)]
        return rows_of(meta, events)[16 * n]["assist_eid"]
    assert assist(4.0) == 16 * 1
    assert assist(12.0) is None  # the pass arrived at most 2.8 s after the kick, so the shot is more than 8 s later
    assert assist(6.0, mid_carry=True) == 16 * 1  # a carry in between does not hide the pass
    solo = [kickoff(), ev(1, 1.0, T.CARRY, "H10", x=52.5, y=34.0, end_x=60.0, end_y=34.0, length=7.5, speed=18.0),
            shot(2, 4.0, "H10", 60.0, 34.0), end(3, 30.0)]
    assert rows_of(meta, solo)[32]["assist_eid"] is None


def test_first_time_shot_when_forced(meta, monkeypatch):
    monkeypatch.setattr(E, "P_FIRST", {"pass": 1.0, "shot": 1.0})
    events = [kickoff(), pas(1, 0.1, "H10", 52.5, 34.0, 66.0, 34.0, "H9"), shot(2, 2.2, "H9", 66.0, 34.0), end(3, 30.0)]
    rows = rows_of(meta, events)
    assert rows[16 * 2]["first_time"] is True
    rc = rows[16 * 1 + 1]
    assert 2.2 - rc["t"] < 0.6 and "hold_s" not in rc
    events = [kickoff(), pas(1, 0.1, "H10", 52.5, 34.0, 66.0, 34.0, "H9"), shot(2, 6.2, "H9", 66.0, 34.0), end(3, 30.0)]
    assert rows_of(meta, events)[16 * 2]["first_time"] is False  # physics: the ball cannot roll for 6 s


def test_every_shot_row_has_the_fields(many):
    for meta, events, res in many.values():
        for r in res.rows:
            if r["type"] == "shot":
                e = events[r["i"]]
                assert r["body_part"] in ("left_foot", "right_foot", "head", "other") and (r["body_part"] == "head") == (e.body_part == "head")
                assert r["technique"] in ("placed", "driven", "volley", "header", "chip", "curled")
                assert (r["technique"] == "header") == (r["body_part"] == "head")
                assert ("placement" in r) == (e.outcome in ("goal", "saved", "post"))
                assert r["assist_eid"] is None or r["assist_eid"] < r["eid"]
                assert r["pressure"]["under"] == bool(e.under_pressure)


# ---------- pressure flag ----------

def test_every_under_pressure_skeleton_event_has_pressure_under(many):
    n = 0
    for meta, events, res in many.values():
        by_eid = {r["eid"]: r for r in res.rows}
        for e in events:
            if e.under_pressure and e.type in (T.PASS, T.CARRY, T.SHOT):
                assert by_eid[16 * e.i]["pressure"]["under"] is True
                n += 1
            elif e.type in (T.PASS, T.CARRY, T.SHOT):
                assert by_eid[16 * e.i]["pressure"]["under"] is False
    assert n > 500


# ---------- carries, take-ons, fouls, interceptions ----------

def test_skeleton_carry_fields(runs):
    meta, events, res = runs["comeback-7"]
    n = 0
    for r in res.rows:
        if r["type"] == "carry" and not r.get("implicit"):
            e = events[r["i"]]
            ax0, ay0 = E._att(e.team, e.period, e.x, e.y)
            ax1, ay1 = E._att(e.team, e.period, e.end_x, e.end_y)
            assert r["distance_m"] == e.length and r["progress_m"] == pytest.approx(ax1 - ax0, abs=0.06)
            assert r["duration_s"] == pytest.approx(e.length / (e.speed / 3.6), abs=0.006)
            assert r["max_speed"] >= e.speed / 3.6 - 0.006
            assert r["into_box"] == (E._in_box(ax1, ay1) and not E._in_box(ax0, ay0))
            n += 1
    assert n > 200


def test_take_on_lost_follows_a_carry_that_ends_in_a_tackle(meta):
    events = [kickoff(), pas(1, 0.1, "H10", 52.5, 34.0, 70.0, 30.0, "H9"),
              ev(2, 3.0, T.CARRY, "H9", x=70.0, y=30.0, end_x=75.0, end_y=30.0, length=5.0, speed=18.0),
              ev(3, 4.5, T.TACKLE, "A3", "A", 75.0, 30.0, outcome="won"),
              ev(4, 4.5, T.POSSESSION_CHANGE, "A3", "A", 75.0, 30.0, reason="tackle"), end(5, 30.0)]
    rows = rows_of(meta, events)
    to = rows[16 * 3 + 1]
    assert to["type"] == "take_on" and to["outcome"] == "lost" and to["player"] == "H9" and to["defender"] == "A3"
    assert to["team"] == "H" and (to["x"], to["y"]) == (75.0, 30.0) and to["t"] == 4.5
    assert to["style"] in ("pace", "skill", "nutmeg", "cut_inside")


def test_no_take_on_when_the_tackle_follows_a_receipt(meta):
    events = [kickoff(), pas(1, 0.1, "H10", 52.5, 34.0, 70.0, 30.0, "H9"),
              ev(2, 4.5, T.TACKLE, "A3", "A", 70.0, 30.0, outcome="won"),
              ev(3, 4.5, T.POSSESSION_CHANGE, "A3", "A", 70.0, 30.0, reason="tackle"), end(4, 30.0)]
    assert not any(r["type"] == "take_on" for r in rows_of(meta, events).values())


def test_take_on_count_equals_tackles_after_carries(many):
    for meta, events, res in many.values():
        want = 0
        for e in events:
            if e.type is T.TACKLE:
                k = e.i - 1
                while events[k].type is T.PRESSURE:
                    k -= 1
                want += events[k].type is T.CARRY and events[k].team != e.team
        assert sum(r["type"] == "take_on" for r in res.rows) == want


def test_interception_rows_point_at_the_incomplete_pass(runs):
    for meta, events, res in runs.values():
        by_eid = {r["eid"]: r for r in res.rows}
        ics = [r for r in res.rows if r["type"] == "interception"]
        assert len(ics) > 90
        for r in ics:
            p = by_eid[r["pass_eid"]]
            assert p["type"] == "pass" and events[p["i"]].outcome == "incomplete"
            assert r["contest_s"] == pytest.approx(r["t"] - p["t_arr"], abs=0.001) and r["contest_s"] >= 0.25 - 1e-9


def test_foul_rows(runs):
    for meta, events, res in runs.values():
        fouls = [r for r in res.rows if r["type"] == "foul"]
        assert len(fouls) == sum(e.type is T.FOUL for e in events)
        for r in fouls:
            e = events[r["i"]]
            ax, _ = E._att(e.team, e.period, e.x, e.y)
            assert r["foul_type"] in E.FOUL_TYPES
            assert r["zone"] == ("defensive" if ax < 35 else "attacking" if ax > 70 else "middle")


def test_foul_type_depends_on_what_came_before(meta):
    # after a lofted ball: aerial fouls (push, holding, pull); after a carry: trips and late tackles
    kinds = {}
    for label, prior in [("aerial", "lofted"), ("carry", "carry")]:
        counts = {}
        for seed in range(400):
            c = E.Context(meta, [])
            fouler = ev(5, 10.0, T.FOUL, "A4", "A", 60.0, 34.0, outcome="free_kick")
            a = act(pas(3, 5.0, "H5", 40, 34, 60, 34, "H6"), height="lofted" if prior == "lofted" else "ground") if prior == "lofted" else \
                act(ev(3, 5.0, T.CARRY, "H5", x=40, y=34, end_x=46, end_y=34, length=6.0, speed=18.0))
            f = E._foul_fields(c, random.Random(seed), [a], fouler)["foul_type"]
            counts[f] = counts.get(f, 0) + 1
        kinds[label] = counts
    assert kinds["aerial"].get("push", 0) + kinds["aerial"].get("holding", 0) > 0.5 * 400
    assert kinds["carry"].get("trip", 0) + kinds["carry"].get("late_tackle", 0) > 0.5 * 400


# ---------- overflow ----------

def test_overflow_drops_the_lowest_value_first_and_counts(runs, monkeypatch):
    meta, events, _ = runs["comeback-135"]
    monkeypatch.setattr(E, "MAX_SUB", 2)
    res = E.enrich(meta, events)
    assert res.stats.overflow > 0 and all(r["k"] <= 2 for r in res.rows)
    # the chain of the insert needs 3 sub-events (receipt, implicit pass, receipt): the implicit pass is the one that goes
    kept = [r["type"] for r in res.rows if r["i"] == 1482 and r["k"] > 0]
    assert kept == ["receipt", "receipt"]
    assert E.DROP_RANK["receipt"] > E.DROP_RANK["pass"] > E.DROP_RANK["carry"] > E.DROP_RANK["take_on"]


# ---------- gates on the demo matches ----------

def test_touches_per_minute_at_least_24(runs):
    for mid, (meta, events, res) in runs.items():
        m = measure(events, res)
        assert m["touches_per_min"] >= 24.0, (mid, m["touches_per_min"])
        assert m["touches_per_min"] > m["touches_per_min_before"] + 8


def test_report_numbers_are_consistent(runs):
    meta, events, res = runs["comeback-135"]
    m = measure(events, res)
    assert m["rows"] == len(res.rows) and m["arrival_outside"] == 0 and m["under_pressure_missing"] == 0
    assert m["kick_rows_with_outcome"] == 0 and m["insert_touches"] == 7 and m["unique_increasing"] and m["overflow"] == 0
    assert m["first_time_passes"] == sum(r["first_time"] for r in res.rows if r["type"] == "pass")


def test_first_time_share_stays_at_the_measured_physical_ceiling(runs):
    # a guard, not the gate: measured 0.6 to 0.9 percent, the most that steering every feasible pass reaches is about 4 percent
    for meta, events, res in runs.values():
        m = measure(events, res)
        assert 0.2 <= m["first_time_pct"] <= 6.0


@pytest.mark.xfail(strict=True, reason="PLAN-DATA phase 2 gate: 15 to 30 percent first-time passes is not reachable under the 3.3 caps; plan owner decides (CLAUDE.md)")
def test_first_time_gate_15_to_30_percent(runs):
    for mid, (meta, events, res) in runs.items():
        assert 15.0 <= measure(events, res)["first_time_pct"] <= 30.0, mid


def test_crosses_have_a_length_and_stay_in_the_4_2_range(runs):
    for mid, (meta, events, res) in runs.items():
        for r in res.rows:
            if r["type"] == "pass" and r["pass_type"] == "cross":
                length = r["length"] if r.get("implicit") else events[r["i"]].length
                assert length >= E.CROSS_MIN_LEN_M, (mid, r["eid"], length)
        for side in ("H", "A"):
            n = sum(1 for r in res.rows if r["type"] == "pass" and r["team"] == side and r["pass_type"] == "cross")
            assert n <= 25, (mid, side, n)


def test_cli_writes_the_file_and_the_directory_needs_no_meta(tmp_path):
    path, res = write_enriched("comeback-135", tmp_path)
    lines = path.read_bytes().splitlines()
    assert len(lines) == len(res.rows) and orjson.loads(lines[0])["eid"] == res.rows[0]["eid"]
    assert not (tmp_path / "comeback-135" / "meta.json").exists()
    assert (DATA / "comeback-135" / "enriched.jsonl").exists() and not (DATA / "comeback-135" / "meta.json").exists()
