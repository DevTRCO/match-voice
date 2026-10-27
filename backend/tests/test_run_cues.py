"""Run cues (`run` messages): the board's off-ball runs, sent RUN_LEAD_S before each pass so the picture can run 1 s behind."""
from __future__ import annotations

import asyncio

import pytest

from matchvoice.commentary.analyst import CallBudget
from matchvoice.pipeline import scenes
from matchvoice.pipeline.library import Library
from matchvoice.pipeline.runner import RUN_LEAD_S, LiveConfig, Runner
from test_pipeline import fake_llm

LIB = Library()
WIN = scenes.SCENES["winner"]
CUE_KEYS = {"eid", "t", "t_arr", "player", "by", "pass_type", "under", "x", "y", "sx", "sy"}


def stream(tmp_path, seed: int, rows: bool = True) -> list[dict]:
    live = LiveConfig(fake_llm(), CallBudget(60), "fake", tmp_path)
    b = LIB.scene_bundle(WIN, seed)
    return asyncio.run(Runner(b, "live", 1.0, False, live, WIN.start, None, WIN.until, fast=True, rows=rows).collect())


@pytest.mark.parametrize("seed", [3, 41])
def test_every_targeted_pass_gets_one_cue_ahead_of_its_row(tmp_path, seed):
    msgs = stream(tmp_path, seed)
    row_at = {r["eid"]: (i, m["t"]) for i, m in enumerate(msgs) if m["k"] == "row" for r in m["rows"]}
    passes = {r["eid"]: r for m in msgs if m["k"] == "row" for r in m["rows"] if r["type"] == "pass" and r.get("target") and r["t"] >= WIN.start}
    cues = [(i, m["t"], c) for i, m in enumerate(msgs) if m["k"] == "run" for c in m["rows"]]
    assert passes, "the scene has passes"
    by_eid = {}
    for i, sent, c in cues:
        assert set(c) == CUE_KEYS  # off-ball movement only: no outcome, no receipt fields
        assert c["eid"] not in by_eid, "each cue is sent once"
        by_eid[c["eid"]] = c
        # it goes out when the run may start (never earlier), at least the page's longest run (2 s) before the kick
        assert sent >= min(c["t"] - RUN_LEAD_S, WIN.start - RUN_LEAD_S) - 1e-6 and sent <= c["t"] - 2.0
        ri, _ = row_at[c["eid"]]
        assert i < ri, "the cue comes before its pass row"
    for eid, r in passes.items():
        c = by_eid[eid]
        assert c["player"] == r["target"] and c["t"] == r["t"] and c["pass_type"] == r.get("pass_type")


def test_cues_change_nothing_the_booth_says(tmp_path):
    """The commentary never reads a cue: the same run with rows and cues on says the same lines at the same times as without."""
    on = stream(tmp_path / "a", 7)
    off = stream(tmp_path / "b", 7, rows=False)
    key = lambda ms: [(m["t"], m["ch"], m["m"], m["text"]) for m in ms if m["k"] == "say"]
    assert any(m["k"] == "run" for m in on) and not any(m["k"] == "run" for m in off)
    assert key(on) and key(on) == key(off)
