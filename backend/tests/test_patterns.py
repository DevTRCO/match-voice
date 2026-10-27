"""The pattern detector (commentary/patterns.py), its set-up line, its pay-off in a goal analysis, and the verifier rules that go with it."""
import asyncio
import json
import re

import pytest

from matchvoice.commentary.analyst import KEYS, PROMPT_VERSION, SYSTEM, CallBudget, build_prompt
from matchvoice.commentary.moments import Moment, render_variants
from matchvoice.commentary.patterns import ACROSS_M, MIN_WINS, QUIET_S, SHORT_M, PatternFeed, pattern_id
from matchvoice.commentary.verifier import Verifier, allowed_for
from matchvoice.facts.engine import FactEngine
from matchvoice.pipeline.demo import story_insert
from matchvoice.pipeline.library import Library
from matchvoice.pipeline.runner import LiveConfig, Runner
from matchvoice.schema import EventType

LIB = Library()
MATCH = "comeback-135"
SAVE_T = 4229.5  # Petrov's save: the ball is dead until the corner at 4249.6 (docs/INSIGHT-SETUP.md)
GOAL_T = 4393.7  # the equaliser, 71'


@pytest.fixture(scope="module")
def bundle():
    return LIB.bundle(MATCH)


def fires(events, meta):
    """Every set-up a detector fed these events would say, asked once in each quiet spell (as a live run's idle frames do)."""
    pf, out = PatternFeed(meta), []
    for k, e in enumerate(events):
        pf.feed(e)
        nxt = events[k + 1].t if k + 1 < len(events) else e.t + 60.0
        if e.t + QUIET_S < nxt:
            out += [(m, ev) for m, ev in pf.quiet(e.t + QUIET_S)]
    return out


def feed_until(bundle, t: float) -> PatternFeed:
    pf = PatternFeed(bundle.meta)
    for e in bundle.events:
        if e.t < t:
            pf.feed(e)
    return pf


# ---------- the detector ----------
def test_the_habit_of_the_demo_match_is_found_in_the_quiet_spell_at_68(bundle):
    pf = feed_until(bundle, SAVE_T + 1)
    got = pf.quiet(SAVE_T + QUIET_S)
    assert len(got) == 1
    m, ev = got[0]
    assert m.kind == "pattern_insight" and m.voice == "analyst" and m.id == pattern_id("H", 2)
    assert m.t == pytest.approx(SAVE_T + QUIET_S) and m.clock == "68"
    p = m.params
    assert p["team"] == "Wexmoor Athletic" and p["player"] == "Ibsen" and p["since"] == "half-time"
    assert p["ball_wins_own_half"] == 11 and p["balls_across"] == 0 and p["ball_winner_wins_this_half"] == 5
    assert ev["wins"] == 11 and ev["across"] == 0 and ev["players"] == ["H3"] and ev["widest_m"] < ACROSS_M
    assert ev["zone"] == [52.5, 0.0, 105.0, 68.0]  # Wexmoor defend the goal at x 105 in the second half
    assert len(ev["dots"]) == 11 and len(ev["arrows"]) == 11
    assert pf.quiet(SAVE_T + QUIET_S + 2) == []  # once per side and half, one per quiet spell


def test_no_lookahead_the_set_up_is_the_same_whatever_comes_after(bundle):
    """Every set-up the detector says over the whole match is identical when the events after it are thrown away."""
    full = fires(bundle.events, bundle.meta)
    assert full
    for m, ev in full:
        cut = [e for e in bundle.events if e.t <= m.t]
        again = [x for x in fires(cut, bundle.meta) if x[0].id == m.id]
        assert again and again[0][0].params == m.params and again[0][1] == ev and again[0][0].t == m.t


def test_it_does_not_fire_in_open_play_or_too_soon(bundle):
    pf = feed_until(bundle, SAVE_T - 3.0)  # the last event is a pass in open play
    assert pf.last.type is EventType.PASS and not pf.dead(pf.last.t + 30.0)
    assert pf.quiet(pf.last.t + 30.0) == []
    pf = feed_until(bundle, SAVE_T + 1)
    assert pf.quiet(SAVE_T + QUIET_S - 0.5) == []  # the ball has not been dead long enough
    early = feed_until(bundle, 2700.0 + 600.0)  # ten minutes into the half: fewer than MIN_WINS ball wins
    assert len([w for w in early.wins.get(("H", 2), []) if w.first is not None]) < MIN_WINS
    assert early.habit("H", 2) is None


