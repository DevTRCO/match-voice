"""Overlay protocol v1: the compact JSON messages every client consumes.

docs/PROTOCOL.md is the contract. This module is its only encoder, so live, replay and the
static export cannot drift apart. Frames carry arrays and numeric codes, everything else
(hello, say, log, end, error) is low volume and uses readable keys.
"""
from __future__ import annotations

from ..commentary.analyst import KEYS
from ..commentary.lang import ALL_KEYS, BOOTH, LANGS, STYLES
from ..schema import PITCH_L, PITCH_W, Event, EventType, MatchMeta

VERSION = 1
SCALE = 10  # coordinates travel as integer decimetres

TYPES: list[str] = [t.value for t in EventType]
OUTCOMES: list[str] = ["", "complete", "incomplete", "out", "goal", "saved", "blocked", "off_target", "post",
                       "won", "free_kick", "half_time", "full_time", "yellow", "red"]
SET_PIECES: list[str] = ["", "corner", "free_kick", "goal_kick", "throw_in"]
STATS: list[str] = ["possession", "shots", "on_target", "xg", "passes", "pass_acc", "corners", "fouls",
                    "yellow", "red", "tackles"]
EVENT_FIELDS: list[str] = ["i", "type", "side", "player", "x", "y", "end_x", "end_y", "outcome", "set_piece", "xg"]

_TYPE = {name: i for i, name in enumerate(TYPES)}
_OUTCOME = {name: i for i, name in enumerate(OUTCOMES)}
_SET_PIECE = {name: i for i, name in enumerate(SET_PIECES)}

def _channel(i: int, key: str) -> dict:
    """One channel of `hello.channels`: id, key, language and level (`style` is the older name of `level`), and its booth: the lead and, in a
    two-person booth, the co-commentator, each with name and gender. The world channels (ids 6 to 11) are solo booths (`solo` true, no `co`)."""
    b = BOOTH[key]
    out = {"id": i, "key": key, "lang": b.lang, "style": b.level, "level": b.level, "solo": b.solo,
           "lead": {"name": b.lead.name, "gender": b.lead.gender}}
    if b.co:
        out["co"] = {"name": b.co.name, "gender": b.co.gender}
    return out


ALL_CHANNELS: list[dict] = [_channel(i, key) for i, key in enumerate(ALL_KEYS)]
CHANNELS: list[dict] = ALL_CHANNELS[:len(KEYS)]  # the core channels, ids 0..5: every run has them; a run with the world booth adds 6..11
assert [c["lang"] for c in CHANNELS[::len(STYLES)]] == list(LANGS)

AGENTS = {
    "analyst_wrote": "analyst", "retry": "analyst", "analyst_unavailable": "analyst", "analyst_error": "analyst",
    "writing": "analyst", "lookup": "analyst", "verified": "verifier", "rejected": "verifier", "fallback": "publisher", "dropped": "publisher",
    "timeout": "analyst",
}


def players_of(meta: MatchMeta) -> list[dict]:
    """Flat player list, home first. The `player` field of an event indexes into it."""
    return [{"id": p.id, "side": s, "n": p.number, "name": p.name, "pos": p.pos, "grp": p.group}
            for s in ("H", "A") for p in meta.teams[s].players]


def hello(meta: MatchMeta, mode: str, speed: float, dt: float, duration: float, start: float = 0.0,
          until: float | None = None, run: str | None = None, channels: list[dict] | None = None) -> dict:
    msg = {
        "k": "hello", "v": VERSION, "t": 0.0, "mode": mode, "speed": speed, "dt": dt, "duration": round(duration, 1),
        "start": round(start, 1),
        "match": {
            "id": meta.id, "title": meta.title, "competition": meta.competition, "venue": meta.venue,
            "arc": meta.arc, "pitch": [PITCH_L, PITCH_W],
            "teams": [{"side": s, "name": meta.teams[s].name, "short": meta.teams[s].short,
                       "color": meta.teams[s].color, "formation": meta.teams[s].formation} for s in ("H", "A")],
        },
        "players": players_of(meta), "scale": SCALE, "types": TYPES, "outcomes": OUTCOMES,
        "setPieces": SET_PIECES, "stats": STATS, "eventFields": EVENT_FIELDS, "channels": CHANNELS if channels is None else channels,
    }
    if until is not None:  # a live insert: the stream ends at this match second instead of full time
        msg["until"] = round(until, 1)
    if run is not None:  # a live run: the id the voice endpoint looks its lines up by
        msg["run"] = run
    return msg


def _dm(v: float | None) -> int:
    return -1 if v is None else round(v * SCALE)


def encode_event(ev: Event, player_index: dict[str, int]) -> list[int]:
    outcome = ev.card if ev.type == EventType.CARD else ev.outcome
    return [ev.i, _TYPE[ev.type], 0 if ev.team == "H" else 1, player_index.get(ev.player or "", -1),
            _dm(ev.x), _dm(ev.y), _dm(ev.end_x), _dm(ev.end_y), _OUTCOME[outcome or ""],
            _SET_PIECE[ev.set_piece or ""], round((ev.xg or 0.0) * 100)]


