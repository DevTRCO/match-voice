"""Phase 1 of docs/PLAN-DATA.md: team tactics and the posture schedule (DATA-MODEL 2.1 to 2.3)."""
import pytest

from matchvoice.schema import Attrs, Event, EventType, Player, Role, Trait
from matchvoice.sim.arcs import ARCS
from matchvoice.sim.engine import FORMATIONS, Sim
from matchvoice.sim.tactics import (
    PRESS_TRIGGERS, RESTART_FALLBACK_S, SHAPE_IN, SHAPE_OUT, block_of, build_tactics, effective_plan, next_posture,
    plan_at, posture_schedule, superseded, tempo_class_of,
)

SEEDS = range(1, 51)
EXPECTED_SHIFTS = {"comeback": 3, "red_card": 4, "unlucky": 2}


@pytest.fixture(scope="module")
def runs():
    out = {}
    for arc in ARCS:
        for seed in SEEDS:
            sim = Sim(arc, seed)
            meta, events, truth = sim.run()
            out[(arc, seed)] = (sim, meta, events)
    return out


def squad(formation="4-4-2", passing=55, pace=50, roles=None, foot="R") -> list[Player]:
    """Eleven players of a formation with flat attributes; `roles` maps a slot index to a Role."""
    roles = roles or {}
    players = []
    for k, (pos, group, _, _) in enumerate(FORMATIONS[formation]):
        a = Attrs(pace=pace, passing=passing, finishing=50, acceleration=50, dribbling=50, vision=50, defending=50,
                  aerial=50, stamina=50)
        players.append(Player(id=f"H{k + 1}", name=f"P{k}", number=k + 1, pos=pos, group=group, attrs=a, foot=foot,
                              role=roles.get(k, Role.CENTRAL_MIDFIELDER), traits=[], captain=False))
    players[5].traits = [Trait.SET_PIECE_TAKER]
    return players


def plan(formation="4-4-2", press=0.5, tempo=0.5, seed=1, **kw):
    return build_tactics(seed, "H", formation, press, tempo, squad(formation, **kw))


# ---------- posture schedule ----------

def shifts_of(meta):
    return [(s.side, s.posture, s.ten_men, s.reason) for side in ("H", "A") for s in meta.teams[side].postures]


def test_shift_counts_per_arc_for_seeds_1_to_50(runs):
    for (arc, seed), (_, meta, _) in runs.items():
        assert len(shifts_of(meta)) == EXPECTED_SHIFTS[arc], (arc, seed)


def test_shift_sequences_follow_table_2_3(runs):
    for (arc, seed), (_, meta, _) in runs.items():
        h, a = meta.teams["H"].postures, meta.teams["A"].postures
        if arc == "comeback":
            assert [(s.posture, s.ten_men, s.reason) for s in h] == [("chase", False, "checkpoint"), ("protect", False, "goal")]
            assert [(s.posture, s.ten_men, s.reason) for s in a] == [("chase", False, "goal")]
        elif arc == "red_card":
            assert [(s.posture, s.ten_men, s.reason) for s in h] == [("base", True, "red_card"), ("chase", True, "checkpoint")]
            assert [(s.posture, s.ten_men, s.reason) for s in a] == [("protect", False, "checkpoint"), ("base", False, "goal")]
        else:
            assert [(s.posture, s.ten_men, s.reason) for s in h] == [("chase", False, "goal")]
            assert [(s.posture, s.ten_men, s.reason) for s in a] == [("protect", False, "checkpoint")]


def test_triggers_sit_on_the_beats_and_checkpoints(runs):
    for (arc, seed), (sim, meta, events) in runs.items():
        goals = {e.t for e in events if e.type is EventType.SHOT and e.outcome == "goal"}
        reds = {e.t for e in events if e.type is EventType.CARD and e.card == "red"}
        checks = {sim._minute_t(61), sim._minute_t(76)}
        for side in ("H", "A"):
            for s in meta.teams[side].postures:
                assert s.t_trigger in {"goal": goals, "red_card": reds, "checkpoint": checks}[s.reason]


