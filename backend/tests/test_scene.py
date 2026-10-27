"""The generated live scene (sim/scene.py): the 89' winner of comeback-135, played differently on every New run.

No model, no network. The rules are the acceptance metrics of docs/live/PLAN.md: a logical phase of play on the whole pitch, passes
of real length and flight, receivers where the page already draws them, one goal for the home side at 2-1 in the window, and
everything before the fork identical to the plain match."""
from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from pathlib import Path

import pytest

from matchvoice.pipeline import scenes
from matchvoice.pipeline.library import SCENE_FALLBACK, SCENE_RETRIES, Library
from matchvoice.schema import EventType
from matchvoice.sim import sceneshape
from matchvoice.sim.engine import Sim
from matchvoice.sim.micro.enrich import _att, enrich
from matchvoice.sim import scene as scene_mod
from matchvoice.sim.scene import FINAL_TYPE, ScenePlan, scene_goal, validate

ROOT = Path(__file__).resolve().parents[2]
WIN = scenes.SCENES["winner"]
BASE_META, BASE_EVENTS, BASE_TRUTH = Sim("comeback", 135).run()
FORK_T = 5408.6


def play(variant: int, retry: int = 0):
    plan = ScenePlan(variant, retry=retry, base_meta=BASE_META, fork_after=WIN.fork_after, kick_at=WIN.kick_at, goal_window=WIN.goal_window)
    sim = Sim("comeback", 135, scene=plan)
    meta, events, truth = sim.run()
    return plan, sim, meta, events, truth


@pytest.fixture(scope="module")
def plays():
    """200 variants, each with its plan, meta, events, the scene events and the enriched rows of the scene."""
    out = []
    for v in range(200):
        plan, sim, meta, events, truth = play(v)
        if validate(meta, events, plan):
            continue  # the library draws such a variant again (test_fallback_is_rare counts them)
        goal = scene_goal(events, plan)[0]
        scene = [e for e in events if FORK_T < e.t <= goal.t]
        rows = [r for r in enrich(meta, events, t0=FORK_T, t1=goal.t).rows if r["t"] > FORK_T]
        out.append({"v": v, "plan": plan, "sim": sim, "meta": meta, "events": events, "truth": truth, "goal": goal, "scene": scene,
                    "rows": rows})
    return out


def test_the_same_variant_gives_the_same_match():
    a, b = play(5), play(5)
    assert a[3] == b[3] and a[2] == b[2] and a[4] == b[4]
    assert play(6)[3] != a[3]


def test_everything_before_the_fork_is_the_plain_match():
    _, _, meta, events, _ = play(3)
    before = [e for e in events if e.i <= 1836]
    assert before == BASE_EVENTS[:1837] and before[-1].reason == "goal_kick" and before[-1].t == FORK_T
    assert events[1837].t >= WIN.kick_at[0] and events[1837].set_piece == "goal_kick"  # the keeper takes it 7 to 9 s later
    rows = [r for r in enrich(meta, events).rows if r["t"] < FORK_T]
    assert rows == [r for r in enrich(BASE_META, BASE_EVENTS).rows if r["t"] < FORK_T]
    assert {s: t.model_dump(exclude={"postures"}) for s, t in meta.teams.items()} == {
        s: t.model_dump(exclude={"postures"}) for s, t in BASE_META.teams.items()}


def test_exactly_one_goal_after_the_fork_the_home_winner_in_the_window(plays):
    assert len(plays) >= 196
    for p in plays:
        goals = [e for e in p["events"] if e.t >= FORK_T and e.type == EventType.SHOT and e.outcome == "goal"]
        assert len(goals) == 1
        g = goals[0]
        assert g.team == "H" and g.score == [2, 1] and g.clock == "89" and WIN.goal_window[0] <= g.t <= WIN.goal_window[1]
        assert not any(b.kind == "goal" for _, b in p["sim"].pending)  # the 89' beat was scored by the scene, none is left
        assert p["sim"].forced is None
        assert [t for t in p["truth"] if t.kind == "goal" and t.t >= FORK_T] == [t for t in p["truth"] if t.kind == "goal" and t.t == g.t]
        assert p["events"][-1].type == EventType.PERIOD_END


def _points(e):
    if e.type in (EventType.PASS, EventType.CARRY):
        return [(e.x, e.y), (e.end_x, e.end_y)]
    if e.type in (EventType.INTERCEPTION, EventType.SHOT):
        return [(e.x, e.y)]  # a shot's end is the goal line
    return []


def test_no_ball_on_the_touchline_or_byline(plays):
    edge = total = 0
    for p in plays:
        for e in p["scene"]:
            for n, (x, y) in enumerate(_points(e)):
                if e.set_piece == "goal_kick" and n == 0:
                    continue  # the restart spot
                total += 1
                edge += min(x, 105 - x) < 2.1 or min(y, 68 - y) < 2.1
    assert total > 3000 and edge == 0  # the plain match has 13 of 17 actions of this window on the clamp edge


