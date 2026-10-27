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
# Two parts of comeback-135, played back to back like a broadcast cut: part 1 is a quiet spell at 68' (the ball is dead from a save to the
# corner) where the co-commentator points out a habit (commentary/patterns.py: Ibsen keeps winning it, then it always goes short, nothing
# across) and the lead says that Wexmoor have come from behind before (the dossier, sim/dossier.py); part 2 is the build-up and the
# equaliser at 71', which breaks the habit (the first ball after Ibsen's interception goes straight across), and the co line pays it off.
# About 37 s in all as heard (docs/INSERT-SCRIPT.md 7, option A, plus the breaths after the goal and 0.5 s after the last voice): the lead-ins are short (the story line 1.5 s after the open, Ibsen 0.7 s after the cut)
# and part 2 runs on long enough for the real TV order after the goal: the call, the co-commentator's line, then the lead's score line.
STORY_LEAD_S, STORY_TAIL_S = 1.0, 6.5  # without a set-up: the story's part from 1 s before it to 6.5 s after it
CUT_BEFORE_S = 0.5  # with a set-up, part 1 runs to just before the dead ball ends (the corner), so set-up and story both fit
GOAL_LEAD_S, GOAL_TAIL_S = 11.0, 15.5


def story_insert(lib: Library) -> dict:
    """The parts of the story insert, found in the data: the comeback story before the equaliser, and the equaliser."""
    from ..commentary.fast import build_layers
    from ..sim.micro.enrich import enrich
    d = demo_insert(lib)
    bundle = lib.bundle(d["match"])
    goal_t = d["goal_t"]
    moments = build_layers(bundle.meta, bundle.events, enrich(bundle.meta, bundle.events).rows)
    story = max((m for m in moments if m.kind == "story_note" and m.t < goal_t and "comebacks" in m.params["story"]), key=lambda m: m.t)
    setup_t = _setup_in_dead_ball(bundle, story.t)
    if setup_t is not None:  # the co-commentator's set-up opens the quiet spell, the lead's story follows it
        nxt = next(e.t for e in bundle.events if e.t > story.t)
        part1 = (float(int(setup_t - STORY_LEAD_S)), float(int(nxt - CUT_BEFORE_S)))
    else:
        part1 = (float(int(story.t - STORY_LEAD_S)), float(int(story.t + STORY_TAIL_S)))
    parts = [part1, (float(int(goal_t - GOAL_LEAD_S)), float(int(goal_t + GOAL_TAIL_S) + 1))]
    before = [e for e in bundle.events if e.t < parts[0][0]]
    score = [sum(1 for e in before if e.type == EventType.SHOT and e.outcome == "goal" and e.team == side) for side in ("H", "A")]
    return {**d, "start": parts[0][0], "until": parts[1][1], "parts": parts, "story_t": round(story.t, 1),
            "setup_t": None if setup_t is None else round(setup_t, 1),
            "length": round(sum(b - a for a, b in parts)), "score": score, "clock": before[-1].clock if before else "0"}


def _setup_in_dead_ball(bundle, t: float) -> float | None:
    """When the pattern detector's set-up for the home side (the side that equalises) falls in the dead ball around match second `t`:
    the time a live run that joins just before that dead ball would say it (patterns.py, no lookahead), or None."""
    from ..commentary.patterns import QUIET_S, PatternFeed
    before = [e for e in bundle.events if e.t < t]
    if not before:
        return None
    pf = PatternFeed(bundle.meta)
    for e in before:
        pf.feed(e)
    at = before[-1].t + QUIET_S
    if at >= t or not pf.dead(at) or pf.habit("H", before[-1].period) is None:
        return None
    return at
