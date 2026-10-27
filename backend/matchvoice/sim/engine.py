"""Possession-chain match simulation.

Each step is one on-ball action (pass, carry, shot, ...). The simulation works in
attacking-normalised coordinates (x = 0 own goal line, x = 105 opponent goal line)
and converts to absolute pitch coordinates only when an event is emitted.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from ..schema import (
    PITCH_L, PITCH_W, Event, EventType, MatchMeta, Side, TeamMeta, TruthItem,
)
from .arcs import ARCS, Arc
from .names import CLUB_COLORS, CLUB_PREFIX, CLUB_SUFFIX, GIVEN, SURNAME
from .profile import build_team
from .tactics import build_tactics, posture_schedule

GOAL_Y = PITCH_W / 2
LEAGUE_GENDER = "men"  # the Synthetic League is a men's league: the booth may say "he" (TeamMeta.gender)
FORMATIONS: dict[str, list[tuple[str, str, float, float]]] = {
    "4-4-2": [
        ("GK", "GK", 5, 34), ("RB", "DEF", 28, 60), ("CB", "DEF", 24, 42), ("CB", "DEF", 24, 26),
        ("LB", "DEF", 28, 8), ("RM", "MID", 52, 58), ("CM", "MID", 48, 40), ("CM", "MID", 48, 28),
        ("LM", "MID", 52, 10), ("ST", "FWD", 76, 40), ("ST", "FWD", 76, 28),
    ],
    "4-3-3": [
        ("GK", "GK", 5, 34), ("RB", "DEF", 30, 60), ("CB", "DEF", 24, 42), ("CB", "DEF", 24, 26),
        ("LB", "DEF", 30, 8), ("CM", "MID", 46, 46), ("DM", "MID", 40, 34), ("CM", "MID", 46, 22),
        ("RW", "FWD", 74, 58), ("ST", "FWD", 80, 34), ("LW", "FWD", 74, 10),
    ],
    "4-2-3-1": [
        ("GK", "GK", 5, 34), ("RB", "DEF", 28, 60), ("CB", "DEF", 24, 42), ("CB", "DEF", 24, 26),
        ("LB", "DEF", 28, 8), ("DM", "MID", 40, 42), ("DM", "MID", 40, 26), ("RW", "MID", 62, 58),
        ("AM", "MID", 62, 34), ("LW", "MID", 62, 10), ("ST", "FWD", 80, 34),
    ],
}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


@dataclass
class SimPlayer:
    id: str
    name: str
    number: int
    pos: str
    group: str
    ax: float  # formation anchor, attacking-normalised
    ay: float
    passing: float
    finishing: float
    pace: float
    yellow: int = 0
    off: bool = False


@dataclass
class SimTeam:
    side: Side
    name: str
    short: str
    color: str
    formation: str
    players: list[SimPlayer]
    attack: float
    defense: float
    press: float
    finishing: float
    tempo: float
    shots: int = 0

    def active(self) -> list[SimPlayer]:
        return [p for p in self.players if not p.off]

    def strength(self) -> float:
        return 0.9 ** sum(p.off for p in self.players)


def _make_team(rng: random.Random, side: Side, name: str, color: str, arc: Arc, used: set[str]) -> SimTeam:
    formation = rng.choice(list(FORMATIONS))
    players: list[SimPlayer] = []
    numbers = [1, 2, 5, 4, 3, 7, 8, 6, 11, 9, 10]
    for k, (pos, group, ax, ay) in enumerate(FORMATIONS[formation]):
        while True:
            given, family = rng.choice(GIVEN), rng.choice(SURNAME)
            if family not in used:  # surnames are unique within a match so commentary is unambiguous
                used.add(family)
                full = f"{given} {family}"
                break
        base = {"GK": 0.45, "DEF": 0.5, "MID": 0.55, "FWD": 0.6}[group]
        players.append(SimPlayer(
            id=f"{side}{k + 1}", name=full, number=numbers[k], pos=pos, group=group, ax=ax, ay=ay,
            passing=_clamp(rng.gauss(base + 0.05, 0.08), 0.3, 0.9),
            finishing=_clamp(rng.gauss(base, 0.1), 0.2, 0.9),
            pace=_clamp(rng.gauss(0.55, 0.12), 0.3, 0.95),
        ))
    s = arc.skills.get(side, {})
    short = "".join(w[0] for w in name.split())[:3].upper()
    return SimTeam(
        side=side, name=name, short=short, color=color, formation=formation, players=players,
        attack=s.get("attack", _clamp(rng.gauss(0.55, 0.03), 0.45, 0.65)),
        defense=s.get("defense", _clamp(rng.gauss(0.55, 0.03), 0.45, 0.65)),
        press=s.get("press", _clamp(rng.gauss(0.5, 0.04), 0.4, 0.6)),
        finishing=s.get("finishing", _clamp(rng.gauss(0.5, 0.05), 0.4, 0.6)),
        tempo=_clamp(rng.gauss(0.5, 0.05), 0.4, 0.6),
    )


class Sim:
    def __init__(self, arc_name: str, seed: int, scene=None):
        self.scene = scene  # a live scene (sim/scene.py) that takes over at a dead ball; draws nothing here, so None is the plain match
        self.arc = ARCS[arc_name]
        self.seed = seed
        self.rng = random.Random(seed)
        r = self.rng
        prefixes = r.sample(CLUB_PREFIX, 2)
        colors = r.sample(CLUB_COLORS, 2)
        used: set[str] = set()
        names = [f"{p} {r.choice(CLUB_SUFFIX)}" for p in prefixes]
        self.teams: dict[str, SimTeam] = {
            "H": _make_team(r, "H", names[0], colors[0], self.arc, used),
            "A": _make_team(r, "A", names[1], colors[1], self.arc, used),
        }
        self.stop1 = 60 * r.randint(1, 3)
        self.stop2 = 60 * r.randint(2, 5)
        self.end_t = self.stop1 + 5400 + self.stop2
        self.t = 0.0
        self.period = 1
        self.poss: Side = "H"
        self.bx, self.by = 52.5, 34.0
        self.carrier: SimPlayer = self.teams["H"].players[9]
        self.score = {"H": 0, "A": 0}
        self.set_piece: str | None = None
        self.events: list[Event] = []
        self.truth: list[TruthItem] = []
        self.pending = [(self._minute_t(b.minute), b) for b in self.arc.beats]
        self.pending.sort(key=lambda x: x[0])
        for w in self.arc.windows:
            self.truth.append(TruthItem(
                t=self._minute_t(w.start), clock=str(w.start), kind="momentum_swing", side=w.side,
                note=w.note, importance=0.6, end=self._minute_t(w.end + 1)))  # type: ignore[arg-type]
        self.forced: Side | None = None
        self.forced_beat = None
        self.forced_since = 0.0

    # ---------- clock helpers ----------
    def _minute_t(self, minute: int) -> float:
        base = (minute - 1) * 60.0
        return base + (self.stop1 if minute > 45 else 0)

    def clock(self, t: float | None = None) -> str:
        t = self.t if t is None else t
        if t <= 2700 + self.stop1 and self.period == 1:
            return str(int(t // 60) + 1) if t < 2700 else f"45+{int((t - 2700) // 60) + 1}"
        tt = t - self.stop1
        return str(int(tt // 60) + 1) if tt < 5400 else f"90+{int((tt - 5400) // 60) + 1}"

    def boost(self, side: Side) -> float:
        b = 0.0
        for w in self.arc.windows:
            if w.side == side and self._minute_t(w.start) <= self.t <= self._minute_t(w.end + 1):
                b += w.boost
        return b

    def edge(self, side: Side) -> float:
        return (1 + self.boost(side)) * self.teams[side].strength()

    # ---------- geometry ----------
    def _direction(self, side: Side) -> int:
        right = (side == "H") == (self.period == 1)
        return 1 if right else -1

    def _abs(self, side: Side, x: float, y: float) -> tuple[float, float]:
        if self._direction(side) > 0:
            return round(x, 1), round(y, 1)
        return round(PITCH_L - x, 1), round(PITCH_W - y, 1)

    def _other(self, side: Side) -> Side:
        return "A" if side == "H" else "H"

    # ---------- emit ----------
    def emit(self, typ: EventType, side: Side, player: SimPlayer | None, x: float, y: float,
             end: tuple[float, float] | None = None, **kw) -> Event:
        ax, ay = self._abs(side, x, y)
        ex = ey = None
        if end is not None:
            ex, ey = self._abs(side, end[0], end[1])
        ev = Event(
            i=len(self.events), t=round(self.t, 1), period=self.period, clock=self.clock(), type=typ,
            team=side, player=player.id if player else None, x=ax, y=ay, end_x=ex, end_y=ey, **kw)
        self.events.append(ev)
        return ev

    def _nearest(self, team: SimTeam, x: float, y: float, exclude: SimPlayer | None = None,
                 allow_gk: bool = False) -> SimPlayer:
        cands = [p for p in team.active() if p is not exclude and (allow_gk or p.group != "GK")]
        weights = []
        for p in cands:
            # players drift towards the ball: shift anchors a third of the way
            px = p.ax + (x - p.ax) * 0.35
            py = p.ay + (y - p.ay) * 0.35
            d = math.hypot(px - x, py - y)
            weights.append(math.exp(-d / 11.0))
        return self.rng.choices(cands, weights)[0]

    def _keeper(self, team: SimTeam) -> SimPlayer:
        return next(p for p in team.active() if p.group == "GK")

    # ---------- possession ----------
    def _flip(self, reason: str, x: float, y: float, taker: SimPlayer | None = None) -> None:
        """Hand the ball to the other side at attacking-normalised (x, y) of the OLD possessor."""
        new = self._other(self.poss)
        nx, ny = PITCH_L - x, PITCH_W - y
        nteam = self.teams[new]
        self.poss = new
        self.bx, self.by = _clamp(nx, 1, PITCH_L - 1), _clamp(ny, 1, PITCH_W - 1)
        self.carrier = taker or self._nearest(nteam, self.bx, self.by)
        self.emit(EventType.POSSESSION_CHANGE, new, self.carrier, self.bx, self.by, reason=reason)

    def _pressure_prob(self, team: SimTeam, opp: SimTeam) -> float:
        zone = _clamp((self.bx - 20) / 80, 0.1, 1.0)
        base = opp.press * (0.35 + 0.4 * zone)
        return _clamp(base * self.edge(opp.side) / self.edge(team.side), 0.05, 0.7)

    # ---------- actions ----------
    def step(self) -> None:
        if self.scene is not None and self.scene.should_fork(self):
            return self.scene.play(self)
        team = self.teams[self.poss]
        opp = self.teams[self._other(self.poss)]
        r = self.rng

        if self.set_piece:
            sp, self.set_piece = self.set_piece, None
            return self._do_set_piece(sp, team, opp)

        # scripted beats
        if self.forced is None and self.pending and self.t >= self.pending[0][0]:
            _, beat = self.pending.pop(0)
            if beat.kind == "red_card":
                return self._red_card(beat)
            self.forced, self.forced_beat, self.forced_since = beat.side, beat, self.t
        if self.forced is not None:
            if self.poss == self.forced:
                return self._scripted_attack(team, opp)
            if self.t - self.forced_since > 45:
                return self._steal(team, opp)

        # foul
        if r.random() < 0.010 * opp.press * 2:
            return self._foul(team, opp)

        carrier = self.carrier
        pressured = r.random() < self._pressure_prob(team, opp)
        defender = self._nearest(opp, PITCH_L - self.bx, PITCH_W - self.by)
        if pressured and r.random() < 0.35:
            self.emit(EventType.PRESSURE, opp.side, defender, PITCH_L - self.bx, PITCH_W - self.by)

        # shot?
        d_goal = math.hypot(PITCH_L - self.bx, GOAL_Y - self.by)
        p_shot = _clamp(0.30 - d_goal * 0.0115, 0.0, 0.30) * (0.75 + team.attack) * (self.edge(team.side) / self.edge(opp.side)) ** 1.25
        if self.bx > 68 and r.random() < p_shot * 0.17:
            return self._shot(team, opp, carrier, pressured)

        roll = r.random()
        if roll < 0.20:
            return self._carry(team, opp, carrier, pressured, defender)
        if roll < 0.60:
            return self._pass(team, opp, carrier, pressured, kind="short")
        if roll < 0.90:
            return self._pass(team, opp, carrier, pressured, kind="progressive")
        return self._pass(team, opp, carrier, pressured, kind="long")

    def _pass(self, team: SimTeam, opp: SimTeam, carrier: SimPlayer, pressured: bool, kind: str,
              set_piece: str | None = None, force_ok: bool = False,
              target: tuple[float, float] | None = None) -> None:
        r = self.rng
        if target is None:
            fwd = {"short": r.uniform(-4, 10), "progressive": r.uniform(10, 26), "long": r.uniform(26, 45)}[kind]
            if team.tempo > 0.5 and r.random() < 0.3:
                fwd += 4
            lat = r.gauss(0, {"short": 8, "progressive": 10, "long": 14}[kind])
            tx = _clamp(self.bx + fwd, 2, PITCH_L - 2)
            ty = _clamp(self.by + lat, 2, PITCH_W - 2)
        else:
            tx, ty = target
        length = math.hypot(tx - self.bx, ty - self.by)
        depth = max(0.0, tx - self.bx)
        difficulty = _clamp(0.04 + length / 70 + (0.2 if pressured else 0) + depth / 150, 0.0, 1.0)
        p_ok = 0.94 - 0.0036 * length + 0.14 * (carrier.passing - 0.5) - 0.22 * pressured - 0.05 * (depth > 20)
        p_ok = _clamp(p_ok * (self.edge(team.side) / self.edge(opp.side)) ** 0.25, 0.3, 0.98)
        speed_ms = r.uniform(14, 24)
        ok = force_ok or r.random() < p_ok
        receiver = self._nearest(team, tx, ty, exclude=carrier, allow_gk=tx < 12)
        out = (not ok) and r.random() < 0.28
        self.emit(
            EventType.PASS, team.side, carrier, self.bx, self.by, end=(tx, ty),
            outcome="complete" if ok else ("out" if out else "incomplete"),
            receiver=receiver.id if ok else None, set_piece=set_piece, length=round(length, 1),
            difficulty=round(difficulty, 2), ball_speed=round(speed_ms * 3.6, 1),
            under_pressure=True if pressured else None)
        self.t += length / speed_ms + r.uniform(1.6, 4.6) / (0.6 + team.tempo)
        if ok:
            self.bx, self.by, self.carrier = tx, ty, receiver
            return
        if out:
            self.t += r.uniform(6, 14)
            self._out_of_play(team, tx, ty)
            return
        taker = self._nearest(opp, PITCH_L - tx, PITCH_W - ty)
        self.emit(EventType.INTERCEPTION, opp.side, taker, PITCH_L - tx, PITCH_W - ty)
        self._flip("interception", tx, ty, taker)

    def _out_of_play(self, team: SimTeam, x: float, y: float) -> None:
        opp_side = self._other(team.side)
        if x > PITCH_L - 3:
            self.set_piece = "goal_kick"
            self.poss = opp_side
            self.bx, self.by = 5.0, 34.0
            self.carrier = self._keeper(self.teams[opp_side])
            self.emit(EventType.POSSESSION_CHANGE, opp_side, self.carrier, self.bx, self.by, reason="out_of_play")
        else:
            self.set_piece = "throw_in"
            self._flip("out_of_play", x, 0.0 if y < 34 else PITCH_W)

    def _carry(self, team: SimTeam, opp: SimTeam, carrier: SimPlayer, pressured: bool,
               defender: SimPlayer) -> None:
        r = self.rng
        dx = r.uniform(3, 16)
        dy = r.gauss(0, 5)
        tx = _clamp(self.bx + dx, 1, PITCH_L - 1)
        ty = _clamp(self.by + dy, 1, PITCH_W - 1)
        dist = math.hypot(tx - self.bx, ty - self.by)
        v = _clamp(r.gauss(4.5 + 3.5 * carrier.pace, 0.8), 2.5, 9.0)
        if pressured and r.random() < 0.28 * (opp.press + 0.5):
            self.emit(EventType.TACKLE, opp.side, defender, PITCH_L - self.bx, PITCH_W - self.by,
                      outcome="won")
            self.t += r.uniform(1.0, 2.5)
            self._flip("tackle", self.bx, self.by, defender)
            return
        self.emit(EventType.CARRY, team.side, carrier, self.bx, self.by, end=(tx, ty),
                  length=round(dist, 1), speed=round(v * 3.6, 1), under_pressure=True if pressured else None)
        self.t += dist / v
        self.bx, self.by = tx, ty

    def _foul(self, team: SimTeam, opp: SimTeam) -> None:
        r = self.rng
        fouler = self._nearest(opp, PITCH_L - self.bx, PITCH_W - self.by)
        self.emit(EventType.FOUL, opp.side, fouler, PITCH_L - self.bx, PITCH_W - self.by, outcome="free_kick")
        # red cards come from the arc only, so the story stays under control
        if r.random() < 0.2 and fouler.yellow == 0:
            fouler.yellow += 1
            self.emit(EventType.CARD, opp.side, fouler, PITCH_L - self.bx, PITCH_W - self.by, card="yellow")
        self.t += r.uniform(12, 25)
        self.set_piece = "free_kick"

    def _send_off(self, team: SimTeam, player: SimPlayer, reason: str) -> None:
        player.off = True
        self.emit(EventType.CARD, team.side, player, PITCH_L - self.bx, PITCH_W - self.by,
                  card="red", reason=reason)

    def _red_card(self, beat) -> None:
        team = self.teams[beat.side]
        victim = self.rng.choice([p for p in team.active() if p.group in ("DEF", "MID")])
        if self.poss == beat.side:
            self._flip("foul", self.bx, self.by)
        self.emit(EventType.FOUL, team.side, victim, PITCH_L - self.bx, PITCH_W - self.by, outcome="free_kick")
        self._send_off(team, victim, "straight_red")
        self.truth.append(TruthItem(t=round(self.t, 1), clock=self.clock(), kind="red_card", side=beat.side,
                                    note=beat.note, importance=beat.importance))
        self.t += self.rng.uniform(40, 70)
        self.set_piece = "free_kick"

    def _do_set_piece(self, sp: str, team: SimTeam, opp: SimTeam) -> None:
        r = self.rng
        if sp == "corner":
            cy = 0.0 if r.random() < 0.5 else PITCH_W
            self.bx, self.by = PITCH_L - 0.5, cy
            taker = self._nearest(team, 60, cy)
            self.carrier = taker
            self.t += r.uniform(10, 22)
            ty = _clamp(34 + r.gauss(0, 6), 22, 46)
            self._pass(team, opp, taker, False, "long", set_piece="corner", target=(PITCH_L - r.uniform(5, 12), ty))
            if self.carrier is not taker and self.poss == team.side:
                self._shot(team, opp, self.carrier, True, header=True)
            return
        if sp == "free_kick":
            if self.bx > 78 and r.random() < 0.35:
                return self._shot(team, opp, self._nearest(team, self.bx, self.by), False, free_kick=True)
            return self._pass(team, opp, self.carrier, False, "progressive" if self.bx < 60 else "short",
                              set_piece="free_kick")
        if sp == "goal_kick":
            return self._pass(team, opp, self.carrier, False, "long", set_piece="goal_kick")
        return self._pass(team, opp, self.carrier, False, "short", set_piece="throw_in")

    def _xg(self, x: float, y: float, pressured: bool, header: bool = False) -> float:
        dx = PITCH_L - x
        dy = y - GOAL_Y
        angle = math.atan2(7.32 * dx, dx * dx + dy * dy - 3.66 ** 2) if dx > 0.5 else 1.0
        angle = angle if angle > 0 else angle + math.pi
        d = math.hypot(dx, dy)
        z = -1.9 - 0.11 * d + 2.0 * angle - (0.3 if pressured else 0) - (0.4 if header else 0)
        return 1 / (1 + math.exp(-z))

    def _shot(self, team: SimTeam, opp: SimTeam, shooter: SimPlayer, pressured: bool, header: bool = False,
              free_kick: bool = False, force_goal: bool = False) -> None:
        r = self.rng
        xg = self._xg(self.bx, self.by, pressured, header)
        if force_goal:
            xg = max(xg, r.uniform(0.12, 0.5))
        team.shots += 1
        gk = self._keeper(opp)
        speed = _clamp(r.gauss(95 + 25 * shooter.finishing, 9), 60, 140)
        part = "head" if header else ("foot" if r.random() < 0.9 else "other")
        on_target = r.random() < 0.3 + 0.35 * shooter.finishing + 0.4 * xg
        roll = r.random()
        if force_goal:
            outcome = "goal"
        elif not on_target:
            outcome = "blocked" if (pressured and roll < 0.3) else ("post" if roll < 0.06 else "off_target")
        else:
            outcome = "saved"  # natural goals are not allowed, goals come from the arc
        extra = {}
        if outcome in ("saved", "goal"):
            extra["keeper"] = gk.id
        if outcome == "goal":
            self.score[team.side] += 1
            extra["score"] = [self.score["H"], self.score["A"]]
        self.emit(EventType.SHOT, team.side, shooter, self.bx, self.by,
                  end=(PITCH_L, GOAL_Y + r.gauss(0, 3.2) if outcome in ("goal", "saved") else GOAL_Y + r.gauss(0, 9)),
                  outcome=outcome, xg=round(xg, 3), shot_speed=round(speed, 1), body_part=part,
                  under_pressure=True if pressured else None, set_piece="free_kick" if free_kick else None, **extra)
        self.t += r.uniform(1.5, 3.0)
        if outcome == "goal":
            self.t += r.uniform(30, 55)
            self._kickoff(self._other(team.side))
        elif outcome == "saved":
            if r.random() < 0.35:
                self.set_piece = "corner"
                self.t += r.uniform(4, 8)
            else:
                self.poss = opp.side
                self.bx, self.by, self.carrier = 6.0, 34.0, gk
                self.emit(EventType.POSSESSION_CHANGE, opp.side, gk, self.bx, self.by, reason="save")
        elif outcome == "blocked":
            if r.random() < 0.4:
                self.set_piece = "corner"
            else:
                self._flip("clearance", self.bx, self.by)
        else:
            self.t += r.uniform(6, 12)
            self.poss = opp.side
            self.bx, self.by, self.carrier = 5.0, 34.0, gk
            self.set_piece = "goal_kick"
            self.emit(EventType.POSSESSION_CHANGE, opp.side, gk, self.bx, self.by, reason="goal_kick")

    def _kickoff(self, side: Side) -> None:
        self.poss = side
        self.bx, self.by = 52.5, 34.0
        team = self.teams[side]
        self.carrier = next(p for p in reversed(team.active()) if p.group in ("FWD", "MID"))
        self.emit(EventType.KICKOFF, side, self.carrier, self.bx, self.by)

    def _scripted_attack(self, team: SimTeam, opp: SimTeam) -> None:
        """Run a short, plausible build-up that ends in the arc's goal."""
        r = self.rng
        beat = self.forced_beat
        for _ in range(r.randint(2, 4)):
            target = (_clamp(self.bx + r.uniform(12, 22), 10, 84), _clamp(34 + r.gauss(0, 12), 6, 62))
            self._pass(team, opp, self.carrier, False, "progressive", force_ok=True, target=target)
        self.bx, self.by = _clamp(self.bx + r.uniform(4, 8), 80, 96), _clamp(34 + r.gauss(0, 7), 22, 46)
        shooter = max(team.active(), key=lambda p: p.finishing * (p.group == "FWD" or r.random() < 0.3))
        self.carrier = shooter
        self._shot(team, opp, shooter, False, force_goal=True)
        shot = next(e for e in reversed(self.events) if e.type == EventType.SHOT)
        self.truth.append(TruthItem(
            t=shot.t, clock=shot.clock, kind="goal", side=beat.side, note=beat.note,
            importance=beat.importance))
        self.forced = None
        self.forced_beat = None

    def _steal(self, team: SimTeam, opp: SimTeam) -> None:
        taker = self._nearest(opp, PITCH_L - self.bx, PITCH_W - self.by)
        self.emit(EventType.INTERCEPTION, opp.side, taker, PITCH_L - self.bx, PITCH_W - self.by)
        self._flip("interception", self.bx, self.by, taker)

    # ---------- run ----------
    def run(self) -> tuple[MatchMeta, list[Event], list[TruthItem]]:
        self._kickoff("H")
        half_done = False
        while self.t < self.end_t:
            if not half_done and self.t >= 2700 + self.stop1:
                self.emit(EventType.PERIOD_END, self.poss, None, self.bx, self.by, outcome="half_time")
                self.period = 2
                half_done = True
                self.set_piece = None
                self._kickoff("A")
                continue
            self.step()
        self.emit(EventType.PERIOD_END, self.poss, None, self.bx, self.by, outcome="full_time")
        self.truth.sort(key=lambda x: x.t)
        # profiles and tactics draw from their own streams and read the finished match, so the skeleton above is untouched
        profiles = {s: build_team(self.seed, t.players, [(p.name, p.number) for p in t.players]) for s, t in self.teams.items()}
        postures = posture_schedule(self.events, self._minute_t)
        meta = MatchMeta(
            id=f"{self.arc.name}-{self.seed}", seed=self.seed, arc=self.arc.name, title=self.arc.title,
            competition="Synthetic League", venue=f"{self.teams['H'].name} Ground",
            teams={s: TeamMeta(
                side=s, name=t.name, short=t.short, color=t.color, formation=t.formation, players=profiles[s],
                tactics=build_tactics(self.seed, s, t.formation, t.press, t.tempo, profiles[s]), postures=postures[s],
                gender=LEAGUE_GENDER,
            ) for s, t in self.teams.items()})
        return meta, self.events, self.truth
