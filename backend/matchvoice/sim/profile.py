"""Player profiles: attributes, roles, traits, season (docs/DATA-MODEL.md 1.1 to 1.3).

Every draw comes from its own stream `Random(f"{seed}:profile:{player_id}")`, never from the simulation's
generator, so adding or changing a profile cannot move a single event of the skeleton. Values the simulation
already draws (`passing`, `finishing`, `pace`) are exported as they are.

Order of draws inside a player's stream (part of the contract, a change reshuffles every profile):
foot, weak foot, height, age, acceleration, dribbling, vision, defending, aerial, stamina, keeping, season.
"""
from __future__ import annotations

import random
from typing import Literal, Protocol

from ..schema import Attrs, Player, Role, Season, Trait

Group = Literal["GK", "DEF", "MID", "FWD"]
Foot = Literal["L", "R", "both"]
WorkRate = Literal["low", "medium", "high"]

LEFT_SLOTS = ("LB", "LM", "LW")
RIGHT_SLOTS = ("RB", "RM", "RW")
FULLBACKS = ("LB", "RB")
BOOL_MARGIN = 5  # margin of a trait that is not a threshold (two_footed), so it ranks like a 5 point lead

HEIGHT_MEAN = {"GK": 190, "CB": 187, "FB": 178, "MID": 179, "W": 175, "ST": 183}
DRIBBLING_MEAN = {"GK": 30, "DEF": 50, "MID": 62, "FWD": 68}
DEFENDING_MEAN = {"GK": 20, "DEF": 72, "MID": 58, "FWD": 35}
GOAL_RATE = {"GK": 0.0, "DEF": 0.04, "MID": 0.09, "FWD": 0.35}  # per appearance, before attribute and role factors
ASSIST_RATE = {"GK": 0.01, "DEF": 0.05, "MID": 0.14, "FWD": 0.12}
GOAL_ROLE = {Role.POACHER: 1.3, Role.SHADOW_STRIKER: 1.2, Role.BOX_TO_BOX: 1.3, Role.TARGET_FORWARD: 1.1,
             Role.ATTACKING_FULLBACK: 1.2, Role.PRESSING_FORWARD: 0.9}
ASSIST_ROLE = {Role.PLAYMAKER: 1.5, Role.ADVANCED_PLAYMAKER: 1.5, Role.DEEP_PLAYMAKER: 1.3, Role.WINGER: 1.3,
               Role.INVERTED_WINGER: 1.2, Role.ATTACKING_FULLBACK: 1.4, Role.COMPLETE_FORWARD: 1.2}


class SlotPlayer(Protocol):
    """What the profile needs from a simulated player (`sim.engine.SimPlayer` fits)."""

    id: str
    pos: str
    group: str
    ay: float
    passing: float
    finishing: float
    pace: float


def _attr(v: float) -> int:
    return max(1, min(99, round(v)))


def slot_class(pos: str) -> str:
    """Height class of a slot: GK, CB, FB, MID, W or ST."""
    if pos in ("GK", "CB", "ST"):
        return pos
    if pos in FULLBACKS:
        return "FB"
    if pos in ("RW", "LW"):
        return "W"
    if pos in ("DM", "CM", "AM", "RM", "LM"):
        return "MID"
    raise ValueError(f"unknown slot {pos!r}")


def flank(pos: str, ay: float) -> str:
    """'L', 'R' or 'C' for a slot. Low ay is the left side (LB sits at ay 8, RB at ay 60)."""
    if pos in LEFT_SLOTS:
        return "L"
    if pos in RIGHT_SLOTS:
        return "R"
    if pos == "CB":
        return "L" if ay < 34 else "R"
    return "C"


def _foot(rng: random.Random, pos: str, ay: float) -> Foot:
    p_left = 0.22 + (0.25 if flank(pos, ay) == "L" else 0.0)
    u = rng.random()
    if u < p_left:
        return "L"
    if u < p_left + 0.06:
        return "both"
    return "R"


