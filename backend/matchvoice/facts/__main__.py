"""python -m matchvoice.facts data/matches/comeback-7"""
from __future__ import annotations

import sys
from pathlib import Path

import orjson

from ..schema import Event, MatchMeta
from .engine import analyse


def load(path: Path) -> tuple[MatchMeta, list[Event]]:
    meta = MatchMeta.model_validate(orjson.loads((path / "meta.json").read_bytes()))
    events = [Event.model_validate(orjson.loads(line)) for line in (path / "events.jsonl").read_text().splitlines()]
    return meta, events


def main() -> None:
    meta, events = load(Path(sys.argv[1]))
    eng = analyse(meta, events)
    print(f"{len(events)} events -> {len(eng.facts)} facts")
    for f in sorted((f for f in eng.facts if f.importance >= 0.3), key=lambda f: f.t):
        who = f.data.get("player_name", "")
        print(f"{f.clock:>5}  {f.kind:<15} {f.side or '-'}  imp {f.importance:.2f}  {who}  {f.tags}  "
              f"{ {k: v for k, v in f.data.items() if k not in ('player_name', 'team')} }")
    snap = eng.snapshot()
    print("final:", snap["score"], snap["stats"]["H"]["possession"], "% poss H, win", snap["win"])
    mid = min(eng.wp_series, key=lambda r: abs(r[0] - 3000))
    print("win prob near 50':", mid)


if __name__ == "__main__":
    main()
