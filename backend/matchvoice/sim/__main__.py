"""python -m matchvoice.sim --arc comeback --seed 7"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import orjson

from ..schema import EventType
from .arcs import ARCS
from .engine import Sim


def write_match(arc: str, seed: int, out_root: Path) -> Path:
    meta, events, truth = Sim(arc, seed).run()
    out = out_root / meta.id
    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_bytes(orjson.dumps(meta.model_dump(mode="json", exclude_none=True), option=orjson.OPT_INDENT_2))
    (out / "events.jsonl").write_bytes(
        b"\n".join(orjson.dumps(e.model_dump(exclude_none=True)) for e in events) + b"\n")
    (out / "truth.json").write_bytes(
        orjson.dumps([t.model_dump() for t in truth], option=orjson.OPT_INDENT_2))
    return out


def summary(out: Path) -> str:
    meta = orjson.loads((out / "meta.json").read_bytes())
    events = [orjson.loads(line) for line in (out / "events.jsonl").read_text().splitlines()]
    lines = [f"{meta['teams']['H']['name']} vs {meta['teams']['A']['name']}  ({meta['arc']}), {len(events)} events"]
    for s in ("H", "A"):
        ev = [e for e in events if e["team"] == s]
        passes = [e for e in ev if e["type"] == "pass"]
        ok = sum(1 for e in passes if e.get("outcome") == "complete")
        shots = [e for e in ev if e["type"] == "shot"]
        goals = sum(1 for e in shots if e.get("outcome") == "goal")
        xg = sum(e.get("xg", 0) for e in shots)
        cnt = Counter(e["type"] for e in ev)
        lines.append(
            f"  {s}: passes {len(passes)} ({100 * ok / max(1, len(passes)):.0f}%), shots {len(shots)}, goals {goals}, "
            f"xG {xg:.2f}, tackles {cnt['tackle']}, fouls {cnt['foul']}, cards {cnt['card']}, press {cnt['pressure']}")
    last = events[-1]
    lines.append(f"  ends at t={last['t']:.0f}s clock {last['clock']}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arc", default="comeback", choices=list(ARCS))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/matches")
    a = ap.parse_args()
    out = write_match(a.arc, a.seed, Path(a.out))
    print(summary(out))
    print(f"written to {out}")


if __name__ == "__main__":
    main()
