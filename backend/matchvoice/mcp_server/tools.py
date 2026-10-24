"""The match tools as plain functions: read data/, the fact engine and the replay pipeline, never a model.

`server.py` exposes them over MCP. Commentary comes from the recorded analyst lines and the templates,
so everything here works without a key. Errors are ValueError with a message a client can act on.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field

from ..commentary.analyst import KEYS
from ..commentary.lang import LANGS, STYLES
from ..commentary.moments import Moment, MomentBuilder
from ..commentary.verifier import Verifier, allowed_for
from ..facts.engine import FactEngine, analyse
from ..pipeline.library import Library, MatchBundle
from ..pipeline.runner import Runner

KEY_MOMENT_MIN = 0.3  # same threshold as `python -m matchvoice.facts`
ALWAYS_KEY = ("goal", "red_card")  # an early goal scores below the threshold (importance follows win-probability swing)
VERIFY_WINDOW_S = 60.0  # players who acted in this window before t may be named in a verified sentence


@lru_cache(maxsize=1)
def library() -> Library:
    return Library()


def _bundle(match: str) -> MatchBundle:
    try:
        return library().bundle(match)
    except KeyError:
        raise ValueError(f"unknown match {match!r}, use one of {library().ids()}") from None


def _t(bundle: MatchBundle, t: float | None) -> float:
    if t is None:
        return bundle.duration
    if not 0 <= t <= bundle.duration:
        raise ValueError(f"t must be between 0 and {bundle.duration:.0f} match seconds")
    return float(t)


def _engine_at(bundle: MatchBundle, t: float | None) -> tuple[FactEngine, list[Moment]]:
    """Fact engine and moments after every event up to and including match second t."""
    eng = FactEngine(bundle.meta)
    mb = MomentBuilder(eng)
    limit, moments = _t(bundle, t), []
    for ev in bundle.events:
        if ev.t > limit:
            break
        moments += mb.feed(ev, eng.ingest(ev))
    return eng, moments


def _channel(lang: str, style: str) -> int:
    if lang not in LANGS or style not in STYLES:
        raise ValueError(f"lang must be one of {list(LANGS)} and style one of {list(STYLES)}")
    return KEYS.index(f"{lang}/{style}")


def _table(headers: list[str], rows: list[list]) -> dict:
    return {"columns": headers, "rows": rows}


# Argument types the MCP client sees as JSON schema: enums, bounds and units.
Match = Annotated[str, Field(description="match id from list_matches, such as comeback-7")]
Lang = Annotated[Literal["en", "de", "fr"], Field(description="commentary language")]
Style = Annotated[Literal["beginner", "expert"], Field(description="commentary style")]
At = Annotated[float, Field(ge=0, description="match seconds since kick-off")]
AtOrEnd = Annotated[float | None, Field(ge=0, description="match seconds since kick-off, full time when omitted")]


# ---------- tools ----------
def list_matches() -> list[dict]:
    """Every demo match: id, title, arc, teams, final score, duration, and whether analyst lines are recorded."""
    return [library().summary(i) for i in library().ids()]


def match_summary(match: Match, t: AtOrEnd = None) -> dict:
    """Score, team statistics, win probability and momentum at match second t (full time when omitted)."""
    b = _bundle(match)
    eng, _ = _engine_at(b, t)
    snap = eng.snapshot()
    names = eng.team_names
    return {**library().summary(match), "at": {
        "t": round(snap["t"], 1), "clock": snap["clock"], "period": snap["period"],
        "score": {"home": snap["score"][0], "away": snap["score"][1], "text": f"{names['H']} {snap['score'][0]}-{snap['score'][1]} {names['A']}"},
        "stats": {"home": snap["stats"]["H"], "away": snap["stats"]["A"]},
        "win_probability": {"home": snap["win"][0], "draw": snap["win"][1], "away": snap["win"][2]},
        "momentum": snap["momentum"], "rhythm": snap["rhythm"]}}


def key_moments(
        match: Match,
        min_importance: Annotated[float, Field(ge=0, le=1, description="importance threshold from 0 to 1")] = KEY_MOMENT_MIN) -> list[dict]:
    """The facts that moved the match (goals, red cards, big chances, saves, pressure phases), in time order.

    Goals and red cards are always included; the rest need `min_importance`.
    """
    b = _bundle(match)
    facts = [f for f in analyse(b.meta, b.events).facts if f.importance >= min_importance or f.kind in ALWAYS_KEY]
    return [f.model_dump(mode="json") for f in sorted(facts, key=lambda f: f.t)]


def commentary_at(
        match: Match, t: At, lang: Lang = "en", style: Style = "expert",
        speed: Annotated[float, Field(ge=0.1, le=600, description="replay speed, 1 is real time")] = 1.0) -> dict:
    """What the commentator on one channel is saying at match second t, and the last line before it.

    The stream is the replay pipeline at `speed` (1 is real time) with the recorded analyst lines, so a
    line's `src` says whether the analyst or a template wrote that exact text.
    """
    b = _bundle(match)
    ch, t = _channel(lang, style), _t(b, t)
    lines = _lines(match, speed)[ch]
    on_air = next((x for x in lines if x["s"] <= t < x["e"]), None)
    before = [x for x in lines if x["s"] <= t]
    last = before[-1] if before else None
    return {"match": match, "t": t, "lang": lang, "style": style, "speed": speed,
            "speaking": on_air is not None, "line": on_air or last,
            "silence_s": None if on_air or last is None else round(t - last["e"], 1)}


def win_probability_curve(
        match: Match,
        step_s: Annotated[float, Field(ge=30, description="minimum match seconds between points")] = 60.0) -> dict:
    """Home, draw and away win probability over the match, at least step_s match seconds apart."""
    b = _bundle(match)
    if step_s < 30:
        raise ValueError("step_s must be at least 30, the engine samples about every 30 match seconds")
    series, kept = analyse(b.meta, b.events).wp_series, []
    for row in series:
        if not kept or row[0] - kept[-1][0] >= step_s:
            kept.append(row)
    if kept[-1] is not series[-1]:
        kept.append(series[-1])
    return {"match": match, "home": b.meta.teams["H"].name, "away": b.meta.teams["A"].name,
            **_table(["t", "home", "draw", "away"], [list(r) for r in kept])}


def player_stats(
        match: Match, player: Annotated[str, Field(description="player id such as H9, a full name or a surname")], t: AtOrEnd = None) -> dict:
    """One player's statistics at match second t. `player` is an id like H9, a full name or a surname."""
    b = _bundle(match)
    roster = [(s, p) for s in ("H", "A") for p in b.meta.teams[s].players]
    key = player.strip().lower()
    hits = [(s, p) for s, p in roster if key in (p.id.lower(), p.name.lower())] \
        or [(s, p) for s, p in roster if key == p.name.split()[-1].lower()]
    if len(hits) != 1:
        raise ValueError(f"{'no player' if not hits else 'several players'} match {player!r}"
                         + (f": {[p.name for _, p in hits]}" if hits else ", use an id like H9 or a full name"))
    side, p = hits[0]
    eng, _ = _engine_at(b, t)
    return {**eng.player_stats(p.id), "team": b.meta.teams[side].name, "side": side, "number": p.number,
            "pos": p.pos, "at": round(eng.t, 1)}


