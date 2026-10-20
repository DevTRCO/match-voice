import asyncio
import json

import pytest

from matchvoice.commentary.analyst import KEYS, CallBudget, GuardedLLM
from matchvoice.commentary.moments import render_variants
from matchvoice.commentary.newsroom import write_moment
from test_commentary import build


@pytest.fixture(scope="module")
def ctx():
    meta, _, _, _, moments, snaps = build("comeback")
    m = next(x for x in moments if x.kind == "goal_analysis")
    return meta, m, snaps[m.id]


def good_answer(m):
    return json.dumps({k: render_variants(m, *k.split("/"))[-1] for k in KEYS})


def run(ctx, tmp_path, fake, max_calls=10):
    meta, m, snap = ctx
    llm = GuardedLLM(fake, CallBudget(max_calls), "fake", tmp_path)
    return asyncio.run(write_moment(llm, meta, m, snap)), llm


def test_clean_run_publishes_analyst_lines(ctx, tmp_path):
    async def fake(prompt):
        return good_answer(ctx[1])
    pub, llm = run(ctx, tmp_path, fake)
    assert set(pub.sources.values()) == {"analyst"} and llm.budget.used == 1


def test_rejected_line_is_rewritten_after_feedback(ctx, tmp_path):
    calls = []

    async def fake(prompt):
        calls.append(prompt)
        data = json.loads(good_answer(ctx[1]))
        if "rejected by the fact checker" not in prompt:
            data["en/expert"] = "A fine goal, worth 0.97 expected goals for the home team on the night."
        return json.dumps(data)
    pub, llm = run(ctx, tmp_path, fake)
    steps = [t["step"] for t in pub.trail]
    assert "rejected" in steps and "retry" in steps
    assert pub.sources["en/expert"] == "analyst" and llm.budget.used == 2
    assert "en/expert" in calls[1] and "0.97" in calls[1]  # the retry names the problem


def test_stubborn_failure_falls_back_to_template_for_that_line_only(ctx, tmp_path):
    async def fake(prompt):
        data = json.loads(good_answer(ctx[1]))
        data["de/beginner"] = "Das war ein Tor mit 0.97 erwarteten Toren und ein Wahnsinn für alle."
        return json.dumps(data)
    pub, _ = run(ctx, tmp_path, fake)
    assert pub.sources["de/beginner"] == "template" and pub.sources["fr/expert"] == "analyst"
    assert "fallback" in [t["step"] for t in pub.trail]


def test_model_error_never_breaks_the_stream(ctx, tmp_path):
    async def fake(prompt):
        raise ConnectionError("model unreachable")
    pub, _ = run(ctx, tmp_path, fake)
    assert set(pub.sources.values()) == {"template"} and pub.lines["en/expert"]


def test_budget_is_a_hard_cap_and_cache_is_free(ctx, tmp_path):
    async def fake(prompt):
        return good_answer(ctx[1])
    pub, _ = run(ctx, tmp_path, fake, max_calls=0)
    assert set(pub.sources.values()) == {"template"}
    run(ctx, tmp_path, fake, max_calls=1)  # fills the cache with one call
    pub2, llm2 = run(ctx, tmp_path, fake, max_calls=0)  # same prompt, no budget needed
    assert set(pub2.sources.values()) == {"analyst"} and llm2.budget.used == 0