class FrameEncoder:
    """Turns engine snapshots into frames. Stats go out as deltas against the previous frame."""

    def __init__(self, meta: MatchMeta):
        self.player_index = {p["id"]: i for i, p in enumerate(players_of(meta))}
        self._last: list[list] = [[None] * len(STATS), [None] * len(STATS)]

    def frame(self, snap: dict, events: list[Event]) -> dict:
        delta: list[dict] = []
        for n, side in enumerate(("H", "A")):
            d = {}
            for j, name in enumerate(STATS):
                v = snap["stats"][side][name]
                if v != self._last[n][j]:
                    d[str(j)] = v
                    self._last[n][j] = v
            delta.append(d)
        out = {"k": "f", "t": round(snap["t"], 1), "c": snap["clock"], "p": snap["period"], "s": snap["score"],
               "wp": [round(x * 1000) for x in snap["win"]], "mo": round(snap["momentum"] * 1000),
               "e": [encode_event(ev, self.player_index) for ev in events]}
        if delta[0] or delta[1]:
            out["st"] = delta
        return out


def say(t: float, channel: int, moment: int, kind: str, voice: str, text: str, start: float, end: float,
        cut: bool, source: str, w: float | None = None, lat: float | None = None, cached: bool = False, who: str | None = None,
        ins: dict | None = None) -> dict:
    out = {"k": "say", "t": round(t, 2), "ch": channel, "m": moment, "kind": kind, "voice": voice, "text": text,
           "s": round(start, 2), "e": round(end, 2), "cut": int(cut), "src": source}
    if who:  # the person in the booth who says it: the channel's lead (voice pbp) or its co-commentator (voice analyst)
        out["who"] = who
    if ins:  # an insight line (a pattern set-up, or the goal line that pays one off): what the overlay highlights, in pitch metres
        out["ins"] = ins
    if cached:  # the analyst line came from the disk cache: written by an earlier call, not by this run
        out["cached"] = 1
    if w is not None:  # paced live only: wall seconds since the stream started, and since the event was due
        out["w"] = round(w, 3)
    if lat is not None:
        out["lat"] = round(lat, 3)
    return out


def voice(t: float, channel: int, moment: int, start: float, end: float, cut: bool = False, skip: bool = False,
          w: float | None = None, lat: float | None = None) -> dict:
    """Live only. The voice side of a line the `say` already captioned: it starts at `s` and ends at `e`, was cut
    at `e` (`cut`), or will never be spoken (`skip`)."""
    out = {"k": "voice", "t": round(t, 2), "ch": channel, "m": moment, "s": round(start, 2), "e": round(end, 2)}
    if cut:
        out["cut"] = 1
    if skip:
        out["skip"] = 1
    if w is not None:
        out["w"] = round(w, 3)
    if lat is not None:
        out["lat"] = round(lat, 3)
    return out


def rows(t: float, rows: list[dict], w: float | None = None) -> dict:
    """Additive, live runs with rows on (`fast=1` or `rows=1`): the enriched rows (sim/micro/enrich.py, the shape of
    ui/public/insert/micro.json) whose time `t` the stream has reached, in time order. A pass row comes at its kick, its receipt
    at the arrival. Coordinates are metres, as in the enriched file (not decimetres like frames)."""
    out = {"k": "row", "t": round(t, 2), "rows": rows}
    if w is not None:
        out["w"] = round(w, 3)
    return out


def heartbeat(t: float, w: float) -> dict:
    """Paced live only: keeps a client's match clock moving while nothing else is sent."""
    return {"k": "hb", "t": round(t, 2), "w": round(w, 3)}


def describe(step: dict) -> str:
    """One readable line for a step of Published.trail."""
    s = step["step"]
    if s == "analyst_wrote":
        if step["cached"]:
            return (f"Analyst reused {step['lines']} cached lines (cache hit, {step.get('wall_s', 0)}s here; "
                    f"the original call took {step['latency_s']}s)")
        return f"Analyst wrote {step['lines']} lines (model call, {step['latency_s']}s)"
    if s == "verified":
        return f"Verifier accepted {step['accepted']} lines, {step['failing']} failing"
    if s == "rejected":
        return f"Verifier rejected {step['key']}: {step['why']}"
    if s == "retry":
        return f"Analyst retries {', '.join(step['failing'])}"
    if s == "fallback":
        return f"Publisher uses templates for {', '.join(step['keys'])}"
    if s == "dropped":
        return f"Publisher drops {', '.join(step['keys'])}: a world line has no template, so it is not said"
    if s in ("analyst_unavailable", "analyst_error"):
        return f"Analyst unavailable: {step['reason']}"
    if s == "timeout":
        return f"Analyst timed out after {step['after_s']}s"
    return s


def log(t: float, at: float, agent: str, step: str, moment: int | None, msg: str, detail: dict | None = None,
        channel: int | None = None, w: float | None = None) -> dict:
    out = {"k": "log", "t": round(t, 2), "at": round(at, 2), "agent": agent, "step": step, "m": moment, "msg": msg}
    if w is not None:  # paced live only: wall seconds since the stream started
        out["w"] = round(w, 3)
    if channel is not None:
        out["ch"] = channel
    if detail:
        out["d"] = detail
    return out


def end(t: float, score: list[int], events: int, says: int, calls: int | None) -> dict:
    return {"k": "end", "t": round(t, 2), "score": score, "events": events, "says": says, "calls": calls}


def error(code: str, message: str) -> dict:
    return {"k": "error", "code": code, "message": message}