def test_it_does_not_fire_once_a_ball_has_gone_across(bundle):
    events = list(bundle.events)
    k = next(i for i, e in enumerate(events) if e.t > 3000 and e.team == "H" and e.type is EventType.PASS and e.set_piece is None
             and e.end_y is not None)
    e = events[k]
    events[k] = e.model_copy(update={"end_y": 64.0 if e.y < 34 else 4.0})  # one Wexmoor ball across the pitch in the half
    pf = PatternFeed(bundle.meta)
    for x in events:
        if x.t < SAVE_T + 1:
            pf.feed(x)
    assert pf.habit("H", 2) is None
    assert all(m.id != pattern_id("H", 2) for m, _ in pf.quiet(SAVE_T + QUIET_S))


def test_one_long_first_pass_after_a_win_and_the_habit_does_not_hold(bundle):
    """"Always short" is the claim: a clearance or a long ball after a ball win (not across) breaks it as surely as a switch."""
    pf = feed_until(bundle, SAVE_T + 1)
    first = pf.wins[("H", 2)][-1].first  # i1412, 6.2 m
    assert first is not None and first.i == 1412
    events = [e if e.i != first.i else e.model_copy(update={"end_x": e.x - SHORT_M - 5.0, "end_y": e.y}) for e in bundle.events]
    pf = PatternFeed(bundle.meta)
    for x in events:
        if x.t < SAVE_T + 1:
            pf.feed(x)
    assert pf.habit("H", 2) is None
    assert all(m.id != pattern_id("H", 2) for m, _ in pf.quiet(SAVE_T + QUIET_S))


@pytest.mark.parametrize("match,expected", [("comeback-135", [("H", 2)]), ("comeback-7", [("A", 2)]), ("red_card-7", [("H", 2)]),
                                            ("unlucky-7", []), ("red_card-11", [("H", 2)])])
def test_every_set_up_on_the_demo_matches_is_true_from_the_raw_events(match, expected):
    """Recomputed from the events before the set-up, without the detector: every first pass after an own-half win was under
    SHORT_M long and under ACROSS_M sideways, and no open-play pass of that side went across in the half. The list of set-ups is pinned:
    before the length rule the detector fired 15 times on these five matches, 11 of them with a clearance or a long first pass."""
    b = LIB.bundle(match)
    got = fires(b.events, b.meta)
    assert sorted((ev["side"], ev["half"]) for _, ev in got) == sorted(expected)
    by_i = {e.i: e for e in b.events}
    for m, ev in got:
        side, half = ev["side"], ev["half"]
        n = len(ev["ev"]) // 2
        assert n == m.params["ball_wins_own_half"] >= MIN_WINS
        for i in ev["ev"][n:]:
            f = by_i[i]
            assert f.t < m.t and f.team == side and f.type is EventType.PASS
            assert ((f.end_x - f.x) ** 2 + (f.end_y - f.y) ** 2) ** 0.5 < SHORT_M and abs(f.end_y - f.y) < ACROSS_M
        assert not [e for e in b.events if e.t < m.t and e.period == half and e.team == side and e.type is EventType.PASS
                    and e.set_piece is None and e.end_y is not None and abs(e.end_y - e.y) >= ACROSS_M]


@pytest.mark.parametrize("match,win_i", [("comeback-135", 984), ("unlucky-7", 361)])
def test_a_restart_ends_the_play_after_a_win(match, win_i):
    """A foul after the win, then a free kick: the open-play pass 23 to 31 s later is not "the first pass after the win"."""
    b = LIB.bundle(match)
    pf = PatternFeed(b.meta)
    for e in b.events:
        pf.feed(e)
    w = next(w for ws in pf.wins.values() for w in ws if w.ev.i == win_i)
    assert w.first is None


