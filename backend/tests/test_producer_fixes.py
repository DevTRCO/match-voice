"""The producers' fixes to the story insert (2026-10-25): a breath after the goal call and after the co line, the score line after the
co line, a finished end on every accepted line, the second shout word, the lead's line after the co line in the v6 prompt, and the
pronoun wordings for a squad whose gender is known."""
from matchvoice.commentary.analyst import AFTER, KEYS, SYSTEM, build_prompt
from matchvoice.commentary.delivery import hype_for_tts
from matchvoice.commentary.director import BREATH_S, ChannelDirector
from matchvoice.commentary.moments import Moment, render_variants
from matchvoice.commentary.newsroom import finish_line
from matchvoice.commentary.templates import T, WORDS
from test_commentary import build


def _m(i, t, kind, voice, priority, ready=None):
    m = Moment(i, t, "71", kind, voice, priority, 60, {})
    m.ready_t = t if ready is None else ready
    return m


def test_the_co_line_breathes_after_the_call_and_the_score_after_the_co_line():
    words = {"shot_goal": ["Goal! Fontaine! Wexmoor are level!"], "goal_analysis": ["Doesn't let it settle, and nobody closes him down. Game on."],
             "score_line": ["One-all, and twenty minutes or so to go."]}
    d = ChannelDirector(lambda m: words[m.kind], "en", 1.0, captions_first=True, voice_wait_s=20.0)
    d.push(_m(1, 10.0, "shot_goal", "pbp", 100))
    d.push(_m(2, 10.0, "goal_analysis", "analyst", 60, ready=10.2))
    d.push(_m(3, 10.0, "score_line", "pbp", 60, ready=10.201))  # known at once (a cached answer): it still waits for the co line
    d.advance(60.0)
    out, _ = d.close()
    call, co, score = (next(s for s in out if s.kind == k) for k in ("shot_goal", "goal_analysis", "score_line"))
    assert co.start >= call.end + BREATH_S[("shot_goal", "goal_analysis")] - 1e-9
    assert score.start >= co.end + BREATH_S[("goal_analysis", "score_line")] - 1e-9
    assert abs(co.start - call.end - 0.7) < 1e-6 and abs(score.start - co.end - 0.4) < 1e-6


def test_an_accepted_line_always_ends_like_a_sentence():
    assert finish_line("Tavares first time, nobody closes him down. Level") == "Tavares first time, nobody closes him down. Level."
    for done in ("Game on.", "Tout est relancé !", "Und heute?", "Da muss doch einer drauf.", ""):
        assert finish_line(done) == done


def test_only_the_first_shout_word_is_stretched_and_the_second_reads_as_a_word():
    assert hype_for_tts("BUT ! BUT de Fontaine ! Wexmoor égalise !", "fr", "peak", "eleven_flash_v2_5") == "BUUUT! But de Fontaine ! Wexmoor égalise !"
    assert hype_for_tts("GOAL! Kenji Fontaine! GOAL!", "en", "peak", "eleven_flash_v2_5") == "GOOOAL! Kenji Fontaine! Goal!"


def test_the_v6_prompt_names_the_leads_line_after_the_co_line_and_the_v5_mistakes():
    meta, _, _, _, moments, snaps = build("comeback")
    m = next(x for x in moments if x.kind == "goal_analysis")
    recent = {k: ["Goal! Fontaine! Wexmoor are level!"] for k in KEYS} | {f"{AFTER}fr/expert": ["Un partout. Le match est relancé, il reste une vingtaine de minutes."]}
    p = build_prompt(m, snaps[m.id], meta, recent=recent)
    assert "The lead's line right AFTER yours" in p and '- fr/expert: "Un partout. Le match est relancé' in p
    assert f"{AFTER}" not in p.split("Continuity")[1].split("The lead's line")[0]  # the after lines are not shown as continuity
    plain = build_prompt(m, snaps[m.id], meta, recent={k: ["Goal!"] for k in KEYS})
    assert "right AFTER yours" not in plain
    bad = SYSTEM.split("Also wrong, from v5")[1]
    for line in ("Fontaine first time, nobody closes him down. Level\"", "Level again.", "Hinten geholt", "und wieder gleich", "Volé chez eux",
                 "Fontaine en une touche. Tout est relancé."):
        assert line in bad, line
    good = SYSTEM.split("Good lines")[1].split("Bad lines")[0]
    assert "chez eux" not in good and "Hinten den Ball geholt" not in good and "first time, Okoro first time" not in good


def test_the_first_time_call_is_the_name_alone_and_the_beginner_chain_is_spoken_not_ordered():
    assert {lang: WORDS["pass_call"][lang]["first_time"] for lang in ("en", "de", "fr")} == {"en": "{target}!", "de": "{target}!", "fr": "{target} !"}
    assert WORDS["pass_call_plain"]["de"]["switch"] == "Rüber zu {target}..." and WORDS["pass_call_plain"]["de"]["long"] == "Lang nach vorne auf {target}!"
    assert all("!" not in v for v in T["duel"]["fr"]["beginner"][1:2])  # no "!" on a ball won in the own half (script 8.6)


def test_a_fragment_says_il_only_for_a_squad_whose_gender_is_known():
    base = {"player": "Rasmussen", "facet": "chest", "team": "Wexmoor Athletic", "team_code": "H", "named": False}
    with_squad = Moment(1, 0.0, "70", "touch", "pbp", 50, 5, {**base, "squad": "men"}, layer="fast")
    without = Moment(2, 0.0, "70", "touch", "pbp", 50, 5, dict(base), layer="fast")
    assert "Il contrôle de la poitrine." in render_variants(with_squad, "fr", "beginner")
    assert not any(v.startswith("Il ") for v in render_variants(without, "fr", "beginner"))
    assert "Elle contrôle de la poitrine." in render_variants(Moment(3, 0.0, "70", "touch", "pbp", 50, 5, {**base, "squad": "women"}, layer="fast"),
                                                             "fr", "beginner")
