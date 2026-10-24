"""The caster persona: template bank, v3 analyst prompt, continuity from the runner. No network, no model."""
import asyncio
import json
import re

import pytest

from matchvoice.commentary.analyst import ANALYST, CALLER, KEYS, PROMPT_VERSION, RECENT_LINES, SYSTEM, CallBudget, GuardedLLM, build_prompt
from matchvoice.commentary.delivery import energy_of
from matchvoice.commentary.lang import LANGS, STYLES
from matchvoice.commentary.moments import Moment, render_variants
from matchvoice.commentary.newsroom import write_moment
from matchvoice.commentary.templates import T
from matchvoice.commentary.verifier import Verifier, allowed_for
from matchvoice.config import ROOT
from matchvoice.pipeline.demo import demo_insert
from matchvoice.pipeline.library import Library
from matchvoice.pipeline.runner import LiveConfig, Runner
from test_commentary import build
from test_pipeline import GOOD

SCORE_FIELDS = {"score", "hg", "ag"}
NUMERIC_FIELDS = {"xg", "speed", "shots", "win_before", "win_after", "share", "shots_n", "shots_n_dat", "length", "men"}
GENDERED = {"en": r"\b(he|she|his|her|him|hers)\b", "de": r"\b(er|sie|ihm|sein|seine|ihr)\b", "fr": r"\b(il|elle|lui|ils|elles)\b"}


def placeholders(text: str) -> set[str]:
    return set(re.findall(r"{(\w+)}", text))


# ---------- the template bank reads like a commentator ----------
def test_template_numbers_follow_the_discipline():
    """Beginner lines carry no number except a score, expert lines at most one (a scoreline counts as that one)."""
    for kind, langs in T.items():
        for lang, styles in langs.items():
            for style, vs in styles.items():
                for v in vs:
                    nums = placeholders(v) & NUMERIC_FIELDS
                    assert len(nums) <= (0 if style == "beginner" else 1), (kind, lang, style, v)


def test_template_text_has_no_dashes_no_gendered_pronouns_and_no_literal_digits():
    for kind, langs in T.items():
        for lang, styles in langs.items():
            for style, vs in styles.items():
                for v in vs:
                    assert not re.search(r"[—–]", v), v
                    assert not re.search(r"\d", v), (kind, lang, v)  # every number comes from a placeholder
                    assert not re.search(GENDERED[lang], v, re.I), (kind, lang, v)


def test_the_common_kinds_have_several_wordings_so_a_channel_does_not_repeat_itself():
    for kind in ("shot_goal", "shot_saved", "long_ball", "pass_final_third", "yellow", "red", "kickoff_start", "tackle_won"):
        for lang in LANGS:
            for style in STYLES:
                assert len(T[kind][lang][style]) >= (3 if kind in ("shot_goal", "yellow", "red", "kickoff_start", "shot_saved") else 2), (kind, lang, style)


@pytest.mark.parametrize("arc,seed", [("comeback", 7), ("comeback", 135), ("red_card", 7), ("unlucky", 7), ("red_card", 11)])
def test_every_wording_passes_the_verifier_and_stays_short(arc, seed):
    meta, _, _, _, moments, snaps = build(arc, seed)
    ver = Verifier(meta)
    for m in moments:
        allowed = allowed_for(m, snaps[m.id], meta)
        for lang in LANGS:
            for style in STYLES:
                for text in render_variants(m, lang, style):
                    verdict = ver.check(text, lang, allowed)
                    assert verdict.ok, (m.kind, lang, style, text, verdict.feedback())
                    assert len(text) <= 130, (m.kind, lang, style, text)


def test_old_robotic_wording_is_gone():
    flat = " ".join(v for langs in T.values() for styles in langs.values() for vs in styles.values() for v in vs)
    for robotic in ("metres", "Meter", "mètres", "plays long", "progressive pass", "progressiver Pass"):
        assert robotic not in flat