def test_the_equaliser_breaks_the_habit_and_the_late_goal_does_not(bundle):
    pf = PatternFeed(bundle.meta)
    breaks = {}
    for e in bundle.events:
        pf.feed(e)
        if e.type is EventType.SHOT and e.outcome == "goal":
            breaks[e.clock] = pf.broken_by(e.team)
    assert breaks["71"] is not None and breaks["71"]["facts"]["ball_winner"] == "Ibsen"
    assert breaks["71"]["evidence"]["players"] == ["H3", "H4"] and breaks["71"]["evidence"]["ev"] == [1479, 1481]
    x0, y0, x1, y1 = breaks["71"]["evidence"]["arrow"]
    assert abs(y1 - y0) >= ACROSS_M
    assert breaks["89"] is None and breaks["14"] is None


def test_the_story_insert_opens_on_the_set_up_and_cuts_before_the_corner(bundle):
    d = story_insert(LIB)
    (a1, b1), (a2, b2) = d["parts"]
    assert d["setup_t"] == pytest.approx(SAVE_T + QUIET_S)
    assert a1 < d["setup_t"] < d["story_t"] < b1 < 4249.6 < a2 < d["goal_t"] < b2


# ---------- the prompt ----------
def test_prompt_v7_names_the_pattern_and_the_pay_off():
    assert PROMPT_VERSION == "v8"
    for needle in ("pattern_insight", "pays_off", "Paying it off", "never refer back", "No count of anything"):
        assert needle in SYSTEM, needle
    assert "two passes" not in SYSTEM and "zwei Pässe" not in SYSTEM and "deux passes" not in SYSTEM


def test_the_set_up_prompt_carries_the_habit_and_no_template_helpers(bundle):
    pf = feed_until(bundle, SAVE_T + 1)
    m, _ = pf.quiet(SAVE_T + QUIET_S)[0]
    eng = FactEngine(bundle.meta)
    for e in bundle.events:
        if e.t < SAVE_T + 1:
            eng.ingest(e)
    prompt = build_prompt(m, eng.snapshot(), bundle.meta)
    facts = json.loads(prompt.split("Facts (the only source you may use; ")[1].split("):\n", 1)[1].split("\n\nRoom per line")[0])
    assert facts["moment"]["pattern"]["player"] == "Ibsen" and facts["moment"]["pattern"]["balls_across"] == 0
    assert "short" not in facts["moment"]  # the club's first word is a template helper


# ---------- the pay-off, end to end through the runner (fake model, private cache) ----------
SETUP_LINES = {"en/beginner": "Ibsen keeps winning it back, but this half it always goes short. Never across.",
               "en/expert": "Ibsen keeps winning it, then it goes short. Not one switch since the break.",
               "de/beginner": "Ibsen holt die Bälle, aber seit der Pause immer kurz. Nie rüber.",
               "de/expert": "Ibsen holt die Bälle, dann immer kurz. Wo ist die Verlagerung?",
               "fr/beginner": "Ibsen récupère le ballon, mais depuis la pause, toujours court. Jamais de l'autre côté.",
               "fr/expert": "Ibsen récupère ballon sur ballon, mais derrière, toujours court. Pas une transversale."}
GOAL_LINES = {"en/beginner": "There you go! Ibsen wins it, and this time it goes across.", "en/expert": "There it is. Ibsen wins it, and this time it goes across.",
              "de/beginner": "Da ist es! Ibsen holt ihn, und diesmal geht's rüber.", "de/expert": "Genau das. Ibsen holt ihn, diesmal sofort rüber.",
              "fr/beginner": "Et voilà ! Ibsen récupère, et cette fois, de l'autre côté !", "fr/expert": "Voilà ! Ibsen récupère, et cette fois, transversale."}


class FakeModel:
    def __init__(self):
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        kind = re.search(r'"kind": "(\w+)"', prompt).group(1)
        keys = re.search(r"these keys \(language/style\): (.+)\.", prompt).group(1).split(", ")
        lines = SETUP_LINES if kind == "pattern_insight" else GOAL_LINES
        return json.dumps({k: lines[k] for k in keys})