def test_pass_lengths(plays):
    lengths = []
    for p in plays:
        own = [e.length for e in p["scene"] if e.type == EventType.PASS]
        assert all(6.0 <= x <= 50.0 for x in own)
        lengths += own
    assert 12 <= statistics.median(lengths) <= 24


def test_flight_times_and_clean_enrichment(plays):
    for p in plays:
        ev = {e.i: e for e in p["events"]}
        assert not any(r.get("implicit") for r in p["rows"])
        kicks = {r["eid"]: r for r in p["rows"] if r["type"] == "pass"}
        for r in p["rows"]:
            if r["type"] != "receipt" or r["pass_eid"] not in kicks:
                continue
            k = kicks[r["pass_eid"]]
            e = ev[k["i"]]
            speed = e.length / (r["t"] - k["t"])
            assert 7.9 <= speed <= 34, (p["v"], e.i, speed)  # 8 m/s is enrich's slowest roll, 0.1 s rounding
        acts = [e for e in p["scene"] if e.type in (EventType.PASS, EventType.CARRY, EventType.SHOT)]
        for a, b in zip(acts, acts[1:]):
            if a.type == EventType.PASS and a.outcome == "complete":
                assert b.t - a.t >= a.length / (a.ball_speed / 3.6) + 0.4 - 0.1  # event times are rounded to 0.1 s
        for a, b in zip(p["scene"], p["scene"][1:]):
            if a.type == EventType.PASS and a.outcome == "complete":  # a press comes after the ball arrived, so enrich squeezes nothing
                assert b.t - a.t >= a.length / (a.ball_speed / 3.6) + 0.25 - 0.1
        g = p["goal"]
        en = enrich(p["meta"], p["events"], t0=FORK_T, t1=g.t)
        assert en.stats.unrepaired == [] and en.stats.squeezed == 0


def _spot(meta, pid, ball, period):
    side = pid[0]
    team = meta.teams[side]
    k = next(n for n, pl in enumerate(team.players) if pl.id == pid)
    pl = team.players[k]
    return sceneshape.shape_spot(team.formation, k, pl.group, pl.number, side, ball, 1.0)


def test_receivers_play_on_and_stand_where_the_page_draws_them(plays):
    gaps = []
    for p in plays:
        acts = [e for e in p["scene"] if e.type in (EventType.PASS, EventType.CARRY, EventType.SHOT)]
        for a, b in zip(acts, acts[1:]):
            if a.type == EventType.PASS and a.outcome == "complete":
                assert b.player == a.receiver and (b.x, b.y) == (a.end_x, a.end_y)  # the next actor is the receiver, from the ball
            if a.type == EventType.CARRY:
                assert b.player == a.player and (b.x, b.y) == (a.end_x, a.end_y)
        for n, e in enumerate(acts):
            if e.type != EventType.PASS or e.outcome != "complete":
                continue
            ball = _att(e.team, e.period, e.x, e.y)
            end = _att(e.team, e.period, e.end_x, e.end_y)
            s = _spot(p["meta"], e.receiver, ball, e.period)
            flight = e.length / (e.ball_speed / 3.6)
            d = math.hypot(end[0] - s[0], end[1] - s[1])
            last = next((a for a in reversed(acts[:n]) if a.player == e.receiver and e.t - a.t <= 3.0), None)
            if last is not None:  # a one-two: he just played it, the page still draws him there (pass and go)
                lx, ly = _att(e.team, e.period, last.x, last.y)
                d = min(d, math.hypot(end[0] - lx, end[1] - ly))
            assert d <= 6.5 * (2 + flight), (p["v"], e.i, d)
            gaps.append(d)
    assert statistics.median(gaps) <= 8


def test_the_final_ball_is_the_pattern_and_every_kind_appears(plays):
    seen = Counter()
    for p in plays:
        passes = [r for r in p["rows"] if r["type"] == "pass" and r["t"] < p["goal"].t]
        seen.update(r["pass_type"] for r in passes)
        want = FINAL_TYPE.get(p["plan"].info["pattern"])
        if want:
            assert passes[-1]["pass_type"] == want, p["v"]
    assert all(seen[k] for k in ("through", "cross", "cut_back", "switch")), seen


def test_variety(plays):
    first = plays[:60]
    assert len({p["plan"].info["pattern"] for p in first}) >= 4
    assert len({p["goal"].player for p in first}) >= 3
    assert len({p["plan"].info["turnover"] for p in first}) >= 2
    assert len({tuple(e.player for e in p["scene"] if e.type == EventType.PASS) for p in first}) >= 40
    tav = sum(p["goal"].player == "H7" for p in plays) / len(plays)
    assert 0.22 <= tav <= 0.42  # Gabriel Tavares scores about 30 percent of the winners


