"""The booth's memory of a match it joined late, and the line that sets the scene.

A live run of the generated winner starts at 88' with the score 1-1 (Tamsworth led 0-1 from 14', Fontaine levelled at 71'). Every core and
world prompt of a live run carries `match_so_far` (the goals up to its moment, how the score got here, red cards, late), the verifier takes
its scorers, minutes and scores as facts, and the lead opens a run that joins at a dead ball with the `match_state` line, after the
restart call. Fake models with private answer caches: no real call, nothing written to data/cache."""
from __future__ import annotations

import asyncio
import json
import re

import pytest

from matchvoice.commentary.analyst import PROMPT_VERSION, CallBudget, build_prompt, facts_of
from matchvoice.commentary.director import ChannelDirector
from matchvoice.commentary.lang import ALL_KEYS, BOOTH, CORE_KEYS
from matchvoice.commentary.moments import Moment, render_variants
from matchvoice.commentary.templates import T
from matchvoice.commentary.verifier import Verifier, allowed_for
from matchvoice.commentary.world import WORLD_PROMPT_VERSION, build_world_prompt, world_moment
from matchvoice.facts.engine import FactEngine
from matchvoice.pipeline import scenes
from matchvoice.pipeline.library import Library
from matchvoice.pipeline.runner import MATCH_STATE_ID, LiveConfig, Runner
from test_pipeline import fake_llm
from test_public import world_fake

LIB = Library()
WIN = scenes.SCENES["winner"]
SEED = 0


def _scene_run(tmp_path, seed=SEED, **kw):
    core, world = [], []
    base = fake_llm()

    async def call(prompt: str) -> str:
        core.append(prompt)
        return await base(prompt)
    live = LiveConfig(call, CallBudget(80), "fake", tmp_path, world_call=world_fake(world))
    msgs = asyncio.run(Runner(LIB.scene_bundle(WIN, seed), "live", 1.0, False, live, WIN.start, None, WIN.until, fast=True,
                              rows=True, world=True, **kw).collect())
    return msgs, core, world


@pytest.fixture(scope="module")
def scene(tmp_path_factory):
    return _scene_run(tmp_path_factory.mktemp("scene"))


def _facts(prompt: str) -> dict:
    return json.loads(prompt.split("(the only source you may use")[1].split(":\n", 1)[1].split("\n\nRoom per line")[0])


# ---------- the memory ----------
def test_the_match_so_far_holds_every_goal_before_the_window_and_how_the_score_got_here():
    b = LIB.bundle(WIN.match)
    eng = FactEngine(b.meta)
    for ev in b.events:
        if ev.t < WIN.start:
            eng.ingest(ev)
    sf = eng.so_far(WIN.start, eng.clock)
    assert sf["minute"] == "88" and sf["score_home_away"] == "1-1" and sf["late"] is True
    assert [(g["minute"], g["scorer"], g["team"], g["made_it"]) for g in sf["goals"]] == [
        ("14", "Okonkwo", "Tamsworth Wanderers", "0-1"), ("71", "Fontaine", "Wexmoor Athletic", "1-1")]
    assert sf["how_it_got_here"] == ("Tamsworth Wanderers took the lead 0-1 through Okonkwo (14'). "
                                     "Wexmoor Athletic equalised 1-1 through Fontaine (71'). Level since 71'.")
    assert "red_cards" not in sf
    early = FactEngine(b.meta)
    for ev in b.events:
        if ev.t < 600:
            early.ingest(ev)
    assert early.so_far(600, early.clock) == {"minute": early.clock, "score_home_away": "0-0", "goals": [], "how_it_got_here": "Still goalless."}


def test_a_red_card_and_a_lead_are_part_of_the_memory():
    b = LIB.bundle("red_card-7")
    eng = FactEngine(b.meta)
    for ev in b.events:
        eng.ingest(ev)
    sf = eng.so_far(b.events[-1].t, eng.clock)
    assert sf["red_cards"] and all({"minute", "player", "team"} <= set(r) for r in sf["red_cards"])
    h, a = (int(x) for x in sf["score_home_away"].split("-"))
    assert len(sf["goals"]) == h + a and (h == a or "have led since" in sf["how_it_got_here"])