def run_part(bundle, start, until, model, booth, tmp_path):
    live = LiveConfig(model, CallBudget(6), cache_dir=tmp_path)
    return asyncio.run(Runner(bundle, "live", 1.0, False, live, start, None, until, fast=True, booth=booth).collect())


def test_a_goal_that_breaks_the_habit_pays_off_the_set_up_said_earlier(bundle, tmp_path):
    model, booth = FakeModel(), {}
    part1 = run_part(bundle, 4233.0, 4249.0, model, booth, tmp_path)
    setup = [m for m in part1 if m["k"] == "say" and m["m"] == pattern_id("H", 2)]
    assert len(setup) == len(KEYS) and all(m["src"] == "analyst" for m in setup)
    ins = setup[0]["ins"]
    assert ins["kind"] == "pattern" and ins["players"] == ["H3"] and ins["zone"] and ins["arrows"]
    assert any(m["k"] == "log" and m["step"] == "pattern" and m["agent"] == "detector" for m in part1)
    assert booth["setups"][("H", 2)]["lines"] == SETUP_LINES
    part2 = run_part(bundle, 4382.0, 4410.0, model, booth, tmp_path)
    goal_prompt = model.prompts[-1]
    assert '"kind": "goal_analysis"' in goal_prompt and '"pays_off"' in goal_prompt and "This goal broke it" in goal_prompt
    for line in SETUP_LINES.values():
        assert line in goal_prompt
    co = [m for m in part2 if m["k"] == "say" and m["kind"] == "goal_analysis"]
    assert co and all(m["src"] == "analyst" for m in co) and co[0]["ins"]["kind"] == "payoff" and co[0]["ins"]["of"] == pattern_id("H", 2)
    assert co[0]["ins"]["arrow"] and co[0]["ins"]["setup_t"] == pytest.approx(SAVE_T + QUIET_S)
    assert any(m["k"] == "log" and m["step"] == "payoff" for m in part2)
    assert all(m["m"] != pattern_id("H", 2) for m in part2 if m["k"] == "say")  # said once in the broadcast


def test_the_same_goal_without_a_set_up_has_no_pay_off(bundle, tmp_path):
    model = FakeModel()
    part2 = run_part(bundle, 4382.0, 4410.0, model, {}, tmp_path)
    goal_prompt = next(p for p in model.prompts if '"kind": "goal_analysis"' in p)
    assert "pays_off" not in goal_prompt and "Earlier in this broadcast" not in goal_prompt
    assert all("ins" not in m for m in part2 if m["k"] == "say" and m["kind"] == "goal_analysis")


def test_a_goal_that_does_not_break_the_habit_does_not_refer_back(bundle, tmp_path):
    goal = [e for e in bundle.events if e.type is EventType.SHOT and e.outcome == "goal"][-1]  # 89', not from a ball won and switched
    booth = {"setups": {("H", 2): {"id": pattern_id("H", 2), "t": 4234.5, "clock": "68", "what": "habit", "lines": dict(SETUP_LINES)}},
             "fired": {("H", 2)}}
    model = FakeModel()
    out = run_part(bundle, float(int(goal.t - 10)), float(int(goal.t + 10)), model, booth, tmp_path)
    goal_prompt = next(p for p in model.prompts if '"kind": "goal_analysis"' in p)
    assert '"pays_off"' not in goal_prompt and "did NOT come that way" in goal_prompt
    assert not any(m["k"] == "log" and m["step"] == "payoff" for m in out)


# ---------- the verifier ----------
def _moments(bundle):
    eng = FactEngine(bundle.meta)
    from matchvoice.commentary.moments import MomentBuilder
    mb, out = MomentBuilder(eng), {}
    for e in bundle.events:
        for m in mb.feed(e, eng.ingest(e)):
            out.setdefault(m.kind, (m, eng.snapshot()))
    return out


