"""The fast and context layers (docs/DATA-MODEL.md 7.1, 7.2, PLAN-DATA phase 3): the builder, the bank, the director rules, the runner.

No model, no key. The density gates themselves are in test_density.py."""
import asyncio
import hashlib
import json
import re
from dataclasses import replace
from functools import lru_cache

import orjson
import pytest

from matchvoice.commentary import fast as fl
from matchvoice.commentary.analyst import KEYS, CallBudget
from matchvoice.commentary.director import (CONTEXT_DEAD_S, CONTEXT_PER_WINDOW, CONTEXT_PLAY_S, FAST_GAP_S, ChannelDirector)
from matchvoice.commentary.fast import (CONTEXT, CONTEXT_BASE, FAST, FAST_BASE, REPLACED_KINDS, TACTICAL_BASE, build_layers, continuity_id,
                                        fatigue_base, layer_of, state_at)
from matchvoice.commentary.lang import LANGS, STYLES
from matchvoice.commentary.moments import _tidy, Moment, MomentBuilder, is_named, render_params, render_variants
from matchvoice.commentary.templates import NAME_KEYS, T, WORDS
from matchvoice.commentary.verifier import Verifier, allowed_for
from matchvoice.facts.engine import FactEngine
from matchvoice.pipeline.demo import demo_insert
from matchvoice.pipeline.guided import pick_window
from matchvoice.pipeline.library import MatchBundle
from matchvoice.pipeline.runner import LiveConfig, Runner
from matchvoice.schema import EventType
from matchvoice.sim.arcs import ARCS
from matchvoice.sim.engine import Sim
from matchvoice.sim.micro.enrich import enrich
from test_pipeline import LIB

MATCHES = [("comeback", 7), ("comeback", 135), ("red_card", 7), ("unlucky", 7), ("red_card", 11)]
FAST_FIRES = {"touch", "pass_kind", "carry", "duel", "restart", "setpiece_setup", "press_on"}  # what the skeleton and the enriched rows can say now
WAITS_FOR_TRACKING = set(FAST) - FAST_FIRES
GENDERED = {"en": r"\b(he|she|his|her|him|hers)\b", "de": r"\b(er|sie|ihm|sein|seine|ihr)\b", "fr": r"\b(il|elle|lui|ils|elles)\b"}
FRAGMENT_WORDS = {"en": 6, "de": 7, "fr": 7}
ONE_WORDING = ("press_note", "phase_note", "shape_note", "story_note")  # a story_note has one sentence per facet; the beginner gets its own  # a context kind with nothing grounded to add to its one sentence has one wording
META_LEADS = re.compile(r"^(worth (noting|a mention)|good to know|look at|notice how|watch this|bemerkenswert|auffällig|gut zu (wissen|sehen)|à noter|"
                        r"bon à savoir|regardez)\b", re.I)


@lru_cache(maxsize=None)
def built(arc: str, seed: int):
    meta, events, _ = Sim(arc, seed).run()
    rows = enrich(meta, events).rows
    return meta, events, rows, build_layers(meta, events, rows)


def ids(arc="comeback", seed=7):
    return [m.id for m in built(arc, seed)[3]]


# ---------- ids, time of knowledge, determinism ----------
@pytest.mark.parametrize("arc,seed", MATCHES)
def test_ids_are_derived_from_data_unique_and_deterministic(arc, seed):
    meta, events, rows, ms = built(arc, seed)
    assert len({m.id for m in ms}) == len(ms)
    again = build_layers(meta, events, rows)
    assert [(m.id, m.kind, m.t, m.params) for m in ms] == [(m.id, m.kind, m.t, m.params) for m in again]
    for m in ms:
        if m.layer == "fast":
            eid, slot = divmod(m.id - FAST_BASE, 8)
            assert slot == FAST[m.kind].slot and 0 <= eid < 16 * len(events) and FAST_BASE <= m.id < TACTICAL_BASE
        else:
            fi, slot = divmod(m.id - CONTEXT_BASE, 8)
            assert m.layer == "context" and slot == CONTEXT[m.kind].slot and fi == round(10 * m.t)
        assert layer_of(m.id) == m.layer
    assert max(m.id for m in ms) < 4_000_000  # fast max about 1,281,600, context about 3,465,800 (0.2)


def test_the_helpers_split_the_id_space():
    assert layer_of(163) == "skeleton" and layer_of(FAST_BASE + 5) == "fast" and layer_of(CONTEXT_BASE + 5) == "context"
    assert layer_of(TACTICAL_BASE + 3) == "skeleton"  # tactical_shift is an analyst moment
    assert continuity_id(163) and continuity_id(TACTICAL_BASE + 3) and not continuity_id(FAST_BASE + 5) and not continuity_id(CONTEXT_BASE + 5)


def test_a_moment_is_stamped_with_its_time_of_knowledge():
    meta, events, rows, ms = built("comeback", 135)
    by_eid = {r["eid"]: r for r in rows}
    for m in ms:
        if m.layer != "fast":
            continue
        eid = (m.id - FAST_BASE) // 8
        if m.kind == "touch":  # a receipt is known when the ball arrives and called once the receiver has kept it for TOUCH_SETTLE_S
            assert by_eid[eid]["type"] == "receipt" and m.t == pytest.approx(by_eid[eid]["t"] + fl.TOUCH_SETTLE_S, abs=1e-3)
        elif m.kind == "pass_kind":  # a kick is known at the kick
            r = by_eid[eid]
            assert r["type"] == "pass" and m.t == pytest.approx(r["t"], abs=1e-3)
            assert m.ttl >= 2.0 and m.ttl >= min(r["t_arr"] - r["t"], fl.MAX_FLIGHT_TTL_S) - 1e-6  # worth saying while the ball flies
        elif m.kind == "carry":  # a carry is known at its end
            r = by_eid[eid]
            assert m.t == pytest.approx(r["t"] + r["duration_s"], abs=1e-3) and r["progress_m"] >= fl.CARRY_MIN_PROGRESS_M


