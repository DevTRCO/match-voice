"""Pattern detector: a habit of one side that the viewer cannot see, found from past events only (docs/INSIGHT-SETUP.md).

The co-commentator points it out in a quiet spell (the set-up, moment kind `pattern_insight`), and when a goal later breaks the
habit, the goal analysis is told so and pays it off ("There it is. Ibsen wins it, and this time it goes across.").

One habit is detected, the one the data of the demo match proves (INSIGHT-SETUP 2, candidate 1):

    short_after_win   a side keeps winning the ball in its own half, and every first pass after it goes short (under SHORT_M long):
                      in this half not one open-play ball has gone across the pitch (ACROSS_M or more sideways)

No lookahead. `feed(ev)` is called with every event in order; `quiet(t)` asks at match second `t`, so everything it reads happened
before `t`. A quiet spell is a dead ball (a saved or missed shot, a foul, a card, a ball out of play) with no event for QUIET_S. The
set-up fires once per side and half, only while the habit holds, and only with enough evidence (MIN_WINS ball wins with a first pass).
The pay-off (`broken_by`) is checked at a goal: the scoring side's possession began with a ball win in its own half and the first
pass after it went across. The runner pays it off only if the set-up was said in this broadcast.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..facts.engine import _attacking_x
from ..schema import PITCH_L, PITCH_W, Event, EventType, MatchMeta
from .moments import Moment, surname

PATTERN_BASE = 800_000  # derived ids of pattern_insight moments: 800000 + 4 * (half - 1) + side (skeleton range, under the score lines' 900000)
QUIET_S = 5.0  # the ball has been dead this long: the co-commentator has room for an observation
MIN_WINS = 8  # ball wins in the own half, each followed by a first pass of the same side, before the habit is worth a line
ACROSS_M = 30.0  # a pass that moves the ball this far sideways goes "across" the pitch
SHORT_M = 30.0  # a first pass shorter than this is "short"; a longer one (a clearance, a long ball, a ball in behind) is not (enrich.py: clearance from 30 m, long from 32 m)
MIN_WINNER = 3  # a player who made this many of the half's own-half ball wins is the one who "keeps winning it"
PRIORITY, TTL_S = 50, 25.0  # above the context layer (30 to 45), below the goal analysis (70); calm energy
DEAD = (EventType.FOUL, EventType.CARD)  # events after which the ball is dead (plus a shot that is not a goal and a pass out of play)
ON_BALL = (EventType.PASS, EventType.CARRY, EventType.SHOT, EventType.INTERCEPTION, EventType.TACKLE, EventType.POSSESSION_CHANGE)


def pattern_id(side: str, half: int) -> int:
    return PATTERN_BASE + 4 * (half - 1) + (0 if side == "H" else 1)


def is_pattern_id(moment_id: int) -> bool:
    return PATTERN_BASE <= moment_id < PATTERN_BASE + 8


@dataclass
class Win:
    ev: Event
    first: Event | None = None  # the first pass of the same side after the win, before the other side touched the ball

    @property
    def across(self) -> bool:
        return self.first is not None and _across(self.first)

    @property
    def short(self) -> bool:
        return self.first is not None and _length(self.first) < SHORT_M


def _across(ev: Event) -> bool:
    return ev.end_y is not None and abs(ev.end_y - ev.y) >= ACROSS_M


def _length(ev: Event) -> float:
    if ev.end_x is None or ev.end_y is None:
        return 0.0
    return ((ev.end_x - ev.x) ** 2 + (ev.end_y - ev.y) ** 2) ** 0.5


def _r(v: float | None) -> float | None:
    return None if v is None else round(v, 1)


@dataclass
class PatternFeed:
    meta: MatchMeta
    wins: dict[tuple[str, int], list[Win]] = field(default_factory=dict)  # (side, half) -> own-half ball wins, oldest first
    across: dict[tuple[str, int], list[int]] = field(default_factory=dict)  # (side, half) -> event ids of open-play passes across
    taken: Counter = field(default_factory=Counter)  # player id -> interceptions and won tackles in the match
    last: Event | None = None
    open: dict[str, Win | None] = field(default_factory=lambda: {"H": None, "A": None})  # the win that started a side's current possession
    fired: set[tuple[str, int]] = field(default_factory=set)  # (side, half) of the set-ups said
    spell: int | None = None  # event id of the stoppage whose quiet spell already had its observation

    def feed(self, ev: Event) -> None:
        if ev.type is EventType.PRESSURE:  # a presser closing in does not move the ball or end a dead ball
            return
        side, other = ev.team, "A" if ev.team == "H" else "H"
        if ev.type in ON_BALL and not (ev.type is EventType.TACKLE and ev.outcome != "won"):
            self.open[other] = None  # this side has the ball now: the other side's possession, if it had one, is over
        if ev.type is EventType.KICKOFF:
            self.open = {"H": None, "A": None}
        won = ev.type is EventType.INTERCEPTION or (ev.type is EventType.TACKLE and ev.outcome == "won")
        if won and ev.player:
            self.taken[ev.player] += 1
            if _attacking_x(side, ev.period, ev.x) < PITCH_L / 2:
                w = Win(ev)
                self.wins.setdefault((side, ev.period), []).append(w)
                self.open[side] = w
            else:
                self.open[side] = None
        elif ev.type is EventType.PASS and ev.set_piece is not None:
            self.open[side] = None  # a restart: the play after the win is over, its first pass never came (a later open-play ball is not "the first pass after the win")
        elif ev.type is EventType.PASS:
            w = self.open.get(side)
            if w is not None and w.first is None:
                w.first = ev
            if _across(ev):
                self.across.setdefault((side, ev.period), []).append(ev.i)
        self.last = ev

    # ---------- the habit ----------
    def habit(self, side: str, half: int) -> dict | None:
        """The facts and the evidence of the habit as it stands now, or None when it does not hold."""
        wins = [w for w in self.wins.get((side, half), []) if w.first is not None]
        # "every first pass went short" is the claim: one clearance or long ball after a win, and the habit does not hold this half
        if len(wins) < MIN_WINS or any(w.across or not w.short for w in wins) or self.across.get((side, half)):
            return None
        team = self.meta.teams[side]
        by = Counter(w.ev.player for w in wins)
        best, n = max(sorted(by.items()), key=lambda kv: kv[1])
        best_players = [p for p, k in by.items() if k == n]
        winner = best if n >= MIN_WINNER and len(best_players) == 1 else None
        names = {p.id: p.name for p in team.players}
        own_x = (PITCH_L / 2, PITCH_L) if _attacking_x(side, half, PITCH_L) < PITCH_L / 2 else (0.0, PITCH_L / 2)
        widest = max(abs((w.first.end_y if w.first.end_y is not None else w.first.y) - w.first.y) for w in wins)
        facts = {"team": team.name, "short": team.name.split()[0], "since": "half-time" if half == 2 else "kick-off",
                 "ball_wins_own_half": len(wins), "balls_across": 0,
                 "what": (f"Every time {team.name} won the ball in their own half this half, the first pass went short; "
                          f"not one open-play ball has gone across the pitch since {'half-time' if half == 2 else 'kick-off'}")}
        if winner:
            facts |= {"player": surname(names.get(winner, winner)), "ball_winner_wins_this_half": n, "ball_winner_wins_match": self.taken[winner]}
        evidence = {"kind": "pattern", "habit": "short_after_win", "side": side, "team": team.name, "half": half,
                    "zone": [own_x[0], 0.0, own_x[1], PITCH_W],
                    "dots": [[_r(w.ev.x), _r(w.ev.y)] for w in wins],
                    "arrows": [[_r(w.first.x), _r(w.first.y), _r(w.first.end_x), _r(w.first.end_y)] for w in wins if w.first.end_x is not None],
                    "players": [winner] if winner else [], "wins": len(wins), "short": len(wins), "across": 0,
                    "widest_m": round(widest, 1), "ev": [w.ev.i for w in wins] + [w.first.i for w in wins]}
        if winner:
            evidence["winner_wins"] = n
        return {"facts": facts, "evidence": evidence}

    def dead(self, t: float) -> bool:
        """The ball has been dead for QUIET_S at `t`: the last event stopped play and nothing has happened since."""
        e = self.last
        if e is None or t - e.t < QUIET_S - 1e-9:
            return False
        if e.type is EventType.SHOT:
            return e.outcome != "goal"  # after a goal the booth has the call, the co line and the score to say
        return e.type in DEAD or (e.type is EventType.PASS and e.outcome == "out")

    def quiet(self, t: float) -> list[tuple[Moment, dict]]:
        """The set-up due at match second `t`: a habit that holds, in a quiet spell, once per side and half, one per quiet spell. With its evidence
        for the overlay (`say.ins`), which is never a fact of the prompt."""
        if not self.dead(t) or self.spell == self.last.i:
            return []
        half = self.last.period
        found = [(side, h) for side in ("H", "A") if (side, half) not in self.fired and (h := self.habit(side, half)) is not None]
        if not found:
            return []
        # one observation per quiet spell: a habit with a player who keeps winning it first, then the one with more evidence
        side, h = max(found, key=lambda sh: (bool(sh[1]["evidence"]["players"]), sh[1]["evidence"]["wins"], sh[0] == "H"))
        self.fired.add((side, half))
        self.spell = self.last.i
        params = dict(h["facts"])
        gender = self.meta.teams[side].gender
        if gender:
            params["squad"] = gender
        m = Moment(id=pattern_id(side, half), t=round(self.last.t + QUIET_S, 3), clock=self.last.clock, kind="pattern_insight",
                   voice="analyst", priority=PRIORITY, ttl=TTL_S, params=params, evidence=list(h["evidence"]["ev"]))
        out = [(m, h["evidence"])]
        return out

    # ---------- the pay-off ----------
    def broken_by(self, side: str) -> dict | None:
        """At a goal by `side`: did its possession begin with a ball win in its own half whose first pass went across? Then the goal
        broke the habit. Returns the facts and the evidence of the break."""
        w = self.open.get(side)
        if w is None or not w.across:
            return None
        names = {p.id: p.name for t in self.meta.teams.values() for p in t.players}
        winner = surname(names.get(w.ev.player or "", ""))
        to = surname(names.get(w.first.receiver or "", "")) if w.first.receiver else None
        f = w.first
        band = min(2, int(f.end_y / (PITCH_W / 3)))  # the third of the pitch's width where the ball lands
        facts = {"ball_winner": winner, "this_time": (f"{winner} won the ball in their own half and the first pass went straight across the pitch"
                                                      + (f" to {to}" if to else "") + ", the ball the habit never had")}
        evidence = {"kind": "payoff", "habit": "short_after_win", "side": side, "half": f.period,
                    "arrow": [_r(f.x), _r(f.y), _r(f.end_x), _r(f.end_y)], "zone": [0.0, _r(band * PITCH_W / 3), PITCH_L, _r((band + 1) * PITCH_W / 3)],
                    "players": [p for p in (w.ev.player, f.receiver) if p], "ev": [w.ev.i, f.i]}
        return {"facts": facts, "evidence": evidence}
