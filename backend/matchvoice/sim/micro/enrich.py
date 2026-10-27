"""Event enrichment without tracking (docs/DATA-MODEL.md 3.3, 3.4 and 4.1 to 4.5, docs/PLAN-DATA.md phase 2).

The skeleton (`events.jsonl`) is read, never changed. Everything here is a function of the skeleton, the profiles and the
tactics plan in `meta.json`, so it can be built and voiced before any tracking exists. The rows go to `enriched.jsonl`:

- annotation rows (`k = 0`, `eid = 16 * i`) for pass, carry, shot, foul and interception events;
- sub-events (`k = 1..15`, `eid = 16 * i + k`) in the gap after skeleton event `i`: `receipt`, implicit `pass` and `carry`
  (gap repair), `take_on` (lost, from a tackle).

Randomness: one stream per segment, `Random(f"{seed}:micro:{16 * i_of_restart}")`, never the simulation's generator. A segment
runs from one restart (kick-off, throw-in, goal kick, free kick, corner) up to the next, and depends only on its own skeleton
events, the next event's time and the global profiles, so a window and a full match give identical rows and identical eids.
The order of draws inside a segment is part of the contract (a change reshuffles the rows).

Kick-time rows (pass annotations, implicit passes) carry no outcome: no `outcome`, `receiver`, `assist`, `touch`, `facing`.
Those live on the resolution rows (receipt, shot, take_on, interception).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from ...schema import PITCH_L, PITCH_W, Event, EventType, MatchMeta, Player, Role, Trait
from ..engine import FORMATIONS
from ..tactics import RESTARTS, plan_at

G = 9.81
MAX_HANG_S = min(3.8, 2 * math.sqrt(2 * 18 / G))  # a lofted ball peaks at 18 m at most (3.3)
GROUND_SLOWEST = 8.0  # m/s, average speed a ground pass may slow down to (3.3)
LOFTED_SLOWEST = 5.0  # m/s, average speed floor for a lofted ball, so a short one does not hang for 3.8 s
MIN_GAP_S = 0.25  # arrival to the next action, at least (3.3)
FIRST_TIME_S = 0.6  # less than this between arrival and the next action is a first-time action
HOLD_MIN_S = 0.15  # a receiver holds the ball at least this long before an implicit pass or carry
MAX_PASS_SPEED = 34.0  # m/s (122 km/h), the fastest an implicit pass is allowed to travel
MAX_CARRY_SPEED = 9.0  # m/s
THROUGH_MARGIN_M = 10.0  # end point at least this far past the opponent's last line (4.2 as first written: any distance, 55 to 85 per team)
THROUGH_MIN_LEN_M = 40.0  # shortest pass that counts as a through ball (with the margin: 3 to 8 per team, 4.2 range 1 to 8)
CROSS_MIN_LEN_M = 15.0  # shortest pass that counts as a cross (a sideways nudge along the box edge is a short pass: 4.2 range 8 to 25 per team)
MAX_SUB = 15
P_FIRST = {"pass": 0.18, "shot": 0.25}  # chance a next action is steered to be first time (15 to 25 percent, 3.3)
ASSIST_MAX_S = 8.0
BOX_AX = PITCH_L - 16.5
BOX_Y = (PITCH_W / 2 - 20.16, PITCH_W / 2 + 20.16)
SIX_Y = (PITCH_W / 2 - 9.16, PITCH_W / 2 + 9.16)
GOAL_HALF = 3.66
LOFTED_TYPES = ("cross", "switch", "clearance", "goal_kick", "corner")
SHORT_GOAL_KICK_M = 24.0  # a goal kick shorter than this is played on the ground (the generated live scene's short goal kick)
RESTART_PASSES = ("corner", "free_kick", "throw_in", "goal_kick")
DROP_RANK = {"take_on": 0, "carry": 1, "pass": 2, "receipt": 3}  # lowest value first
FOUL_TYPES = ("trip", "push", "holding", "late_tackle", "pull")


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _ceil_ms(v: float) -> float:
    return math.ceil(v * 1000 - 1e-9) / 1000


def _floor_ms(v: float) -> float:
    return math.floor(v * 1000 + 1e-9) / 1000


def _dir(side: str, period: int) -> int:
    return 1 if (side == "H") == (period == 1) else -1


def _att(side: str, period: int, x: float, y: float) -> tuple[float, float]:
    """Absolute pitch metres to the attacking frame of `side` (x 0 = own goal line)."""
    return (x, y) if _dir(side, period) > 0 else (PITCH_L - x, PITCH_W - y)


def _in_box(ax: float, ay: float) -> bool:
    return ax >= BOX_AX and BOX_Y[0] <= ay <= BOX_Y[1]


@dataclass(eq=False)
class Act:
    """One touch of the ball that moves it: a skeleton pass, carry or shot, or an implicit pass or carry (gap repair)."""

    kind: str  # pass | carry | shot | ipass | icarry
    ev: Event | None
    before: int  # skeleton event index (the event itself, or the one this implicit act comes right before)
    anchor: int  # event whose gap holds the sub-events of this act
    team: str
    period: int
    actor: str
    x0: float  # absolute start and end
    y0: float
    x1: float
    y1: float
    t: float = 0.0  # kick time
    complete: bool = False  # passes only
    target: str | None = None  # passes only: the intended receiver
    incoming: Act | None = None  # the completed pass that delivered the ball to the actor, nothing in between
    carry_prev: Act | None = None  # a carry by the actor between that pass and this act
    nxt: Act | None = None  # the act by the receiver after a completed pass
    flight: float = 0.0  # passes: minimum flight time T = length / ball speed
    speed_ms: float = 0.0
    t_arr: float | None = None
    t_next: float = 0.0  # time of the next skeleton event (upper bound of the arrival)
    first_time: bool = False
    height: str = "ground"
    ptype: str = ""
    after_kickoff: bool = False
    squeezed: bool = False
    dropped: bool = False  # a gap-repair act the skeleton leaves no time for (counted in Stats.unrepaired)
    eid: int = -1  # set when the rows are numbered
    duration: float = 0.0  # carries
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def implicit(self) -> bool:
        return self.ev is None

    @property
    def length(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)

    @property
    def a0(self) -> tuple[float, float]:
        return _att(self.team, self.period, self.x0, self.y0)

    @property
    def a1(self) -> tuple[float, float]:
        return _att(self.team, self.period, self.x1, self.y1)


@dataclass
class TakeOn:
    anchor: int
    t: float
    team: str  # the dribbler's team
    player: str
    defender: str
    x: float
    y: float


@dataclass
class Stats:
    """Counters the gate reports."""

    segments: int = 0
    implicit_passes: int = 0
    implicit_carries: int = 0
    unrepaired: list[dict[str, Any]] = field(default_factory=list)  # jumps the skeleton makes in less time than the ball can travel
    squeezed: int = 0  # arrivals that could not keep the minimum gap (only the ones the physics forced)
    overflow: int = 0  # sub-events dropped because a gap had more than 15


@dataclass
class Enriched:
    rows: list[dict[str, Any]]
    stats: Stats


class Context:
    """Everything a segment reads that is not in the segment: events, profiles, sent-off players, tactics."""

    def __init__(self, meta: MatchMeta, events: list[Event]):
        self.meta = meta
        self.events = events
        self.seed = meta.seed
        self.players: dict[str, Player] = {p.id: p for t in meta.teams.values() for p in t.players}
        self.slots: dict[str, list[tuple[Player, float, float]]] = {}
        for side, team in meta.teams.items():
            layout = FORMATIONS[team.formation]
            self.slots[side] = [(p, ax, ay) for p, (_, _, ax, ay) in zip(team.players, layout, strict=True)]
        self.red: dict[str, int] = {e.player: e.i for e in events if e.type is EventType.CARD and e.card == "red" and e.player}

    def player(self, pid: str) -> Player:
        return self.players[pid]

    def foot(self, pid: str) -> tuple[str, int]:
        p = self.players[pid]
        return p.foot or "R", p.weak_foot or 3

    def nearest_mate(self, side: str, idx: int, ax: float, ay: float, exclude: str) -> str:
        """The team-mate whose formation anchor is nearest the point (the skeleton's own `_nearest` geometry, without the draw)."""
        best: tuple[float, str] | None = None
        for p, sx, sy in self.slots[side]:
            if p.id == exclude or self.red.get(p.id, 10**9) < idx or (p.group == "GK" and ax >= 12):
                continue
            d = math.hypot(sx - ax, sy - ay)
            if best is None or d < best[0]:
                best = (d, p.id)
        assert best is not None
        return best[1]

    def opp_line_ax(self, team: str, ax0: float, t: float) -> float | None:
        """x of the opponent's planned last line in the attacker's frame, at the kick (2.1, 2.3, 3.2)."""
        opp = "A" if team == "H" else "H"
        tm = self.meta.teams[opp]
        if tm.tactics is None:
            return None
        plan = plan_at(tm.tactics, tm.postures or [], tm.players, t)
        return PITCH_L - (plan.line_height + 0.25 * ((PITCH_L - ax0) - PITCH_L / 2))


def segment_starts(events: list[Event]) -> list[int]:
    """Indices of the restarts: kick-off, throw-in, goal kick, free kick, corner. Index 0 always starts a segment."""
    starts = [i for i, e in enumerate(events) if e.type is EventType.KICKOFF or e.set_piece in RESTARTS]
    return starts if starts and starts[0] == 0 else [0, *starts]


# ---------- structure: the touches of a segment, with the gap repair ----------

def _act_of(e: Event) -> Act:
    kind = e.type.value
    ex, ey = (e.end_x, e.end_y) if e.end_x is not None else (e.x, e.y)
    a = Act(kind=kind, ev=e, before=e.i, anchor=e.i, team=e.team, period=e.period, actor=e.player or "",
            x0=e.x, y0=e.y, x1=ex, y1=ey, t=e.t)
    if kind == "pass":
        a.complete = e.outcome == "complete"
        a.target = e.receiver if a.complete else None
        a.speed_ms = (e.ball_speed or 60.0) / 3.6
        a.flight = (e.length or a.length) / a.speed_ms
    return a


def _structure(ctx: Context, lo: int, hi: int) -> tuple[list[Act], list[TakeOn]]:
    events = ctx.events
    acts: list[Act] = []
    takeons: list[TakeOn] = []
    holder: str | None = None
    hteam = ""
    ball = (0.0, 0.0)
    anchor = lo
    recv: Act | None = None  # the pass that delivered the ball to the holder
    carry_prev: Act | None = None
    last: Act | None = None
    for idx in range(lo, hi):
        e = events[idx]
        if e.type in (EventType.PASS, EventType.CARRY, EventType.SHOT):
            act = _act_of(e)
            if idx > lo and holder is not None and hteam == e.team:
                if e.player != holder:
                    ip = Act(kind="ipass", ev=None, before=idx, anchor=anchor, team=e.team, period=e.period, actor=holder,
                             x0=ball[0], y0=ball[1], x1=e.x, y1=e.y, complete=True, target=e.player, incoming=recv)
                    if recv is not None:
                        recv.nxt = ip
                    acts.append(ip)
                    recv, act.incoming, carry_prev = ip, ip, None
                elif math.hypot(e.x - ball[0], e.y - ball[1]) > 2.0:
                    ic = Act(kind="icarry", ev=None, before=idx, anchor=anchor, team=e.team, period=e.period, actor=holder,
                             x0=ball[0], y0=ball[1], x1=e.x, y1=e.y, incoming=recv)
                    if recv is not None:
                        recv.nxt = ic
                    acts.append(ic)
                    carry_prev, recv = ic, None
                    act.carry_prev = ic
                    ic.nxt = act
                elif recv is not None and recv.target == e.player:
                    act.incoming = recv
                elif carry_prev is not None and carry_prev.actor == e.player:
                    act.carry_prev = carry_prev
            if act.incoming is not None:
                act.incoming.nxt = act
            prev_e = events[idx - 1]
            if e.type is EventType.PASS and idx > lo and prev_e.type is EventType.KICKOFF and prev_e.player == e.player:
                act.after_kickoff = True  # the first pass of a half or after a goal: the skeleton gives it no set_piece
            acts.append(act)
            last = act
            anchor = idx
            if e.type is EventType.PASS and act.complete:
                holder, hteam, ball, recv, carry_prev = e.receiver, e.team, (e.end_x, e.end_y), act, None
            elif e.type is EventType.CARRY:
                holder, hteam, ball = e.player, e.team, (e.end_x, e.end_y)
                carry_prev, recv = act, None
            else:
                holder, recv, carry_prev = None, None, None
        elif e.type is EventType.PRESSURE:
            continue
        elif e.type is EventType.TACKLE:
            if holder is not None and hteam != e.team and last is not None and last.kind == "carry" and last.actor == holder:
                takeons.append(TakeOn(anchor=idx, t=e.t, team=hteam, player=holder, defender=e.player or "", x=e.x, y=e.y))
            holder, hteam, ball, anchor, recv, carry_prev, last = e.player, e.team, (e.x, e.y), idx, None, None, None
        elif e.type in (EventType.KICKOFF, EventType.INTERCEPTION, EventType.POSSESSION_CHANGE):
            holder, hteam, ball, anchor, recv, carry_prev, last = e.player, e.team, (e.x, e.y), idx, None, None, None
        else:  # foul, card, period end: the ball is dead
            holder, recv, carry_prev, last = None, None, None, None
    return acts, takeons


# ---------- classification (kick-time fields that need no tracking, 4.2) ----------

def _won_ball(events: list[Event], lo: int, a: Act) -> bool:
    """The passer won the ball (interception or tackle) within the last 2 s and within 3 m."""
    for k in range(a.before - 1, max(lo, a.before - 5) - 1, -1):
        e = events[k]
        if e.player != a.actor or a.t - e.t > 2.0:
            continue
        won = e.type in (EventType.INTERCEPTION, EventType.TACKLE) or (
            e.type is EventType.POSSESSION_CHANGE and e.reason in ("interception", "tackle"))
        if won and math.hypot(e.x - a.x0, e.y - a.y0) <= 3.0:
            return True
    return False


def _pass_type(ctx: Context, lo: int, a: Act, first_time: bool) -> str:
    """First match wins (4.2). `first_time` is the passer's own touch, which is in the past."""
    sp = a.ev.set_piece if a.ev is not None else None
    if sp in RESTART_PASSES:
        return sp
    if a.after_kickoff:
        return "kickoff"
    (ax0, ay0), (ax1, ay1) = a.a0, a.a1
    length, dx, dy = a.length, ax1 - ax0, abs(ay1 - ay0)
    wide = ay0 < BOX_Y[0] or ay0 > BOX_Y[1]
    if wide and ax0 > 70 and _in_box(ax1, ay1) and length >= CROSS_MIN_LEN_M:
        return "cross"
    if _in_box(ax0, ay0) and not (SIX_Y[0] <= ay0 <= SIX_Y[1]) and dx < 0:
        return "cut_back"
    if dy >= 40 and length >= 40:
        return "switch"
    line = ctx.opp_line_ax(a.team, ax0, a.t)
    if line is not None and dx > 0 and ax0 < line and ax1 - line > THROUGH_MARGIN_M and length >= THROUGH_MIN_LEN_M:
        return "through"
    pl = ctx.player(a.actor)
    own_box_def = pl.group == "DEF" and ax0 <= 16.5 and BOX_Y[0] <= ay0 <= BOX_Y[1] and bool(a.ev and a.ev.under_pressure)
    if length >= 30 and (own_box_def or (a.ev is not None and _won_ball(ctx.events, lo, a))):
        return "clearance"
    if dx < -3:
        return "back"
    if length < 10 and first_time:
        return "lay_off"
    return "long" if length >= 32 else "short"


def _height(rng: random.Random, ptype: str, length: float, kick_kmh: float) -> str:
    if ptype == "goal_kick" and length < SHORT_GOAL_KICK_M:  # rolled to a centre back at the edge of the box (no plain-match goal kick is this short)
        return "ground"
    if ptype in LOFTED_TYPES:
        return "lofted"
    if ptype == "long":
        p = 0.3 + 0.5 * _clamp((length - 32) / 18, 0.0, 1.0)
        if rng.random() < p:
            return "lofted"
    if kick_kmh >= 70 and length >= 18:
        return "driven"
    return "ground"


def _classify(ctx: Context, rng: random.Random, lo: int, a: Act) -> None:
    a.ptype = _pass_type(ctx, lo, a, a.first_time)
    a.height = _height(rng, a.ptype, a.length, a.speed_ms * 3.6)


# ---------- scheduling: arrival retiming and gap repair (3.3, 3.4) ----------

def _hi_phys(a: Act) -> float:
    """Latest arrival the flight physics allows (3.3)."""
    if a.height == "lofted":
        dur = max(a.flight, min(MAX_HANG_S, a.length / LOFTED_SLOWEST))
    elif a.height == "driven":
        dur = 1.25 * a.flight
    else:
        dur = max(a.flight, a.length / GROUND_SLOWEST)
    return a.t + dur


def _arrival(rng: random.Random, lo: float, hi_phys: float, t_next: float, flagged: bool, late: bool = False) -> tuple[float, bool]:
    """Draw an arrival in [lo, hi] with hi = min(hi_phys, t_next - 0.25). Returns (t_arr, squeezed).

    `flagged` steers the next action to be first time (arrival 0.25 to 0.55 s before it) when the flight physics allow it.
    Otherwise the arrival stays clear of the 0.6 s line unless the gap is too small for that. `late` skews toward the end
    (a contested ball arrives late, a pass early)."""
    lo = _ceil_ms(lo)
    hi = _floor_ms(min(hi_phys, t_next - MIN_GAP_S))
    if hi < lo:
        return lo, lo > t_next - MIN_GAP_S + 1e-9
    if flagged:
        a, b = max(lo, _ceil_ms(t_next - 0.55)), hi
        if a <= b:
            return _clamp(round(rng.uniform(a, b), 3), a, b), False
    b = min(hi, _floor_ms(t_next - FIRST_TIME_S - 0.05))
    if b < lo:
        b = hi  # the gap is too small to avoid a first-time action
    u = rng.random()
    u = u ** 0.6 if late else u ** 1.5
    return _clamp(round(lo + (b - lo) * u, 3), lo, hi), False


def _p_first(e: Act | None, a: Act) -> float:
    """Chance that the action after `a` is steered to be first time. A header from a cross or corner always is (if physics allow)."""
    if e is None or e.kind in ("carry", "icarry"):
        return 0.0
    if e.kind == "shot" and e.ev is not None and e.ev.body_part == "head" and a.ptype in ("cross", "corner"):
        return 1.0
    return P_FIRST["shot" if e.kind == "shot" else "pass"]


def _event_t(ctx: Context, idx: int, fallback: float) -> float:
    return ctx.events[idx + 1].t if idx + 1 < len(ctx.events) else fallback


def _fits(ip: Act, lo: float, t_e: float) -> bool:
    """Is there time between the arrival (`lo`) and the skeleton act at `t_e` for the implicit act?"""
    if ip.kind == "ipass":
        return ip.length / MAX_PASS_SPEED + HOLD_MIN_S + MIN_GAP_S <= t_e - lo
    return ip.length / MAX_CARRY_SPEED + HOLD_MIN_S + 0.05 <= t_e - lo


def _chain(ctx: Context, rng: random.Random, st: Stats, lo_i: int, prev: Act | None, anchor_t: float, ip: Act, e: Act) -> None:
    """Schedule the implicit act `ip` between the arrival of `prev` (or the holder event at `anchor_t`) and the skeleton act `e`.

    Planned backwards from `e`: the implicit pass arrives 0.25 to 0.55 s (steered first time) or 0.65 to 1.3 s before `e`, the
    implicit carry ends just before it. If the time is short the pass gets faster (up to 34 m/s) and the gap shrinks to 0.25 s.
    The caller has checked that it fits (`_fits`)."""
    t_e = e.t
    if prev is not None:
        lo, hi = _ceil_ms(prev.t + prev.flight), _hi_phys(prev)
    else:
        lo = hi = anchor_t
    ip.t = t_e - 1.0  # provisional, only for the tactics plan in force
    if ip.kind == "ipass":
        ip.speed_ms = rng.uniform(14.0, 24.0)
        ip.flight = ip.length / ip.speed_ms
        ip.ptype = _pass_type(ctx, lo_i, ip, False)
        ip.height = _height(rng, ip.ptype, ip.length, ip.speed_ms * 3.6)
        flagged = rng.random() < _p_first(e, ip)
        gap = rng.uniform(0.25, 0.55) if flagged else rng.uniform(0.65, 1.3)
        kick = t_e - gap - ip.flight
        if kick < lo + HOLD_MIN_S:
            gap = MIN_GAP_S
            kick = t_e - gap - ip.flight
        if kick < lo + HOLD_MIN_S:
            ip.flight = t_e - gap - (lo + HOLD_MIN_S)  # at least L / MAX_PASS_SPEED, `_fits` checked
            kick = t_e - gap - ip.flight
        ip.t = round(max(kick, lo + HOLD_MIN_S), 3)
        ip.t_arr = round(min(ip.t + ip.flight, t_e - MIN_GAP_S + 1e-9), 3)
        ip.speed_ms = ip.length / (ip.t_arr - ip.t)
        e.first_time = e.kind in ("pass", "shot") and (t_e - ip.t_arr) < FIRST_TIME_S
    else:
        v = rng.uniform(3.5, 7.0)
        dur = ip.length / v
        start = t_e - dur - rng.uniform(0.05, 0.3)
        if start < lo + HOLD_MIN_S:
            v = ip.length / (t_e - 0.05 - (lo + HOLD_MIN_S))  # at most MAX_CARRY_SPEED, `_fits` checked
            dur = ip.length / v
            start = t_e - dur - 0.05
        ip.t, ip.duration, ip.speed_ms = round(max(start, lo + HOLD_MIN_S), 3), round(dur, 3), v
        e.first_time = False
    ip.t_next = t_e
    if prev is not None:
        arr, _ = _arrival(rng, lo, min(hi, ip.t - HOLD_MIN_S), ip.t - HOLD_MIN_S + MIN_GAP_S, False)
        prev.t_arr, prev.t_next = arr, ip.t
        ip.first_time = ip.kind == "ipass" and (ip.t - arr) < FIRST_TIME_S


def _drop(st: Stats, prev: Act | None, ip: Act, e: Act, lo: float, t_e: float) -> None:
    """The skeleton moves the ball further than it can travel in the time it leaves: no row, listed in the stats."""
    ip.dropped = True
    st.unrepaired.append({"before": ip.before, "kind": ip.kind, "length_m": round(ip.length, 1), "available_s": round(t_e - lo, 2)})
    if prev is not None:
        prev.nxt = e if ip.kind == "icarry" else None
    e.incoming = prev if (ip.kind == "icarry" and prev is not None) else None
    e.carry_prev = None


def _schedule(ctx: Context, rng: random.Random, st: Stats, lo: int, acts: list[Act]) -> None:
    """Set `t`, `t_arr`, `first_time`, `ptype` and `height` of every act. Passes are handled in event order, so the first-time
    flag of an act is known (from the arrival before it) when its own type is classified."""
    for n, a in enumerate(acts):
        if a.implicit:
            if a.incoming is None and a.nxt is not None:  # the holder came from an interception or a restart: fixed start
                anchor_t = ctx.events[a.anchor].t
                if _fits(a, anchor_t, a.nxt.t):
                    _chain(ctx, rng, st, lo, None, anchor_t, a, a.nxt)
                else:
                    _drop(st, None, a, a.nxt, anchor_t, a.nxt.t)
            continue
        a.t = a.ev.t
        if a.kind != "pass":
            continue
        _classify(ctx, rng, lo, a)
        t_next = _event_t(ctx, a.before, a.t + 10.0)
        a.t_next = t_next
        e = a.nxt
        if a.complete and e is not None and e.implicit and e.nxt is not None:
            if _fits(e, _ceil_ms(a.t + a.flight), e.nxt.t):
                _chain(ctx, rng, st, lo, a, a.t, e, e.nxt)
                continue
            _drop(st, a, e, e.nxt, _ceil_ms(a.t + a.flight), e.nxt.t)
            e = a.nxt
        if a.complete:
            flagged = e is not None and rng.random() < _p_first(e, a)
            a.t_arr, sq = _arrival(rng, a.t + a.flight, _hi_phys(a), t_next, flagged)
            if e is not None:
                e.first_time = e.kind in ("pass", "shot") and (e.t - a.t_arr) < FIRST_TIME_S
        else:
            a.t_arr, sq = _arrival(rng, a.t + a.flight, _hi_phys(a), t_next, False, late=True)
        if sq:
            st.squeezed += 1
    for a in acts:
        if a.implicit and not a.dropped and a.ptype == "short" and a.length < 10 and a.first_time:
            a.ptype = "lay_off"


# ---------- annotation: the fields of 4.1 to 4.5 ----------

def _foot_for(ctx: Context, rng: random.Random, pid: str, lateral: float) -> str:
    """Preferred foot; the weak foot with probability (5 - weak_foot) * 0.04, reversed when the angle (a target 8 m or more to
    the weak side, in the attacking frame where a low `ay` is the left) favours the weak foot (4.2)."""
    foot, wf = ctx.foot(pid)
    u = rng.random()
    favoured = "left_foot" if lateral <= -8 else ("right_foot" if lateral >= 8 else None)
    if foot == "both":
        return favoured or ("left_foot" if u < 0.5 else "right_foot")
    pref = "left_foot" if foot == "L" else "right_foot"
    weak = "right_foot" if pref == "left_foot" else "left_foot"
    p = (5 - wf) * 0.04
    return weak if u < (1 - p if favoured == weak else p) else pref


def _pass_fields(ctx: Context, rng: random.Random, a: Act, under: bool) -> dict[str, Any]:
    """Kick-time fields of a pass (skeleton or implicit). No outcome of any kind."""
    (ax0, ay0), (ax1, ay1) = a.a0, a.a1
    inc = a.incoming
    if inc is not None and a.first_time and inc.height == "lofted":
        u = rng.random()
        head = u < (0.85 if inc.ptype in ("cross", "corner", "free_kick") else 0.4)
        body = "head" if head else ("other" if rng.random() < 0.15 else _foot_for(ctx, rng, a.actor, ay1 - ay0))
    else:
        body = _foot_for(ctx, rng, a.actor, ay1 - ay0)
    if a.ptype in ("cross", "corner") and body != "head":
        technique = "inswing" if (body == "left_foot") != (ay0 < PITCH_W / 2) else "outswing"
    elif a.ptype == "through" and a.height == "lofted":
        technique = "chip"
    else:
        technique = "straight"
    target = a.target
    if target is None:  # an incomplete pass: the team-mate nearest the end point, by formation anchors
        target = ctx.nearest_mate(a.team, a.before, ax1, ay1, a.actor)
    out: dict[str, Any] = {
        "target": target, "pass_type": a.ptype, "height": a.height, "body_part": body, "technique": technique,
        "pressure": {"under": under}, "first_time": a.first_time, "t_arr": a.t_arr,
        "ball_speed": round(a.length / max(a.t_arr - a.t, 1e-6) * 3.6, 1),
    }
    if a.ptype == "corner":
        near = 1 if ay0 > PITCH_W / 2 else -1  # the near post is on the side the corner is taken from
        lateral = (ay1 - PITCH_W / 2) * near
        out["delivery"] = technique if technique in ("inswing", "outswing") else "short"
        out["target_zone"] = ("edge" if ax1 < BOX_AX else "near_post" if lateral >= 3.0 else "far_post" if lateral <= -3.0
                              else "six_yard" if ax1 >= PITCH_L - 5.5 else "penalty_spot")
    elif a.ptype == "free_kick":
        out["distance_m"] = round(math.hypot(PITCH_L - ax0, PITCH_W / 2 - ay0), 1)
        out["direct"] = False
    elif a.ptype == "throw_in":
        out["long"] = a.length > 20
    elif a.ptype == "goal_kick":
        out["short"] = ax1 < PITCH_L / 3
    return out


def _carry_fields(ctx: Context, a: Act, under: bool) -> dict[str, Any]:
    (ax0, ay0), (ax1, ay1) = a.a0, a.a1
    v = a.speed_ms if a.implicit else (a.ev.speed or 18.0) / 3.6
    top = ctx.player(a.actor).top_speed or 9.0
    dur = a.duration if a.implicit else (a.ev.length or a.length) / v
    return {"distance_m": round(a.ev.length if a.ev is not None and a.ev.length else a.length, 1), "duration_s": round(dur, 2), "max_speed": round(max(v, min(top, 1.15 * v)), 2),
            "progress_m": round(ax1 - ax0, 1), "into_box": _in_box(ax1, ay1) and not _in_box(ax0, ay0),
            "pressure": {"under": under}}


def _shot_fields(ctx: Context, rng: random.Random, a: Act) -> dict[str, Any]:
    e = a.ev
    (ax0, ay0), _ = a.a0, a.a1
    pl = ctx.player(a.actor)
    inc = a.incoming
    if e.body_part == "head":
        body = "head"
    elif e.body_part == "other":
        body = "other"
    else:
        body = _foot_for(ctx, rng, a.actor, PITCH_W / 2 - ay0)
    dist = math.hypot(PITCH_L - ax0, PITCH_W / 2 - ay0)
    taker = Trait.SET_PIECE_TAKER in (pl.traits or [])
    if body == "head":
        technique = "header"
    elif a.first_time and inc is not None and inc.height == "lofted":
        technique = "volley"
    elif e.set_piece == "free_kick":
        technique = "curled" if rng.random() < (0.65 if taker else 0.3) else "driven"
    elif pl.role is Role.INVERTED_WINGER and 14 <= dist <= 24 and abs(ay0 - PITCH_W / 2) > 5:
        technique = "curled"
    elif (e.shot_speed or 0) >= 118:
        technique = "driven"
    else:
        technique = "placed"
    out: dict[str, Any] = {"body_part": body, "technique": technique, "first_time": a.first_time, "assist_eid": None}
    if e.set_piece == "free_kick":
        out["distance_m"] = round(dist, 1)
        out["direct"] = True
    if e.outcome in ("goal", "saved", "post"):
        right = _dir(a.team, a.period) > 0
        y = (e.end_y - (PITCH_W / 2 - GOAL_HALF)) if right else ((PITCH_W / 2 + GOAL_HALF) - e.end_y)
        if e.outcome == "post":
            y = 0.0 if y < GOAL_HALF else 7.32
            z = rng.uniform(0.3, 2.2)
        elif e.outcome == "goal":
            y = _clamp(y, 0.15, 7.17)
            z = rng.uniform(0.15, 2.25)
        else:  # a saved shot is biased toward the keeper: low and central
            y = _clamp(y, 0.15, 7.17)
            z = _clamp(rng.gauss(0.9, 0.6), 0.1, 2.3)
        col = "left" if y < 2.44 else ("right" if y >= 4.88 else "centre")
        out["placement"] = {"y": round(y, 2), "z": round(z, 2), "zone": f"{'low' if z < 1.22 else 'high'}_{col}"}
    return out


def _receipt(ctx: Context, rng: random.Random, a: Act) -> dict[str, Any]:
    nxt = a.nxt
    height_lofted = a.height == "lofted"
    p_head = 0.1 + 0.3 * (ctx.player(a.target or a.actor).attrs.aerial / 99 if ctx.player(a.target or a.actor).attrs else 0.5)
    u = rng.random()
    if nxt is not None and nxt.kind == "shot" and nxt.ev.body_part == "head" and nxt.first_time:
        touch = "head"
    elif height_lofted and u < p_head:
        touch = "head"
    elif height_lofted and u < p_head + 0.2:
        touch = "chest"
    else:
        touch = "chest" if u > 0.97 else "control"
    # facing and pressure come from data at or before the arrival (0.1): the direction the incoming pass travelled, never the next action
    f = rng.random()
    d = a.a1[0] - a.a0[0]
    p_fwd, p_side = (0.65, 0.30) if d > 4 else ((0.15, 0.40) if d < -3 else (0.40, 0.50))
    facing = "forward" if f < p_fwd else ("side" if f < p_fwd + p_side else "own_goal")
    under = None  # the skeleton has no flag for a receiver: the tracking frame sets it in phase 4 (4.3)
    # no hold time on the row: it is the gap to the next skeleton event, a lookahead (0.1), and 4.1 has no such field
    return {"pass_eid": None, "touch": touch, "facing": facing, "pressure": {"under": under}}


def _foul_fields(ctx: Context, rng: random.Random, acts: list[Act], e: Event) -> dict[str, Any]:
    pl = ctx.player(e.player)
    prior = next((a for a in reversed(acts) if a.before < e.i and a.team != e.team), None)
    if prior is not None and prior.kind in ("carry", "icarry"):
        w = {"trip": 0.35, "push": 0.10, "holding": 0.05, "late_tackle": 0.30, "pull": 0.20}
    elif prior is not None and prior.kind in ("pass", "ipass") and prior.height == "lofted":
        w = {"trip": 0.05, "push": 0.40, "holding": 0.30, "late_tackle": 0.05, "pull": 0.20}
    else:
        w = {"trip": 0.25, "push": 0.20, "holding": 0.15, "late_tackle": 0.25, "pull": 0.15}
    if pl.role in (Role.BALL_WINNER, Role.STOPPER, Role.ANCHOR, Role.DEFENSIVE_FULLBACK) or Trait.TOUGH_TACKLER in (pl.traits or []):
        w["late_tackle"] *= 1.6
        w["trip"] *= 1.2
    if pl.role in (Role.TARGET_FORWARD, Role.STOPPER) or Trait.AERIAL_THREAT in (pl.traits or []):
        w["push"] *= 1.3
        w["holding"] *= 1.3
    u = rng.random() * sum(w.values())
    ftype = FOUL_TYPES[-1]
    for k in FOUL_TYPES:
        u -= w[k]
        if u < 0:
            ftype = k
            break
    ax, _ = _att(e.team, e.period, e.x, e.y)
    return {"foul_type": ftype, "zone": "defensive" if ax < PITCH_L / 3 else ("attacking" if ax > 2 * PITCH_L / 3 else "middle")}


def _style(ctx: Context, rng: random.Random, pid: str) -> str:
    pl = ctx.player(pid)
    a = pl.attrs
    w = {"pace": 0.2 + (0.3 if a and a.pace >= 70 else 0.0), "skill": 0.3 + (0.3 if a and a.dribbling >= 70 else 0.0),
         "nutmeg": 0.05, "cut_inside": 0.15 + (0.25 if pl.role in (Role.INVERTED_WINGER, Role.WINGER) else 0.0)}
    u = rng.random() * sum(w.values())
    for k, v in w.items():
        u -= v
        if u < 0:
            return k
    return "skill"


def _row(eid: int, t: float, typ: str, team: str, **fields: Any) -> dict[str, Any]:
    return {"eid": eid, "i": eid // 16, "k": eid % 16, "t": t, "type": typ, "team": team, **fields}


def _emit(ctx: Context, rng: random.Random, st: Stats, lo: int, hi: int, acts: list[Act], takeons: list[TakeOn]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    subs: dict[int, list[tuple[float, int, dict[str, Any], bool]]] = {}  # anchor -> (t, order, row, is_receipt)
    owner: dict[int, Act] = {}  # id(row) -> the act it describes, to number it
    pending: list[tuple[dict[str, Any], Act]] = []  # (receipt or shot row, the pass it refers to)

    def sub(anchor: int, t: float, row: dict[str, Any], receipt: bool = False, act: Act | None = None) -> None:
        subs.setdefault(anchor, []).append((t, len(subs.get(anchor, [])), row, receipt))
        if act is not None:
            owner[id(row)] = act

    for a in acts:
        if a.dropped:
            continue
        under = bool(a.ev is not None and a.ev.under_pressure)
        if a.kind in ("pass", "ipass"):
            f = _pass_fields(ctx, rng, a, under)
            if a.implicit:
                sub(a.anchor, a.t, _row(0, a.t, "pass", a.team, player=a.actor, x=round(a.x0, 1), y=round(a.y0, 1),
                                        end_x=round(a.x1, 1), end_y=round(a.y1, 1), length=round(a.length, 1), implicit=True, **f),
                    act=a)
            else:
                a.eid = 16 * a.before
                rows.append(_row(a.eid, a.t, "pass", a.team, **f))
            if a.complete:
                r = _receipt(ctx, rng, a)
                row = _row(0, a.t_arr, "receipt", a.team, player=a.target, x=round(a.x1, 1), y=round(a.y1, 1), **r)
                sub(a.anchor, a.t_arr, row, True)
                pending.append((row, a))
        elif a.kind in ("carry", "icarry"):
            f = _carry_fields(ctx, a, under)
            if a.implicit:
                sub(a.anchor, a.t, _row(0, a.t, "carry", a.team, player=a.actor, x=round(a.x0, 1), y=round(a.y0, 1),
                                        end_x=round(a.x1, 1), end_y=round(a.y1, 1), implicit=True, **f))
            else:
                rows.append(_row(16 * a.before, a.t, "carry", a.team, **f))
        else:
            f = _shot_fields(ctx, rng, a)
            f["pressure"] = {"under": under}
            row = _row(16 * a.before, a.t, "shot", a.team, **f)
            rows.append(row)
            src = a.incoming if a.incoming is not None else (a.carry_prev.incoming if a.carry_prev is not None else None)
            if src is not None and src.t_arr is not None and a.t - src.t_arr <= ASSIST_MAX_S:
                pending.append((row, src))
    for to in takeons:
        sub(to.anchor, to.t, _row(0, to.t, "take_on", to.team, player=to.player, defender=to.defender, x=to.x, y=to.y,
                                  outcome="lost", style=_style(ctx, rng, to.player)))
    passes = [a for a in acts if a.kind == "pass"]
    for idx in range(lo, hi):
        e = ctx.events[idx]
        if e.type is EventType.FOUL:
            rows.append(_row(16 * idx, e.t, "foul", e.team, **_foul_fields(ctx, rng, acts, e)))
        elif e.type is EventType.INTERCEPTION:
            p = next((a for a in reversed(passes) if a.before < idx), None)
            if p is not None and not p.complete and p.t_arr is not None:
                rows.append(_row(16 * idx, e.t, "interception", e.team, pass_eid=16 * p.before, contest_s=round(e.t - p.t_arr, 3)))
    for anchor, items in subs.items():
        if len(items) > MAX_SUB:  # drop the lowest-value sub-events first, receipts last (4.1 overflow rule); the latest of a rank goes first
            ranked = sorted(range(len(items)), key=lambda n: (DROP_RANK[items[n][2]["type"]], -n))
            gone = set(ranked[: len(items) - MAX_SUB])
            st.overflow += len(gone)
            items = [it for n, it in enumerate(items) if n not in gone]
        items.sort(key=lambda it: (it[0], it[1]))
        for k, (t, _, row, _r) in enumerate(items, start=1):
            row["eid"] = 16 * anchor + k
            row["i"], row["k"] = anchor, k
            if id(row) in owner:
                owner[id(row)].eid = row["eid"]
            rows.append(row)
    for row, a in pending:  # numbers are known now: a receipt names its pass, a shot names the pass that set it up
        row["pass_eid" if row["type"] == "receipt" else "assist_eid"] = a.eid if a.eid >= 0 else None
    return rows


# ---------- entry points ----------

def enrich_segment(ctx: Context, st: Stats, lo: int, hi: int) -> list[dict[str, Any]]:
    """Rows of the segment of events [lo, hi). Depends only on those events, the time of event `hi` and the global context."""
    rng = random.Random(f"{ctx.seed}:micro:{16 * lo}")
    acts, takeons = _structure(ctx, lo, hi)
    _schedule(ctx, rng, st, lo, acts)
    st.segments += 1
    st.implicit_passes += sum(a.kind == "ipass" and not a.dropped for a in acts)
    st.implicit_carries += sum(a.kind == "icarry" and not a.dropped for a in acts)
    return sorted(_emit(ctx, rng, st, lo, hi, acts, takeons), key=lambda r: r["eid"])


def enrich(meta: MatchMeta, events: list[Event], t0: float | None = None, t1: float | None = None) -> Enriched:
    """All rows of a match, sorted by `eid`. With a window only the rows with `t0 <= t <= t1` are returned, built from the
    segments that touch the window (a restart up to 220 s before it), with the same eids as a full run."""
    ctx = Context(meta, events)
    st = Stats()
    starts = segment_starts(events)
    bounds = [*starts, len(events)]
    rows: list[dict[str, Any]] = []
    for lo, hi in zip(bounds[:-1], bounds[1:], strict=True):
        if t0 is not None and (events[hi].t if hi < len(events) else events[-1].t) < t0:
            continue
        if t1 is not None and events[lo].t > t1:
            continue
        rows += enrich_segment(ctx, st, lo, hi)
    if t0 is not None or t1 is not None:
        rows = [r for r in rows if (t0 is None or r["t"] >= t0) and (t1 is None or r["t"] <= t1)]
    rows.sort(key=lambda r: r["eid"])
    return Enriched(rows, st)