def test_every_live_prompt_core_and_world_carries_the_match_so_far(scene):
    msgs, core, world = scene
    assert core and world
    for p in core + world:
        sf = _facts(p)["match_so_far"]
        assert sf["goals"][:2] == [{"minute": "14", "scorer": "Okonkwo", "team": "Tamsworth Wanderers", "made_it": "0-1"},
                                   {"minute": "71", "scorer": "Fontaine", "team": "Wexmoor Athletic", "made_it": "1-1"}]
        assert sf["late"] is True and "goalless" not in p.split("Facts")[1]
    goal = next(p for p in core if '"kind": "goal_analysis"' in p)
    sf = _facts(goal)["match_so_far"]
    assert sf["score_home_away"] == "2-1" and len(sf["goals"]) == 3 and sf["goals"][2]["made_it"] == "2-1"
    assert "Wexmoor Athletic went ahead 2-1" in sf["how_it_got_here"] and sf["how_it_got_here"].endswith("have led since 89'.")
    before = [p for p in world if "Moment kind shot_goal" not in p and '"made_it": "2-1"' not in p]
    assert before and all(_facts(p)["match_so_far"]["score_home_away"] == "1-1" for p in before)  # a moment before the goal: 1-1


def test_prompt_versions_are_bumped_and_the_rules_name_the_memory():
    from matchvoice.commentary.analyst import SYSTEM
    from matchvoice.commentary.world import WORLD_SYSTEM
    assert PROMPT_VERSION == "v9" and WORLD_PROMPT_VERSION == "w3"
    for system in (SYSTEM, WORLD_SYSTEM):
        assert "match_so_far" in system and "opener" in system and "goalless" in system


def test_a_recording_builds_its_prompt_without_the_memory():
    """Precompute and replays pass the plain snapshot: no `match_so_far`, the facts block keeps its old shape."""
    m = Moment(id=5, t=4393.7, clock="71", kind="goal_analysis", voice="analyst", priority=70, ttl=40.0,
               params={"player": "Fontaine", "team": "Wexmoor Athletic", "score": "1-1", "tags": "equaliser"})
    snap = {"score": [1, 1], "stats": {}, "win": [0.4, 0.3, 0.3]}
    meta = LIB.bundle(WIN.match).meta
    assert set(facts_of(m, snap, meta)) == {"moment", "match"} and "match_so_far" not in build_prompt(m, snap, meta)
    assert "match_so_far" in facts_of(m, {**snap, "so_far": {"goals": []}}, meta)


def test_the_same_run_builds_the_same_prompts_so_the_cache_still_works(tmp_path, scene):
    _, core, world = scene
    _, core2, world2 = _scene_run(tmp_path)
    assert core2 == core and world2 == world


def test_the_world_line_that_sets_the_scene_has_one_prompt_for_every_variant(tmp_path):
    """Everything before the fork is the same in every variant, so its prompt is answered from the cache after the first run."""
    first = [p for p in _scene_run(tmp_path / "a", 0)[2] if p.startswith("Moment kind match_state")]
    other = [p for p in _scene_run(tmp_path / "b", 3)[2] if p.startswith("Moment kind match_state")]
    assert len(first) == 1 and first == other


# ---------- the verifier takes the memory as facts ----------
def test_the_verifier_accepts_the_memory_and_still_rejects_the_rest():
    meta = LIB.bundle(WIN.match).meta
    ver = Verifier(meta)
    m = Moment(id=7, t=5466.0, clock="89", kind="goal_analysis", voice="analyst", priority=70, ttl=40.0,
               params={"player": "Tavares", "team": "Wexmoor Athletic", "score": "2-1", "chain": ["Moreau"]})
    snap = {"score": [2, 1], "stats": {s: {"possession": 50, "shots": 9, "on_target": 4, "xg": 1.2, "pass_acc": 80} for s in ("H", "A")},
            "win": [0.8, 0.15, 0.05]}
    sf = {"minute": "89", "score_home_away": "2-1", "goals": [
        {"minute": "14", "scorer": "Okonkwo", "team": "Tamsworth Wanderers", "made_it": "0-1"},
        {"minute": "71", "scorer": "Fontaine", "team": "Wexmoor Athletic", "made_it": "1-1"},
        {"minute": "89", "scorer": "Tavares", "team": "Wexmoor Athletic", "made_it": "2-1"}]}
    line = "From 0-1 down to 2-1: Fontaine levelled on 71, and now Tavares."
    assert not ver.check(line, "en", allowed_for(m, snap, meta)).ok  # without the memory: 0-1, 71 and Fontaine are not facts of the goal
    allowed = allowed_for(m, {**snap, "so_far": sf}, meta)
    assert ver.check(line, "en", allowed).ok, ver.check(line, "en", allowed).feedback()
    assert ver.check("Fontaines Ausgleich, jetzt Tavares zum 2:1.", "de", allowed).ok
    other = next(p.name.split()[-1] for p in meta.teams["H"].players if p.name.split()[-1] not in ("Tavares", "Fontaine", "Moreau", "Okonkwo"))
    for bad in (f"{other} levelled on 71, and now Tavares.", "Tavares makes it 3-1.", "Fontaine levelled on 64, and now Tavares."):
        assert not ver.check(bad, "en", allowed).ok, bad


