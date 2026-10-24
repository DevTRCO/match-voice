"""The demo insert: a short live window around one goal, for a 30 second look at the whole pipeline at 1x.

comeback-135 was picked by simulating the candidates offline: one model moment in the window (the goal analysis, so
one call), two spoken lines before the goal and the second one still talking when the goal cuts it off, and the
analyst's reaction inside the window. The window starts LEAD_S before the goal and ends TAIL_S after it.
"""
from __future__ import annotations

from ..schema import EventType
from .library import Library

ARC, SEED, GOAL_NUMBER = "comeback", 135, 2  # the home side's equaliser, 71'
LEAD_S, TAIL_S = 12.0, 8.0  # the first spoken line lands under 2 s after Play


def demo_insert(lib: Library) -> dict:
    bundle = lib.bundle(f"{ARC}-{SEED}")
    goals = [e for e in bundle.events if e.type == EventType.SHOT and e.outcome == "goal"]
    goal = goals[GOAL_NUMBER - 1]
    start = float(int(goal.t - LEAD_S))
    before = [e for e in bundle.events if e.t < start]
    score = [sum(1 for e in before if e.type == EventType.SHOT and e.outcome == "goal" and e.team == side) for side in ("H", "A")]
    clock = before[-1].clock if before else "0"
    return {"match": bundle.meta.id, "arc": ARC, "seed": SEED, "start": start,
            "until": float(int(goal.t + TAIL_S) + 1), "goal_t": round(goal.t, 1), "goal_clock": goal.clock,
            "score": score, "clock": clock}  # the state the viewer sees before Play
