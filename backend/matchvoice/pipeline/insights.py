"""Insight logs: short, true sentences about the match for the live log, from numbers the fact engine already has.

No model, no lookahead: every insight is computed from the state right after one event, and carries that event's
id. Three kinds, all from existing engine output:

    wp_swing   the win probability of one side moved by 10 points or more across one event (before and after given)
    momentum   the engine's five-minute pressure phase fact (`momentum_phase`): one side holds 75% of the threat
    shots      the engine's `shot_milestone` fact: a player's 3rd or 5th shot, with the team tally

They go out as `log` messages, agent `facts`, step `insight` (docs/PROTOCOL.md). A few per minute at most.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from ..facts.engine import FactEngine
from ..facts.models import Fact
from ..schema import Event

SWING_POINTS = 10  # win probability points (rounded percent) one event must move a side by
MIN_SWING_T = 240.0  # before this a single shot swings the xG-based probability wildly; only a goal or red card is reported then
MAX_PER_MINUTE = 3  # across all kinds, counted over the last 60 match seconds
MIN_GAP_S = {"wp_swing": 20.0, "momentum": 60.0, "shots": 30.0}  # per kind, match seconds


@dataclass
class Insight:
    kind: str
    msg: str
    d: dict


def _shots(n: int) -> str:
    return f"{n} shot" if n == 1 else f"{n} shots"


def _pct(p: float) -> int:
    return round(100 * p)


class InsightFeed:
    """Feed it every event in order, with the win probabilities before and after and the facts that event produced."""

    def __init__(self) -> None:
        self._sent: deque[float] = deque()  # match times of the insights sent in the last minute
        self._last: dict[str, float] = {}
        self._seen: set[tuple[str, int]] = set()  # (kind, event id): one insight per kind and event

    def _allowed(self, kind: str, ev: Event) -> bool:
        while self._sent and self._sent[0] <= ev.t - 60.0:
            self._sent.popleft()
        if (kind, ev.i) in self._seen or len(self._sent) >= MAX_PER_MINUTE:
            return False
        return ev.t - self._last.get(kind, -1e9) >= MIN_GAP_S[kind]

    def _take(self, kind: str, ev: Event) -> None:
        self._seen.add((kind, ev.i))
        self._sent.append(ev.t)
        self._last[kind] = ev.t

    def observe(self, eng: FactEngine, ev: Event, before: tuple[float, float, float],
                new_facts: list[Fact]) -> list[Insight]:
        """Call right after `eng.ingest(ev)`; `before` is `eng.win_probs()` taken just before it."""
        out: list[Insight] = []
        names = eng.team_names
        after = eng.win_probs()
        moves = [(side, _pct(before[i]), _pct(after[i])) for side, i in (("H", 0), ("A", 2))]
        side, was, now = max(moves, key=lambda m: abs(m[2] - m[1]))
        decisive = any(f.kind in ("goal", "red_card") for f in new_facts)
        if abs(now - was) >= SWING_POINTS and (ev.t >= MIN_SWING_T or decisive) and self._allowed("wp_swing", ev):
            self._take("wp_swing", ev)
            move = "rose" if now > was else "fell"
            out.append(Insight("wp_swing", f"Win probability for {names[side]} {move} from {was}% to {now}% ({now - was:+d} points)",
                               {"kind": "wp_swing", "ev": [ev.i], "side": side, "team": names[side],
                                "before": was, "after": now, "delta": now - was,
                                "score": [eng.score["H"], eng.score["A"]]}))
        for f in new_facts:
            if f.kind == "momentum_phase" and f.side and self._allowed("momentum", ev):
                self._take("momentum", ev)
                d = f.data
                out.append(Insight("momentum", f"{names[f.side]} hold {_pct(d['share'])}% of the attacking threat over the last "
                                   f"{d['minutes']} minutes ({_shots(d['shots'])}, {d['possession']}% possession)",
                                   {"kind": "momentum", "ev": list(f.evidence), "side": f.side, "team": names[f.side],
                                    "share": _pct(d["share"]), "shots": d["shots"], "possession": d["possession"],
                                    "minutes": d["minutes"]}))
            elif f.kind == "shot_milestone" and f.side and self._allowed("shots", ev):
                self._take("shots", ev)
                team = eng.team[f.side]
                out.append(Insight("shots", f"{f.data['player_name']} has taken {f.data['shots']} shots, "
                                   f"{names[f.side]} {team.shots} in total ({team.on_target} on target)",
                                   {"kind": "shots", "ev": list(f.evidence), "side": f.side, "team": names[f.side],
                                    "player": f.data["player_name"], "shots": f.data["shots"],
                                    "team_shots": team.shots, "on_target": team.on_target}))
        return out