# ---------- the world score line in the last minutes ----------
def test_the_world_score_line_says_no_time_left_in_the_last_minutes():
    late = Moment(id=900007, t=5466.0, clock="89", kind="score_line", voice="pbp", priority=60, ttl=30.0,
                  params={"score": "2-1", "team": "Wexmoor Athletic", "left_min": 1, "half": 2})
    wm = world_moment(late)
    assert "left_about" not in wm.params and "left_min" not in wm.params and late.params["left_min"] == 1
    snap = {"score": [2, 1], "stats": {}, "win": [0.8, 0.1, 0.1]}
    assert '"left_about"' not in build_world_prompt(wm, snap, LIB.bundle(WIN.match).meta)
    mid = Moment(id=900005, t=4400.0, clock="71", kind="score_line", voice="pbp", priority=60, ttl=30.0,
                 params={"score": "1-1", "team": "Wexmoor Athletic", "left_min": 19, "half": 2})
    assert world_moment(mid).params["left_about"] == 20


# ---------- the line that sets the scene ----------
WANT = {"en/beginner": "It's one-all, late on, and Wexmoor have fought back from a goal down.",
        "en/expert": "Eighty-eight minutes gone, one-all, and Wexmoor have fought back from a goal down.",
        "de/beginner": "Es steht eins zu eins, kurz vor Schluss, und Wexmoor hat einen Rückstand aufgeholt.",
        "de/expert": "Achtundachtzig Minuten gespielt, eins zu eins, und Wexmoor hat einen Rückstand aufgeholt.",
        "fr/beginner": "Un partout en fin de match, et Wexmoor est revenu au score.",
        "fr/expert": "Quatre-vingt-huit minutes de jeu, un partout, et Wexmoor est revenu au score."}


def test_every_channel_sets_the_scene_after_the_restart_call(scene):
    msgs, _, world = scene
    says = [m for m in msgs if m["k"] == "say"]
    skipped = {(m["ch"], m["m"]) for m in msgs if m["k"] == "voice" and m.get("skip")}
    state = {m["ch"]: m for m in says if m["kind"] == "match_state"}
    restart = {m["ch"]: m for m in says if m["kind"] == "restart"}
    assert set(state) == set(restart) == set(range(12))
    for ch in range(12):
        s, r = state[ch], restart[ch]
        assert (ch, s["m"]) not in skipped and (ch, r["m"]) not in skipped  # both are spoken: the goal kick call is not crowded out
        assert s["m"] == MATCH_STATE_ID and s["who"] == BOOTH[ALL_KEYS[ch]].lead.name
        assert s["s"] >= r["e"] - 1e-6 and r["s"] <= r["t"] + 1e-6  # the restart is called at its kick, then the scene is set
    for ch, key in enumerate(CORE_KEYS):
        assert state[ch]["text"] == WANT[key] and not re.search(r"\d", state[ch]["text"]) and state[ch]["src"] == "template"
    assert sum(p.startswith("Moment kind match_state") for p in world) == 1  # one world call for six languages
    goal = min(m["t"] for m in says if m["kind"] == "shot_goal")
    assert max(m["e"] for m in state.values()) < goal - 20  # long done before the attack