def test_red_card_home_side_is_ten_men_and_chasing_after_61(runs):
    for seed in SEEDS:
        sim, meta, events = runs[("red_card", seed)]
        h = meta.teams["H"]
        last = h.postures[-1]
        before, after = plan_at(h.tactics, h.postures, h.players, sim._minute_t(60)), plan_at(
            h.tactics, h.postures, h.players, last.t)
        assert (last.posture, last.ten_men, last.on_pitch) == ("chase", True, 10)
        assert last.t_trigger == sim._minute_t(61)
        assert before.shape_out == "4-4-1" and before.shape_in == "4-3-2"  # ten men, not yet chasing
        assert after.shape_out == "4-4-1" and after.shape_in == "3-3-3"  # still ten men, now with the extra forward


def test_shifts_take_effect_at_a_restart_or_the_fallback(runs):
    restarts = ("throw_in", "goal_kick", "free_kick", "corner")
    for (arc, seed), (_, meta, events) in list(runs.items())[::7]:
        for side in ("H", "A"):
            for s in meta.teams[side].postures:
                assert s.t >= s.t_trigger
                at = [e for e in events if e.t == s.t]
                if s.t - s.t_trigger <= RESTART_FALLBACK_S:
                    assert any(e.type is EventType.KICKOFF or e.set_piece in restarts for e in at), (arc, seed, s)
                else:
                    assert s.t - s.t_trigger >= RESTART_FALLBACK_S
                    assert not at or any(e.type is EventType.POSSESSION_CHANGE for e in at)


def ev(i, t, typ=EventType.PASS, team="H", **kw):
    return Event(i=i, t=t, period=1, clock="1", type=typ, team=team, x=50, y=30, **kw)


def red_then(*after):
    return [ev(0, 100.0, EventType.CARD, card="red"), *after]


def test_restart_inside_180_seconds_wins():
    events = red_then(ev(1, 130.0, EventType.POSSESSION_CHANGE), ev(2, 150.0, set_piece="free_kick"),
                      ev(3, 400.0, EventType.POSSESSION_CHANGE))
    s = posture_schedule(events, lambda m: (m - 1) * 60.0 + (0 if m <= 45 else 100.0))["H"][0]
    assert (s.t_trigger, s.t) == (100.0, 150.0)


def test_no_restart_falls_back_to_the_possession_change_after_180_seconds():
    events = red_then(ev(1, 130.0, EventType.POSSESSION_CHANGE), ev(2, 285.0, EventType.POSSESSION_CHANGE),
                      ev(3, 300.0, set_piece="free_kick"))  # the restart comes 200 s later: too late
    s = posture_schedule(events, lambda m: (m - 1) * 60.0)["H"][0]
    assert s.t == 285.0


def test_no_restart_and_no_possession_change_uses_the_deadline():
    s = posture_schedule(red_then(ev(1, 130.0)), lambda m: (m - 1) * 60.0)["H"][0]
    assert s.t == 100.0 + RESTART_FALLBACK_S


def test_a_restart_before_the_trigger_does_not_count():
    events = [ev(0, 50.0, set_piece="corner"), ev(1, 100.0, EventType.CARD, card="red"), ev(2, 120.0, set_piece="throw_in")]
    assert posture_schedule(events, lambda m: (m - 1) * 60.0)["H"][0].t == 120.0


@pytest.mark.parametrize("state,d,minute,expected", [
    ("base", -1, 60, "chase"), ("base", -1, 59, "base"), ("base", 0, 80, "base"), ("base", 1, 75, "protect"),
    ("base", 1, 74, "base"), ("base", 3, 20, "base"),
    ("chase", 0, 80, "chase"), ("chase", -2, 30, "chase"), ("chase", 1, 80, "protect"), ("chase", 1, 70, "base"),
    ("protect", 1, 88, "protect"), ("protect", 0, 88, "base"), ("protect", -1, 88, "chase"), ("protect", -1, 55, "base"),
])
def test_next_posture(state, d, minute, expected):
    assert next_posture(state, d, minute) == expected


