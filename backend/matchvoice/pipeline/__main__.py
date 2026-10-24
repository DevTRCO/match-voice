"""python -m matchvoice.pipeline play --match comeback-7 --speed 600
python -m matchvoice.pipeline export --out ui/public/replays --speed 30
python -m matchvoice.pipeline export-insert --out ui/public/insert/replay.json   # 30 s, answer cache only, no model call
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import orjson

from ..commentary.analyst import KEYS
from .export import capture_insert, write_static
from .library import Library
from .runner import DEFAULT_SPEED, LiveConfig, LiveUnavailable, Runner


async def play(a: argparse.Namespace) -> None:
    lib = Library()
    live = LiveConfig.from_env(a.live_calls) if a.mode == "live" else None
    ch = KEYS.index(a.channel)
    async for msg in Runner(lib.bundle(a.match), a.mode, a.speed, not a.unpaced, live).stream():
        k = msg["k"]
        if k == "say" and msg["ch"] == ch:
            print(f"{msg['s']:7.1f}s {msg['kind']:<18} [{msg['src']}]{' (cut)' if msg['cut'] else ''} {msg['text']}")
        elif k == "log" and msg.get("ch", ch) == ch:
            print(f"{msg['at']:7.1f}s   {msg['agent']:<9} {msg['msg']}")
        elif k in ("hello", "end"):
            print({x: v for x, v in msg.items() if x in ("k", "mode", "speed", "duration", "score", "says", "calls")})


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("play", help="print one channel of a run")
    p.add_argument("--match", default="comeback-7")
    p.add_argument("--mode", choices=["replay", "live"], default="replay")
    p.add_argument("--speed", type=float, default=DEFAULT_SPEED)
    p.add_argument("--channel", choices=KEYS, default="en/expert")
    p.add_argument("--unpaced", action="store_true", help="do not wait for the wall clock")
    p.add_argument("--live-calls", type=int, default=0, help="model call budget, live mode only")
    e = sub.add_parser("export", help="write the static replay files")
    e.add_argument("--out", type=Path, default=Path("ui/public/replays"))
    e.add_argument("--speed", type=float, default=DEFAULT_SPEED)
    i = sub.add_parser("export-insert", help="record the demo insert (live run at 1x, from the answer cache) as one JSON file")
    i.add_argument("--out", type=Path, default=Path("ui/public/insert/replay.json"))
    a = ap.parse_args()
    try:
        if a.cmd == "play":
            asyncio.run(play(a))
        elif a.cmd == "export-insert":
            doc = asyncio.run(capture_insert(Library()))
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_bytes(orjson.dumps(doc))
            print(a.out, f"{len(doc['messages'])} messages, {doc['calls']} model calls", file=sys.stderr)
        else:
            for path in write_static(Library(), a.out, a.speed):
                print(path)
    except LiveUnavailable as exc:
        raise SystemExit(f"live mode refused ({exc.code}): {exc}")


if __name__ == "__main__":
    main()
