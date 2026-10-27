"""The scenes a public server may run live: a whitelist of (match, start, until) windows, so a visitor cannot start arbitrary
matches or windows that never hit a cap. One entry today, the 89' winner of comeback-135 (the same match as the recorded insert,
same players); a second scene is one more entry in SCENES.

The winner is generated per run (sim/scene.py, `Library.scene_bundle`): the match is the plain simulation up to Tamsworth's goal
kick at 5408.6, then a new 45 to 55 s phase of play (build-up, turnover, Wexmoor's attack) ends in the home side's 2-1 inside
`goal_window`; who scores and how changes with the run's variant. The window is 75 s (the production cap, `LiveLimits`): about 50 s of
play, the goal, then at least 18.5 s for the goal call, the co-commentator's analysis and the lead's score line (checked by
backend/tests/test_public.py with the fake model over several variants).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..schema import EventType
from .library import Library

TOLERANCE_S = 0.05  # a client echoes the numbers it was given; float text may round


@dataclass(frozen=True)
class Scene:
    id: str
    match: str
    start: float
    until: float
    title: str
    fork_after: float | None = None  # generated scenes: the play is new from the first goal kick after this match second
    kick_at: tuple[float, float] | None = None  # the goal kick is taken at a time in this range
    goal_window: tuple[float, float] | None = None  # the generated goal lands inside it

    @property
    def generated(self) -> bool:
        return self.fork_after is not None


SCENES: dict[str, Scene] = {s.id: s for s in (
    Scene("winner", "comeback-135", 5415.0, 5490.0, "The winner, 89 minutes", fork_after=5400.0, kick_at=(5416.0, 5417.5),
          goal_window=(5462.0, 5471.5)),
)}
DEFAULT_SCENE = "winner"


def find_scene(match: str | None, start: float, until: float | None) -> Scene | None:
    """The whitelisted scene with exactly this match and window, or None."""
    for s in SCENES.values():
        if s.match == match and until is not None and abs(s.start - start) <= TOLERANCE_S and abs(s.until - until) <= TOLERANCE_S:
            return s
    return None


def scene_info(lib: Library, scene_id: str = DEFAULT_SCENE) -> dict:
    """What the page shows before Play: the window, the clock and score at its start, and the first goal inside it.
    From the simulation only (no model call). A generated scene has no goal time before it is played (`goal_t` null), only the
    window the goal will land in (`goal_window`); everything before `fork_after` is the same in every variant."""
    s = SCENES[scene_id]
    bundle = lib.bundle(s.match)
    before = [e for e in bundle.events if e.t < s.start]
    score = [sum(1 for e in before if e.type == EventType.SHOT and e.outcome == "goal" and e.team == side) for side in ("H", "A")]
    goal = None if s.generated else next((e for e in bundle.events if s.start <= e.t <= s.until and e.type == EventType.SHOT
                                          and e.outcome == "goal"), None)
    period = before[-1].period if before else 1
    out = {"id": s.id, "match": s.match, "start": s.start, "until": s.until, "clock": before[-1].clock if before else "0",
           "score": score, "goal_t": None if goal is None else round(goal.t, 1), "title": s.title, "attack": attack_of(period)}
    if s.goal_window is not None:
        out["goal_window"] = list(s.goal_window)
    return out


def attack_of(period: int) -> dict[str, float]:
    """The x of the goal each side attacks in this period (the simulation's rule, sim/engine.py `_direction`: the home side attacks
    x = 105 in the first half and x = 0 in the second). Fixed per half, so a page needs no shot to draw the board the right way round."""
    home = 105.0 if period == 1 else 0.0
    return {"H": home, "A": 105.0 - home}
