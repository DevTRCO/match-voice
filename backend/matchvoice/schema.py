"""Event and match schema.

The vocabulary (pass, shot, tackle, pressure, ...) follows common football
event data. All coordinates are absolute pitch metres: x in 0..105 (left to
right on screen), y in 0..68. Every match is synthetic.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

PITCH_L = 105.0
PITCH_W = 68.0

Side = Literal["H", "A"]


class EventType(StrEnum):
    KICKOFF = "kickoff"
    PASS = "pass"
    CARRY = "carry"
    SHOT = "shot"
    TACKLE = "tackle"
    INTERCEPTION = "interception"
    PRESSURE = "pressure"
    FOUL = "foul"
    CARD = "card"
    POSSESSION_CHANGE = "possession_change"
    PERIOD_END = "period_end"


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    i: int
    t: float  # match seconds, half-time break excluded
    period: int
    clock: str  # display clock, e.g. "67" or "45+2"
    type: EventType
    team: Side
    player: str | None = None
    x: float
    y: float
    end_x: float | None = None
    end_y: float | None = None
    outcome: str | None = None
    receiver: str | None = None
    set_piece: str | None = None
    length: float | None = None  # pass or carry distance, m
    difficulty: float | None = None  # pass difficulty 0..1
    ball_speed: float | None = None  # km/h
    speed: float | None = None  # player speed on carries, km/h
    xg: float | None = None
    shot_speed: float | None = None  # km/h
    body_part: str | None = None
    keeper: str | None = None
    under_pressure: bool | None = None
    card: str | None = None
    reason: str | None = None
    score: list[int] | None = None  # [home, away] after a goal


class Player(BaseModel):
    id: str
    name: str
    number: int
    pos: str
    group: Literal["GK", "DEF", "MID", "FWD"]


class TeamMeta(BaseModel):
    side: Side
    name: str
    short: str
    color: str
    formation: str
    players: list[Player]


class MatchMeta(BaseModel):
    id: str
    seed: int
    arc: str
    title: str
    competition: str
    venue: str
    teams: dict[str, TeamMeta]


class TruthItem(BaseModel):
    """Ground truth about what really happened, used to evaluate commentary."""

    t: float
    clock: str
    kind: str  # goal | red_card | momentum_swing | late_goal ...
    side: Side
    note: str
    importance: float