def test_fallback_is_rare_and_the_fallback_variants_pass():
    first_try_bad, never = 0, 0
    for v in range(300):
        plan, _, meta, events, _ = play(v)
        if not validate(meta, events, plan):
            continue
        first_try_bad += 1
        def bad(r):
            plan_r, _, meta_r, events_r, _ = play(v, r)
            return validate(meta_r, events_r, plan_r)
        if all(bad(r) for r in range(1, SCENE_RETRIES)):
            never += 1
    assert first_try_bad / 300 < 0.05 and never / 300 < 0.02
    for v in SCENE_FALLBACK:
        plan, _, meta, events, _ = play(v)
        assert validate(meta, events, plan) == []


def test_the_library_keeps_the_plain_match_and_caches_scenes():
    lib = Library()
    a = lib.scene_bundle(WIN, 42)
    assert lib.scene_bundle(WIN, 42) is a and a.variant == "42" and a.scene["pattern"] in (*FINAL_TYPE, "edge")
    plain = lib.bundle("comeback-135")
    assert plain.variant is None and plain.events == BASE_EVENTS


def test_form_matches_the_page():
    html = (ROOT / "ui/public/mock4.html").read_text(encoding="utf-8")
    block = re.search(r"const FORM = \{(.*?)\n\};", html, re.S).group(1) + "\n"
    form = {}
    for name, body in re.findall(r'"([\d-]+)":\s*\[(.*?)\],?\n', block):
        form[name] = [tuple(float(v) for v in pair.split(",")) for pair in re.findall(r"\[([^\[\]]+)\]", body)]
    assert form == {k: [tuple(map(float, p)) for p in v] for k, v in sceneshape.FORM.items()}


def test_no_tackles_in_the_scene(plays):
    for p in plays:
        assert not any(e.type == EventType.TACKLE for e in p["scene"])  # the page draws no tackle: turnovers are interceptions
        assert any(e.type == EventType.INTERCEPTION for e in p["scene"])
        assert any(e.type == EventType.PRESSURE for e in p["scene"])


def test_postures_follow_the_generated_goal(plays):
    for p in plays[:20]:
        g = p["goal"]
        h = [s for s in p["meta"].teams["H"].postures if s.reason == "goal" and s.t_trigger >= FORK_T]
        a = [s for s in p["meta"].teams["A"].postures if s.reason == "goal" and s.t_trigger >= FORK_T]
        assert [s.t_trigger for s in h] == [g.t] == [s.t_trigger for s in a]
        assert h[0].posture == "protect" and a[0].posture == "chase"


# ---------- review fixes (2026-10-27): who presses, who wins it, the run in behind, the finish ----------
def _pos(meta, pid):
    return next(p.pos for t in meta.teams.values() for p in t.players if p.id == pid)


def test_nobody_passes_to_himself_and_validate_catches_it(plays):
    for p in plays:
        assert not any(e.type == EventType.PASS and e.receiver == e.player for e in p["scene"]), p["v"]
    p = plays[0]
    e = next(e for e in p["scene"] if e.type == EventType.PASS and e.outcome == "complete")
    bad = [x.model_copy(update={"receiver": x.player}) if x.i == e.i else x for x in p["events"]]
    assert "a pass to the passer himself" in validate(p["meta"], bad, p["plan"])


def test_wexmoor_are_pressed_in_their_attack(plays):
    pressed, passes, scenes_with = 0, 0, 0
    for p in plays:
        win = next(e for e in p["scene"] if e.type == EventType.INTERCEPTION and e.team == "H")
        att = [e for e in p["scene"] if e.t > win.t]
        presses = [e for e in att if e.type == EventType.PRESSURE and e.team == "A"]
        hp = [e for e in att if e.type == EventType.PASS and e.team == "H"]
        passes += len(hp)
        pressed += sum(bool(e.under_pressure) for e in hp)
        scenes_with += bool(presses)
        assert len(presses) == sum(bool(e.under_pressure) for e in hp)  # every press in the attack is a pass played under it
    assert pressed / passes >= 0.2 and scenes_with / len(plays) >= 0.6


def test_the_ball_winner_fits_the_zone(plays):
    mid = Counter()
    for p in plays:
        win = next(e for e in p["scene"] if e.type == EventType.INTERCEPTION and e.team == "H")
        if p["plan"].info["turnover"] == "mid":
            mid[_pos(p["meta"], win.player)] += 1
    n = sum(mid.values())
    assert mid["ST"] / n <= 0.15 and (mid["CM"] + mid["DM"]) / n >= 0.25, mid  # a midfield regain is a midfielder's ball


