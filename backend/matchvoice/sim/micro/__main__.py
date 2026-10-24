"""python -m matchvoice.sim.micro [--match comeback-7 ...]: write enriched.jsonl next to the matches. No model call."""
from __future__ import annotations

import argparse
from pathlib import Path

import orjson

from ..engine import Sim
from .enrich import Enriched, enrich
from .report import measure, summary

DEMO = ("comeback-7", "red_card-7", "unlucky-7", "red_card-11", "comeback-135")


def write_enriched(match_id: str, out_root: Path) -> tuple[Path, Enriched]:
    arc, seed = match_id.rsplit("-", 1)
    meta, events, _ = Sim(arc, int(seed)).run()
    result = enrich(meta, events)
    out = out_root / match_id
    out.mkdir(parents=True, exist_ok=True)
    path = out / "enriched.jsonl"
    path.write_bytes(b"\n".join(orjson.dumps(r) for r in result.rows) + b"\n")
    return path, result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", action="append", help="<arc>-<seed>, repeatable; default the demo matches plus comeback-135")
    ap.add_argument("--out", default="data/matches")
    ap.add_argument("--report", action="store_true", help="print the gate measurements of each match")
    a = ap.parse_args()
    for mid in a.match or DEMO:
        path, res = write_enriched(mid, Path(a.out))
        s = res.stats
        print(f"{mid}: {len(res.rows)} rows, {s.segments} segments, {s.implicit_passes} implicit passes, "
              f"{s.implicit_carries} implicit carries, unrepaired {len(s.unrepaired)}, overflow {s.overflow} -> {path}")
        if a.report:
            arc, seed = mid.rsplit("-", 1)
            _, events, _ = Sim(arc, int(seed)).run()
            print(summary(mid, measure(events, res)))


if __name__ == "__main__":
    main()