def work_rate_of(stamina: int, group: str) -> WorkRate:
    """From stamina and the slot's group: midfielders count a little more, defenders a little less."""
    adj = stamina + {"GK": 0, "DEF": -3, "MID": 4, "FWD": 2}[group]
    return "high" if adj >= 80 else ("low" if adj < 62 else "medium")


def role_of(pos: str, attrs: Attrs, foot: Foot, height_cm: int, work_rate: WorkRate) -> Role:
    """First matching rule of table 1.2 wins."""
    a = attrs
    opposite = {"L": "R", "R": "L"}
    if pos == "GK":
        return Role.SWEEPER_KEEPER if a.passing >= 60 else Role.SHOT_STOPPER
    if pos == "CB":
        if a.passing >= 62:
            return Role.BALL_PLAYING_CB
        if a.defending >= 72 and a.aerial >= 65:
            return Role.STOPPER
        return Role.COVER_CB if a.pace >= 65 else Role.CENTRE_BACK
    if pos in FULLBACKS:
        side = "L" if pos == "LB" else "R"
        if a.passing >= 62 and foot == opposite[side]:
            return Role.INVERTED_FULLBACK
        if a.pace >= 60 and a.stamina >= 65:
            return Role.ATTACKING_FULLBACK
        return Role.DEFENSIVE_FULLBACK
    if pos == "DM":
        return Role.ANCHOR if a.defending >= 65 else Role.DEEP_PLAYMAKER
    if pos == "CM":
        if a.passing >= 68:
            return Role.PLAYMAKER
        if a.defending >= 66:
            return Role.BALL_WINNER
        return Role.BOX_TO_BOX if a.stamina >= 70 else Role.CENTRAL_MIDFIELDER
    if pos == "AM":
        return Role.SHADOW_STRIKER if a.finishing >= 62 else Role.ADVANCED_PLAYMAKER
    if pos in ("RM", "LM"):
        return Role.WIDE_MIDFIELDER
    if pos in ("RW", "LW"):
        side = "L" if pos == "LW" else "R"
        return Role.INVERTED_WINGER if foot == opposite[side] else Role.WINGER
    if pos == "ST":
        if a.aerial >= 68 and height_cm >= 186:
            return Role.TARGET_FORWARD
        if a.finishing >= 65:
            return Role.POACHER
        if a.stamina >= 70 and work_rate == "high":
            return Role.PRESSING_FORWARD
        return Role.COMPLETE_FORWARD
    raise ValueError(f"unknown slot {pos!r}")


def trait_margins(group: str, attrs: Attrs, foot: Foot, weak_foot: int) -> list[tuple[Trait, int]]:
    """Every trait whose rule holds, with its margin over the threshold, in table order. `set_piece_taker` is team level."""
    a = attrs
    rules: list[tuple[Trait, int | None]] = [
        (Trait.RAPID, a.pace - 80),
        (Trait.QUICK_OFF_THE_MARK, a.acceleration - 80),
        (Trait.AERIAL_THREAT, a.aerial - 72),
        (Trait.LONG_RANGE, a.finishing - 70 if group == "MID" else None),
        (Trait.PRESS_RESISTANT, min(a.dribbling - 72, a.passing - 65)),
        (Trait.ENGINE, a.stamina - 82),
        (Trait.TWO_FOOTED, BOOL_MARGIN if foot == "both" or weak_foot == 5 else None),
        (Trait.TOUGH_TACKLER, a.defending - 75),
        (Trait.VISIONARY, a.vision - 78),
        (Trait.DRIBBLER, a.dribbling - 78),
    ]
    return [(t, m) for t, m in rules if m is not None and m >= 0]