def test_the_scene_setting_line_is_in_the_analysts_continuity(scene):
    _, core, _ = scene
    goal = next(p for p in core if '"kind": "goal_analysis"' in p)
    for key in CORE_KEYS:
        assert f'"{WANT[key]}"' in goal.split("Continuity.")[1].split(f"\n{key}:\n")[1].split("\n\n")[0], key


@pytest.mark.parametrize("seed", (1, 3, 11))
def test_the_scene_is_set_on_every_channel_for_other_variants(tmp_path, seed):
    msgs, _, _ = _scene_run(tmp_path, seed)
    skipped = {(m["ch"], m["m"]) for m in msgs if m["k"] == "voice" and m.get("skip")}
    says = [m for m in msgs if m["k"] == "say"]
    assert {m["ch"] for m in says if m["kind"] == "match_state" and (m["ch"], m["m"]) not in skipped} == set(range(12))
    assert {m["ch"] for m in says if m["kind"] == "restart" and (m["ch"], m["m"]) not in skipped} == set(range(12))
    for kind in ("shot_goal", "goal_analysis", "score_line"):
        assert {m["ch"] for m in says if m["kind"] == kind} == set(range(12)), kind


def test_no_scene_setting_line_where_it_does_not_belong(tmp_path):
    """Not from kick-off, not in open play (it would talk over the move: the recorded insert's window), not on a restarted stream,
    not without the dense voice, not when switched off (the insert captures and the density report), never in a replay."""
    b = LIB.scene_bundle(WIN, SEED)
    cfg = lambda: LiveConfig(fake_llm(), CallBudget(80), "fake", tmp_path)

    def kinds(r: Runner) -> set[str]:
        return {m["kind"] for m in asyncio.run(r.collect()) if m["k"] == "say"}
    assert "match_state" in kinds(Runner(b, "live", 1.0, False, cfg(), WIN.start, None, WIN.until, fast=True))
    assert "match_state" not in kinds(Runner(b, "live", 1.0, False, cfg(), WIN.start, None, WIN.until, fast=True, rejoin=False))
    assert "match_state" not in kinds(Runner(b, "live", 1.0, False, cfg(), WIN.start, None, WIN.until))  # no dense voice
    assert "match_state" not in kinds(Runner(b, "live", 1.0, False, cfg(), WIN.start, WIN.start, WIN.until, fast=True))  # a restart
    plain = LIB.bundle(WIN.match)
    assert "match_state" not in kinds(Runner(plain, "live", 1.0, False, cfg(), 4382.0, None, 4410.0, fast=True))  # open play
    assert "match_state" not in kinds(Runner(plain, "live", 1.0, False, cfg(), 0.0, None, 300.0, fast=True))
    assert "match_state" not in kinds(Runner(LIB.bundle("comeback-7"), "replay", 30.0, paced=False))


def test_the_templates_have_two_wordings_short_to_long_for_every_state():
    def state(facet: str, h: int, a: int, team: str | None, phase="late", n=88) -> Moment:
        p = {"facet": facet, "n": n, "goals_h": h, "goals_a": a, "phase": phase, "dead": True, "window": -1, "long": True}
        if team:
            p |= {"team": team, "other": "Tamsworth"}
        return Moment(id=MATCH_STATE_ID, t=1.0, clock=str(n), kind="match_state", voice="pbp", priority=45, ttl=12.0, params=p, layer="context")
    for key in CORE_KEYS:
        lang, style = key.split("/")
        assert len(T["match_state"][lang][style]) == 2
    assert render_variants(state("goalless", 0, 0, None, "first", 30), "en", "expert") == [
        "Thirty minutes gone, nil-nil.", "Thirty minutes gone, nil-nil, and nobody has found a way through yet."]
    assert render_variants(state("lead", 2, 0, "Wexmoor", "second", 60), "de", "beginner")[-1] == \
        "Es steht zwei zu null, in der zweiten Halbzeit, und Wexmoor liegt vorn."
    assert render_variants(state("lead_back", 2, 1, "Wexmoor", "added", 90), "fr", "beginner")[-1] == \
        "Deux à un dans le temps additionnel, et Wexmoor a renversé la situation."
    assert render_variants(state("lead_back", 2, 1, "Wexmoor"), "en", "beginner")[-1] == \
        "It's two-one, late on, and Wexmoor have come from behind to lead."


