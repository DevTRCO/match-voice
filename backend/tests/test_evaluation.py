import pytest

import matchvoice.commentary.analyst as analyst
from matchvoice.commentary.analyst import KEYS
from matchvoice.evaluation import metrics as mx
from matchvoice.evaluation.report import render
from matchvoice.evaluation.run import evaluate_all
from matchvoice.pipeline.library import Library

LIB = Library()


@pytest.fixture(scope="module")
def res():
    return evaluate_all(LIB)


def test_covers_all_matches_and_channels_without_a_model_call(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the evaluation must not call a model")
    monkeypatch.setattr(analyst, "claude_llm", refuse)
    out = evaluate_all(LIB, speeds=(30.0,))
    run = out["runs"]["30"]
    assert out["model_calls"] == 0 and run["matches"] == LIB.recorded_ids()
    assert set(run["by_channel"]) == set(KEYS) and set(run["by_language"]) == {"en", "de", "fr"}
    assert set(run["by_style"]) == {"beginner", "expert"}


def test_rates_are_consistent(res):
    for run in res["runs"].values():
        for g in (run["overall"], *run["by_channel"].values()):
            for key in ("grounding_rate", "said_by_analyst_share", "keymoment_spoken_coverage", "speech_share"):
                assert 0 <= g[key] <= 1, key
            assert abs(g["speech_share"] + g["silence_share"] - 1) < 1e-3
        assert run["overall"]["lines"] == sum(g["lines"] for g in run["by_channel"].values())
        det = run["overall"]["keymoment_detection_coverage"]
        assert run["overall"]["keymoment_spoken_coverage"] <= det + 1e-9 <= 1 + 1e-9


def test_every_spoken_line_is_grounded_and_goals_are_found(res):
    run = res["runs"]["30"]
    assert run["overall"]["grounding_rate"] == 1.0
    for m in run["per_match"].values():
        goals = [it for it in m["detection"]["items"] if it["kind"] == "goal"]
        assert goals and all(it["detected"] and len(it["spoken"]) == len(KEYS) for it in goals)


def test_verifier_catches_injected_errors(res):
    for kind, v in res["runs"]["30"]["overall"]["injected_errors"].items():
        assert v["applicable"] > 0 and v["catch_rate"] >= 0.95, kind


def test_silence_only_appears_in_real_time(res):
    assert res["runs"]["30"]["overall"]["speech_share"] > 0.99
    real = res["runs"]["1"]["overall"]
    assert 0.05 < real["speech_share"] < 0.4 and real["longest_silence_viewer_s"] > 20


def test_latency_matches_the_recorded_model_latency(res):
    o = res["runs"]["30"]["overall"]
    assert o["ready_delay_viewer_s"]["n"] == o["model_latency_s"]["n"] > 0
    assert abs(o["ready_delay_viewer_s"]["median"] - o["model_latency_s"]["median"]) < 1.0


def test_results_are_deterministic(res):
    assert evaluate_all(LIB) == res


def test_report_is_plain_text_without_em_dashes(res):
    text = render(res)
    assert "—" not in text and "–" not in text
    assert "## Weaknesses" in text and "Per channel" in text


def test_mutations_produce_wrong_but_well_formed_lines():
    b = LIB.bundle("comeback-7")
    run = mx.run_replay(b, 30.0)
    from matchvoice.commentary.verifier import Verifier, allowed_for
    ver = Verifier(b.meta)
    m = next(x for x in run.moments.values() if x.kind == "shot_goal")
    allowed = allowed_for(m, run.snapshots[m.id], b.meta)
    muts = mx.mutations("Lemaire scores for Marlow Bay United, it is 0-1.", allowed, ver)
    assert "1-0" in muts["score_swapped"] and not ver.check(muts["score_swapped"], "en", allowed).ok
