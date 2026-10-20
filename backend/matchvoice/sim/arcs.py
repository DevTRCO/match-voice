"""Narrative arcs: the scripted skeleton a synthetic match is simulated around.

Goals and red cards only happen where an arc says so. The simulation fills the
rest, so each match has a known story we can later score commentary against.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Beat:
    kind: str  # goal | red_card
    side: str  # H | A (the team that scores, or the team that gets the card)
    minute: int  # display minute, 1-based
    note: str
    importance: float


@dataclass(frozen=True)
class Window:
    """A stretch of play where one side has the upper hand."""

    side: str
    start: int
    end: int
    boost: float
    note: str


@dataclass(frozen=True)
class Arc:
    name: str
    title: str
    beats: tuple[Beat, ...]
    windows: tuple[Window, ...] = ()
    skills: dict[str, dict[str, float]] = field(default_factory=dict)


ARCS: dict[str, Arc] = {
    "comeback": Arc(
        name="comeback",
        title="Late comeback after an early away goal",
        beats=(
            Beat("goal", "A", 14, "Away side score first on a counter", 0.9),
            Beat("goal", "H", 71, "Home side equalise after sustained pressure", 1.0),
            Beat("goal", "H", 89, "Home side win it late", 1.0),
        ),
        windows=(
            Window("A", 8, 32, 0.30, "Away side start brightly"),
            Window("H", 52, 90, 0.50, "Home side take control and pin the visitors back"),
        ),
        skills={"H": {"attack": 0.60, "finishing": 0.5}, "A": {"attack": 0.5, "finishing": 0.55}},
    ),
    "red_card": Arc(
        name="red_card",
        title="Ten men fight back",
        beats=(
            Beat("red_card", "H", 38, "Home defender sent off", 0.95),
            Beat("goal", "A", 52, "Away side punish the extra man", 0.9),
            Beat("goal", "H", 78, "Ten-man home side equalise", 1.0),
        ),
        windows=(
            Window("A", 38, 62, 0.40, "Away side press the advantage"),
            Window("H", 70, 90, 0.30, "Home side throw everything forward"),
        ),
    ),
    "unlucky": Arc(
        name="unlucky",
        title="Total dominance, no reward",
        beats=(Beat("goal", "A", 64, "Away side score from their only real chance", 1.0),),
        windows=(Window("H", 1, 90, 0.35, "Home side dominate from the first whistle"),),
        skills={"H": {"attack": 0.68, "press": 0.62, "finishing": 0.35}},
    ),
}
