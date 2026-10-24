"""Team tactics: the base plan, shapes per phase and the posture schedule (docs/DATA-MODEL.md 2.1 to 2.3).

The base plan draws only from its own stream `Random(f"{seed}:tactics:{side}")`. The posture schedule is a pure
function of the finished event list, so it cannot move an event either.
"""
from __future__ import annotations

import random
from collections.abc import Callable

from ..schema import Event, EventType, Player, PostureShift, PressPlan, Role, Side, Tactics, Trait

PRESS_TRIGGERS = ("back_pass", "pass_to_fullback", "poor_touch", "keeper_pass", "receiver_facing_own_goal")
SHAPE_IN = {  # formation: (default, with an inverted full-back)
    "4-3-3": ("2-3-5", "3-2-5"),
    "4-4-2": ("4-2-4", "3-3-4"),
    "4-2-3-1": ("2-4-4", "3-2-5"),
}
SHAPE_OUT = {  # formation: block -> shape. The deep 4-5-1 of the 4-3-3 is the same string, the block field says deep
    "4-3-3": {"mid": "4-5-1", "high": "4-3-3", "low": "4-5-1"},
    "4-4-2": {"mid": "4-4-2", "high": "4-4-2", "low": "4-4-1-1"},
    "4-2-3-1": {"mid": "4-4-1-1", "high": "4-2-3-1", "low": "4-5-1"},
}
CHASE_SHAPE_IN = {"4-4-2": "3-4-3", "4-3-3": "2-3-5", "4-2-3-1": "2-3-5"}
TEN_MEN_SHAPE_IN = "4-3-2"
TEN_MEN_SHAPE_OUT = "4-4-1"
CHECKPOINT_MINUTES = (61, 76)
RESTART_FALLBACK_S = 180.0
RESTARTS = ("throw_in", "goal_kick", "free_kick", "corner")


def block_of(line_height: float) -> str:
    return "low" if line_height < 32 else ("high" if line_height > 42 else "mid")


def tempo_class_of(tempo: float) -> str:
    return "slow" if tempo < 0.45 else ("high" if tempo > 0.55 else "measured")


def _roles(players: list[Player]) -> list[Role]:
    return [p.role for p in players if p.role is not None]


def _width(players: list[Player]) -> float:
    """Team width in possession from the wide roles, 44..62 m."""
    roles = _roles(players)
    w = 48.0 + 3 * roles.count(Role.WINGER) + 2 * roles.count(Role.WIDE_MIDFIELDER) + 2 * roles.count(Role.ATTACKING_FULLBACK)
    w -= 2 * roles.count(Role.INVERTED_FULLBACK) + 2 * roles.count(Role.INVERTED_WINGER)
    return max(44.0, min(62.0, w))


def build_tactics(seed: int, side: Side, formation: str, press: float, tempo: float, players: list[Player]) -> Tactics:
    """The base plan of table 2.1. `press` and `tempo` are the team skills the simulation already has."""
    rng = random.Random(f"{seed}:tactics:{side}")
    n_triggers = rng.choice((2, 3))
    picked = set(rng.sample(PRESS_TRIGGERS, n_triggers))
    triggers = [t for t in PRESS_TRIGGERS if t in picked]
    short_roll = rng.random()

    roles = _roles(players)
    cbs = [p.role for p in players if p.pos == "CB"]
    line = 30 + 25 * (press - 0.4)
    if len(cbs) == 2 and all(r is Role.BALL_PLAYING_CB for r in cbs):
        line += 4
    if Role.COVER_CB in cbs:
        line -= 3
    line = round(max(26.0, min(50.0, line)), 1)
    block = block_of(line)

    backs = [p.attrs.passing for p in players if p.group in ("GK", "DEF")]
    mean_pass = sum(backs) / len(backs)
    build_up = "short" if mean_pass >= 60 else ("direct" if mean_pass < 52 else "mixed")

    inverted = Role.INVERTED_FULLBACK in roles
    shape_in = SHAPE_IN[formation][1 if inverted else 0]

    fast = [p for p in players if p.group == "FWD" or p.pos in ("RM", "LM", "RW", "LW")]
    counter = sum(p.attrs.pace >= 75 for p in fast) >= 2

    taker = next(p for p in players if Trait.SET_PIECE_TAKER in (p.traits or []))
    # a natural inswinger when the taker has a strong side, outswing for a two-footed taker; some short-playing teams go short
    corner = "outswing" if taker.foot == "both" else "inswing"
    if build_up == "short" and short_roll < 0.25:
        corner = "short"

    return Tactics(
        formation=formation, shape_in=shape_in, shape_out=SHAPE_OUT[formation][block], line_height=line, block=block,
        press=PressPlan(height=block, intensity=round(press, 2), triggers=triggers), build_up=build_up,
        width=_width(players), tempo=round(tempo, 2), tempo_class=tempo_class_of(tempo), counter=counter,
        corner_delivery=corner)