def test_the_director_holds_the_scene_setting_line_behind_the_call_it_came_with():
    """The voice is busy when both arrive: by priority the scene-setting line (45) would go before the restart (28); it waits for it."""
    busy = Moment(id=2, t=9.0, clock="88", kind="carry", voice="pbp", priority=30, ttl=8.0, params={}, ready_t=9.0)
    call = Moment(id=1, t=10.0, clock="88", kind="restart", voice="pbp", priority=28, ttl=3.0, params={}, ready_t=10.0)
    state = Moment(id=MATCH_STATE_ID, t=10.0, clock="88", kind="match_state", voice="pbp", priority=45, ttl=12.0,
                   params={"dead": True, "window": -1, "long": True}, layer="context", ready_t=10.001)
    texts = {2: ["Up the pitch it goes."], 1: ["Goal kick for Tamsworth."],
             MATCH_STATE_ID: ["Eighty-eight minutes gone, one-all."]}
    d = ChannelDirector(lambda m: texts[m.id], "en", captions_first=True, voice_wait_s=8.0, dense=True)
    for m in (busy, call, state):
        d.push(m)
    d.advance(40.0)
    starts = [sp.moment_id for kind, sp in d.drain() if kind == "start"]
    assert starts == [2, 1, MATCH_STATE_ID]


def test_a_world_context_line_gets_raw_facts_not_the_english_sentence(scene):
    """A context line (the goal's move, the tally) reached the world booth through the English renderer, its finished sentence included."""
    _, _, world = scene
    notes = [p for p in world if p.startswith("Moment kind counter_note")]
    assert notes
    for p in notes:
        moment = _facts(p)["moment"]
        assert not {"note", "note_long", "score_words", "team_code", "window", "dead"} & set(moment), sorted(moment)
        assert "finishes it off" not in p and "worked it" not in p and moment["kind_means"].startswith("a fact of this match")
    move = next((_facts(p)["moment"] for p in notes if _facts(p)["moment"]["facet"] == "move"), None)
    assert move is None or (move["chain"] and move["goals_h"] == 2 and move["goals_a"] == 1)


# ---------- review fixes: the memory is bound, scoped, and the world scene line never blocks or trails play ----------
def _memory_allowed(kind: str, clock: str, goals: int, params: dict):
    meta = LIB.bundle(WIN.match).meta
    st = {s: {"possession": 50, "shots": 9, "on_target": 4, "xg": 1.2, "pass_acc": 80} for s in ("H", "A")}
    all_goals = [{"minute": "14", "scorer": "Okonkwo", "team": "Tamsworth Wanderers", "made_it": "0-1"},
                 {"minute": "71", "scorer": "Fontaine", "team": "Wexmoor Athletic", "made_it": "1-1"},
                 {"minute": "89", "scorer": "Tavares", "team": "Wexmoor Athletic", "made_it": "2-1"}][:goals]
    score = all_goals[-1]["made_it"]
    sf = {"minute": clock, "score_home_away": score, "goals": all_goals}
    m = Moment(id=7, t=5466.0, clock=clock, kind=kind, voice="analyst" if kind == "goal_analysis" else "pbp", priority=70, ttl=40.0, params=params)
    snap = {"score": [int(x) for x in score.split("-")], "stats": st, "win": [0.4, 0.3, 0.3], "so_far": sf}
    return Verifier(meta), allowed_for(m, snap, meta)


GOAL = {"player": "Tavares", "team": "Wexmoor Athletic", "score": "2-1", "chain": ["Moreau"]}


@pytest.mark.parametrize("lang,line", [
    ("en", "Okonkwo equalised for Wexmoor on 71, and now Tavares."),
    ("en", "Fontaine opened the scoring on 14, and now Tavares."),
    ("en", "Fontaine scored on 89, Tavares on 71."),
    ("en", "Tavares with the first goal of the match."),
    ("en", "The opener! Tavares breaks the deadlock."),
    ("en", "Goalless no more, Tavares."),
    ("de", "Das erste Tor des Spiels, Tavares!"),
    ("fr", "Tavares ouvre le score !"),
    ("es", "¡Tavares abre el marcador!"),
    ("ja", "タバレスが先制！"),
])
def test_the_memory_is_bound_a_minute_to_its_scorer_and_no_later_goal_is_the_opener(lang, line):
    ver, allowed = _memory_allowed("goal_analysis", "89", 3, GOAL)
    v = ver.check(line, lang, allowed, spelled=True)
    assert not v.ok and "history_mismatch" in v.feedback(), (line, v.feedback())


