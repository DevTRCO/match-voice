import pytest

from matchvoice.commentary.director import schedule
from matchvoice.commentary.lang import LANGS, STYLES
from matchvoice.commentary.moments import MomentBuilder, render_variants
from matchvoice.commentary.templates import T
from matchvoice.commentary.verifier import Verifier, allowed_for
from matchvoice.facts.engine import FactEngine
from matchvoice.sim.engine import Sim


def build(arc: str, seed: int = 7):
    meta, events, truth = Sim(arc, seed).run()
    eng, mb = FactEngine(meta), None
    mb = MomentBuilder(eng)
    moments, snaps = [], {}
    for ev in events:
        facts = eng.ingest(ev)
        for m in mb.feed(ev, facts):
            moments.append(m)
            snaps[m.id] = eng.snapshot()
    return meta, events, truth, eng, moments, snaps


@pytest.fixture(scope="module")
def comeback():
    return build("comeback")


def test_template_bank_is_complete_and_ordered():
    for kind, langs in T.items():
        assert set(langs) == set(LANGS), kind
        for lang, styles in langs.items():
            assert set(styles) == set(STYLES), (kind, lang)
            for style, vs in styles.items():
                assert vs and [len(v) for v in vs] == sorted(len(v) for v in vs), (kind, lang, style)


def test_every_template_line_passes_the_verifier(comeback):
    meta, _, _, _, moments, snaps = comeback
    ver = Verifier(meta)
    assert moments
    for m in moments:
        allowed = allowed_for(m, snaps[m.id], meta)
        for lang in LANGS:
            for style in STYLES:
                for text in render_variants(m, lang, style):
                    verdict = ver.check(text, lang, allowed)
                    assert verdict.ok, (m.kind, lang, style, text, verdict.feedback())


def test_verifier_rejects_invented_facts(comeback):
    meta, _, _, _, moments, snaps = comeback
    ver = Verifier(meta)
    goal = next(m for m in moments if m.kind == "shot_goal")
    allowed = allowed_for(goal, snaps[goal.id], meta)
    other = next(p for t in meta.teams.values() for p in t.players
                 if p.name.split()[-1].lower() != goal.params["player"].lower()).name.split()[-1]
    bad = {
        "number_unsupported": f"{goal.params['player']} scores with a chance worth 0.97 expected goals for the team.",
        "score_mismatch": f"What a goal by {goal.params['player']} and it is 7-0 for the team on the pitch.",
        "player_unsupported": f"A goal by {other} and the team are celebrating this goal now.",
        "language_mismatch": "Das ist ein Tor und die Mannschaft ist sehr glücklich mit dem Ergebnis.",
    }
    for code, text in bad.items():
        verdict = ver.check(text, "en", allowed)
        assert not verdict.ok and code in {x.code for x in verdict.violations}, (code, verdict)


def test_director_never_overlaps_and_always_speaks_goals(comeback):
    meta, _, _, _, moments, _ = comeback
    for lang in LANGS:
        for speed in (1.0, 20.0):
            spoken, dropped = schedule(moments, lambda m: render_variants(m, lang, "expert"), lang, speed)
            spoken.sort(key=lambda s: s.start)
            assert all(a.end <= b.start + 1e-6 for a, b in zip(spoken, spoken[1:]))
            said = {s.moment_id for s in spoken}
            assert all(m.id in said for m in moments if m.kind == "shot_goal")
            assert all(d.reason in ("stale", "low_priority") for d in dropped)


def test_director_interrupts_for_a_goal():
    from matchvoice.commentary.moments import Moment
    low = Moment(0, 0.0, "1", "corner", "pbp", 45, 60, {"team": "X"})
    goal = Moment(1, 1.0, "1", "shot_goal", "pbp", 100, 60, {"player": "A", "team": "X", "score": "1-0", "xg": 0.3})
    spoken, _ = schedule([low, goal], lambda m: ["a long sentence that takes a while to say out loud"] if m is low else ["GOAL!"], "en")
    assert spoken[0].cut and spoken[1].kind == "shot_goal"


def test_shorter_wording_when_a_bigger_moment_is_close():
    from matchvoice.commentary.moments import Moment
    a = Moment(0, 0.0, "1", "corner", "pbp", 45, 60, {})
    b = Moment(1, 3.0, "1", "shot_saved", "pbp", 70, 60, {})
    variants = {0: ["Corner.", "A corner for the home side, and they will send it into the box."], 1: ["Saved!"]}
    spoken, _ = schedule([a, b], lambda m: variants[m.id], "en")
    assert spoken[0].text == "Corner."