def _more_forwards(shape: str) -> str:
    """Move one defender into attack: 4-3-2 becomes 3-3-3."""
    d, *rest = (int(x) for x in shape.split("-"))
    return "-".join(str(x) for x in [d - 1, *rest[:-1], rest[-1] + 1])


def effective_plan(base: Tactics, posture: str, ten_men: bool, defensive_fullback: bool = False) -> Tactics:
    """The plan in force for a game-state posture. `ten_men` is applied first, the posture on top (table 2.3)."""
    line, intensity, tempo, width = base.line_height, base.press.intensity, base.tempo, base.width
    shape_in, shape_out, block = base.shape_in, base.shape_out, None
    if ten_men:
        shape_in, shape_out = TEN_MEN_SHAPE_IN, TEN_MEN_SHAPE_OUT
        line -= 4
        intensity -= 0.10
    if posture == "chase":
        line += 6
        intensity += 0.15
        shape_in = _more_forwards(TEN_MEN_SHAPE_IN) if ten_men else CHASE_SHAPE_IN[base.formation]
        width += 4
        tempo += 0.05
    elif posture == "protect":
        line -= 8
        intensity -= 0.15
        block = "low"
        if ten_men:
            shape_out = "5-3-1" if defensive_fullback else "4-4-1"
        else:
            shape_out = "5-4-1" if defensive_fullback else "4-5-1"
        tempo -= 0.05
    line = round(max(18.0, min(56.0, line)), 1)
    block = block or block_of(line)
    tempo = round(max(0.0, min(1.0, tempo)), 2)
    return base.model_copy(update=dict(
        shape_in=shape_in, shape_out=shape_out, line_height=line, block=block, width=min(66.0, width), tempo=tempo,
        tempo_class=tempo_class_of(tempo),
        press=PressPlan(height=block, intensity=round(max(0.0, min(1.0, intensity)), 2), triggers=base.press.triggers)))


def next_posture(state: str, d: int, minute: int) -> str:
    """Game-state posture after a trigger. `d` is own goals minus opponent goals, `minute` the display minute."""
    if state == "chase":
        if d <= 0:
            return "chase"  # stays chase when level again
        return "protect" if minute >= 75 else "base"
    if state == "protect":
        if d > 0:
            return "protect"
        return "chase" if d < 0 and minute >= 60 else "base"
    if d < 0 and minute >= 60:
        return "chase"
    if d > 0 and minute >= 75:
        return "protect"
    return "base"