def test_a_protect_team_that_loses_its_lead_returns_to_base():
    # away lead from the 34th minute, home pull level in the 79th
    events = [ev(0, 2000.0, EventType.SHOT, team="A", outcome="goal"), ev(1, 2040.0, EventType.KICKOFF),
              ev(2, 4700.0, EventType.SHOT, team="H", outcome="goal"), ev(3, 4750.0, EventType.KICKOFF)]
    out = posture_schedule(events, lambda m: (m - 1) * 60.0)
    assert [(s.posture, s.reason, s.t) for s in out["A"]] == [("protect", "checkpoint", 4500.0 + RESTART_FALLBACK_S),
                                                              ("base", "goal", 4750.0)]
    assert [(s.posture, s.reason) for s in out["H"]] == [("chase", "checkpoint")]  # stays chase when level again


def test_level_before_the_75th_minute_never_protects():
    events = [ev(0, 4000.0, EventType.SHOT, team="A", outcome="goal"), ev(1, 4040.0, EventType.KICKOFF),
              ev(2, 4300.0, EventType.SHOT, team="H", outcome="goal"), ev(3, 4350.0, EventType.KICKOFF)]
    out = posture_schedule(events, lambda m: (m - 1) * 60.0)
    assert [(s.posture, s.reason, s.t) for s in out["H"]] == [("chase", "goal", 4040.0)]
    assert out["A"] == []


# ---------- the base plan ----------

def test_every_plan_is_complete_and_in_range(runs):
    for _, meta, _ in runs.values():
        for t in meta.teams.values():
            x = t.tactics
            assert x.formation == t.formation
            assert 26 <= x.line_height <= 50 and 44 <= x.width <= 62 and 0 <= x.tempo <= 1
            assert x.shape_in in (v for pair in SHAPE_IN.values() for v in pair)
            assert x.shape_out in SHAPE_OUT[t.formation].values()
            assert 2 <= len(x.press.triggers) <= 3 and set(x.press.triggers) <= set(PRESS_TRIGGERS)
            assert x.press.triggers == [k for k in PRESS_TRIGGERS if k in x.press.triggers]  # canonical order, no repeats


def test_line_height_formula():
    assert plan(press=0.4).line_height == 30.0
    assert plan(press=0.6).line_height == 35.0
    # the two CB slots of the 4-4-2 are indexes 2 and 3
    assert plan(press=0.5, roles={2: Role.BALL_PLAYING_CB, 3: Role.BALL_PLAYING_CB}).line_height == 36.5
    assert plan(press=0.5, roles={2: Role.BALL_PLAYING_CB}).line_height == 32.5  # one is not a pair
    assert plan(press=0.5, roles={3: Role.COVER_CB}).line_height == 29.5


def test_line_height_is_clamped_to_26_50():
    assert plan(press=0.0, roles={2: Role.COVER_CB}).line_height == 26.0
    assert plan(press=1.2, roles={2: Role.BALL_PLAYING_CB, 3: Role.BALL_PLAYING_CB}).line_height == 50.0


@pytest.mark.parametrize("line,block,height", [(26, "low", "low"), (31.9, "low", "low"), (32, "mid", "mid"), (42, "mid", "mid"),
                                               (42.1, "high", "high")])
def test_block_thresholds(line, block, height):
    assert block_of(line) == block
    press = (line - 30) / 25 + 0.4
    x = plan(press=press)
    if abs(x.line_height - line) < 0.06:
        assert (x.block, x.press.height) == (block, height)


def test_press_intensity_is_the_skill():
    assert plan(press=0.57).press.intensity == 0.57


