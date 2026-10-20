"""Director: decides what is said, when, and in which words, under a speech-time budget.

One voice per channel (a language and style). The director keeps silence when nothing
matters, lets the highest-priority moment speak first, interrupts for goals and red
cards, and picks the longest wording that fits the time it has. Every decision, spoken
or dropped, is recorded for the log.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .lang import est_seconds
from .moments import Moment

INF = float("inf")


@dataclass
class Spoken:
    moment_id: int
    kind: str
    voice: str
    start: float  # match seconds
    end: float
    text: str
    cut: bool = False  # interrupted by something more important


@dataclass
class Dropped:
    moment_id: int
    kind: str
    reason: str  # low_priority | stale


def schedule(
    moments: list[Moment],
    variants_of: Callable[[Moment], list[str]],
    lang: str,
    speed: float = 1.0,
    min_priority: int = 25,
    interrupt_min: int = 90,
    interrupt_margin: int = 20,
    max_line_s: float = 25.0,
) -> tuple[list[Spoken], list[Dropped]]:
    """Schedule one channel. `speed` is match seconds per wall second (1 = real time)."""
    arrivals = sorted(moments, key=lambda m: (m.ready_t, -m.priority))
    n = len(arrivals)
    queue: list[Moment] = []
    out: list[Spoken] = []
    dropped: list[Dropped] = []
    cur: tuple[Moment, float, float, str] | None = None
    last_said: dict[str, str] = {}
    now, i = 0.0, 0

    def speech(text: str) -> float:
        return est_seconds(text, lang) * speed

    def pick(t: float) -> Moment | None:
        for m in list(queue):
            if t > m.t + m.ttl:
                queue.remove(m)
                dropped.append(Dropped(m.id, m.kind, "stale"))
        cands = list(queue)
        if any(m.voice == "pbp" for m in cands):
            cands = [m for m in cands if m.voice == "pbp"]  # analysis waits for the action
        return max(cands, key=lambda m: (m.priority, -m.t)) if cands else None

    def arrive(m: Moment) -> None:
        if m.priority < min_priority:
            dropped.append(Dropped(m.id, m.kind, "low_priority"))
        else:
            queue.append(m)

    while True:
        next_arr = arrivals[i].ready_t if i < n else INF
        if cur is None:
            m = pick(now)
            if m is not None:
                queue.remove(m)
                texts = sorted(variants_of(m), key=len)
                limit = next((a.ready_t for a in arrivals[i:] if a.priority > m.priority), INF)
                budget = min(max(limit - now, 0.0), max_line_s * speed)
                fitting = [x for x in texts if speech(x) <= budget] or texts[:1]
                fresh = [x for x in fitting if x != last_said.get(m.kind)] or [x for x in texts if x != last_said.get(m.kind)]
                text = (fresh or fitting)[-1]
                last_said[m.kind] = text
                cur = (m, now, now + speech(text), text)
                continue
            if i >= n:
                break
            now = max(now, next_arr)
            arrive(arrivals[i])
            i += 1
            continue

        m, start, end, text = cur
        if end <= next_arr:
            out.append(Spoken(m.id, m.kind, m.voice, start, end, text))
            now, cur = end, None
            continue
        a = arrivals[i]
        i += 1
        now = a.ready_t
        arrive(a)
        if a.priority >= interrupt_min and m.priority < interrupt_min and a.priority >= m.priority + interrupt_margin:
            out.append(Spoken(m.id, m.kind, m.voice, start, now, text, cut=True))
            cur = None

    for m in queue:
        dropped.append(Dropped(m.id, m.kind, "stale"))
    return out, dropped