def test_a_beginner_line_with_a_count_is_rejected_and_an_expert_line_is_not(bundle):
    m, snap = _moments(bundle)["goal_analysis"]
    allowed = allowed_for(m, snap, bundle.meta)
    allowed.numbers |= {3.0}
    ver = Verifier(bundle.meta)
    for lang, text in (("en", "Won in their own half, three passes, and it's in the net."), ("de", "Ball hinten gewonnen, drei Pässe, drin."),
                       ("fr", "Ballon récupéré dans son propre camp, trois passes, et c'est au fond !"),
                       ("en", "Won in their own half, 3 quick passes, and it's in the net.")):
        v = ver.check(text, lang, allowed, style="beginner", spelled=True)
        assert not v.ok and any(x.code == "count_in_beginner" for x in v.violations), (lang, text)
        assert ver.check(text, lang, allowed, style="expert", spelled=True).ok, (lang, text)
        assert ver.check(text, lang, allowed).ok  # templates and tools call it without a style: unchanged
    assert ver.check("Won in their own half, and seconds later it's in the net.", "en", allowed, style="beginner", spelled=True).ok


def test_a_number_written_as_a_word_must_be_in_the_facts(bundle):
    pf = feed_until(bundle, SAVE_T + 1)
    m, _ = pf.quiet(SAVE_T + QUIET_S)[0]
    snap = FactEngine(bundle.meta).snapshot()
    allowed = allowed_for(m, snap, bundle.meta)
    ver = Verifier(bundle.meta)
    # a true line (11 is the side's own-half wins); the verifier does not check WHOSE number it is, see the attribution gap in CLAUDE.md
    assert ver.check("Eleven times they win it in their own half, and then it goes short.", "en", allowed, spelled=True).ok
    bad = ver.check("Ibsen keeps winning it, seventeen times this half, and then it goes short.", "en", allowed, spelled=True)
    assert not bad.ok and bad.violations[0].code == "number_unsupported"
    assert not ver.check("Ibsen holt die Bälle, siebzehnmal, und dann immer kurz.", "de", allowed, spelled=True).ok


def test_habit_claims_need_a_pattern_in_the_facts(bundle):
    ms = _moments(bundle)
    goal, gsnap = ms["goal_analysis"]
    ver = Verifier(bundle.meta)
    plain = allowed_for(goal, gsnap, bundle.meta)
    for lang, text in (("en", "Nothing across all half, and then Fontaine scores."), ("de", "Immer kurz, und dann trifft Fontaine."),
                       ("fr", "Toujours court, puis Fontaine marque.")):
        v = ver.check(text, lang, plain)
        assert any(x.code == "claim_unsupported" for x in v.violations), (lang, text)
    paid = Moment(**{**goal.__dict__, "params": {**goal.params, "pays_off": {"habit": "short", "ball_winner": "Ibsen", "this_time": "across"}}})
    assert ver.check("There it is. Ibsen keeps winning it, and this time it goes across.", "en", allowed_for(paid, gsnap, bundle.meta)).ok
    pf = feed_until(bundle, SAVE_T + 1)
    m, _ = pf.quiet(SAVE_T + QUIET_S)[0]
    allowed = allowed_for(m, FactEngine(bundle.meta).snapshot(), bundle.meta)
    for key, line in SETUP_LINES.items():
        lang, style = key.split("/")
        v = ver.check(line, lang, allowed, style=style, spelled=True)
        assert v.ok, (key, line, v.feedback())


def test_the_pattern_templates_pass_the_verifier(bundle):
    pf = feed_until(bundle, SAVE_T + 1)
    m, _ = pf.quiet(SAVE_T + QUIET_S)[0]
    allowed = allowed_for(m, FactEngine(bundle.meta).snapshot(), bundle.meta)
    ver = Verifier(bundle.meta)
    nameless = Moment(**{**m.__dict__, "params": {k: v for k, v in m.params.items() if k != "player"}})
    for mm in (m, nameless):
        for key in KEYS:
            lang, style = key.split("/")
            texts = render_variants(mm, lang, style)
            assert texts
            for text in texts:
                v = ver.check(text, lang, allowed, style=style, spelled=True)
                assert v.ok, (key, text, v.feedback())
                assert "{" not in text and not re.search(r"\d", text)
    assert all("Ibsen" not in t for key in KEYS for t in render_variants(nameless, *key.split("/")))

