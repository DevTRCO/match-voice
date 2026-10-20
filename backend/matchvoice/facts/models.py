from __future__ import annotations

from pydantic import BaseModel, Field

from ..schema import Side


class Fact(BaseModel):
    """A verified statement about the match, with the events that prove it.

    The commentary agents may only say what a Fact (or a snapshot) supports.
    """

    id: int
    t: float
    clock: str
    kind: str  # goal | red_card | big_chance | big_save | momentum_phase | sprint | shot_milestone
    side: Side | None = None
    player: str | None = None
    importance: float  # 0..1, how much the moment moved the match
    data: dict[str, float | int | str] = Field(default_factory=dict)
    evidence: list[int] = Field(default_factory=list)  # event ids
    tags: list[str] = Field(default_factory=list)  # opener, equaliser, go_ahead, late, comeback