@pytest.mark.parametrize("lang,line", [
    ("en", "Okonkwo put Tamsworth ahead on 14, Fontaine levelled on 71, and now Tavares turns it round."),
    ("en", "Tamsworth's opener came on 14, and Wexmoor have turned it round."),
    ("de", "Erst Okonkwo in der 14., dann Fontaine in der 71., jetzt Tavares."),
    ("fr", "Fontaine avait égalisé à la 71e, Tavares donne l'avantage."),
    ("es", "Fontaine empató en el 71 y ahora Tavares."),
    ("ja", "オコンクォの先制から、フォンテーヌが71分に同点、そしてタバレス！"),
])
def test_true_history_still_passes(lang, line):
    ver, allowed = _memory_allowed("goal_analysis", "89", 3, GOAL)
    assert ver.check(line, lang, allowed, spelled=True).ok, ver.check(line, lang, allowed, spelled=True).feedback()


def test_the_real_opener_may_be_called_the_opener():
    ver, allowed = _memory_allowed("goal_analysis", "14", 1, {"player": "Okonkwo", "team": "Tamsworth Wanderers", "score": "0-1", "chain": ["Okonkwo"]})
    assert ver.check("The opener, and it's Okonkwo.", "en", allowed, spelled=True).ok
    assert ver.check("Okonkwo ouvre le score.", "fr", allowed, spelled=True).ok


def test_play_by_play_gets_no_scorers_or_goal_minutes_from_the_memory():
    """A pass at 88' may not name an earlier scorer who is not part of it, nor use a goal minute as a count (the review's false lines)."""
    ver, allowed = _memory_allowed("pass_kind", "88", 2, {"player": "Quinlan", "receiver": "Okonkwo"})
    for lang, line, code in (("en", "Fontaine to Okonkwo.", "player_unsupported"), ("es", "Fontaine para Okonkwo.", "player_unsupported"),
                             ("en", "Quinlan's 71st pass of the day.", "number_unsupported"),
                             ("en", "Quinlan has fourteen touches now.", "number_unsupported"),
                             ("en", "Still goalless? No, Quinlan to Okonkwo.", "history_mismatch")):
        v = ver.check(line, lang, allowed, spelled=True)
        assert not v.ok and code in v.feedback(), (line, v.feedback())
    assert ver.check("Quinlan to Okonkwo.", "en", allowed, spelled=True).ok
    assert ver.check("Quinlan to Okonkwo, still 1-1.", "en", allowed, spelled=True).ok
    assert ver.check("Level again after 0-1, Quinlan to Okonkwo.", "en", allowed, spelled=True).ok  # a score the match has had


def _paced(tmp_path, seed, world_call, speed=2.0, span=30.0):
    """A paced run of the window's first `span` match seconds (the goal kick and the dead ball after it), 2x, as on the public server."""
    live = LiveConfig(fake_llm(), CallBudget(80), "fake", tmp_path, world_call=world_call)
    live.world_skip_late = True
    return asyncio.run(Runner(LIB.scene_bundle(WIN, seed), "live", speed, True, live, WIN.start, None, WIN.start + span, fast=True,
                              rows=True, world=True).collect())


def _slow(base, s: float, state_s: float | None = None):
    async def call(prompt: str) -> str:
        await asyncio.sleep(state_s if state_s is not None and prompt.startswith("Moment kind match_state") else s)
        return await base(prompt)
    return call


