"""Run the newsroom over one match and store the published lines for replay.

python -m matchvoice.commentary.precompute --arc comeback --seed 7 --max-calls 10
Calls the model only for the analyst moment kinds below, through the disk cache.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from pathlib import Path

import orjson

from ..config import ROOT, anthropic_api_key
from ..facts.engine import FactEngine
from ..sim.engine import Sim
from .analyst import KEYS, RECENT_LINES, CallBudget, GuardedLLM, claude_llm
from .moments import MomentBuilder
from .newsroom import write_moment

MODEL = "claude-haiku-5-5"
MODEL_KINDS = ("momentum", "goal_analysis", "big_save_analysis", "big_chance_analysis", "pattern_insight")  # pattern_insight: live dense runs only (runner)


async def main_async(arc: str, seed: int, max_calls: int) -> None:
    meta, events, _ = Sim(arc, seed).run()
    eng = FactEngine(meta)
    mb = MomentBuilder(eng)
    todo = []
    for ev in events:
        for m in mb.feed(ev, eng.ingest(ev)):
            if m.kind in MODEL_KINDS:
                todo.append((m, eng.snapshot()))
    budget = CallBudget(max_calls)
    llm = GuardedLLM(claude_llm(MODEL, anthropic_api_key()), budget, MODEL)
    published, records = [], []
    said: dict[str, list[str]] = {k: [] for k in KEYS}  # a recording has no director: the lines published so far stand in for what was spoken
    for m, snap in todo:
        pub = await write_moment(llm, meta, m, snap, {k: v[-RECENT_LINES:] for k, v in said.items()})
        for k in KEYS:
            said[k].append(pub.lines[k][-1])
        published.append(pub)
        records.append({**asdict(pub), "kind": m.kind, "t": m.t})  # kind and t let the replay check its ids
        src = sorted(set(pub.sources.values()))
        steps = [t["step"] for t in pub.trail]
        print(f"{m.clock:>5}' {m.kind:<18} sources={src} rejected={steps.count('rejected')} "
              f"retries={steps.count('retry')} latency={pub.latency_s:.1f}s calls_used={budget.used}/{max_calls}", flush=True)
    out = ROOT / "data" / "replays" / meta.id
    out.mkdir(parents=True, exist_ok=True)
    (out / "analyst.json").write_bytes(orjson.dumps(records, option=orjson.OPT_INDENT_2))
    n = sum(len(p.sources) for p in published)
    ok = sum(1 for p in published for s in p.sources.values() if s == "analyst")
    print(f"{ok}/{n} lines written by the analyst, rest template fallback; model calls this run: {budget.used}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arc", default="comeback")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--max-calls", type=int, default=10)
    a = ap.parse_args()
    asyncio.run(main_async(a.arc, a.seed, a.max_calls))


if __name__ == "__main__":
    main()
