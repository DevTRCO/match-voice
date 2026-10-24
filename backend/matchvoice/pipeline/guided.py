"""The guided live run: a fresh random match and the 60 second window of it with the most going on.

Picked by simulation and the fact engine only (deterministic code, no model). The answer is just a match id, a seed and a
window; `<arc>-<seed>` is the id the protocol already knows, so the same id always gives the same match.
"""
from __future__ import annotations

import random

from ..commentary.moments import MomentBuilder
from ..facts.engine import FactEngine
from ..schema import EventType
from ..sim.arcs import ARCS
from .library import Library, MatchBundle

WINDOW_S = 60.0  # the longest guided run, match seconds
LEAD_S = 40.0  # the window opens this long before the goal: build-up the voice can describe
TAIL_S = 14.0  # and closes this long after it. The simulator is silent for about 50 s after a goal, so a longer tail is a frozen pitch
MAX_SEED = 999_999  # the largest seed a `<arc>-<seed>` id can carry


def pick_window(bundle: MatchBundle) -> dict:
    """{start, until, goal_t}: the window of at most WINDOW_S match seconds with the most action.

    Candidates are the goals, one window each, from LEAD_S before the goal to TAIL_S after it (the pitch is silent after that). Without a goal the single highest-priority
    moment is the candidate. A window's action is the summed priority of the moments in it (the same moments the live
    commentary would detect); the best wins, the earlier one on a tie."""
    eng = FactEngine(bundle.meta)
    mb = MomentBuilder(eng)
    moments = []
    for ev in bundle.events:
        moments += [(m.t, m.priority) for m in mb.feed(ev, eng.ingest(ev))]
    goals = [e.t for e in bundle.events if e.type == EventType.SHOT and e.outcome == "goal"]
    anchors = goals or ([min(moments, key=lambda m: (-m[1], m[0]))[0]] if moments else [0.0])
    last = float(int(bundle.duration))

    def window(anchor: float) -> tuple[float, float]:
        start = float(max(0, int(min(anchor - LEAD_S, last - (LEAD_S + TAIL_S)))))
        return start, min(anchor + TAIL_S, start + WINDOW_S, last)

    def action(anchor: float) -> int:
        start, until = window(anchor)
        return sum(p for t, p in moments if start <= t <= until)

    best = max(anchors, key=lambda a: (action(a), -a))
    start, until = window(best)
    return {"start": start, "until": until, "goal_t": round(best, 1) if goals else None}


def guided_live(lib: Library, rng: random.Random | None = None) -> dict:
    """A random arc and seed, simulated, and its best window. `rng` is a SystemRandom unless a test passes its own."""
    rng = rng or random.SystemRandom()
    arc = rng.choice(sorted(ARCS))
    seed = rng.randint(1, MAX_SEED)
    match_id = f"{arc}-{seed}"
    win = pick_window(lib.bundle(match_id))
    return {"match": match_id, "arc": arc, "seed": seed, "start": win["start"], "until": win["until"],
            "window_s": win["until"] - win["start"], "goal_t": win["goal_t"]}