def test_build_up_thresholds():
    assert plan(passing=60).build_up == "short" and plan(passing=59).build_up == "mixed"
    assert plan(passing=52).build_up == "mixed" and plan(passing=51).build_up == "direct"


def test_shape_in_follows_the_inverted_full_back():
    for f, (default, inverted) in SHAPE_IN.items():
        assert plan(f).shape_in == default
        rb = next(k for k, (pos, *_) in enumerate(FORMATIONS[f]) if pos == "RB")
        assert plan(f, roles={rb: Role.INVERTED_FULLBACK}).shape_in == inverted


@pytest.mark.parametrize("formation", list(SHAPE_OUT))
@pytest.mark.parametrize("press,block", [(0.3, "low"), (0.5, "mid"), (0.9, "high")])
def test_shape_out_follows_the_block(formation, press, block):
    x = plan(formation, press=press)
    assert x.block == block and x.shape_out == SHAPE_OUT[formation][block]


def test_width_comes_from_the_wide_roles_and_is_clamped():
    assert plan("4-3-3").width == 48.0
    assert plan("4-3-3", roles={8: Role.WINGER, 10: Role.WINGER}).width == 54.0
    assert plan("4-3-3", roles={1: Role.ATTACKING_FULLBACK, 4: Role.ATTACKING_FULLBACK, 8: Role.WINGER, 10: Role.WINGER}).width == 58.0
    assert plan("4-3-3", roles={1: Role.INVERTED_FULLBACK, 4: Role.INVERTED_FULLBACK, 8: Role.INVERTED_WINGER,
                                10: Role.INVERTED_WINGER}).width == 44.0
    wide = {k: Role.WIDE_MIDFIELDER for k in (5, 8)} | {k: Role.ATTACKING_FULLBACK for k in (1, 4)}
    assert plan("4-4-2", roles=wide).width == 56.0
    assert plan("4-3-3", roles={k: Role.WINGER for k in (1, 4, 8, 10)} | {1: Role.ATTACKING_FULLBACK, 4: Role.ATTACKING_FULLBACK},
                ).width <= 62.0


def test_tempo_classes():
    assert tempo_class_of(0.44) == "slow" and tempo_class_of(0.45) == "measured"
    assert tempo_class_of(0.55) == "measured" and tempo_class_of(0.56) == "high"
    assert plan(tempo=0.4).tempo_class == "slow" and plan(tempo=0.6).tempo_class == "high"


def test_counter_needs_two_fast_forwards_or_wide_midfielders():
    def fast(*idx):
        players = squad("4-4-2")
        for k in idx:
            players[k].attrs.pace = 75
        return build_tactics(1, "H", "4-4-2", 0.5, 0.5, players).counter

    assert fast(9, 10) is True        # both strikers
    assert fast(5, 8) is True         # both wide midfielders
    assert fast(9) is False
    assert fast(2, 3) is False        # centre backs do not count
    assert fast(9, 3) is False


def test_corner_delivery_follows_the_taker():
    both, right = squad(), squad()
    both[5].foot, right[5].foot = "both", "R"
    assert build_tactics(1, "H", "4-4-2", 0.5, 0.5, both).corner_delivery == "outswing"
    assert build_tactics(1, "H", "4-4-2", 0.5, 0.5, right).corner_delivery == "inswing"


def test_only_short_playing_teams_go_short_and_not_all_of_them():
    mixed = {build_tactics(s, "H", "4-4-2", 0.5, 0.5, squad(passing=55)).corner_delivery for s in range(60)}
    short = [build_tactics(s, "H", "4-4-2", 0.5, 0.5, squad(passing=70)).corner_delivery for s in range(60)]
    assert "short" not in mixed
    assert 0 < short.count("short") < 60 and set(short) <= {"short", "inswing"}