def traits_of(group: str, attrs: Attrs, foot: Foot, weak_foot: int, taker: bool) -> list[Trait]:
    """At most two traits, largest margin first. The team's set piece taker always keeps that trait."""
    ranked = sorted(trait_margins(group, attrs, foot, weak_foot), key=lambda tm: -tm[1])  # stable: table order breaks ties
    room = 2 - int(taker)
    out = [t for t, _ in ranked[:room]]
    return ([Trait.SET_PIECE_TAKER] if taker else []) + out


def _season(rng: random.Random, group: str, role: Role, attrs: Attrs) -> Season:
    apps = max(8, min(36, round(rng.gauss(24, 5))))
    p_goal = min(0.8, GOAL_RATE[group] * (attrs.finishing / 55) ** 1.5 * GOAL_ROLE.get(role, 1.0))
    p_assist = min(0.6, ASSIST_RATE[group] * (attrs.vision / 60) * ASSIST_ROLE.get(role, 1.0))
    goals = sum(rng.random() < p_goal for _ in range(apps))
    assists = sum(rng.random() < p_assist for _ in range(apps))
    clean = None
    if group in ("GK", "DEF"):
        p_clean = max(0.15, min(0.5, 0.30 + 0.002 * (attrs.defending - 65)))
        clean = sum(rng.random() < p_clean for _ in range(apps))
    return Season(apps=apps, goals=goals, assists=assists, clean_sheets=clean)


def build_player(seed: int, sp: SlotPlayer, name: str, number: int) -> Player:
    """Everything but `traits` and `captain`, which need the whole team."""
    rng = random.Random(f"{seed}:profile:{sp.id}")
    group: str = sp.group
    foot = _foot(rng, sp.pos, sp.ay)
    weak_foot = 5 if foot == "both" else rng.randint(2, 4)
    height = max(165, min(198, round(rng.gauss(HEIGHT_MEAN[slot_class(sp.pos)], 5))))
    age = max(18, min(35, round(rng.gauss(26.5, 4))))
    pace = _attr(100 * sp.pace)
    passing = _attr(100 * sp.passing)
    attrs = Attrs(
        pace=pace, passing=passing, finishing=_attr(100 * sp.finishing),
        acceleration=_attr(pace + rng.gauss(0, 8)),
        dribbling=_attr(rng.gauss(DRIBBLING_MEAN[group], 9)),
        vision=_attr(passing + rng.gauss(0, 7) + (4 if group == "MID" else 0)),
        defending=_attr(rng.gauss(DEFENDING_MEAN[group], 8)),
        aerial=_attr(40 + 1.6 * (height - 175) + rng.gauss(0, 8)),
        stamina=_attr(rng.gauss(70, 9) + {"MID": 5, "GK": -15}.get(group, 0)),
    )
    if group == "GK":
        attrs.keeping = _attr(rng.gauss(72, 7))
    work = work_rate_of(attrs.stamina, group)
    role = role_of(sp.pos, attrs, foot, height, work)
    return Player(
        id=sp.id, name=name, number=number, pos=sp.pos, group=group, attrs=attrs, foot=foot, weak_foot=weak_foot,
        height_cm=height, age=age, top_speed=round(max(7.6, min(9.8, 7.6 + 2.2 * (pace - 30) / 65)), 2),
        work_rate=work, role=role, traits=[], season=_season(rng, group, role, attrs), captain=False)


def build_team(seed: int, sim_players: list, names: list[tuple[str, int]]) -> list[Player]:
    """Profiles for one team. `names[k]` is (name, number) of `sim_players[k]`."""
    players = [build_player(seed, sp, n, num) for sp, (n, num) in zip(sim_players, names, strict=True)]
    outfield = [p for p in players if p.group != "GK"]
    taker = max(outfield, key=lambda p: p.attrs.passing + p.attrs.vision)  # first of equals wins
    elders = [p for p in players if p.group in ("DEF", "MID")]
    captain = max(elders, key=lambda p: p.age + p.attrs.stamina / 10)
    for p in players:
        p.traits = traits_of(p.group, p.attrs, p.foot, p.weak_foot, p is taker)
        p.captain = p is captain
    return players
