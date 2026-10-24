"""Static export: the whole replay stream as one JSON document a static host can serve."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable

import orjson

from . import protocol as proto
from ..commentary.analyst import CallBudget
from .demo import demo_insert
from .library import Library, MatchBundle
from .runner import DEFAULT_SPEED, LiveConfig, Runner

CATCH_UP_KEPT = 3  # catch-up frames kept: the last ones carry the score, clock and the ring of recent events the pitch draws


async def build_replay(bundle: MatchBundle, speed: float = DEFAULT_SPEED) -> dict:
    """Same messages as a replay stream at this speed, each with its emission time `t`."""
    hello, *messages = await Runner(bundle, "replay", speed, paced=False).collect()
    return {"v": proto.VERSION, "speed": speed, "hello": hello, "messages": messages}


def write_static(lib: Library, out: Path, speed: float = DEFAULT_SPEED) -> list[Path]:
    """<out>/matches.json plus <out>/<match>/replay.json for every match."""
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for match_id in lib.recorded_ids():
        path = out / match_id / "replay.json"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(orjson.dumps(asyncio.run(build_replay(lib.bundle(match_id), speed))))
        written.append(path)
    index = out / "matches.json"
    index.write_bytes(orjson.dumps([lib.summary(i) for i in lib.recorded_ids()], option=orjson.OPT_INDENT_2))
    return written + [index]


def trim_catch_up(messages: list[dict], start: float, kept: int = CATCH_UP_KEPT) -> list[dict]:
    """Drop all but the last `kept` catch-up frames (match time before `start`). They are state for a client that
    resumes a stream; a recording that always starts at the insert needs only the newest ones."""
    early = [i for i, m in enumerate(messages) if m["k"] == "f" and m["t"] < start]
    drop = set(early[:-kept]) if kept else set(early)
    return [m for i, m in enumerate(messages) if i not in drop]


async def capture_insert(lib: Library, call: Callable[[str], Awaitable[str]] | None = None) -> dict:
    """The demo insert as a paced live run at 1x (about 30 s of wall time), saved as it was streamed.

    The static build and a server without a live budget play this file. Analyst answers come from the answer cache; the
    default model call raises, so a prompt that is not cached fails the capture instead of costing money."""
    async def no_call(prompt: str) -> str:
        raise RuntimeError("the insert capture makes no model calls: the answer is not in the cache")

    d = demo_insert(lib)
    live = LiveConfig(call or no_call, CallBudget(1))
    runner = Runner(lib.bundle(d["match"]), "live", 1.0, True, live, d["start"], None, d["until"])
    hello, *messages = await runner.collect()
    hello.pop("run", None)  # a recording has no run: the server voice endpoint knows nothing about it
    return {"v": proto.VERSION, "demo": d, "hello": hello, "calls": live.budget.used,
            "messages": trim_catch_up(messages, d["start"])}