def test_plan_is_deterministic_and_has_its_own_stream():
    assert plan(seed=4) == plan(seed=4)
    assert {tuple(plan(seed=s).press.triggers) for s in range(40)} != {tuple(plan(seed=0).press.triggers)}
    sides = {tuple(build_tactics(4, side, "4-4-2", 0.5, 0.5, squad()).press.triggers) for side in ("H", "A")}
    seeds = {tuple(plan(seed=s).press.triggers) for s in range(40)}
    assert len(seeds) > 3 and len(sides) >= 1


def test_building_tactics_does_not_touch_the_simulation_generator():
    sim = Sim("comeback", 5)
    sim.run()
    state = sim.rng.getstate()
    build_tactics(5, "H", "4-4-2", 0.5, 0.5, squad())
    assert sim.rng.getstate() == state


# ---------- postures change the plan, ten_men composes ----------

def test_ten_men_alone():
    base = plan("4-4-2", press=0.5)
    x = effective_plan(base, "base", True)
    assert (x.shape_in, x.shape_out) == ("4-3-2", "4-4-1")
    assert x.line_height == base.line_height - 4 and x.press.intensity == round(base.press.intensity - 0.10, 2)


@pytest.mark.parametrize("formation,shape_in", [("4-4-2", "3-4-3"), ("4-3-3", "2-3-5"), ("4-2-3-1", "2-3-5")])
def test_chase(formation, shape_in):
    base = plan(formation)
    x = effective_plan(base, "chase", False)
    assert x.shape_in == shape_in and x.shape_out == base.shape_out
    assert x.line_height == base.line_height + 6 and x.width == base.width + 4
    assert x.press.intensity == round(base.press.intensity + 0.15, 2) and x.tempo == round(base.tempo + 0.05, 2)


def test_ten_men_and_chase_compose_to_3_3_3():
    base = plan("4-3-3")
    x = effective_plan(base, "chase", True)
    assert (x.shape_in, x.shape_out) == ("3-3-3", "4-4-1")
    assert x.line_height == base.line_height - 4 + 6
    assert x.press.intensity == round(base.press.intensity - 0.10 + 0.15, 2)


def test_protect():
    base = plan("4-4-2", press=0.55)
    x = effective_plan(base, "protect", False)
    assert x.block == "low" and x.press.height == "low" and x.shape_out == "4-5-1"
    assert x.line_height == pytest.approx(base.line_height - 8) and x.press.intensity == round(base.press.intensity - 0.15, 2)
    assert x.tempo == round(base.tempo - 0.05, 2) and x.shape_in == base.shape_in
    assert effective_plan(base, "protect", False, defensive_fullback=True).shape_out == "5-4-1"


def test_ten_men_protect_keeps_ten_outfield_players():
    base = plan("4-4-2")
    assert effective_plan(base, "protect", True).shape_out == "4-4-1"
    assert effective_plan(base, "protect", True, defensive_fullback=True).shape_out == "5-3-1"


def test_effective_plan_does_not_change_the_base_and_base_is_identity():
    base = plan("4-2-3-1")
    snapshot = base.model_copy(deep=True)
    effective_plan(base, "chase", True)
    assert base == snapshot
    assert effective_plan(base, "base", False) == base


def test_effective_values_stay_in_range():
    base = plan("4-4-2", press=0.0, tempo=0.0)
    x = effective_plan(base, "protect", True)
    assert x.line_height >= 18 and x.press.intensity >= 0 and x.tempo >= 0
    top = effective_plan(plan(press=1.0, tempo=1.0), "chase", False)
    assert top.press.intensity <= 1 and top.tempo <= 1 and top.line_height <= 56