def test_a_cold_world_call_for_the_scene_line_never_takes_the_restart_call_slot(tmp_path):
    """Paced, every world call 2.5 match s, empty cache (the first public run after a deploy): the world booth still calls the goal kick
    (before, the scene line took the one serial call and the goal kick was skipped as too late), then sets the scene behind it, starting
    within 12 match s of the goal kick while the ball is still dead, and spoken."""
    prompts: list[str] = []
    msgs = _paced(tmp_path, 3, _slow(world_fake(prompts), 1.25))
    says = [m for m in msgs if m["k"] == "say"]
    skipped = {(m["ch"], m["m"]) for m in msgs if m["k"] == "voice" and m.get("skip")}
    starts = {(m["ch"], m["m"]): m["s"] for m in msgs if m["k"] == "voice" and not m.get("skip") and not m.get("cut")}
    starts |= {(m["ch"], m["m"]): m["s"] for m in says if m["e"] > m["s"]}
    for ch in range(6, 12):
        state = next(m for m in says if m["ch"] == ch and m["kind"] == "match_state")
        restart = next(m for m in says if m["ch"] == ch and m["kind"] == "restart")
        assert (ch, state["m"]) not in skipped and (ch, restart["m"]) not in skipped
        assert restart["t"] <= state["t"] and starts[(ch, state["m"])] <= WIN.start + 1.3 + 12.0 + 1e-6, (ch, starts[(ch, state["m"])])
    assert sum(p.startswith("Moment kind match_state") for p in prompts) == 1
    assert not [m for m in msgs if m["k"] == "log" and m.get("step") == "too_late" and m.get("m") != MATCH_STATE_ID and m["t"] < WIN.start + 3]


def test_a_scene_line_that_comes_back_too_late_is_not_said_and_leaves_the_queue_moving(tmp_path):
    """The scene-setting call takes 16 match s: the line would talk over play, so the world booth drops it (log too_late), and the world
    lines after the goal kick are said as usual."""
    msgs = _paced(tmp_path, 3, _slow(world_fake(), 0.05, state_s=8.0))
    says = [m for m in msgs if m["k"] == "say"]
    assert not [m for m in says if m["kind"] == "match_state" and m["ch"] >= 6]
    assert [m for m in msgs if m["k"] == "log" and m.get("step") == "too_late" and m.get("m") == MATCH_STATE_ID]
    assert {m["ch"] for m in says if m["kind"] == "restart" and m["ch"] >= 6} == set(range(6, 12))
    assert len({m["m"] for m in says if m["ch"] == 6}) >= 3


def test_a_world_scene_line_with_the_wrong_score_is_stopped(tmp_path):
    """The world booth's own scene-setting text is checked against the memory: 0-0 or an opener at 1-1 never reaches a viewer."""
    base = world_fake()
    wrong = {"es/expert": "Minuto 88, 0-0 en el marcador.", "it/beginner": "Siamo ancora sullo 0-0.", "pt/expert": "Ainda 0-0, minuto 88.",
             "nl/beginner": "Het is nog altijd 0-0.", "tr/expert": "Skor hâlâ 0-0, dakika 88.", "ja/beginner": "88分、まだ0対0です。"}
    right = {"es/expert": "Minuto 88, 1-1, y el Wexmoor ha vuelto tras ir perdiendo.", "it/beginner": "Siamo sull'1-1, il Wexmoor ha recuperato.",
             "pt/expert": "Minuto 88, 1-1, o Wexmoor buscou o empate.", "nl/beginner": "Het staat 1-1, Wexmoor kwam terug.",
             "tr/expert": "Dakika 88, skor 1-1, Wexmoor geri döndü.", "ja/beginner": "88分、1対1。ウェクスモアが追いつきました。"}

    def fake(lines):
        async def call(prompt: str) -> str:
            if prompt.startswith("Moment kind match_state"):
                return json.dumps(lines, ensure_ascii=False)
            return await base(prompt)
        return call
    for lines, said in ((wrong, False), (right, True)):
        live = LiveConfig(fake_llm(), CallBudget(80), "fake", tmp_path / str(said), world_call=fake(lines))
        msgs = asyncio.run(Runner(LIB.scene_bundle(WIN, SEED), "live", 1.0, False, live, WIN.start, None, WIN.until, fast=True,
                                  rows=True, world=True).collect())
        state = {m["ch"]: m["text"] for m in msgs if m["k"] == "say" and m["kind"] == "match_state" and m["ch"] >= 6}
        assert (set(state) == set(range(6, 12))) is said, state
        if said:
            assert state[6] == right["es/expert"]