def verify_sentence(match: Match, t: At, text: Annotated[str, Field(description="the sentence to check")], lang: Lang = "en") -> dict:
    """Check a sentence about the match at second t against the facts, with the same verifier the pipeline uses.

    Allowed: the scoreline and statistics at t, the team names, and the players, shot xG values and
    minutes of the last minute of play.
    """
    b = _bundle(match)
    if lang not in LANGS:
        raise ValueError(f"lang must be one of {list(LANGS)}")
    eng, _ = _engine_at(b, t)
    snap = eng.snapshot()
    recent = {ev.player for ev in b.events if eng.t - VERIFY_WINDOW_S <= ev.t <= eng.t and ev.player}
    probe = Moment(id=-1, t=eng.t, clock=eng.clock, kind="query", voice="analyst", priority=0, ttl=0,
                   params={"score": f"{snap['score'][0]}-{snap['score'][1]}"})
    allowed = allowed_for(probe, snap, b.meta)
    allowed.names |= {eng.names[pid].split()[-1].lower() for pid in recent}
    window = [ev for ev in b.events if eng.t - VERIFY_WINDOW_S <= ev.t <= eng.t]
    allowed.numbers |= {round(ev.xg, 2) for ev in window if ev.xg} | {float(ev.clock.split("+")[0]) for ev in window}
    verdict = Verifier(b.meta).check(text, lang, allowed)
    return {"ok": verdict.ok, "violations": [{"code": v.code, "detail": v.detail} for v in verdict.violations],
            "context": {"t": round(eng.t, 1), "clock": eng.clock, "score": snap["score"], "win": snap["win"],
                        "players": sorted(eng.names[pid] for pid in recent)}}


# ---------- replay lines ----------
@lru_cache(maxsize=8)
def _lines(match: str, speed: float) -> tuple[tuple[dict, ...], ...]:
    """Per channel, the final lines of an unpaced replay in start order (a later cut message replaces the first)."""
    if not 0.1 <= speed <= 600:
        raise ValueError("speed must be between 0.1 and 600")
    runner = Runner(_bundle(match), "replay", speed, paced=False)
    with ThreadPoolExecutor(1) as pool:  # an MCP tool runs inside an event loop, asyncio.run needs its own thread
        msgs = pool.submit(asyncio.run, runner.collect()).result()
    final: dict[tuple[int, int], dict] = {}
    for msg in msgs:
        if msg["k"] == "say":
            final[(msg["ch"], msg["m"])] = {k: msg[k] for k in ("m", "kind", "voice", "text", "s", "e", "cut", "src")}
    return tuple(tuple(sorted((v for (ch, _), v in final.items() if ch == c), key=lambda x: x["s"]))
                 for c in range(len(KEYS)))