def posture_schedule(events: list[Event], minute_t: Callable[[int], float]) -> dict[Side, list[PostureShift]]:
    """Every posture shift of a match, per side, from the finished event list.

    Triggers: every goal, every red card and the checkpoints at the start of minutes 61 and 76. A change takes effect
    at the first restart after the trigger (kick-off, throw-in, free kick, corner, goal kick). If no restart comes within
    180 s it takes effect at the first possession change at or after that deadline (at the deadline itself if the match
    has none). Every shift carries its own date by that rule, so `t` may be out of order within a side: a pending shift can
    be overtaken by a later trigger that restarts sooner. The overtaken shift is `superseded` (it never was in force) and
    `plan_at` ignores it; the later trigger's posture is the one in force. `minute_t(m)` is the match second the display minute `m` starts.
    """
    half_end = minute_t(46)  # first second of the second half

    def minute_of(t: float) -> int:
        return min(45, int(t // 60) + 1) if t < half_end else int((t - (half_end - 2700)) // 60) + 1

    triggers: list[tuple[float, int, str]] = []  # (t, event index or -1, reason)
    for e in events:
        if e.type is EventType.SHOT and e.outcome == "goal":
            triggers.append((e.t, e.i, "goal"))
        elif e.type is EventType.CARD and e.card == "red":
            triggers.append((e.t, e.i, "red_card"))
    triggers += [(minute_t(m), -1, "checkpoint") for m in CHECKPOINT_MINUTES]
    triggers.sort(key=lambda x: (x[0], x[1]))

    def effective(t: float, idx: int) -> float:
        after = [e for e in events if e.i > idx and e.t >= t]
        restart = next((e for e in after if e.type is EventType.KICKOFF or e.set_piece in RESTARTS), None)
        if restart is not None and restart.t - t <= RESTART_FALLBACK_S:
            return restart.t
        change = next((e for e in after if e.type is EventType.POSSESSION_CHANGE and e.t >= t + RESTART_FALLBACK_S), None)
        return change.t if change is not None else t + RESTART_FALLBACK_S

    goals: dict[Side, int] = {"H": 0, "A": 0}
    reds: dict[Side, int] = {"H": 0, "A": 0}
    posture: dict[Side, str] = {"H": "base", "A": "base"}
    ten: dict[Side, bool] = {"H": False, "A": False}
    out: dict[Side, list[PostureShift]] = {"H": [], "A": []}
    pos_i = 0
    for t, idx, reason in triggers:
        # fold in every goal and card up to this trigger (a checkpoint sees all earlier ones)
        while pos_i < len(events) and (events[pos_i].t < t or (idx >= 0 and events[pos_i].i <= idx)):
            e = events[pos_i]
            if e.type is EventType.SHOT and e.outcome == "goal":
                goals[e.team] += 1
            elif e.type is EventType.CARD and e.card == "red":
                reds[e.team] += 1
            pos_i += 1
        for side in ("H", "A"):
            other: Side = "A" if side == "H" else "H"
            new_ten = reds[side] > 0
            new_posture = next_posture(posture[side], goals[side] - goals[other], minute_of(t))
            if (new_posture, new_ten) != (posture[side], ten[side]):
                posture[side], ten[side] = new_posture, new_ten
                out[side].append(PostureShift(
                    side=side, t_trigger=t, t=effective(t, idx), reason=reason, posture=new_posture, ten_men=new_ten,
                    on_pitch=11 - reds[side]))
    return out


def superseded(shifts: list[PostureShift]) -> list[bool]:
    """Per shift (trigger order): a later trigger of the side takes effect no later than this one, so it was never in force."""
    return [any(b.t <= a.t for b in shifts[i + 1:]) for i, a in enumerate(shifts)]


def plan_at(base: Tactics, shifts: list[PostureShift], players: list[Player], t: float) -> Tactics:
    """The plan in force at match second `t`: the latest trigger among the shifts already in effect (a shift counts from its effective time)."""
    posture, ten_men = "base", False
    for s in sorted(shifts, key=lambda s: s.t_trigger):
        if s.t <= t:
            posture, ten_men = s.posture, s.ten_men
    backs = [p for p in players if p.pos in ("LB", "RB")]
    return effective_plan(base, posture, ten_men, any(p.role is Role.DEFENSIVE_FULLBACK for p in backs))
