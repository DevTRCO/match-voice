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


class Role(StrEnum):
    """How a player plays his slot (docs/DATA-MODEL.md 1.2)."""

    SWEEPER_KEEPER = "sweeper_keeper"
    SHOT_STOPPER = "shot_stopper"
    BALL_PLAYING_CB = "ball_playing_cb"
    STOPPER = "stopper"
    COVER_CB = "cover_cb"
    CENTRE_BACK = "centre_back"
    INVERTED_FULLBACK = "inverted_fullback"
    ATTACKING_FULLBACK = "attacking_fullback"
    DEFENSIVE_FULLBACK = "defensive_fullback"
    ANCHOR = "anchor"
    DEEP_PLAYMAKER = "deep_playmaker"
    PLAYMAKER = "playmaker"
    BALL_WINNER = "ball_winner"
    BOX_TO_BOX = "box_to_box"
    CENTRAL_MIDFIELDER = "central_midfielder"
    SHADOW_STRIKER = "shadow_striker"
    ADVANCED_PLAYMAKER = "advanced_playmaker"
    WIDE_MIDFIELDER = "wide_midfielder"
    INVERTED_WINGER = "inverted_winger"
    WINGER = "winger"
    TARGET_FORWARD = "target_forward"
    POACHER = "poacher"
    PRESSING_FORWARD = "pressing_forward"
    COMPLETE_FORWARD = "complete_forward"


class Trait(StrEnum):
    """A trait a commentator may cite (docs/DATA-MODEL.md 1.3)."""

    RAPID = "rapid"
    QUICK_OFF_THE_MARK = "quick_off_the_mark"
    AERIAL_THREAT = "aerial_threat"
    LONG_RANGE = "long_range"
    SET_PIECE_TAKER = "set_piece_taker"
    PRESS_RESISTANT = "press_resistant"
    ENGINE = "engine"
    TWO_FOOTED = "two_footed"
    TOUGH_TACKLER = "tough_tackler"
    VISIONARY = "visionary"
    DRIBBLER = "dribbler"


class Attrs(BaseModel):
    """Player attributes on a 1..99 scale. `keeping` is for goalkeepers only."""

    pace: int
    passing: int
    finishing: int
    acceleration: int
    dribbling: int
    vision: int
    defending: int
    aerial: int
    stamina: int
    keeping: int | None = None


class Season(BaseModel):
    """Synthetic season so far (invented like everything else)."""

    apps: int
    goals: int
    assists: int
    clean_sheets: int | None = None  # GK and DEF only


class Player(BaseModel):
    id: str
    name: str
    number: int
    pos: str
    group: Literal["GK", "DEF", "MID", "FWD"]
    # profile (docs/DATA-MODEL.md 1.1); optional so older meta.json files still load
    attrs: Attrs | None = None
    foot: Literal["L", "R", "both"] | None = None
    weak_foot: int | None = None  # 1..5
    height_cm: int | None = None
    age: int | None = None
    top_speed: float | None = None  # m/s
    work_rate: Literal["low", "medium", "high"] | None = None
    role: Role | None = None
    traits: list[Trait] | None = None  # at most 2
    season: Season | None = None
    captain: bool | None = None


class PressPlan(BaseModel):
    height: Literal["high", "mid", "low"]
    intensity: float  # 0..1
    triggers: list[str]


class Tactics(BaseModel):
    """A team plan (docs/DATA-MODEL.md 2.1). Heights and widths are metres in the attacking frame."""

    formation: str
    shape_in: str
    shape_out: str
    line_height: float  # m from own goal line
    block: Literal["low", "mid", "high"]
    press: PressPlan
    build_up: Literal["short", "mixed", "direct"]
    width: float  # m, team width in possession
    tempo: float  # 0..1
    tempo_class: Literal["slow", "measured", "high"]
    counter: bool
    corner_delivery: Literal["inswing", "outswing", "short"]


class PostureShift(BaseModel):
    """One change of game-state posture or of the ten_men modifier (docs/DATA-MODEL.md 2.3)."""

    side: Side
    t_trigger: float  # match second of the goal, card or checkpoint
    t: float  # match second it takes effect (first restart, or the 180 s fallback)
    reason: Literal["goal", "red_card", "checkpoint"]
    posture: Literal["base", "chase", "protect"]
    ten_men: bool
    on_pitch: int


class TeamMeta(BaseModel):
    side: Side
    name: str
    short: str
    color: str
    formation: str
    players: list[Player]
    tactics: Tactics | None = None
    postures: list[PostureShift] | None = None  # shifts only; the plan starts as `base`


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
    end: float | None = None  # momentum_swing only: match second the stretch ends