def test_play_by_play_never_recites_expected_goals_and_the_longest_goal_call_is_a_call():
    for kind in ("shot_goal", "shot_saved", "shot_post", "shot_off"):
        for lang, styles in T[kind].items():
            for style, vs in styles.items():
                assert not any("{xg}" in v or "xpected" in v or "erwartet" in v or "attendu" in v for v in vs), (kind, lang, style)
    meta, _, _, _, moments, _ = build("comeback", 135)
    goal = next(x for x in moments if x.kind == "shot_goal")
    shouts = {"en": "GOAL", "de": "TOR", "fr": "BUT"}
    for lang in LANGS:
        for style in STYLES:
            longest = max(render_variants(goal, lang, style), key=len)
            assert shouts[lang] in longest and goal.params["score"] in longest, (lang, style, longest)
            assert "0,2" not in longest and "0.2" not in longest, longest


def test_analysis_fallbacks_and_the_bank_avoid_the_known_calques():
    flat = " ".join(v for langs in T.values() for styles in langs.values() for vs in styles.values() for v in vs)
    for bad in ("Notizbuch", "Das Spiel hat sich bewegt", "Le match a bougé", "The game has moved", "{share}", "a la main", "dreht sich zu",
                "buts attendus", "erwartete Tore", "file sur le terrain", "rate le gros coup", "nach dem Schlusspfiff"):
        assert bad not in flat, bad


def test_director_prefers_the_model_line_whatever_its_length_and_falls_back_when_it_does_not_fit():
    from matchvoice.commentary.director import ChannelDirector
    from matchvoice.commentary.moments import Moment
    m = Moment(1, 0.0, "1", "goal_analysis", "analyst", 60, 60, {})
    short_model = "Level, and the game is open."
    d = ChannelDirector(lambda _m: ["A template that is quite a bit longer than the model line.", short_model], "en", 1.0)
    assert d._choose(m, lookahead=False) == short_model
    d2 = ChannelDirector(lambda _m: ["Short template.", "A very long model line " * 6], "en", 1.0, max_line_s=2.0)
    assert d2._choose(m, lookahead=False) == "Short template."


# ---------- the v4 prompt ----------
def goal_ctx():
    meta, _, _, _, moments, snaps = build("comeback")
    m = next(x for x in moments if x.kind == "goal_analysis")
    return meta, m, snaps[m.id]


def test_version_and_booth_are_named_in_the_system_prompt():
    assert PROMPT_VERSION == "v4"
    for needle in (CALLER, ANALYST, "play-by-play", "colour analyst", "British broadcast", "German TV commentator", "French broadcast",
                   "ONE number", "60 to 110", "home-away", "peak", "rising", "calm"):
        assert needle in SYSTEM, needle


def test_the_bad_examples_are_real_v2_lines_from_the_recording():
    rec = json.loads((ROOT / "data" / "replays" / "comeback-7" / "analyst.json").read_text(encoding="utf-8"))
    spoken = {line for row in rec for key, srcs in row["sources"].items() if srcs == "analyst" for line in [row["lines"][key][-1]]}
    bad = re.findall(r'^- "(.+)"  \(', SYSTEM.split("Bad lines")[1], re.M)
    assert len(bad) >= 4
    for line in bad:
        assert line in spoken, line


def test_good_examples_obey_the_number_discipline():
    block = SYSTEM.split("Good lines")[1].split("Bad lines")[0]
    for line in re.findall(r'"(?:en|de|fr)/(?:beginner|expert)": "([^"]+)"', block):
        scores = re.findall(r"\d+-\d+", line)
        rest = re.sub(r"\d+-\d+", "", line)
        assert len(re.findall(r"\d+(?:[.,]\d+)?", rest)) + bool(scores) <= 1, line


def test_prompt_carries_energy_and_angle_and_no_continuity_by_default():
    meta, m, snap = goal_ctx()
    prompt = build_prompt(m, snap, meta)
    assert f"This moment is {ANALYST}'s" in prompt and f"Energy: {energy_of(m)}" in prompt and "Angle:" in prompt
    assert "Continuity" not in prompt
    assert '"score_home_away": "0-1"' in prompt


def test_the_colour_analyst_does_not_react_again_after_the_caller():
    meta, m, snap = goal_ctx()
    prompt = build_prompt(m, snap, meta)
    assert "do not react again" in prompt and "do not open with a reaction" in prompt
    assert "open with a reaction fragment" not in prompt
    caller = Moment(m.id, m.t, m.clock, "shot_goal", "pbp", 100, 60, {"player": "A", "team": "X", "score": "1-1"})
    assert "Open with a fragment of pure reaction" in build_prompt(caller, snap, meta)
    block = SYSTEM.split("Good lines")[1].split("Bad lines")[0]
    assert "36" not in block and "go_ahead" in block