def test_the_kick_names_the_target_never_the_receiver_and_does_not_reveal_the_outcome():
    meta, events, rows, ms = built("comeback", 135)
    by_eid = {r["eid"]: r for r in rows}
    outcomes = set()
    for m in ms:
        if m.kind != "pass_kind":
            continue
        assert "receiver" not in m.params and "outcome" not in m.params
        row = by_eid[(m.id - FAST_BASE) // 8]
        assert "outcome" not in row and "receiver" not in row  # a kick row carries no outcome (phase 2)
        outcomes.add(next(e.outcome for e in events if e.i == row["i"]))
    assert {"complete", "incomplete"} <= outcomes  # it is said for balls that do not arrive, too


@pytest.mark.parametrize("arc,seed", MATCHES)
def test_no_double_call_with_a_skeleton_moment(arc, seed):
    meta, events, rows, ms = built(arc, seed)
    eng, mb = FactEngine(meta), None
    mb = MomentBuilder(eng)
    owned = {ev.i for ev in events for m in mb.feed(ev, eng.ingest(ev)) if m.kind not in REPLACED_KINDS}
    assert owned  # corners, shots, fouls, cards, tackles, sprints
    for m in ms:
        if m.layer == "fast" and m.kind != "touch":  # a receipt is the ball arriving: the skeleton call at the kick (a corner) is a different moment
            assert m.evidence[0] not in owned, (m.kind, m.evidence)
    # the kinds that wait for tracking, and take_on (its lost kind shares an event with a skeleton tackle call), are silent now
    assert {m.kind for m in ms if m.layer == "fast"} <= FAST_FIRES


def test_a_receipt_gets_a_touch_when_it_is_worth_one_every_interception_a_duel_and_pressure_a_press_on():
    """A receipt is called when it is a ball worth a word (chest, head) or the kick did not already name him with his type ("Long ball for Tavares"),
    and when the receiver keeps the ball for TOUCH_SETTLE_S: a first-time pass, a carry or a shot at once voids it."""
    meta, events, rows, ms = built("comeback", 135)
    kinds = {k: [m for m in ms if m.kind == k] for k in FAST_FIRES}
    touches = {(m.id - FAST_BASE) // 8 for m in kinds["touch"]}
    typed_named = {(m.id - FAST_BASE) // 8 for m in kinds["pass_kind"] if "pass_type" in m.params and "target" in m.params and m.params["named"]}
    recs = [x for x in fl.Layers(meta, events, rows).timeline() if not (x.kind == "ev" and x.payload.type is EventType.PRESSURE)]
    pos = {x.payload["eid"]: i for i, x in enumerate(recs) if x.kind == "row"}
    receipts = [r for r in rows if r["type"] == "receipt"]
    voided = 0
    for r in receipts:
        nxt = recs[pos[r["eid"]] + 1].t if pos[r["eid"]] + 1 < len(recs) else float("inf")
        gone = nxt <= r["t"] + fl.TOUCH_SETTLE_S
        worth = r["touch"] != "control" or r["pass_eid"] not in typed_named
        assert (r["eid"] in touches) == (worth and not gone), (r["eid"], r["touch"], worth, gone)
        voided += worth and gone
    assert voided and 0.6 * len(receipts) < len(touches) < len(receipts)  # the first-time chain of the insert is one of the voided ones
    ints = [e for e in events if e.type is EventType.INTERCEPTION]
    assert len(kinds["duel"]) == len(ints) and all(m.params["facet"] == "interception" for m in kinds["duel"])
    by_i = {e.i: e for e in events}
    surname = {p.id: p.name.split()[-1] for t in meta.teams.values() for p in t.players}
    for m in kinds["duel"]:
        assert m.params["winner"] == surname[by_i[m.evidence[0]].player]
    assert kinds["press_on"], "skeleton pressure events become press_on"
    for m in kinds["press_on"]:
        e = by_i[m.evidence[0]]
        assert e.type is EventType.PRESSURE and m.params["team_code"] == e.team


def test_a_first_time_pass_is_not_preceded_by_the_name_of_the_man_who_plays_it_on():
    """The insert: the long ball reaches Tavares at 4392.085 s and he plays it on at 4392.301 s. The fragment for that kick is the news, not a receipt."""
    meta, events, rows, ms = built("comeback", 135)
    long_ball = next(r for r in rows if r["type"] == "pass" and abs(r["t"] - 4389.6) < 0.01)
    receipt = next(r for r in rows if r["type"] == "receipt" and r["pass_eid"] == long_ball["eid"])
    assert receipt["eid"] not in {(m.id - FAST_BASE) // 8 for m in ms if m.kind == "touch"}
    assist = next(m for m in ms if m.kind == "pass_kind" and abs(m.t - 4392.301) < 0.01)
    assert assist.params["pass_type"] == "first_time" and assist.params["player"] == "Tavares" and assist.params["target"] == "Fontaine"


def test_restarts_name_the_side_and_a_free_kick_in_range_is_a_setup():
    seen = set()
    for arc, seed in MATCHES:
        meta, events, rows, ms = built(arc, seed)
        by_eid = {r["eid"]: r for r in rows}
        for m in ms:
            if m.kind == "restart":
                assert m.params["facet"] in ("throw_in", "goal_kick", "free_kick", "kickoff")
                if m.params["facet"] == "throw_in":
                    assert m.params["side"] in ("left", "right", "centre")
                if m.params["facet"] == "free_kick":
                    assert by_eid[(m.id - FAST_BASE) // 8]["distance_m"] > fl.FREE_KICK_RANGE_M
                seen.add(m.params["facet"])
            if m.kind == "setpiece_setup":
                assert by_eid[(m.id - FAST_BASE) // 8]["distance_m"] <= fl.FREE_KICK_RANGE_M
                seen.add("setup")
    assert {"throw_in", "goal_kick", "free_kick", "kickoff"} <= seen


# ---------- name rationing ----------
@pytest.mark.parametrize("arc,seed", MATCHES)
def test_a_name_less_fragment_is_for_a_ball_worth_a_word_and_never_two_in_a_row(arc, seed):
    ms = sorted((m for m in built(arc, seed)[3] if m.layer == "fast"), key=lambda m: (m.t, (m.id - FAST_BASE) // 8))  # the builder's own order
    run = 0
    last_team = None
    named_total = rationed_total = 0
    for m in ms:
        if m.kind not in fl.RATIONED:
            run, last_team = 0, m.params["team_code"]
            continue
        named = m.params["named"]
        if m.params.get("name_said"):
            assert not named  # the player was named a moment ago: the fragment goes without him, outside the rationing
            continue
        if m.params["team_code"] != last_team:
            assert named  # the other side's ball: name the player
        if named:
            run = 0
        else:
            run += 1
            assert run <= fl.NAMED_EVERY - 1, run  # at most one name-less fragment in a row
            if m.kind == "touch":  # a ball worth a word: a chested ball, a header, a ball taken with the back to goal
                assert m.params["facet"] != "control" or m.params["facing"] == "own_goal", m.params
            elif m.kind == "pass_kind":
                assert m.params["pass_type"] in fl.BARE_PASS, m.params
        last_team = m.params["team_code"]
        named_total += named
        rationed_total += 1
    assert 0.8 < named_total / rationed_total < 1.0  # names and verbs are the volume; the name-less ones are the exception


@pytest.mark.parametrize("arc,seed", MATCHES)
def test_a_pass_with_a_type_names_its_target_and_a_long_ball_always_has_one(arc, seed):
    meta, events, rows, ms = built(arc, seed)
    seen = set()
    for m in ms:
        if m.kind != "pass_kind" or "pass_type" not in m.params:
            continue
        seen.add(m.params["pass_type"])
        assert ("target" in m.params) == (m.params["pass_type"] != "clearance")  # a clearance is not for anyone
        if m.params["pass_type"] not in fl.BARE_PASS:
            assert m.params["named"] and "target" in m.params, m.params  # a long ball, a through ball, a cut-back: always with its target
        for lang in LANGS:
            for style in STYLES:
                for text in render_variants(m, lang, style):
                    if m.params["named"] and "target" in m.params:
                        assert m.params["target"] in text, (lang, style, text)
                    assert not re.search(r"(clears it|schlägt ihn weg|dégage) (to|auf|pour|vers)\b", text, re.I), text
    assert seen and "long" in seen
    long_balls = [m for m in ms if m.kind == "pass_kind" and m.params.get("pass_type") == "long"]
    assert long_balls and all(m.params["target"] in render_variants(m, "en", "expert")[-1] for m in long_balls)


def test_a_name_less_moment_renders_only_name_less_wordings_and_a_named_one_only_named_ones():
    ms = [m for m in built("comeback", 7)[3] if m.kind in fl.RATIONED]
    for m in ms[:300]:
        for lang in LANGS:
            for style in STYLES:
                p = render_params(m, lang)
                allowed = {_tidy(v.format(**p)) for v in T[m.kind][lang][style]
                           if is_named(v) == m.params["named"] and all(k in p for k in re.findall(r"{(\w+)}", v))}  # a wording needs every fact it names (no `dir` for a back-pass)
                texts = render_variants(m, lang, style)
                assert texts and set(texts) <= allowed


def test_the_bank_has_name_less_and_named_wordings_for_every_rationed_kind():
    for kind in fl.RATIONED:
        for lang in LANGS:
            for style in STYLES:
                vs = T[kind][lang][style]
                assert sum(is_named(v) for v in vs) >= 2 and sum(not is_named(v) for v in vs) >= 2, (kind, lang, style)


# ---------- the context layer ----------
def known(r: dict) -> float:
    return r["t"] + (r["duration_s"] if r["type"] == "carry" and "duration_s" in r else 0.0)


def ball_moving(events, rows):
    """Times at which something moved the ball (a pressure event does not)."""
    row_t = [known(r) for r in rows if r["type"] in ("pass", "receipt", "shot", "foul", "interception", "carry")]  # a carry is known at its end
    return sorted([e.t for e in events if e.type not in (EventType.PRESSURE, EventType.CARRY)] + row_t)


@pytest.mark.parametrize("arc,seed", MATCHES)
def test_a_context_slot_is_offered_only_if_nothing_happened_before_it(arc, seed):
    meta, events, rows, ms = built(arc, seed)
    times = ball_moving(events, rows)
    by_eid = {r["eid"]: r for r in rows}
    ctx = [m for m in ms if m.layer == "context"]
    assert len(ctx) > 50
    goal_windows = {r["eid"] for r in rows if r["type"] == "shot" and next(e for e in events if e.i == r["i"]).outcome == "goal"}
    kinds = set()
    for m in ctx:
        w = m.params["window"]
        row = by_eid.get(w)
        if m.params["dead"]:
            src = row["t_arr"] if row and row["type"] == "pass" else (row["t"] if row else events[w // 16].t)
            offsets = [(fl.GOAL_QUIET_S if w in goal_windows else 1.0) + fl.DEAD_STEP_S * k for k in range(fl.DEAD_SLOTS)]
            assert any(abs(m.t - src - o) < 1e-3 for o in offsets), (m.t, src)
            kinds.add("dead")
        else:
            # a slot after a receipt (the hold slots, then the quiet ones) or after any other record (the quiet ones): the window is the record's id
            src = known(row) if row else events[w // 16].t
            hold = row is not None and row["type"] == "receipt"
            offsets = (fl.CONTEXT_FIRST_HOLD_S, fl.SECOND_HOLD_S, *fl.QUIET_SLOTS_S[1:]) if hold else fl.QUIET_SLOTS_S
            assert any(abs(m.t - src - o) < 1e-3 for o in offsets), (m.t, src, hold)
            assert m.params["long"] == (m.t - src > 4.4)  # the first slots take the short wording, the ones after a longer hold the long one
            kinds.add("hold" if hold else "quiet")
        gap = [t for t in times if src + 1e-6 < t <= m.t - 1e-6]
        assert not gap, (m.kind, m.t, gap[:3])
    assert kinds == {"dead", "hold", "quiet"}, kinds


def test_a_goal_leaves_the_voice_alone_for_the_call_and_the_analysis_before_the_first_context_line():
    meta, events, rows, ms = built("comeback", 7)
    goals = [r for r in rows if r["type"] == "shot" and next(e for e in events if e.i == r["i"]).outcome == "goal"]
    assert len(goals) >= 3
    for g in goals:
        mine = [m for m in ms if m.layer == "context" and m.params["window"] == g["eid"]]
        assert mine and all(m.t >= g["t"] + fl.GOAL_QUIET_S - 1e-6 for m in mine)


@pytest.mark.parametrize("arc,seed", MATCHES)
def test_context_content_is_real_and_rate_limited(arc, seed):
    meta, events, rows, ms = built(arc, seed)
    ctx = [m for m in ms if m.layer == "context"]
    assert {m.kind for m in ctx} >= {"player_note", "counter_note", "tempo_note"} and {m.kind for m in ctx} & set(fl.TACTIC_KINDS)
    assert all(m.priority in range(30, 46) and m.ttl == 8.0 and m.voice_wait == 3.0 for m in ctx)
    assert all(m.voice == ("pbp" if m.kind in fl.LEAD_CONTEXT else "analyst") for m in ctx)  # the lead reads the dossier, the co-commentator the rest
    last: dict[tuple[str, str], float] = {}
    note_at: dict[str, float] = {}
    passes_at: dict[str, int] = {}
    previous_facet = None
    players = {p.id: p for t in meta.teams.values() for p in t.players}
    for m in ctx:
        f = m.params.get("facet")
        if m.kind == "player_note":
            pid = next(i for i, p in players.items() if p.name.split()[-1] == m.params["player"])
            assert m.t - note_at.get(pid, -1e9) >= fl.PLAYER_GAP_S - 1e-6
            facets = [f, *(m.params[k] for k in ("facet2", "facet3") if k in m.params)]  # a dead ball may hold two or three facts of one player
            assert len(set(facets)) == len(facets) and sum(x in fl.SEASONAL for x in facets) <= 1, facets
            if f == "passes":  # a number that moves on: never the same sentence again
                assert m.params["count"] > passes_at.get(pid, -1) and fl.PASSES_MIN <= m.params["count"] <= fl.PASSES_MAX
                assert m.params["count"] // fl.PASSES_STEP > passes_at.get(pid, -fl.PASSES_STEP) // fl.PASSES_STEP  # a new step of the count
                passes_at[pid] = m.params["count"]
            for x in facets:
                if x != "passes":  # a fact about a player is said once in the match, word for word it never comes back
                    assert (pid, x) not in last, (m.params, last[(pid, x)])
                    last[(pid, x)] = m.t
            assert f != previous_facet, f  # and never the same kind of fact twice in a row
            previous_facet = f
            note_at[pid] = m.t
        if m.kind == "fatigue_note":
            pid = next(i for i, p in players.items() if p.name.split()[-1] == m.params["player"])
            assert m.t >= fl.FATIGUE_MIN_T and fatigue_base(players[pid], m.t) >= fl.FATIGUE_AT and (pid, "fatigue") not in last
            last[(pid, "fatigue")] = m.t
        if m.kind == "tempo_note":
            assert f in ("slow", "high", "slow_2", "high_2") and m.t >= 300.0


def state_lines(ms):
    return [m for m in ms if m.kind == "counter_note" and re.sub(r"_(\d|added)$", "", m.params.get("facet", "")) in ("goalless", "level", "lead")]


def score_at(events, t):
    goals = {"H": 0, "A": 0}
    for e in events:
        if e.t < t and e.type is EventType.SHOT and e.outcome == "goal":
            goals[e.team] += 1
    return goals["H"], goals["A"]


@pytest.mark.parametrize("arc,seed", MATCHES)
def test_the_game_state_comes_back_when_the_score_moved_or_five_minutes_have_passed_and_never_says_the_same_thing_twice(arc, seed):
    meta, events, rows, ms = built(arc, seed)
    states = state_lines(ms)
    assert states
    prev_t, prev_score = None, (0, 0)
    texts = []
    for m in states:
        score, minute = score_at(events, m.t), int(m.clock.split("+")[0])
        moved = score != prev_score
        assert prev_t is None or m.t - prev_t >= fl.STATE_GAP_S - 1e-6  # never twice within a minute
        assert moved or (minute >= fl.STATE_FROM_MIN and (prev_t is None or m.t - prev_t >= fl.STATE_STEP_S - 1e-6)), (m.clock, m.t, prev_t)
        base = re.sub(r"_(\d|added)$", "", m.params["facet"])
        assert (base == "lead") == (score[0] != score[1]) and (base == "goalless") == (score == (0, 0))
        if "+" in m.clock:  # added time: the clock stands still at 45 or 90, so the line does not name a minute
            assert m.params["facet"].endswith("_added") and "n" not in m.params
        else:
            assert not m.params["facet"].endswith("_added") and m.params["n"] == minute
        texts.append(render_variants(m, "en", "expert")[0])
        prev_t, prev_score = m.t, score
    assert all(a != b for a, b in zip(texts, texts[1:])), texts  # not the same sentence twice in a row
    assert len(texts) == len(set(texts)), [t for t in texts if texts.count(t) > 1]  # and not once more in the whole match


@pytest.mark.parametrize("arc,seed", MATCHES)
def test_a_counter_note_never_comes_back_word_for_word_and_the_counters_are_capped(arc, seed):
    meta, events, rows, ms = built(arc, seed)
    counters = [m for m in ms if m.kind == "counter_note"]
    for lang in LANGS:
        for style in STYLES:
            for pick in (0, -1):  # the short and the long wording
                texts = [render_variants(m, lang, style)[pick] for m in counters if pick or not m.params["facet"].startswith("chance_")]  # a chance is only said in its long form (`long_only`), which holds the move
                assert len(texts) == len(set(texts)), (lang, style, pick, [t for t in texts if texts.count(t) > 1][:3])
    streaks = [m for m in counters if m.params["facet"] in ("passes", "passes_2")]
    assert len(streaks) <= fl.STREAK_MAX
    for side in ("H", "A"):  # each side: ten, then fifteen, then twenty, never the same number twice
        ns = [m.params["n"] for m in streaks if m.params["team_code"] == side]
        assert ns == sorted(set(ns)) and set(ns) <= {10, 15, 20}
    per: dict[tuple[str, str], list[int]] = {}
    for m in counters:
        base = re.sub(r"_\d$", "", m.params["facet"])
        if base in fl.STAT_FACETS:
            per.setdefault((base, m.params["team_code"]), []).append(m.params["n"])
    assert per
    for (facet, side), ns in per.items():
        assert len(ns) <= fl.STAT_MAX, (facet, side, ns)  # a cap per match
        step = fl.STAT_STEP.get(facet, 1)
        assert all(b >= a + step for a, b in zip(ns, ns[1:])), (facet, side, ns)  # the value must have grown, every time
    poss = [m for m in counters if m.params["facet"].startswith("possession")]
    assert all(m.params["n"] >= fl.STAT_FLOOR["possession"] for m in poss)  # and the share of the ball carries its number: not "the better of the ball" again and again


def test_the_clock_and_the_score_are_the_ones_at_that_time():
    meta, events, rows, ms = built("comeback", 135)
    states = state_lines(ms)
    assert len(states) >= 5
    for m in states:
        goals = score_at(events, m.t)
        base = re.sub(r"_(\d|added)$", "", m.params["facet"])
        assert (base != "lead") == (goals[0] == goals[1])
        if base == "lead":
            lead = "H" if goals[0] > goals[1] else "A"
            assert m.params["team_code"] == lead
        if "n" in m.params:
            assert m.params["n"] == int(m.clock.split("+")[0])
        assert m.params["sh"] >= 0 and m.params["so"] >= 0  # the shots of the long sentence are the builder's own counts


def test_fatigue_is_a_function_of_the_clock_and_the_profile():
    meta = built("comeback", 7)[0]
    p = next(p for p in meta.teams["H"].players if p.group == "MID")
    assert fatigue_base(p, 0.0) == 0.0
    assert fatigue_base(p, 5400.0) >= fatigue_base(p, 2700.0) > 0
    assert 0.0 <= fatigue_base(p, 99999.0) <= 1.0


def test_state_at_follows_the_shifts_in_effect():
    from matchvoice.schema import PostureShift
    s = [PostureShift(side="H", t_trigger=100.0, t=130.0, reason="goal", posture="chase", ten_men=False, on_pitch=11),
         PostureShift(side="H", t_trigger=200.0, t=260.0, reason="red_card", posture="chase", ten_men=True, on_pitch=10)]
    assert state_at(s, 50.0) == ("base", False) and state_at(s, 129.9) == ("base", False)
    assert state_at(s, 130.0) == ("chase", False) and state_at(s, 259.0) == ("chase", False) and state_at(s, 260.0) == ("chase", True)
    assert state_at(None, 10.0) == ("base", False)
    meta = built("red_card", 7)[0]
    assert state_at(meta.teams["H"].postures, 3000.0)[1] is True  # the sent-off side plays with ten from the 38th minute


# ---------- no lookahead ----------
@pytest.mark.parametrize("arc,seed,cuts", [("comeback", 7, (400.0, 1500.0, 3300.0, 5000.0)), ("red_card", 7, (900.0, 2600.0, 4300.0))])
def test_a_moment_reads_only_what_happened_before_it(arc, seed, cuts):
    """Cut the data at `now` (delete every event and row known after it): every moment up to `now` comes out identical."""
    meta, events, rows, full = built(arc, seed)
    for now in cuts:
        evs = [e for e in events if e.t <= now]
        rs = [r for r in rows if known(r) <= now and r["i"] <= evs[-1].i]
        cut = build_layers(meta, evs, rs)
        want = [(m.id, m.kind, m.t, m.params, m.ttl, m.clock) for m in full if m.t <= now]
        got = [(m.id, m.kind, m.t, m.params, m.ttl, m.clock) for m in cut if m.t <= now]
        assert got == want, (now, len(got), len(want))


# ---------- the bank ----------
def test_every_fast_and_context_kind_has_a_full_bank_and_the_word_tables_agree():
    for kind in [*FAST, *CONTEXT]:
        assert set(T[kind]) == set(LANGS)
        for lang in LANGS:
            assert set(T[kind][lang]) == set(STYLES)
            for style in STYLES:
                assert len(T[kind][lang][style]) >= (1 if kind in ONE_WORDING else 2), (kind, lang, style)
    assert len(FAST) == 12 and len(CONTEXT) == 8  # story_note: the dossier (sim/dossier.py)
    for table, langs in WORDS.items():
        assert set(langs) == set(LANGS), table
        assert len({frozenset(v) for v in langs.values()}) == 1, table  # the same codes in every language
    for kind in ("take_on", "duel", "block", "restart", "player_note", "shape_note", "press_note", "tempo_note", "counter_note", "phase_note"):
        assert kind in WORDS
    for kind in ("duel", "block", "restart"):
        assert set(WORDS[f"{kind}_bare"]["en"]) == set(WORDS[kind]["en"])


def test_the_word_tables_obey_the_caster_rules():
    for table, langs in WORDS.items():
        for lang, codes in langs.items():
            for code, text in codes.items():
                assert not re.search(r"[—–]", text) and not re.search(r"\d", text), (table, lang, text)
                club = text.replace("ils sont revenus", "") if table.startswith("story_note") else text  # "ils": the club (plural), not a player
                assert table.endswith("_pron") or not re.search(GENDERED[lang], club, re.I), (table, lang, text)  # _pron: only with the squad's gender
    flat = [t for table in T.values() for langs in table.values() for styles in langs.values() for t in styles]
    assert not any(re.search(r"[—–]", t) for t in flat)


def test_name_keys_cover_every_player_placeholder_of_the_bank():
    used = {k for kind in [*FAST, *CONTEXT] for langs in T[kind].values() for vs in langs.values() for v in vs for k in re.findall(r"{(\w+)}", v)}
    placeholders = used - {"note", "bare", "why", "plain", "bare_plain", "also", "more", "note_long", "team", "dir_word", "Dir_word", "pass_word", "Pass_word", "pass_verb",
                           "Pass_done", "pass_prep", "Pass_prep", "pressed_word", "Pressed_word", "driven_word", "driven_bare", "driven_alt", "back_word", "lane_word", "third_word", "Third_word",
                           "wing_word", "Wing_word"}
    assert placeholders <= set(NAME_KEYS), placeholders


@pytest.mark.parametrize("arc,seed", MATCHES)
def test_the_verifier_accepts_every_wording_of_every_fast_and_context_moment(arc, seed):
    """The caster test of test_caster.py, extended to the new kinds: every wording passes the verifier, has no digits, no dashes, no gendered
    pronoun, and a fast fragment stays within 6 words (en) and 7 (de, fr)."""
    meta, events, rows, ms = built(arc, seed)
    ver = Verifier(meta)
    eng = FactEngine(meta)
    i = 0
    for m in ms:
        while i < len(events) and events[i].t <= m.t:
            eng.ingest(events[i])
            i += 1
        allowed = allowed_for(m, eng.snapshot(), meta)
        for lang in LANGS:
            for style in STYLES:
                texts = render_variants(m, lang, style)
                assert texts
                for text in texts:
                    verdict = ver.check(text, lang, allowed)
                    assert verdict.ok, (m.kind, m.params, lang, style, text, verdict.feedback())
                    assert not re.search(r"\d", text) and not re.search(r"[—–]", text), text
                    if not m.params.get("squad"):  # a pronoun for a player only when the squad's gender is known (comeback-135 is a men's squad)
                        assert not re.search(GENDERED[lang], text.replace("ils sont revenus", ""), re.I), (lang, text)  # the club, plural
                    if m.layer == "fast" and not (m.kind == "restart" and style == "beginner" and len(text.split()) > 10):  # the beginner's explanation of a restart is a sentence
                        assert len(text.split()) <= FRAGMENT_WORDS[lang], (m.kind, lang, text)


def test_a_name_less_line_names_nobody_and_a_named_one_names_a_player():
    meta, events, rows, ms = built("comeback", 135)
    surnames = {p.name.split()[-1] for t in meta.teams.values() for p in t.players}
    for m in ms:
        if m.layer == "fast" and m.kind in fl.RATIONED:
            for lang in LANGS:
                for text in render_variants(m, lang, "expert"):
                    names = [s for s in surnames if re.search(rf"(?<!\w){re.escape(s)}(?!\w)", text)]
                    assert bool(names) == m.params["named"], (m.params["named"], text)


# ---------- the director ----------
def fastm(i: int, t: float, kind: str = "touch", prio: int = 26, ttl: float = 5.0, wait: float = 5.0, **kw) -> Moment:
    return Moment(i, t, "1", kind, "pbp", prio, ttl, kw.pop("params", {}), layer="fast", voice_wait=wait)


def ctxm(i: int, t: float, dead: bool = False, window: int = 0, long: bool | None = None, ttl: float = 30.0) -> Moment:
    return Moment(i, t, "1", "counter_note", "analyst", 40, ttl, {"dead": dead, "window": window, "long": dead if long is None else long},
                  layer="context", voice_wait=30.0)


def ddir(speed=1.0, captions_first=True, **kw) -> ChannelDirector:
    return ChannelDirector(lambda m: ["Short.", "A somewhat longer line of talk.", "A long wording that a dead ball has the time for, indeed."],
                           "en", speed, captions_first=captions_first, dense=True,
                           voice_wait_s=lambda m: float("inf") if m.voice_wait is None else m.voice_wait, **kw)


def starts(d: ChannelDirector):
    return [(sp.moment_id, round(sp.start, 2)) for k, sp in d.drain() if k == "start"]


def test_a_newer_fast_fragment_replaces_an_older_one_still_waiting():
    d = ddir()
    d.push(Moment(0, 0.0, "1", "shot_off", "pbp", 50, 30, {}))  # keeps the voice busy
    for i, t in enumerate((0.5, 1.0, 1.5), start=1):
        d.push(fastm(i, t))
    d.advance(30.0)
    done = [m for m, _ in starts(d)]
    assert done == [0, 3]  # 1 and 2 never queue up behind the busy voice
    assert [x.reason for x in d.dropped if x.moment_id in (1, 2)] == ["replaced", "replaced"]


def test_a_fast_line_is_not_replaced_by_a_lower_priority_one():
    d = ddir()
    d.push(Moment(0, 0.0, "1", "shot_off", "pbp", 50, 30, {}))
    d.push(fastm(1, 0.5, prio=38, ttl=60.0, wait=60.0))
    d.push(fastm(2, 1.0, prio=26, ttl=60.0, wait=60.0))
    d.advance(60.0)
    assert [m for m, _ in starts(d)] == [0, 1, 2]


def test_fast_lines_start_at_least_the_gap_apart_in_viewer_seconds():
    for speed in (1.0, 10.0):
        d = ddir(speed=speed, captions_first=False)
        for i in range(12):
            d.push(fastm(i, i * 0.1 * speed, prio=26 + (i % 3), ttl=60.0))
        d.advance(1e6)
        t = [s for _, s in starts(d)]
        assert len(t) >= 2 and all(b - a >= FAST_GAP_S * speed - 0.011 for a, b in zip(t, t[1:])), (speed, t)


def test_a_fast_line_is_captioned_when_the_voice_takes_it_and_a_replaced_one_is_never_shown():
    d = ddir()
    d.push(Moment(0, 0.0, "1", "shot_off", "pbp", 50, 30, {}))
    d.push(fastm(1, 0.5))
    d.push(fastm(2, 1.0))
    d.advance(30.0)
    notes = d.drain()
    kinds = [(k, sp.moment_id) for k, sp in notes]
    assert ("caption", 0) in kinds and not any(k in ("caption", "skip") and m in (1, 2) for k, m in kinds)
    assert ("start", 2) in kinds and ("start", 1) not in kinds


def test_a_fast_line_that_waited_too_long_is_dropped_without_a_skip_notice():
    d = ddir()
    d.push(Moment(0, 0.0, "1", "shot_off", "pbp", 50, 30, {}))
    d.push(fastm(1, 0.5, wait=0.5, ttl=60.0))
    d.advance(60.0)
    assert not any(sp.moment_id == 1 for _, sp in d.drain()) and [x.reason for x in d.dropped if x.moment_id == 1] == ["stale"]


def test_context_in_play_is_spaced_and_waits_for_a_quiet_moment_and_the_dead_ball_has_its_own_cap():
    d = ddir()
    for i, t in enumerate((0.0, 1.0, 2.0)):
        d.push(ctxm(i, t, ttl=60.0))  # in play: one per CONTEXT_PLAY_S
    d.advance(200.0)
    t = [s for _, s in starts(d)]
    assert len(t) == 3 and t[0] == 0.0 and all(b - a >= CONTEXT_PLAY_S - 0.01 for a, b in zip(t, t[1:]))
    # a fast fragment waiting blocks a context line in play, not in a dead ball
    d = ddir()
    d.push(Moment(0, 0.0, "1", "shot_off", "pbp", 50, 30, {}))
    d.push(fastm(1, 0.2, prio=26, ttl=60.0, wait=60.0))
    d.push(ctxm(2, 0.3, dead=False, ttl=60.0))
    d.push(ctxm(3, 0.4, dead=True, window=7, ttl=60.0))
    d.advance(200.0)
    order = [m for m, _ in starts(d)]
    assert order[:2] == [0, 3]  # the dead-ball line goes first although the fragment waits
    assert order.index(1) < order.index(2)  # the in-play line waited for the fragment


def test_a_dead_ball_window_takes_three_context_lines_at_most_seven_seconds_apart():
    d = ddir()
    for i in range(6):
        d.push(ctxm(i, i * 1.0, dead=True, window=9, ttl=200.0))
    d.advance(500.0)
    t = [s for _, s in starts(d)]
    assert len(t) == CONTEXT_PER_WINDOW and all(b - a >= CONTEXT_DEAD_S - 0.01 for a, b in zip(t, t[1:]))
    d = ddir()
    for i, w in enumerate((1, 2, 3, 4)):  # four windows: three lines each would be allowed, the spacing still holds
        d.push(ctxm(i, i * 1.0, dead=True, window=w, ttl=200.0))
    d.advance(500.0)
    t = [s for _, s in starts(d)]
    assert len(t) == 4 and all(b - a >= CONTEXT_DEAD_S - 0.01 for a, b in zip(t, t[1:]))


def test_context_uses_the_shortest_wording_in_play_and_the_longest_in_a_dead_ball_or_a_long_hold():
    for dead, long, want in ((False, False, "Short."), (True, True, "A long wording that a dead ball has the time for, indeed."),
                             (False, True, "A long wording that a dead ball has the time for, indeed.")):
        d = ddir()
        d.push(ctxm(0, 0.0, dead=dead, long=long))
        d.advance(1.0)
        assert [sp.text for k, sp in d.drain() if k == "start"] == [want]


def test_skeleton_play_by_play_in_play_takes_its_shortest_wording():
    m = Moment(0, 0.0, "1", "tackle_won", "pbp", 28, 5, {})
    d = ddir(short_kinds=frozenset({"tackle_won"}))
    d.push(m)
    d.advance(1.0)
    assert [sp.text for k, sp in d.drain() if k == "start"] == ["Short."]
    d = ddir()
    d.push(m)
    d.advance(1.0)
    assert [sp.text for k, sp in d.drain() if k == "start"] != ["Short."]


def test_a_context_line_is_captioned_when_the_voice_takes_it_too():
    d = ddir()
    d.push(Moment(0, 0.0, "1", "shot_off", "pbp", 50, 30, {}))
    d.push(ctxm(1, 0.5, dead=True, window=1, ttl=60.0))
    d.advance(30.0)
    kinds = [(k, sp.moment_id) for k, sp in d.drain()]
    assert ("caption", 1) not in kinds and ("start", 1) in kinds


def test_a_channel_with_only_stale_fast_lines_goes_idle():
    d = ddir()
    d.push(Moment(0, 0.0, "1", "shot_off", "pbp", 50, 30, {}))
    d.push(fastm(1, 0.5, ttl=1.0, wait=30.0))
    d.advance(10.0)
    assert d.idle


def test_the_dense_rules_change_nothing_for_skeleton_moments():
    ms = [Moment(i, i * 3.0, "1", "corner", "pbp", 45, 8, {}) for i in range(8)]
    a = ChannelDirector(lambda m: ["Short.", "A longer one here."], "en", 1.0, captions_first=True)
    b = ddir()
    b.variants_of = a.variants_of
    for m in ms:
        a.push(m)
        b.push(m)
    a.advance(100.0)
    b.advance(100.0)
    assert [(k, sp.moment_id, sp.start, sp.end, sp.text) for k, sp in a.drain()] == [(k, sp.moment_id, sp.start, sp.end, sp.text) for k, sp in b.drain()]


# ---------- the runner ----------
async def no_call(prompt: str) -> str:
    raise RuntimeError("no model in this test")


def live(tmp_path, bundle, start, until, fast=True, paced=False, cfg=None):
    cfg = cfg or LiveConfig(no_call, CallBudget(100), "fake", tmp_path, fresh=True)
    return Runner(bundle, "live", 1.0, paced=paced, live=cfg, start=start, until=until, fast=fast)


@pytest.fixture(scope="module")
def insert_run(tmp_path_factory):
    d = demo_insert(LIB)
    r = live(tmp_path_factory.mktemp("c"), LIB.bundle(d["match"]), d["start"], d["until"])
    return r, asyncio.run(r.collect()), d


def says(msgs):
    return [m for m in msgs if m["k"] == "say"]


def test_the_insert_with_the_fast_layer_is_dense_and_keeps_the_skeleton_moments(insert_run):
    r, msgs, d = insert_run
    s = says(msgs)
    fast_says = [m for m in s if layer_of(m["m"]) == "fast"]
    assert len(fast_says) >= 8 * 1 and {m["ch"] for m in s} == set(range(6))
    assert all(m["e"] > m["s"] for m in s if layer_of(m["m"]) != "skeleton")  # captioned when voiced: a fragment has a slot from its first message
    assert not any(m["kind"] in REPLACED_KINDS for m in s)  # the two skeleton pass calls are replaced
    goal = [m for m in s if m["kind"] == "shot_goal"]
    assert len(goal) == 6 and {m["m"] for m in goal} == {162}  # the goal keeps its skeleton id and every channel calls it
    assert {m["m"] for m in s if m["kind"] == "goal_analysis"} == {163}
    assert all(m["src"] == "template" for m in fast_says)
    # nothing is spoken after the window nor before it
    assert all(m["s"] >= d["start"] - 1e-6 for m in s)


def test_fast_and_context_wording_never_enters_the_continuity(insert_run):
    r, _, _ = insert_run
    spoken_by_layer = {"fast": set(), "context": set(), "skeleton": set()}
    for (ch, mid), (text, lang) in r.lines.items():
        spoken_by_layer[layer_of(mid)].add(text)
    for ch, said in enumerate(r._said):
        for text in said:
            assert text not in spoken_by_layer["fast"] | spoken_by_layer["context"] or text in spoken_by_layer["skeleton"], (ch, text)
    assert any(r._said)  # the goal call is in the block


def test_the_goal_prompt_carries_only_skeleton_and_analyst_lines(tmp_path):
    prompts: list[str] = []

    async def call(prompt: str) -> str:
        prompts.append(prompt)
        raise RuntimeError("record only")

    d = demo_insert(LIB)
    cfg = LiveConfig(call, CallBudget(10), "fake", tmp_path, fresh=True)
    r = live(tmp_path, LIB.bundle(d["match"]), d["start"], d["until"], cfg=cfg)
    msgs = asyncio.run(r.collect())
    assert len(prompts) == 1
    block = prompts[0].split("Continuity")[1].split("Write one line")[0]
    lines = re.findall(r'^  - "(.+)"$', block, re.M)
    texts_by_layer = {"fast": set(), "context": set()}
    for m in says(msgs):
        if layer_of(m["m"]) in texts_by_layer:
            texts_by_layer[layer_of(m["m"])].add(m["text"])
    assert lines and not set(lines) & (texts_by_layer["fast"] | texts_by_layer["context"])
    assert len(lines) == 6  # one goal call per channel, no long_ball lines any more


def test_a_skipped_skeleton_line_stays_in_the_continuity_with_the_fast_layer(tmp_path, monkeypatch):
    monkeypatch.setattr("matchvoice.pipeline.runner.STANDIN_BEHIND_GOAL_S", 0.0)  # the old rule: a template stand-in is perishable 4 s after the goal
    d = demo_insert(LIB)
    r = live(tmp_path, LIB.bundle(d["match"]), d["start"], d["until"])
    msgs = asyncio.run(r.collect())
    skipped = [(m["ch"], m["m"]) for m in msgs if m["k"] == "voice" and m.get("skip")]
    caps = {(m["ch"], m["m"]): m["text"] for m in says(msgs)}
    assert skipped, "the template fallback of the analysis line is perishable (4 s), so a long goal call makes it skip"
    for ch, mid in skipped:
        if layer_of(mid) == "skeleton":
            assert caps[(ch, mid)] in r._said[ch]  # v5: no skip removal


def test_moments_before_the_start_are_not_voiced_and_ids_do_not_depend_on_the_start(tmp_path):
    d = demo_insert(LIB)
    b = LIB.bundle(d["match"])
    late = live(tmp_path, b, d["start"] + 8.0, d["until"])
    ids_late = {m["m"] for m in says(asyncio.run(late.collect())) if layer_of(m["m"]) != "skeleton"}
    full = {m.id for m in late._layers}
    assert ids_late <= {m.id for m in build_layers(b.meta, b.events, enrich(b.meta, b.events).rows)}
    assert all(m.t >= d["start"] + 8.0 for m in late._layers) and full


def test_the_default_runner_has_no_fast_layer(tmp_path):
    d = demo_insert(LIB)
    msgs = asyncio.run(live(tmp_path, LIB.bundle(d["match"]), d["start"], d["until"], fast=False).collect())
    assert not any(layer_of(m["m"]) != "skeleton" for m in says(msgs))
    assert any(m["kind"] == "long_ball" for m in says(msgs))


def test_a_replay_with_the_fast_layer_plays_the_recording_and_adds_the_dense_lines():
    off = asyncio.run(Runner(LIB.bundle("comeback-7"), "replay", 1.0, paced=False).collect())  # the dense voice is meant for 1x
    on = asyncio.run(Runner(LIB.bundle("comeback-7"), "replay", 1.0, paced=False, fast=True).collect())
    ids_on = {m["m"] for m in says(on)}
    assert {i for i in ids_on if layer_of(i) == "skeleton"} <= {m["m"] for m in says(off)}
    assert any(layer_of(i) == "fast" for i in ids_on) and any(layer_of(i) == "context" for i in ids_on)
    assert len(says(on)) > 2 * len(says(off))  # the voice talks most of the time
    assert all(m["k"] != "voice" for m in on)  # a recording shows a line when it is spoken


# ---------- nothing else moved ----------
def moment_digest(match_id: str):
    b = LIB.bundle(match_id)
    eng = FactEngine(b.meta)
    mb = MomentBuilder(eng)
    ms = [(m.id, m.kind, round(m.t, 2), m.priority) for ev in b.events for m in mb.feed(ev, eng.ingest(ev))]
    return len(ms), hashlib.sha256(json.dumps(ms).encode()).hexdigest()[:16]


def test_skeleton_moment_ids_kinds_times_and_priorities_are_unchanged():
    """Measured before phase 3 (scratchpad snapshot): count and digest of [(id, kind, t, priority)] per match."""
    want = {"comeback-135": (207, "8275097499e83ce8"), "comeback-7": (193, "c84a0617c913b575"), "red_card-11": (190, "fec28daa7c799e1b"),
            "red_card-7": (183, "afdeedde459e16d6"), "unlucky-7": (221, "d7e0f15581ed6a3f")}
    for match_id, digest in want.items():
        assert moment_digest(match_id) == digest, match_id


def test_the_guided_window_choice_is_unchanged_for_50_seeds_per_arc():
    w = {}
    for arc in sorted(ARCS):
        for seed in range(1, 51):
            meta, events, _ = Sim(arc, seed).run()
            w[f"{arc}-{seed}"] = pick_window(MatchBundle(meta, events))
    assert len(w) == 150
    assert hashlib.sha256(json.dumps(w, sort_keys=True).encode()).hexdigest()[:16] == "2b7efab39f3cd087"  # measured before phase 3


def test_the_recorded_replays_stream_exactly_as_before():
    """sha-256 of the replay stream at x30 for the three recorded matches (fast layer off). Re-measured 2026-10-25 for the insert script
    (docs/INSERT-SCRIPT.md): goal calls without the score, the lead's score line after each goal analysis, `who` on every say."""
    # Re-measured 2026-10-25 for the producers' fixes: a breath after the goal call and after the co line (director.BREATH_S), the score line waits for the co line.
    # Re-measured 2026-10-26 for the world channels: hello.channels carries level, solo, lead and co (name, gender); with those fields taken out
    # the three streams hash to the 2026-10-25 digests (9915c4256e16185f, 01a1a6616db3b139, b94c8b9a570280dd), so nothing else moved.
    want = {"comeback-7": (1761, "7c39024aef58f1c1"), "red_card-7": (1753, "e1f52e5f7b1d7b0d"), "unlucky-7": (1844, "f7edd037fb097ee4")}
    for match_id, (n, digest) in want.items():
        msgs = asyncio.run(Runner(LIB.bundle(match_id), "replay", 30.0, paced=False).collect())
        assert (len(msgs), hashlib.sha256(orjson.dumps(msgs)).hexdigest()[:16]) == (n, digest), match_id


# ---------- phase 3 review fixes (Opus review, 2026-10-21) ----------
VERDICT = {  # a judgement or the outcome of a ball that has only just been kicked or received
    "en": r"\b(good|tidy|nice|nicely|neat|keep|keeps|kept|clean|smooth|sharp|lovely)\b",
    "de": r"\b(gut|guter|sauber|saubere|ordentlich|bleibt|läuft|schön|schöner)\b",
    "fr": r"\b(bon|bien|joli|joliment|propre|reste|poursuit|beau)\b",
}


def test_a_name_less_pass_fragment_says_what_the_kick_shows_and_never_judges_or_announces_the_outcome():
    for lang in LANGS:
        for style in STYLES:
            bare = [v for v in T["pass_kind"][lang][style] if not is_named(v)]
            assert len(bare) >= 3, (lang, style)  # not a two-line loop
            for v in bare:
                assert re.search(r"{Pass_(done|word)}|{(P|p)ressed_word}|{driven_(bare|alt)}", v), v  # it is about this pass (or about what the kick shows)
                assert not re.search(VERDICT[lang], v, re.I), (lang, style, v)
            for v in T["pass_kind"][lang][style]:
                assert not re.search(VERDICT[lang], v, re.I), (lang, style, v)


def test_one_pass_gets_the_same_words_whether_it_arrives_or_not():
    meta, events, rows, ms = built("comeback", 135)
    by_eid = {r["eid"]: r for r in rows}
    outs = {}
    for m in ms:
        if m.kind == "pass_kind":
            assert set(m.params) <= {"player", "target", "pass_type", "lane", "arr", "pressed", "driven", "team", "team_code", "named", "kicker_said", "name_said", "squad"}  # nothing about how it ends
            outs.setdefault(next(e.outcome for e in events if e.i == by_eid[(m.id - FAST_BASE) // 8]["i"]), []).append(m)
    assert {"complete", "incomplete"} <= set(outs)
    for kind_of_end, group in outs.items():  # name-less lines for a failed pass exist, and none of them carries a verdict
        for m in group:
            for lang in LANGS:
                assert not any(re.search(VERDICT[lang], t, re.I) for t in render_variants(m, lang, "expert")), (kind_of_end, lang)


def test_a_touch_says_how_the_ball_arrived_never_what_the_receiver_does_next():
    for lang in LANGS:
        for style in STYLES:
            for v in T["touch"][lang][style]:
                if "dir_word" in v.lower():
                    assert v.startswith("{Dir_word}") and "{player}" in v, v  # "Forward to X": the incoming ball
                assert not re.search(r"\bthen\b|\bdann\b|\bpuis\b|looking|schaut|regarde|goes|geht", v), v
    meta, events, rows, ms = built("comeback", 7)
    pass_dir = {}
    for r in rows:
        if r["type"] == "pass":
            e = next(e for e in events if e.i == r["i"])
            pass_dir[r["eid"]] = (r.get("x", e.x), r.get("y", e.y), r.get("end_x", e.end_x), r.get("end_y", e.end_y), e.period, r["team"])
    by_eid = {r["eid"]: r for r in rows}
    n = 0
    for m in ms:
        if m.kind == "touch":
            r = by_eid[(m.id - FAST_BASE) // 8]
            if "dir" in m.params:  # not when the kick named the target: the receipt does not say who he is again
                assert m.params["dir"] == fl.Layers.direction(pass_dir[r["pass_eid"]])  # the direction of the pass that arrived
                n += 1
    assert n > 300


def test_the_expert_press_line_says_high_only_for_a_presser_in_the_opponents_half():
    for arc, seed in MATCHES[:4]:
        meta, events, rows, ms = built(arc, seed)
        ev = {e.i: e for e in events}
        facets = set()
        for m in ms:
            if m.kind != "press_on":
                continue
            e = ev[m.evidence[0]]
            x, _ = fl._att(e.team, e.period, e.x, e.y)
            assert (m.params["facet"] == "high") == (x >= fl.PRESS_HIGH_X)
            facets.add(m.params["facet"])
            texts = [t for lang in LANGS for t in render_variants(m, lang, "expert")]
            says_high = any(re.search(r"\bhigh\b|hoch|haut", t) for t in texts)
            assert says_high == (m.params["facet"] == "high"), (m.params, texts)
        assert facets == {"high", "low"}  # both happen: a high press is the minority, not every press


def test_no_context_wording_announces_the_occasion():
    lead = re.compile(r"ball is dead|wait for the restart|Solange der Ball|Während der Ball|jeu est arrêté|arrêt de jeu", re.I)
    for kind in CONTEXT:
        for lang in LANGS:
            for style in STYLES:
                for v in T[kind][lang][style]:
                    assert not lead.search(v) and not META_LEADS.search(v), (kind, lang, style, v)
                assert (1 if kind in ONE_WORDING else 2) <= len(T[kind][lang][style]) <= 3


@pytest.mark.parametrize("arc,seed", MATCHES[:3])
def test_a_saved_shot_or_the_post_is_not_a_dead_ball_and_a_goal_gives_no_trivia_about_the_side_that_conceded(arc, seed):
    meta, events, rows, ms = built(arc, seed)
    shots = {r["eid"]: next(e for e in events if e.i == r["i"]) for r in rows if r["type"] == "shot"}
    windows = {m.params["window"] for m in ms if m.layer == "context" and m.params["dead"]}
    for eid, e in shots.items():
        if e.outcome in ("saved", "post"):
            assert eid not in windows
    surnames = {s: {p.name.split()[-1] for p in meta.teams[s].players} for s in ("H", "A")}
    goals = {eid: e for eid, e in shots.items() if e.outcome == "goal"}
    assert goals
    for m in ms:
        if m.kind == "player_note" and m.params["window"] in goals:
            conceded = "A" if goals[m.params["window"]].team == "H" else "H"
            assert m.params["player"] not in surnames[conceded] or m.params["player"] in surnames[goals[m.params["window"]].team], m.params


def test_the_german_context_wordings_say_what_they_mean():
    flat = " ".join(w for table in ("shape_note", "press_note") for w in WORDS[table]["de"].values())
    assert "lässt den Ball gern laufen" not in flat and "ist einen Mann weniger" not in flat
    assert WORDS["press_note"]["de"]["passive"] == "{team} presst kaum und lässt den Gegner kommen"
    assert WORDS["shape_note"]["de"]["ten_men"].startswith("{team} hat einen Mann weniger")


# ---------- the verifier's claims lexicon (7.5) ----------
def _moment(kind: str, **params) -> Moment:
    return Moment(id=1_000_001, t=100.0, clock="1", kind=kind, voice="pbp", priority=30, ttl=2.0, params=params, evidence=[0], layer="fast")


def _verdict(text: str, m: Moment, lang: str = "en", arc: str = "comeback", seed: int = 7):
    meta = built(arc, seed)[0]
    return Verifier(meta).check(text, lang, allowed_for(m, FactEngine(meta).snapshot(), meta))


def test_a_tactical_phrase_needs_the_matching_claim_in_the_facts():
    low = _moment("press_on", presser="Abara", player="Okafor", facet="low", team="Wexmoor", team_code="H")
    high = _moment("press_on", presser="Abara", player="Okafor", facet="high", team="Wexmoor", team_code="H")
    assert _verdict("Abara presses high up here.", low).violations[0].code == "claim_unsupported"
    assert _verdict("Abara presses high up here.", high).ok
    passive = _moment("press_note", facet="passive", team="Wexmoor", team_code="H")
    intense = _moment("press_note", facet="intense", team="Wexmoor", team_code="H")
    assert not _verdict("Wexmoor are pressing high and in numbers.", passive).ok
    assert _verdict("Wexmoor are pressing high and in numbers.", intense).ok
    low_block = _moment("phase_note", facet="low", team="Tamsworth", team_code="A")
    assert not _verdict("Tamsworth sit on a high line.", low_block).ok
    assert _verdict("Tamsworth sit in a low block and wait for the turnover.", low_block).ok
    assert not _verdict("Wexmoor are set up to break at speed.", low_block).ok
    assert not _verdict("Tavares in behind!", low_block).ok
    assert _verdict("Tavares in behind!", _moment("in_behind", runner="Tavares")).ok


def test_the_lexicon_is_there_in_german_and_french_too():
    passive = _moment("press_note", facet="passive", team="Wexmoor", team_code="H")
    assert not _verdict("Wexmoor presst hoch und mit vielen Leuten.", passive, "de").ok
    assert _verdict("Wexmoor presst kaum und lässt den Gegner kommen.", passive, "de").ok
    assert not _verdict("Wexmoor presse haut et à plusieurs.", passive, "fr").ok
    assert not _verdict("Wexmoor défend très haut sur le terrain.", _moment("phase_note", facet="low", team="Wexmoor", team_code="H"), "fr").ok


def test_an_analyst_moment_carries_its_claims_in_the_shape_and_build_up_blocks():
    shape = {"home": {"posture": "base", "block": "high", "press": "intense"}, "away": {"posture": "base", "block": "low", "press": "passive"}}
    m = _moment("goal_analysis", player="Fontaine", team="Wexmoor", team_code="H", shape=shape,
                build_up={"chain": [["Ibsen", "interception"], ["Ibsen", "switch", "lofted"]], "line_break": True, "run_in_behind": None})
    assert fl_claims(m) == {"high_line", "low_block", "press_high", "press_passive", "switch", "line_break"}
    bare = _moment("goal_analysis", player="Fontaine", team="Wexmoor", team_code="H")
    assert fl_claims(bare) == set()
    assert not _verdict("Wexmoor played a switch and split the lines.", bare).ok


def fl_claims(m: Moment) -> set[str]:
    from matchvoice.commentary.verifier import claims_of
    return claims_of(m)


def test_a_trait_word_needs_a_named_player_who_has_the_trait():
    meta = built("comeback", 7)[0]
    players = [p for t in meta.teams.values() for p in t.players]
    codes = lambda p: [getattr(t, "value", t) for t in (p.traits or [])]  # noqa: E731
    tackler = next(p for p in players if "tough_tackler" in codes(p))
    other = next(p for p in players if "tough_tackler" not in codes(p))
    mine, theirs = tackler.name.split()[-1], other.name.split()[-1]
    m = _moment("player_note", player=mine, facet="trait:tough_tackler", team="Wexmoor", team_code="H")
    assert _verdict(f"{mine} is a tough tackler.", m).ok
    n = _moment("player_note", player=theirs, facet="apps", team="Wexmoor", team_code="H", count=4)
    assert _verdict(f"{theirs} is a tough tackler.", n).violations[0].code == "trait_unsupported"
    assert _verdict("There is a tough tackler in this side.", m).violations[0].code == "trait_unsupported"  # said of nobody
    assert _verdict(f"{theirs} has played four games this season. {mine} is a tough tackler.", n).violations[0].code == "player_unsupported"  # per sentence


def test_the_density_run_of_a_full_match_has_no_filler_loop(tmp_path):
    """The measurement behind the review: comeback-7 at x1, en/expert and de/beginner. No line is more than a tenth of the segments,
    no segment is a verdict, and no context line opens with an announcement of the occasion."""
    from matchvoice.evaluation import density
    b = LIB.bundle("comeback-7")
    msgs = density.run_span(b, 0.0, None)
    segs, _, _ = density.segments(msgs)
    for key, lang in (("en/expert", "en"), ("de/beginner", "de")):
        mine = [x for x in segs if x.ch == KEYS.index(key)]
        counts: dict[str, int] = {}
        for x in mine:
            counts[x.text] = counts.get(x.text, 0) + 1
        top, n = max(counts.items(), key=lambda kv: kv[1])
        assert n / len(mine) < 0.12, (key, top, n, len(mine))
        assert not any(re.search(VERDICT[lang], x.text, re.I) for x in mine if x.kind in ("pass_kind", "touch")), key


# ---------- phase 3 review fixes, second round ----------
def _surname_ids(meta) -> dict[tuple[str, str], str]:
    return {(s, p.name.split()[-1]): p.id for s in ("H", "A") for p in meta.teams[s].players}


@pytest.mark.parametrize("arc,seed", MATCHES)
def test_a_season_note_counts_what_the_player_has_done_in_this_match(arc, seed):
    """The profile's season numbers are from before the match: a note that comes after his goal or assist adds it, and an appearance counts."""
    meta, events, rows, ms = built(arc, seed)
    players = {p.id: p for t in meta.teams.values() for p in t.players}
    ids_ = _surname_ids(meta)
    ev = {e.i: e for e in events}
    kicker = {r["eid"]: r.get("player") or ev[r["i"]].player for r in rows if r["type"] == "pass"}
    goals: list[tuple[float, str]] = []
    assists: list[tuple[float, str]] = []
    for r in rows:
        if r["type"] == "shot" and ev[r["i"]].outcome == "goal":
            goals.append((ev[r["i"]].t, ev[r["i"]].player))
            if kicker.get(r.get("assist_eid")):
                assists.append((ev[r["i"]].t, kicker[r["assist_eid"]]))
    checked = 0
    for m in ms:
        if m.kind != "player_note":
            continue
        pid = ids_[(m.params["team_code"], m.params["player"])]
        se = players[pid].season
        if m.params["facet"] == "season":
            assert m.params["season_goals"] == se.goals + sum(1 for t, p in goals if p == pid and t < m.t), m.params
        elif m.params["facet"] == "assists":
            assert m.params["count"] == se.assists + sum(1 for t, p in assists if p == pid and t < m.t), m.params
        elif m.params["facet"] == "apps":
            assert m.params["count"] == se.apps + 1  # this match is one of them
        else:
            continue
        checked += 1
    assert checked > 10


def test_the_scorer_gets_the_goal_added_to_his_season_in_the_demo_insert_match():
    """comeback-135: Fontaine scores at 4393.7 s (71'). A season note about him from then on counts the goal (the review saw 'six' at 4616.8 s)."""
    meta, events, rows, _ = built("comeback", 135)
    fontaine = next(p for p in meta.teams["H"].players if p.name.endswith("Fontaine"))
    pre = fontaine.season.goals
    layers = fl.Layers(meta, events, rows)
    out = layers.run()
    assert layers.match_goals[fontaine.id] == 1
    layers.said_facets, layers.note_at, layers.last_facet = {}, {}, None  # start the notes over, as if none had been said
    fontaine.traits, fontaine.role = [], None  # so that the season is his first fact
    slot = fl._Slot(4616.8, True, 0, fontaine.id, "H")
    kind, params = layers.topic_player(slot)
    assert kind == "player_note" and params["facet"] == "season" and params["season_goals"] == pre + 1
    news = [m for m in out if m.kind == "counter_note" and m.params.get("facet") in ("tally", "tally_first") and m.params["player"] == "Fontaine"]
    assert news and news[0].t > 4393.7 and news[0].params["n"] == pre + 1  # and the goal itself is news in the dead ball that follows


@pytest.mark.parametrize("arc,seed", MATCHES[:3])
def test_every_goal_is_followed_by_its_move_and_its_tally_before_anything_else(arc, seed):
    meta, events, rows, ms = built(arc, seed)
    ev = {e.i: e for e in events}
    names = {(s, p.id): p.name.split()[-1] for s in ("H", "A") for p in meta.teams[s].players}
    goals = [r for r in rows if r["type"] == "shot" and ev[r["i"]].outcome == "goal"]
    assert goals
    moves = [m for m in ms if m.kind == "counter_note" and m.params.get("facet") == "move"]
    assert moves
    for m in moves:
        g = next(r for r in goals if r["eid"] == m.params["window"])
        scorer = names[(g["team"], ev[g["i"]].player)]
        assert m.params["player"] == scorer and scorer not in m.params["chain"] and 2 <= len(m.params["chain"]) <= 3
        assert set(m.params["chain"]) <= {names[(g["team"], p.id)] for p in meta.teams[g["team"]].players}  # his own side, nobody else
        assert m.t >= g["t"] + fl.GOAL_QUIET_S - 1e-6
        text = render_variants(m, "en", "expert")[-1]
        assert scorer in text and all(c in text for c in m.params["chain"]), text


# ---------- lane and direction: where the kick starts, never the path ----------
@pytest.mark.parametrize("arc,seed", MATCHES)
def test_the_lane_is_the_flank_the_kick_leaves_from_and_a_pass_has_no_direction_phrase(arc, seed):
    meta, events, rows, ms = built(arc, seed)
    by_eid = {r["eid"]: r for r in rows}
    ev = {e.i: e for e in events}
    layers = fl.Layers(meta, events, rows)
    n = 0
    for m in ms:
        if m.kind != "pass_kind":
            continue
        assert "dir" not in m.params  # the direction of a pass is said by its type ("cross", "switch", "back") or not at all
        r = by_eid[(m.id - FAST_BASE) // 8]
        e = ev[r["i"]]
        if "lane" in m.params:
            assert m.params["lane"] == layers.side_of(r["team"], e.period, r.get("x", e.x), r.get("y", e.y))
            n += 1
        else:
            assert "pass_type" not in m.params  # a routine short pass: the kicker
    assert n > 20


def test_no_pass_wording_reads_as_the_path_of_the_ball_or_says_a_thing_twice():
    path = {"en": r"\bdown the\b|\balong the\b|\bthrough the middle\b", "de": r"\büber (links|rechts)\b|\bdurch die Mitte\b", "fr": r"\bcôté (gauche|droit)\b|\bdans l'axe\b"}
    for lang in LANGS:
        assert all(v.startswith(("from", "von", "aus", "depuis")) for v in WORDS["lane"][lang].values()), lang
        for style in STYLES:
            for v in T["pass_kind"][lang][style]:
                assert "{dir_word}" not in v and not re.search(path[lang], v), (lang, v)
    total = 0
    for arc, seed in MATCHES:
        for m in built(arc, seed)[3]:
            if m.layer != "fast":
                continue
            for lang in LANGS:
                for style in STYLES:
                    for text in render_variants(m, lang, style):
                        parts = [p.strip().lower() for p in re.split(r"[,.;]", text) if p.strip()]
                        assert len(parts) == len(set(parts)), (m.kind, lang, text)  # "Joué court dans l'axe, dans l'axe." and the like
                        total += 1
    assert total > 10_000


def test_the_insert_switch_leaves_from_the_right_and_says_so():
    meta, events, rows, ms = built("comeback", 135)
    sw = next(m for m in ms if m.kind == "pass_kind" and m.params.get("pass_type") == "switch" and abs(m.t - 4382.7) < 0.01)
    assert sw.params["lane"] == "right"  # it starts on the right and ends on the left
    sw = replace(sw, params={**sw.params, "named": False})  # the wording a name-less switch takes (the rationing may name the target instead)
    en, de, fr = (render_variants(sw, lang, "expert") for lang in LANGS)
    assert "Switched from the right." in en and "Verlagert von rechts." in de and "Jeu renversé depuis la droite." in fr
    assert not any("down the right" in t or "über rechts" in t for t in en + de)


# ---------- the volume layer is names and places, not the mechanics of routine passes ----------
@pytest.mark.parametrize("arc,seed", MATCHES)
def test_a_routine_short_pass_names_the_kicker_with_what_the_kick_shows(arc, seed):
    """A routine kick is called with the kicker's name, with what the kick shows. When its kicker was named a moment ago (his receipt, a tackle, a duel) the
    kick is not called, or, when it shows something (closed down, hit hard and low) and now and then, called without his name."""
    meta, events, rows, ms = built(arc, seed)
    by_eid = {r["eid"]: r for r in rows}
    eng, mb = FactEngine(meta), None
    mb = MomentBuilder(eng)
    owned = {ev.i for ev in events for m in mb.feed(ev, eng.ingest(ev)) if m.kind not in REPLACED_KINDS}  # a skeleton call (a corner) owns its kick
    shorts = [r for r in rows if r["type"] == "pass" and r["pass_type"] == "short" and not r.get("first_time") and (r["i"] not in owned or r.get("implicit"))]
    said = [m for m in ms if m.kind == "pass_kind" and "pass_type" not in m.params]
    assert said and 0.2 * len(shorts) < len(said) < len(shorts)  # some kicks are not called: their kicker has just been named
    pressed = driven = bare = 0
    for m in said:
        r = by_eid[(m.id - FAST_BASE) // 8]
        assert r["pass_type"] == "short" and ("pressed" in m.params) == bool(r["pressure"].get("under"))
        pressed += "pressed" in m.params
        driven += "driven" in m.params
        assert not ("pressed" in m.params and "driven" in m.params)
        if m.params.get("name_said"):  # called without the kicker, only for what the kick shows
            bare += 1
            assert m.params["kicker_said"] and not m.params["named"] and ("pressed" in m.params or "driven" in m.params), m.params
        else:
            assert m.params["named"] and not m.params.get("kicker_said"), m.params
        for lang in LANGS:
            for style in STYLES:
                texts = render_variants(m, lang, style)
                assert len(texts) >= (1 if m.params.get("name_said") else 4)  # the rota has room: no wording is the only one that fits
                for text in texts:
                    assert (m.params["player"] in text) == (not m.params.get("name_said")) and "target" not in m.params  # the kicker; the receipt names the receiver
                    assert not re.search(r"\bshort\b|\bkurz\b|\bcourt\b", text, re.I), text
    assert pressed and driven and bare  # "Okafor, under pressure, plays it on", "Okafor drives it", and "Played on under pressure." exist
    with_type = [m for m in ms if m.kind == "pass_kind" and "pass_type" in m.params]
    assert all(m.params["pass_type"] != "short" for m in with_type)
    assert all(m.params["named"] and "target" in m.params for m in with_type if m.params["pass_type"] == "first_time")  # a one-touch pass names both


def test_a_full_match_is_names_and_verbs_not_a_position_readout_and_no_near_identical_line_loops(tmp_path):
    """The review measured comeback-7 en/expert: 'Under control.' 231 times, 'In the final third.' 215, 'Dead centre, in the final third.' and its mirror image
    about 110 each, name-less receipt fragments 34 to 38% of the segments. Now: names and verbs, a zone only on a rare turn and in one order."""
    from matchvoice.evaluation import density
    b = LIB.bundle("comeback-7")
    msgs = density.run_span(b, 0.0, None)
    segs, _, _ = density.segments(msgs)
    names = density.Names(b)
    shown = {m.id for m in built("comeback", 7)[3] if m.params.get("name_said") and m.kind == "pass_kind"}
    zone = {"en": r"\b(final third|middle third|own third|dead centre|left side|right side|out on the (left|right)|in the middle)\b",
            "de": r"\b(letzten Drittel|mittleren Drittel|eigenen Drittel|links außen|rechts außen|in der Mitte)\b",
            "fr": r"\b(dernier tiers|tiers médian|propre tiers|côté (gauche|droit)|(, |est )dans l'axe)\b"}  # "Dans l'axe pour X" is the direction of the incoming ball, not a zone
    for key, lang in (("en/expert", "en"), ("en/beginner", "en"), ("de/beginner", "de"), ("de/expert", "de"), ("fr/beginner", "fr"), ("fr/expert", "fr")):
        mine = [x for x in segs if x.ch == KEYS.index(key)]
        n = len(mine)
        nameless = [x for x in mine if x.kind in ("touch", "pass_kind") and not names.count(x.text) and x.m not in shown]  # what a kick shows ("Played on under pressure.") is no position readout
        assert len(nameless) / n < 0.08, (key, len(nameless) / n)  # was 34 to 38%
        assert len([x for x in mine if x.m in shown]) / n < 0.1, key  # and it is rare
        zoned = [x for x in mine if re.search(zone[lang], x.text, re.I) and x.kind == "touch"]
        assert len(zoned) / n < 0.03, (key, len(zoned) / n)
        for a, b_ in zip(zoned, zoned[1:]):
            assert b_.s - a.s >= fl.PLACE_EVERY_S - 1.0, (key, a.text, b_.text)  # never twice in a row, never within PLACE_EVERY_S
        counts: dict[str, int] = {}
        shapes = [names.rx.sub("_", x.text) for x in mine]
        for sh in shapes:
            counts[sh] = counts.get(sh, 0) + 1
        top, k = max(counts.items(), key=lambda kv: kv[1])
        assert k / n < 0.15, (key, top, k / n)  # no wording is a loop (was 12% for one line, 20% for one shape)
        assert not any(re.fullmatch(r"(Under control|Unter Kontrolle|Sous contrôle|The ball is received|Safely received)\.?", x.text) for x in mine), key
        run = best = 0
        prev = None
        for sh in shapes:  # and no stretch of the commentary is one line repeated (a move passed on is "A to B", "B finds C", "C on the ball")
            run = run + 1 if run and sh == prev else 1
            prev = sh
            best = max(best, run)
        assert best <= 3, (key, best)
        # two zone words never meet in one line, in either order
        assert not any(len(re.findall(zone[lang], x.text, re.I)) > 1 for x in mine), key


# ---------- tempo: the side that has the ball, with hysteresis ----------
def _layers() -> fl.Layers:
    meta, events, rows, _ = built("comeback", 7)
    return fl.Layers(meta, events, rows)


def _feed(layers: fl.Layers, h: int, a: int, t: float = 600.0) -> None:
    """h and a completed passes of the home and the away side spread over the three minutes before t."""
    layers.completed["H"].clear(), layers.completed["A"].clear()
    for side, n in (("H", h), ("A", a)):
        layers.completed[side].extend(t - 180.0 + 180.0 * (k + 0.5) / max(n, 1) for k in range(n))


def test_a_side_that_lacks_the_ball_does_not_slow_the_game_down():
    L = _layers()
    _feed(L, 10, 40)  # 3.3 passes a minute, against 13.3: H is under siege, not slowing anything
    assert L._class_tempo("H", 600.0) == "measured" and L._class_tempo("A", 600.0) == "high" and L.tempo_class["H"] == "measured"
    _feed(L, 10, 10)  # both slow, neither has the ball: no claim for either side
    assert L._class_tempo("H", 600.0) == "measured" and L._class_tempo("A", 600.0) == "measured"
    _feed(L, 10, 4)  # H has 71% of the passes at 3.3 a minute: now it is a claim
    assert L._class_tempo("H", 600.0) == "slow" and L._class_tempo("A", 600.0) == "measured"


def test_the_tempo_class_has_hysteresis_and_enters_on_a_clear_rate():
    L = _layers()
    _feed(L, 12, 8)  # 4.0 a minute: between the limits, never enough to enter
    assert L._class_tempo("H", 600.0) == "measured"
    _feed(L, 10, 8)  # 3.3 a minute with 56% of the passes: enters
    assert L._class_tempo("H", 600.0) == "slow"
    L.tempo_class["H"] = "slow"
    _feed(L, 12, 8)  # 4.0 a minute: stays slow, as it is above the entry limit but under the exit limit
    assert L._class_tempo("H", 600.0) == "slow"
    _feed(L, 15, 8)  # 5.0 a minute: out
    assert L._class_tempo("H", 600.0) == "measured"
    _feed(L, 30, 8)  # 10 a minute: high
    assert L._class_tempo("H", 600.0) == "high"
    L.tempo_class["H"] = "high"
    _feed(L, 26, 8)  # 8.7 a minute: stays high
    assert L._class_tempo("H", 600.0) == "high"
    _feed(L, 23, 8)  # 7.7 a minute: out
    assert L._class_tempo("H", 600.0) == "measured"


@pytest.mark.parametrize("arc,seed", MATCHES)
def test_every_tempo_note_is_about_the_side_that_has_the_ball(arc, seed):
    meta, events, rows, ms = built(arc, seed)
    receipts = {s: [r["t"] for r in rows if r["type"] == "receipt" and r["team"] == s] for s in ("H", "A")}
    notes = [m for m in ms if m.kind == "tempo_note"]
    assert notes
    times = [m.t for m in notes]
    assert len(times) == len(set(times))  # never both sides at one slot
    for m in notes:
        side, other = m.params["team_code"], "A" if m.params["team_code"] == "H" else "H"
        own = sum(m.t - fl.TEMPO_WINDOW_S <= t < m.t for t in receipts[side])
        theirs = sum(m.t - fl.TEMPO_WINDOW_S <= t < m.t for t in receipts[other])
        assert own / (own + theirs) >= fl.TEMPO_HAS_BALL - 1e-9, (m.t, own, theirs)
        ppm = own / (fl.TEMPO_WINDOW_S / 60)
        assert (ppm < fl.TEMPO_SLOW_PPM) if m.params["facet"].startswith("slow") else (ppm > fl.TEMPO_HIGH_PPM), (m.params["facet"], ppm)


def test_the_tempo_wording_is_a_claim_the_lexicon_knows():
    slow = _moment("tempo_note", facet="slow", team="Wexmoor", team_code="H")
    high = _moment("tempo_note", facet="high", team="Wexmoor", team_code="H")
    assert _verdict("Wexmoor are in no hurry on the ball.", slow).ok and not _verdict("Wexmoor are in no hurry on the ball.", high).ok
    assert _verdict("Wexmoor are playing at a real tempo.", high).ok and not _verdict("Wexmoor are playing at a real tempo.", slow).ok
    assert not _verdict("Wexmoor are slowing the game right down.", high).ok  # the old wording is a tactical claim of its own
    assert _verdict("Wexmoor lässt sich Zeit am Ball.", slow, "de").ok and not _verdict("Wexmoor lässt sich Zeit am Ball.", high, "de").ok
    assert _verdict("Wexmoor prend son temps avec le ballon.", slow, "fr").ok and not _verdict("Wexmoor prend son temps avec le ballon.", high, "fr").ok
    for lang in LANGS:
        for facet, text in WORDS["tempo_note"][lang].items():
            m = _moment("tempo_note", facet=facet, team="Wexmoor", team_code="H")
            assert _verdict(text.format(team="Wexmoor") + ".", m, lang).ok, (lang, facet)


# ---------- press wording: the idioms ----------
def test_the_press_wordings_are_idiomatic_and_do_not_say_the_presser_has_the_ball():
    assert WORDS["press_on"]["de"] == {"high": "läuft früh an", "low": "geht eng drauf"}
    assert WORDS["press_on"]["en"]["high"] == "presses high" and WORDS["press_on"]["fr"]["high"] == "presse haut"
    flat = " ".join(w for lang in LANGS for w in WORDS["press_on"][lang].values())
    for gone in ("bleibt eng am Ball", "an dieser Stelle", "à cet endroit", "up here"):
        assert gone not in flat
    high = _moment("press_on", presser="Abara", player="Okafor", facet="high", team="Wexmoor", team_code="H")
    low = _moment("press_on", presser="Abara", player="Okafor", facet="low", team="Wexmoor", team_code="H")
    assert _verdict("Abara läuft früh an.", high, "de").ok and _verdict("Abara läuft früh an.", low, "de").violations[0].code == "claim_unsupported"
    assert _verdict("Abara geht eng drauf.", low, "de").ok


# ---------- the director: fragments take turns and a kick fragment ends with the ball's flight ----------
def test_fast_fragments_take_turns_and_do_not_repeat_a_wording_while_others_fit():
    wordings = ["Taken down.", "Under control.", "Settled on it.", "{p}, in the final third.", "In the final third, left side."]
    d = ChannelDirector(lambda m: [w.replace("{p}", m.params["player"]) for w in wordings], "en", 1.0, captions_first=True, dense=True,
                        voice_wait_s=lambda m: float("inf"))
    for i in range(30):
        d.push(Moment(i, 3.0 * i, "1", "touch", "pbp", 26, 2.0, {"player": f"Name{i}"}, layer="fast", voice_wait=2.0))
    d.advance(1e6)
    said = [sp.text.replace(f"Name{sp.moment_id}", "{p}") for _, sp in d.drain() if _ == "start"]
    assert len(said) == 30
    assert all(a != b for a, b in zip(said, said[1:]))
    assert set(said) == set(wordings) and all(said.count(w) == 6 for w in wordings)  # a rota, not one favourite (the longest used to win every time)


def test_a_kick_fragment_ends_with_the_flight_of_the_ball_so_the_receipt_gets_the_voice():
    d = ChannelDirector(lambda m: ["Switch.", "Switched from the right.", "Switched from the right, a long way."], "en", 1.0, captions_first=True, dense=True,
                        voice_wait_s=lambda m: float("inf"))
    d.push(Moment(0, 0.0, "1", "pass_kind", "pbp", 32, 4.0, {"arr": 1.4}, layer="fast", voice_wait=4.0))  # lands 1.4 s after the kick
    d.advance(1e6)
    spoken = [sp for k, sp in d.drain() if k == "start"]
    assert spoken[0].text == "Switch."  # the longer wordings would run 1 s past the arrival plus the slack
    d = ChannelDirector(lambda m: ["Switch.", "Switched from the right.", "Switched from the right, a long way."], "en", 1.0, captions_first=True, dense=True,
                        voice_wait_s=lambda m: float("inf"))
    d.push(Moment(0, 0.0, "1", "pass_kind", "pbp", 32, 4.0, {"arr": 4.0}, layer="fast", voice_wait=4.0))
    d.advance(1e6)
    assert [sp.text for k, sp in d.drain() if k == "start"][0].startswith("Switched from the right")


# ---------- phase 3, round 3: names and verbs, the chain of the insert, no meta leads, the dead ball and the numbers ----------
def test_no_wording_of_the_bank_opens_with_a_meta_lead_in_any_language():
    flat = [(kind, lang, style, v) for kind, langs in T.items() for lang, styles in langs.items() for style, vs in styles.items() for v in vs]
    flat += [(table, lang, code, text) for table, langs in WORDS.items() for lang, codes in langs.items() for code, text in codes.items()]
    assert len(flat) > 1000
    for where in flat:
        assert not META_LEADS.search(where[3]), where
    lead_words = re.compile(r"worth noting|worth a mention|good to know|bemerkenswert:|auffällig:|à noter :|bon à savoir|gut zu wissen", re.I)
    assert not any(lead_words.search(w[3]) for w in flat)


@pytest.mark.parametrize("arc,seed", MATCHES)
def test_the_long_sentences_are_real_sentences_of_twelve_words_in_every_language(arc, seed):
    """A `note_long` is a connected sentence built from facts the builder holds, not a short line with a lead in front of it."""
    meta, events, rows, ms = built(arc, seed)
    n = 0
    for m in ms:
        if m.kind != "counter_note":
            continue
        for lang in LANGS:
            p = render_params(m, lang)
            if "note_long" in p:
                assert len(p["note_long"].split()) >= 12, (m.params["facet"], lang, p["note_long"])
                assert len(p["note_long"]) > len(p["note"]) and p["note_long"].startswith(p["note"][:6]) is not None
                n += 1
    assert n > 200
    chances = [m for m in ms if m.kind == "counter_note" and m.params["facet"].startswith("chance_")]
    assert chances and all(m.params.get("chain") and render_params(m, "en")["note_long"].startswith("After a move through") for m in chances)  # a recap of the build-up


@pytest.mark.parametrize("arc,seed", MATCHES[:3])
def test_every_goal_is_followed_by_its_move_then_its_tally_before_anything_else(arc, seed):
    meta, events, rows, ms = built(arc, seed)
    ev = {e.i: e for e in events}
    names = {(s, p.id): p.name.split()[-1] for s in ("H", "A") for p in meta.teams[s].players}
    goals = [r for r in rows if r["type"] == "shot" and ev[r["i"]].outcome == "goal"]
    assert goals
    for g in goals:
        scorer = names[(g["team"], ev[g["i"]].player)]
        after = sorted((m for m in ms if m.layer == "context" and m.params["window"] == g["eid"]), key=lambda m: m.t)
        assert after and after[0].t >= g["t"] + fl.GOAL_QUIET_S - 1e-6
        facets = [m.params["facet"] for m in after]
        move = [m for m in after if m.params["facet"] == "move"]
        tally = [m for m in after if m.params["facet"] in ("tally", "tally_first")]
        assert tally and tally[0].params["player"] == scorer  # the tally is never lost
        assert move and move[0] is after[0], facets  # the move first, even for a scorer who had a move before (the key of a news item holds the score it made)
        assert tally[0] is after[1], facets  # then the tally, before any other line
        if move:
            m = move[0]
            assert m.params["player"] == scorer and scorer not in m.params["chain"] and 1 <= len(m.params["chain"]) <= 3
            assert set(m.params["chain"]) <= {names[(g["team"], p.id)] for p in meta.teams[g["team"]].players}  # his own side, nobody else
            text = render_variants(m, "en", "expert")[-1]
            assert scorer in text and all(c in text for c in m.params["chain"]), text
            assert (m.params["goals_h"], m.params["goals_a"]) == score_at(events, g["t"] + 0.001)
        t = tally[0]
        assert t.params["n"] >= 1 and (t.params["facet"] == "tally_first") == (t.params["n"] == 1)


@pytest.mark.parametrize("key,lang", [("en/expert", "en"), ("de/beginner", "de"), ("fr/expert", "fr")])
def test_the_goal_build_up_of_the_insert_names_the_chain_and_the_long_ball_its_target(insert_run, key, lang):
    """comeback-135, 4381 to 4402 s: Ibsen wins it, the switch, Rasmussen (3.6 s on the ball), the long ball to Tavares, the pass to Fontaine, the goal."""
    r, msgs, d = insert_run
    from matchvoice.evaluation import density
    segs, _, _ = density.segments(msgs)
    mine = sorted((x for x in segs if x.ch == KEYS.index(key)), key=lambda x: x.s)
    texts = [x.text for x in mine]
    first_at = {name: next(i for i, t in enumerate(texts) if name in t) for name in ("Ibsen", "Rasmussen", "Tavares", "Fontaine")}
    goal_at = next(i for i, x in enumerate(mine) if x.kind == "shot_goal")
    assert first_at["Ibsen"] < first_at["Rasmussen"] < first_at["Tavares"] < first_at["Fontaine"] <= goal_at, texts  # the chain, in the order of the move
    assert mine[first_at["Ibsen"]].kind == "duel"
    long_ball = next(x for x in mine if x.kind == "pass_kind" and "Tavares" in x.text)
    assert "Tavares" in long_ball.text and long_ball.s < 8.6 + d["start"] + 1.0  # the long ball is called while it flies, with its target
    assert any(x.kind == "pass_kind" and "Rasmussen" in x.text for x in mine) and any(x.kind == "touch" for x in mine)  # the switch names him, and the ball he holds is called
    assist = next(x for x in mine if x.kind == "pass_kind" and "Fontaine" in x.text)
    assert assist.s < d["start"] + 12.7 and not any("Tavares" in x.text for x in mine if x.kind == "touch")  # the pass to Fontaine is the news, not a receipt
    zone = {"en": r"third|dead centre|left side|right side", "de": r"Drittel|auf der (linken|rechten) Seite", "fr": r"tiers|côté (gauche|droit)"}[lang]
    assert not any(re.search(zone, x.text) for x in mine), texts  # no position readout in the build-up
    assert all(x.kind != "goal_analysis" or x.e > x.s for x in mine)


def test_a_template_stand_in_for_the_goal_analysis_is_not_perishable_behind_the_goal_call(insert_run):
    """The beginner goal call runs 5.2 s; the analysis fallback used to be perishable after 4 s and was skipped. Now it is spoken on every channel."""
    r, msgs, d = insert_run
    skipped = [(m["ch"], m["m"]) for m in msgs if m["k"] == "voice" and m.get("skip")]
    assert not skipped, skipped
    from matchvoice.evaluation import density
    segs, _, _ = density.segments(msgs)
    assert {x.ch for x in segs if x.kind == "goal_analysis"} == set(range(6))
    for x in segs:
        if x.kind == "shot_goal":  # the analysis follows the call
            nxt = next(y for y in segs if y.ch == x.ch and y.kind == "goal_analysis")
            assert nxt.s >= x.e - 1e-6


def test_the_dead_ball_slots_of_the_builder_are_as_far_apart_as_the_director_voices_them():
    from matchvoice.commentary.director import CONTEXT_DEAD_S as DEAD, CONTEXT_PLAY_S as PLAY
    assert fl.DEAD_STEP_S == DEAD + fl.SLOT_SLACK_S and fl.SLOT_SLACK_S * 3 >= 3.0 - 1e-9 or fl.SLOT_SLACK_S > 0  # room for a late start, so the next line is not too early
    assert fl.DEAD_STEP_S - DEAD > 0 and fl.CONTEXT_DEAD_S == DEAD and fl.CONTEXT_PLAY_S == PLAY
    for arc, seed in MATCHES:
        ctx = [m for m in built(arc, seed)[3] if m.layer == "context"]
        last = -1e9
        per_window: dict[int, int] = {}
        for m in ctx:
            gap = fl.CONTEXT_DEAD_S if m.params["dead"] else fl.CONTEXT_PLAY_S
            assert m.t - last >= gap + fl.SLOT_SLACK_S - 1e-3, (arc, seed, m.t, last)  # the director would drop it otherwise
            last = m.t
            if m.params["dead"]:
                per_window[m.params["window"]] = per_window.get(m.params["window"], 0) + 1
        assert per_window and max(per_window.values()) <= CONTEXT_PER_WINDOW  # three to a dead-ball window, as the director allows


def test_every_context_line_of_a_dead_ball_is_voiced_on_every_channel(tmp_path):
    """The review: of the five goals of the full matches two lost their tally (built, never spoken). The post-goal lines are all voiced now."""
    from matchvoice.evaluation import density
    for match in ("comeback-7", "unlucky-7"):
        b = LIB.bundle(match)
        msgs = density.run_span(b, 0.0, None)
        segs, say_by, voice_by = density.segments(msgs)
        spoken = {(x.ch, x.m) for x in segs}
        meta, events, rows, ms = built(*match.split("-")[:1], int(match.split("-")[1]))
        goal_windows = {r["eid"] for r in rows if r["type"] == "shot" and next(e for e in events if e.i == r["i"]).outcome == "goal"}
        post = [m for m in ms if m.layer == "context" and m.params["window"] in goal_windows]
        assert post
        for m in post:
            assert all((ch, m.id) in spoken for ch in range(6)), (match, m.params["facet"], m.t)
        dead = [m for m in ms if m.layer == "context" and m.params["dead"]]
        got = sum((KEYS.index("en/expert"), m.id) in spoken for m in dead)
        assert got / len(dead) > 0.85, (match, got, len(dead))  # a dead-ball line is rarely lost any more


def test_a_dead_ball_takes_the_long_wording_every_time_it_has_one():
    """The live director avoids the wording slot it used last for a kind; for the dead-ball context lines that made every second sentence the short one."""
    d = ChannelDirector(lambda m: [f"Short {m.id}.", f"A long wording number {m.id} that a dead ball has the time for."], "en", 1.0, captions_first=True, dense=True,
                        voice_wait_s=lambda m: float("inf") if m.voice_wait is None else m.voice_wait)
    for i in range(4):
        d.push(ctxm(i, i * 9.0, dead=True, window=i, ttl=200.0))
    d.advance(500.0)
    said = [sp.text for k, sp in d.drain() if k == "start"]
    assert len(said) == 4 and all(t.startswith("A long wording") for t in said), said


def test_the_stats_wait_for_a_dead_ball_or_a_long_hold_and_never_take_the_voice_in_play():
    for arc, seed in MATCHES:
        ctx = [m for m in built(arc, seed)[3] if m.layer == "context" and m.kind == "counter_note"]
        stat = [m for m in ctx if re.sub(r"_\d$", "", m.params["facet"]) in fl.STAT_FACETS]
        assert stat and all(m.params["dead"] or m.params["long"] for m in stat)  # the long sentence, with the other side's figure
        assert len({re.sub(r"_\d$", "", m.params["facet"]) for m in stat}) >= 5 and "shots_total" in {re.sub(r"_\d$", "", m.params["facet"]) for m in stat}


def test_a_french_sentence_with_two_perfects_is_still_french_to_the_verifier():
    ver = Verifier(built("comeback", 7)[0])
    text = "Valdes est gaucher, a réussi dix-sept passes jusqu'ici et a disputé vingt-cinq matches cette saison."
    assert ver.detect_lang(text) == "fr"
    assert ver.detect_lang("The keeper has made a save and a second one is coming in the game.") == "en"


@pytest.mark.parametrize("arc,seed", MATCHES[:2])
def test_a_receipt_never_says_a_sentence_the_kick_that_brought_it_has_among_its_wordings(arc, seed):
    """'Rahimi finds Arnaud.' for the kick and again for the receipt would be one sentence twice in a row."""
    meta, events, rows, ms = built(arc, seed)
    by_id = {m.id: m for m in ms}
    by_eid = {r["eid"]: r for r in rows}
    n = 0
    for m in ms:
        if m.kind != "touch":
            continue
        kick = by_id.get(FAST_BASE + 8 * by_eid[(m.id - FAST_BASE) // 8]["pass_eid"] + FAST[ "pass_kind"].slot)
        if kick is None:
            continue
        for lang in LANGS:
            for style in STYLES:
                assert not set(render_variants(m, lang, style)) & set(render_variants(kick, lang, style)), (lang, style, m.params)
        n += 1
    assert n > 100


def test_the_wordings_the_review_called_bad_are_gone():
    """de 'auf' twice in a line, 'Lemaire, dead centre.', a clearance with a target, 'X gets tight on the ball', and a docstring that still rations by thirds."""
    for m in (m for arc, seed in MATCHES[:3] for m in built(arc, seed)[3] if m.layer == "fast"):
        for style in STYLES:
            for text in render_variants(m, "de", style):
                assert len(re.findall(r"\bauf\b", text)) <= 1, text
            for text in render_variants(m, "en", style):
                assert "dead centre" not in text and "gets tight on the ball" not in text, text
    assert WORDS["press_on"]["en"]["low"] == "gets tight" and WORDS["wing"]["en"]["centre"] == "in the middle"
    src = open(fl.__file__, encoding="utf-8").read()
    assert not re.search(r"every (second|third|fourth) (fast )?fragment", src)
    assert fl.NAMED_EVERY == 2 and "never two in a row" in fl.__doc__ and "at most one name-less fragment in a row" in fl.Layers.fast.__doc__


@pytest.mark.parametrize("arc,seed", MATCHES)
def test_no_name_is_said_twice_in_a_routine_hop(arc, seed):
    """The review read 'Lindqvist finds Lemaire. / Inside to Lemaire.' 242 times in one match and 'Lemaire to Wrenfield. / Wrenfield, from Lemaire.' 24 to 39 times."""
    meta, events, rows, ms = built(arc, seed)
    kicks = {(m.id - FAST_BASE) // 8: m for m in ms if m.kind == "pass_kind"}
    by_eid = {r["eid"]: r for r in rows}
    n = 0
    for m in ms:
        if m.kind != "touch":
            continue
        kick = kicks.get(by_eid[(m.id - FAST_BASE) // 8]["pass_eid"])
        if kick is None or "pass_type" in kick.params:
            continue
        assert "kicker" not in m.params and "target" not in kick.params  # the kick named the kicker, the receipt names the receiver
        for lang in LANGS:
            for style in STYLES:
                assert all(m.params["player"] not in text for text in render_variants(kick, lang, style)), (kick.params, m.params)
                assert all(kick.params["player"] not in text for text in render_variants(m, lang, style)), (kick.params, m.params)
        n += 1
    assert n > 20


def test_a_scorers_second_goal_has_its_move_and_its_tally_like_his_first():
    meta, events, rows, ms = built("comeback", 7)
    ev = {e.i: e for e in events}
    goals = [r for r in rows if r["type"] == "shot" and ev[r["i"]].outcome == "goal"]
    twice = [p for p in {ev[r["i"]].player for r in goals} if sum(ev[r["i"]].player == p for r in goals) > 1]
    assert twice  # Rahimi scores at 4392 s and again at 5511 s
    for pid in twice:
        for g in (r for r in goals if ev[r["i"]].player == pid):
            facets = [m.params["facet"] for m in sorted(ms, key=lambda m: m.t) if m.layer == "context" and m.params["window"] == g["eid"]]
            assert facets[:2] == ["move", "tally"], facets


@pytest.mark.parametrize("arc,seed", MATCHES)
def test_the_same_fact_is_not_said_twice_in_a_row_and_a_zero_is_no_contrast(arc, seed):
    """The review: 'Marlow have had nine shots, and Tamsworth three' then 'Tamsworth have had three shots, and Marlow nine' 8 s later; shots on target and then
    the saves with the same numbers; three tactical notes in 30 s; the tempo note six times; 'and Tamsworth have had zero'; 'ninety-nine percent ... zero percent'."""
    meta, events, rows, ms = built(arc, seed)
    ctx = [m for m in sorted(ms, key=lambda m: m.t) if m.layer == "context"]
    counters = [m for m in ctx if m.kind == "counter_note"]
    base = lambda m: re.sub(r"_\d$", "", m.params["facet"])
    for group in (("on_target_total", "saves_total"), *((f,) for f in fl.STAT_FACETS if f not in ("on_target_total", "saves_total"))):
        said = [m.t for m in counters if base(m) in group]
        assert all(b - a >= fl.STAT_GAP_S - 1e-6 for a, b in zip(said, said[1:])), (group, said)  # either side's figure, 120 s apart
    for side in ("H", "A"):
        tactic = [m.t for m in ctx if m.kind in fl.TACTIC_KINDS and m.params["team_code"] == side]
        assert all(b - a >= fl.TACTIC_GAP_S - 1e-6 for a, b in zip(tactic, tactic[1:])), (side, tactic)
        tempo = [m for m in ctx if m.kind == "tempo_note" and m.params["team_code"] == side]
        assert len(tempo) <= fl.TEMPO_MAX and len({m.params["facet"] for m in tempo}) == len(tempo)  # a capped note whose second wording is another
    for m in counters:
        assert m.params.get("m") != 0 and m.params.get("sh") != 0 and m.params.get("so") != 0, m.params
        if base(m) == "recent_ball":
            assert 0 < m.params["n"] < 100 and m.params.get("m", 100 - m.params["n"]) == 100 - m.params["n"]
        if base(m) == "possession":
            assert m.params.get("m", 100 - m.params["n"]) == 100 - m.params["n"]
        if base(m) == "drought":
            assert m.params["m"] > 0  # the other side shot meanwhile: neither side without a shot is no news
    tallied = {m.params["player"] for m in counters if m.params["facet"] in ("tally", "tally_first")}
    assert not [m for m in ctx if m.kind == "player_note" and m.params["player"] in tallied and any(m.params.get(k) == "season" for k in ("facet", "facet2", "facet3"))
                and any(t.params["player"] == m.params["player"] and t.t < m.t for t in counters if t.params["facet"] in ("tally", "tally_first"))]  # his season goals were just said


# ---------- phase 3 review fixes, round 5 ----------
def _names_in(text: str, surnames: set[str]) -> set[str]:
    return {n for n in surnames if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text)}


@pytest.mark.parametrize("arc,seed", MATCHES)
def test_no_player_is_named_by_two_fast_fragments_in_a_row_within_the_name_gap(arc, seed):
    """The round 4 review: 'Inside to Wrenfield.' and then 'Wrenfield gets it away.' (237 to 404 per match and channel): the double naming had moved, not gone.
    A name that every wording of a fragment says is not said again by every wording of the next fast fragment within NAME_GAP_S."""
    meta, events, rows, ms = built(arc, seed)
    surnames = {p.name.split()[-1] for t in meta.teams.values() for p in t.players}
    fast = sorted((m for m in ms if m.layer == "fast"), key=lambda m: (m.t, (m.id - FAST_BASE) // 8))
    pairs = clash = 0
    for lang in LANGS:
        for style in STYLES:
            sure = [set.intersection(*(_names_in(t, surnames) for t in render_variants(m, lang, style))) for m in fast]
            for (a, na), (b, nb) in zip(zip(fast, sure), list(zip(fast, sure))[1:]):
                if b.t - a.t <= fl.NAME_GAP_S:
                    pairs += 1
                    clash += bool(na & nb and a.kind != "press_on" and b.kind != "press_on")
    assert pairs > 1000 and clash <= 0.01 * pairs, (clash, pairs)  # a ball that comes back to a player who held it a moment ago is the only case left


@pytest.mark.parametrize("arc,seed", MATCHES)
def test_a_routine_kick_whose_kicker_was_just_named_is_not_called_with_his_name(arc, seed):
    meta, events, rows, ms = built(arc, seed)
    fast = sorted((m for m in ms if m.layer == "fast"), key=lambda m: (m.t, (m.id - FAST_BASE) // 8))
    said_at: dict[str, float] = {}
    for m in fast:
        if m.kind == "pass_kind" and "pass_type" not in m.params:
            recent = m.t - said_at.get(m.params["player"], -1e9) < fl.NAME_GAP_S
            assert not recent or m.params.get("name_said"), (m.t, m.params)  # named a moment ago: no kick with his name
            assert not m.params.get("name_said") or m.params["kicker_said"]  # (a tackle or a duel of the skeleton can have named him too)
        if m.params.get("named", True):
            for key in ("player", "target", "winner", "presser", "taker"):
                if key in m.params and not m.params.get("name_said"):
                    said_at[m.params[key]] = m.t
    routine = [r for r in rows if r["type"] == "pass" and r["pass_type"] == "short" and not r.get("first_time")]
    called = [m for m in fast if m.kind == "pass_kind" and "pass_type" not in m.params]
    assert len(called) < 0.6 * len(routine)  # most routine kicks follow the receipt that named their kicker: they are not called
    assert not [m for m in called if m.params.get("name_said") and not (m.params.get("pressed") or m.params.get("driven"))]  # and the ones called without him show something


def test_a_typed_pass_whose_kicker_was_just_named_names_only_its_target():
    meta, events, rows, ms = built("comeback", 7)
    typed = [m for m in ms if m.kind == "pass_kind" and m.params.get("kicker_said") and "pass_type" in m.params and "target" in m.params]
    assert len(typed) > 5
    for m in typed:
        for lang in LANGS:
            for style in STYLES:
                assert all(m.params["player"] not in t for t in render_variants(m, lang, style)), (m.params, lang, style)


@pytest.mark.parametrize("arc,seed", MATCHES)
def test_the_context_layer_is_not_a_ticker(arc, seed):
    """The round 4 review: 125 of 184 context lines were counters ('move of N passes' 11 times, fouls 11, 'gone long' 9, throw-ins and goal kicks 6, three stat lines
    in 14 s), the pass count of one player 4 times, the 'no shot for N minutes' line 4 to 6 times, a pass streak said twice, the same shots said as news and as a stat."""
    meta, events, rows, ms = built(arc, seed)
    ctx = [m for m in sorted(ms, key=lambda m: m.t) if m.layer == "context"]
    counters = [m for m in ctx if m.kind == "counter_note"]
    base = lambda m: re.sub(r"_\d$", "", m.params["facet"])
    minor = [m for m in counters if base(m) in fl.STAT_FACETS or base(m) in fl.MINOR_NEWS]
    assert all(b.t - a.t >= fl.MINOR_GAP_S - 1e-6 for a, b in zip(minor, minor[1:]))  # no stat line behind another
    for facet, cap in fl.NEWS_MAX.items():
        assert sum(base(m) == facet for m in counters) <= cap, facet
    for facet in fl.STAT_FACETS:
        for side in ("H", "A"):
            assert sum(base(m) == facet and m.params["team_code"] == side for m in counters) <= fl.STAT_MAX_BY.get(facet, fl.STAT_MAX), (facet, side)
    assert len(counters) < 0.62 * len(ctx)  # was 68%
    assert len(ctx) / (ms[-1].t / 60) < 1.8  # context lines a minute (was 1.9)
    # an idea (sit deep, press high, push on) is said once per side in a match, whichever of shape, press and phase says it
    ideas = [(m.params["team_code"], fl.TACTIC_IDEA[m.params["facet"]]) for m in ctx if m.kind in fl.TACTIC_KINDS]
    assert len(ideas) == len(set(ideas))
    # the pass count of a player is said once
    passes = [m.params["player"] for m in ctx if m.kind == "player_note" and any(str(m.params.get(k, "")).startswith("passes") for k in ("facet", "facet2", "facet3"))]
    assert len(passes) == len(set(passes))
    # a pass streak and the end of the same move are one fact
    for end in (m for m in counters if base(m) == "spell_end"):
        assert not [s for s in counters if base(s) in ("passes", "passes_2") and s.params["team_code"] == end.params["team_code"]
                    and s.params["n"] == end.params["n"] and 0 <= end.t - s.t <= 60.0]
    # the nth shot and the shots stat do not give the same figures
    news = [m for m in counters if base(m) == "shots"]
    for st in (m for m in counters if base(m) == "shots_total" and "m" in m.params):
        for n in news:
            other = lambda c: "A" if c == "H" else "H"
            said = {n.params["team_code"]: n.params["nth"], other(n.params["team_code"]): n.params.get("so")}
            now = {st.params["team_code"]: st.params["n"], other(st.params["team_code"]): st.params["m"]}
            assert not (0 <= st.t - n.t <= 120.0 and said == now), (n.params, st.params)
    for m in counters:
        for lang in LANGS:
            assert not any(re.search(r"(?<![-\w])one (times|shots)", t) for style in STYLES for t in render_variants(m, lang, style)), m.params


def test_a_count_of_one_is_not_times():
    m = Moment(id=1, t=1.0, clock="21", kind="counter_note", voice="analyst", priority=40, ttl=8.0,
               params={"facet": "long_total", "team": "Tamsworth", "team_code": "H", "other": "Marlow", "n": 6, "m": 1, "dead": True, "long": True}, layer="context")
    assert "Marlow have gone long once" in render_params(m, "en")["note_long"] and "one times" not in render_params(m, "en")["note_long"]
    m.params["m"] = 3
    assert "Marlow have gone long three times" in render_params(m, "en")["note_long"]