def test_plan_at_switches_at_the_effective_time(runs):
    sim, meta, _ = runs[("comeback", 7)]
    h = meta.teams["H"]
    s = h.postures[0]
    assert plan_at(h.tactics, h.postures, h.players, s.t - 0.1) == h.tactics
    assert plan_at(h.tactics, h.postures, h.players, s.t) == effective_plan(
        h.tactics, "chase", False, any(p.role is Role.DEFENSIVE_FULLBACK for p in h.players if p.pos in ("LB", "RB")))
    assert plan_at(h.tactics, [], h.players, 5000) == h.tactics


def test_posture_schedule_uses_the_sims_clock(runs):
    sim, _, events = runs[("unlucky", 3)]
    assert sim._minute_t(61) == 60 * 60 + sim.stop1
    assert posture_schedule(events, sim._minute_t)["A"][0].t_trigger == sim._minute_t(76)


def test_every_shift_is_dated_by_the_restart_rule_and_a_later_trigger_wins():
    # away lead; the 76' checkpoint (4500) would protect, but the first restart is 242 s away, so it waits for the
    # possession change at 4758.4. Home level at 4688.9: back to base at its own kick-off 4742.7, which comes first.
    events = [ev(0, 2000.0, EventType.SHOT, team="A", outcome="goal"), ev(1, 2040.0, EventType.KICKOFF),
              ev(2, 4688.9, EventType.SHOT, team="H", outcome="goal"), ev(3, 4742.7, EventType.KICKOFF),
              ev(4, 4758.4, EventType.POSSESSION_CHANGE)]
    out = posture_schedule(events, lambda m: (m - 1) * 60.0)
    assert [(s.posture, s.t) for s in out["A"]] == [("protect", 4758.4), ("base", 4742.7)]
    assert [s.t_trigger for s in out["A"]] == [4500.0, 4688.9]
    assert superseded(out["A"]) == [True, False]
    base = plan(formation="4-4-2")
    assert plan_at(base, out["A"], squad(), 5000) == base  # the later trigger wins: base, not protect
    assert plan_at(base, out["A"], squad(), 4750.0) == base
    assert plan_at(base, out["A"], squad(), 4758.4) == base


def test_posture_shifts_are_in_trigger_order_for_all_150_runs(runs):
    for (arc, seed), (_, meta, _) in runs.items():
        for side in ("H", "A"):
            shifts = meta.teams[side].postures
            assert all(a.t_trigger < b.t_trigger for a, b in zip(shifts, shifts[1:])), (arc, seed, side)
            final = shifts[-1].posture if shifts else "base"
            assert plan_at(meta.teams[side].tactics, shifts, meta.teams[side].players, 99999.0) == effective_plan(
                meta.teams[side].tactics, final, shifts[-1].ten_men if shifts else False,
                any(p.role is Role.DEFENSIVE_FULLBACK for p in meta.teams[side].players if p.pos in ("LB", "RB")))


def test_every_shift_of_150_runs_takes_effect_at_a_restart_or_the_fallback(runs):
    from matchvoice.sim.tactics import RESTARTS
    for (arc, seed), (_, meta, events) in runs.items():
        for side in ("H", "A"):
            for s in meta.teams[side].postures:
                restarts = [e for e in events if e.t >= s.t_trigger and (e.type is EventType.KICKOFF or e.set_piece in RESTARTS)]
                first = restarts[0].t if restarts else None
                if first is not None and first - s.t_trigger <= RESTART_FALLBACK_S:
                    assert s.t == first, (arc, seed, side, s)  # a restart within 180 s: the shift is read there
                else:
                    assert s.t >= s.t_trigger + RESTART_FALLBACK_S, (arc, seed, side, s)  # otherwise the fallback, never earlier
                    assert any(e.t == s.t and e.type is EventType.POSSESSION_CHANGE for e in events) or s.t == s.t_trigger + RESTART_FALLBACK_S


def test_superseded_shifts_are_rare_and_never_the_last(runs):
    for (arc, seed), (_, meta, _) in runs.items():
        for side in ("H", "A"):
            flags = superseded(meta.teams[side].postures)
            assert not flags or not flags[-1], (arc, seed, side)