def test_prompt_shows_the_last_three_lines_per_wanted_channel_only():
    meta, m, snap = goal_ctx()
    recent = {"en/expert": ["one", "two", "three", "four"], "de/expert": ["eins"], "fr/beginner": []}
    prompt = build_prompt(m, snap, meta, only=["en/expert", "fr/beginner"], recent=recent)
    assert "Continuity" in prompt
    assert '"four"' in prompt and '"three"' in prompt and '"two"' in prompt and '"one"' not in prompt and len(["x"] * RECENT_LINES) == 3
    assert "eins" not in prompt and "fr/beginner:" not in prompt  # not asked for, or nothing said yet


def test_newsroom_hands_the_recent_lines_to_every_attempt(tmp_path):
    meta, m, snap = goal_ctx()
    seen = []

    async def fake(prompt):
        seen.append(prompt)
        data = {k: render_variants(m, *k.split("/"))[-1] for k in KEYS}
        if "rejected by the fact checker" not in prompt:
            data["en/expert"] = "A fine goal, worth 0.97 expected goals for the home team on the night."
        return json.dumps(data)
    llm = GuardedLLM(fake, CallBudget(5), "fake", tmp_path)
    asyncio.run(write_moment(llm, meta, m, snap, {"en/expert": ["Corner, Tamsworth United."]}))
    assert len(seen) == 2 and all("Corner, Tamsworth United." in p for p in seen)


# ---------- the runner supplies continuity from lines the channel showed ----------
def run_insert(tmp_path, prompts):
    lib = Library()
    d = demo_insert(lib)

    async def fake(prompt):
        prompts.append(prompt)
        return json.dumps({k: GOOD[k.split("/")[0]] for k in KEYS})
    cfg = LiveConfig(fake, CallBudget(4), "fake", tmp_path)
    r = Runner(lib.bundle(d["match"]), "live", 1.0, paced=False, live=cfg, start=d["start"], until=d["until"])
    asyncio.run(r.collect())
    return r, cfg


def test_runner_passes_the_lines_each_channel_showed_before_the_goal(tmp_path):
    prompts: list[str] = []
    r, cfg = run_insert(tmp_path, prompts)
    assert len(prompts) == 1
    p = prompts[0]
    for key in KEYS:  # two long balls were captioned on every channel before the goal analysis was asked for
        block = p.split(f"\n{key}:\n")[1].split("\n\n")[0].split("\nen/")[0].split("\nde/")[0].split("\nfr/")[0]
        assert block.count("\n  - ") + 1 == 3, (key, block)  # two long balls, then the goal call of the same event
        assert block.rstrip().split("\n")[-1].lower().count("goal") + block.rstrip().split("\n")[-1].count("TOR") + block.rstrip().split("\n")[-1].count("BUT") >= 1, (key, block)
    assert cfg.recent_memo and all(isinstance(v, dict) for v in cfg.recent_memo.values())


def test_a_second_run_builds_the_identical_prompt_so_the_answer_is_cached(tmp_path):
    prompts: list[str] = []
    run_insert(tmp_path, prompts)
    again: list[str] = []
    run_insert(tmp_path, again)  # same cache dir, a new server-side config: its recent-lines memo starts empty
    assert len(prompts) == 1 and again == []  # the second run built the identical prompt, so the cached answer served it


def test_the_runner_records_the_energy_of_each_line_for_the_voice(tmp_path):
    r, _ = run_insert(tmp_path, [])
    levels = {r.energies[k] for k in r.energies}
    assert levels <= {"calm", "rising", "peak"} and "peak" in levels
    goal_lines = [k for k in r.lines if r.energies[k] == "peak"]
    assert goal_lines


def test_every_channel_whose_source_is_analyst_captions_the_analyst_line(tmp_path):
    r, _ = run_insert(tmp_path, [])
    mid = next(i for i, p in r.pubs.items() if any(v == "analyst" for v in p.sources.values()))
    pub = r.pubs[mid]
    assert all(v == "analyst" for v in pub.sources.values())
    for ch, key in enumerate(KEYS):
        text, _ = r.lines[(ch, mid)]
        assert text == pub.lines[key][-1] == GOOD[key.split("/")[0]], (key, text)
