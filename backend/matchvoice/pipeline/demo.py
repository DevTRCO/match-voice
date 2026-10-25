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


# ---------- the story insert: the booth fills a quiet spell, then the goal ----------
# Two parts of comeback-135, played back to back like a broadcast cut: part 1 is a quiet spell at 68' where the co-commentator
# says that Wexmoor have come from behind before (the dossier, sim/dossier.py), part 2 is the build-up and the equaliser at 71'.
STORY_LEAD_S, STORY_TAIL_S = 3.0, 6.5
GOAL_LEAD_S, GOAL_TAIL_S = 12.0, 7.0


def story_insert(lib: Library) -> dict:
    """The parts of the story insert, found in the data: the comeback story before the equaliser, and the equaliser."""
    from ..commentary.fast import build_layers
    from ..sim.micro.enrich import enrich
    d = demo_insert(lib)
    bundle = lib.bundle(d["match"])
    goal_t = d["goal_t"]
    moments = build_layers(bundle.meta, bundle.events, enrich(bundle.meta, bundle.events).rows)
    story = max((m for m in moments if m.kind == "story_note" and m.t < goal_t and "comebacks" in m.params["story"]), key=lambda m: m.t)
    parts = [(float(int(story.t - STORY_LEAD_S)), float(int(story.t + STORY_TAIL_S))),
             (float(int(goal_t - GOAL_LEAD_S)), float(int(goal_t + GOAL_TAIL_S) + 1))]
    before = [e for e in bundle.events if e.t < parts[0][0]]
    score = [sum(1 for e in before if e.type == EventType.SHOT and e.outcome == "goal" and e.team == side) for side in ("H", "A")]
    return {**d, "start": parts[0][0], "until": parts[1][1], "parts": parts, "story_t": round(story.t, 1),
            "length": round(sum(b - a for a, b in parts)), "score": score, "clock": before[-1].clock if before else "0"}
