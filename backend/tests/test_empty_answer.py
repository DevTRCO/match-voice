"""An empty model answer is retried once (paid from the budget), never cached, and fails loudly on a second empty answer."""
import asyncio

import pytest

from matchvoice.commentary.analyst import ANALYST_OPTIONS, CallBudget, EmptyAnswer, GuardedLLM


def _fake(answers: list[str]):
    calls: list[str] = []

    async def call(prompt: str) -> str:
        calls.append(prompt)
        return answers[len(calls) - 1]

    return call, calls


def test_empty_answer_is_retried_once_and_counts_toward_the_budget(tmp_path):
    call, calls = _fake(["", '{"en/beginner": "Fine."}'])
    budget = CallBudget(2)
    llm = GuardedLLM(call, budget, "fake", tmp_path)
    assert asyncio.run(llm("p")) == '{"en/beginner": "Fine."}'
    assert len(calls) == 2 and budget.used == 2


def test_two_empty_answers_raise_and_nothing_is_cached(tmp_path):
    call, _ = _fake(["  ", ""])
    llm = GuardedLLM(call, CallBudget(2), "fake", tmp_path)
    with pytest.raises(EmptyAnswer):
        asyncio.run(llm("p"))
    assert not llm.has("p")


def test_empty_answer_with_no_budget_left_does_not_call_again(tmp_path):
    call, calls = _fake(["", "late"])
    llm = GuardedLLM(call, CallBudget(1), "fake", tmp_path)
    with pytest.raises(RuntimeError):
        asyncio.run(llm("p"))
    assert len(calls) == 1 and not llm.has("p")


def test_live_analyst_options_keep_thinking_off_and_room_small():
    assert ANALYST_OPTIONS["thinking"] == {"type": "disabled"}
    assert 1024 <= ANALYST_OPTIONS["max_tokens"] <= 2048