def test_the_press_is_shared_by_role_and_flank(plays):
    by = Counter()
    for p in plays:
        for e in p["scene"]:
            if e.type == EventType.PRESSURE and e.team == "H":
                by[e.player] += 1
    wide = by["H6"] + by["H9"]
    assert by["H3"] + by["H4"] == 0 and wide / sum(by.values()) >= 0.15, by  # centre backs stay home, wide players take their flank


def test_the_counter_is_a_run_in_behind_met_first_time(plays):
    seen = 0
    for p in plays:
        if p["plan"].info["pattern"] != "counter":
            continue
        seen += 1
        final = [e for e in p["scene"] if e.type == EventType.PASS][-1]
        assert final.receiver != final.player and _pos(p["meta"], final.receiver) == "ST"
        ball = _att(final.team, final.period, final.x, final.y)
        end = _att(final.team, final.period, final.end_x, final.end_y)
        s = _spot(p["meta"], final.receiver, ball, final.period)
        assert end[0] - s[0] >= 6.9, (p["v"], end, s)  # he runs onto it: the page draws a sprint, not a ball to feet
        rec = next(r for r in p["rows"] if r["type"] == "receipt" and r["player"] == final.receiver and r["t"] >= final.t)
        nxt = next(e for e in p["scene"] if e.t > final.t and e.type in (EventType.CARRY, EventType.SHOT))
        assert nxt.t - rec["t"] <= 1.05  # no standing still after the ball arrives (a first touch: 0.35 to 0.55 s plus 0.15 to 0.45 s)
        if nxt.type == EventType.CARRY:
            assert nxt.speed / 3.6 >= 6.9
    assert seen >= 5


def test_the_finish_varies(plays):
    spots = Counter((round(p["goal"].x, 1), round(p["goal"].y, 1)) for p in plays)
    assert len(spots) >= 0.9 * len(plays) and spots.most_common(1)[0][1] <= 3, spots.most_common(3)
    cut = Counter((e.player, e.receiver) for p in plays if p["plan"].info["pattern"] == "cutback"
                  for e in [[x for x in p["scene"] if x.type == EventType.PASS][-1]])
    assert len(cut) >= 4 and max(cut.values()) / sum(cut.values()) <= 0.7, cut  # was one pair in every cutback
    edge = Counter(p["goal"].player for p in plays if p["plan"].info["pattern"] == "edge")
    assert len(edge) >= 2, edge
    under = sum(bool(p["goal"].under_pressure) for p in plays) / len(plays)
    assert 0.4 <= under <= 0.85  # most finishes beat a defender who is closing


def test_no_counter_press_in_the_demo(plays):
    assert scene_mod.COUNTER_PRESS_P == 0.0
    for p in plays:
        assert sum(e.type == EventType.INTERCEPTION for e in p["scene"]) == 1, p["v"]  # one turnover, no swing back and forth


def test_the_short_goal_kick_is_rolled_out(plays):
    for p in plays:
        gk = next(r for r in p["rows"] if r["type"] == "pass" and r["pass_type"] == "goal_kick")
        ev = next(e for e in p["scene"] if e.i == gk["i"])
        rec = next(r for r in p["rows"] if r["type"] == "receipt" and r["pass_eid"] == gk["eid"])
        if ev.length < 24:
            assert gk["height"] == "ground" and rec["touch"] != "head", p["v"]
        else:
            assert gk["height"] == "lofted"


def test_the_booth_calls_the_winning_move_not_the_club_file(plays):
    """fast.py with `scene_at`: from the ball won back to the goal only the play is called (no story, table or stats line), a carry under
    way is play, a receipt is not called at the instant of the shot, a short pass that is cut out is not "played on", and the ball that
    makes the chance (cross, cutback, through ball) outranks a touch or a press."""
    from matchvoice.commentary.fast import SCENE_FINAL_PRIO, build_layers
    for p in plays[:40]:
        meta, events = p["meta"], p["events"]
        rows = enrich(meta, events).rows
        ms = build_layers(meta, events, rows, scene_at=WIN.start)
        win = next(e for e in p["scene"] if e.type == EventType.INTERCEPTION and e.team == "H")
        g = p["goal"]
        assert not [m for m in ms if m.layer == "context" and win.t <= m.t < g.t], p["v"]
        assert not [m for m in ms if m.kind == "touch" and g.t - 0.3 <= m.t <= g.t], p["v"]
        cut = {e.i for e in p["scene"] if e.type == EventType.PASS and e.outcome == "incomplete"}
        assert not [m for m in ms if m.kind == "pass_kind" and m.evidence[0] in cut and m.t >= WIN.start and "pass_type" not in m.params], p["v"]
        for m in ms:
            if m.kind == "pass_kind" and m.t >= WIN.start and m.params.get("pass_type") in ("cross", "cut_back", "through"):
                assert m.priority == SCENE_FINAL_PRIO
