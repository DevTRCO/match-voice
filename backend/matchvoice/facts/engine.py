"""Fact engine: turns the raw event stream into verified facts and live match state.

Pure code, no model calls. Every fact carries the ids of the events it follows from,
so a commentary sentence can always be traced back to what happened on the pitch.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from ..schema import PITCH_L, PITCH_W, Event, EventType, MatchMeta, Side
from .models import Fact
from .winprob import expected_points, rate_per_s, red_multiplier, win_probs

WINDOW_S = 300.0  # momentum looks at the last five minutes
SPRINT_KMH = 30.0
BIG_CHANCE_XG = 0.20
HEAT_COLS, HEAT_ROWS = 21, 14


def minute_of(clock: str) -> int:
    return int(clock.split("+")[0])


@dataclass
class TeamStats:
    shots: int = 0
    on_target: int = 0
    xg: float = 0.0
    passes: int = 0
    passes_ok: int = 0
    tackles: int = 0
    interceptions: int = 0
    fouls: int = 0
    yellow: int = 0
    red: int = 0
    corners: int = 0
    poss_s: float = 0.0


@dataclass
class PlayerStats:
    passes: int = 0
    passes_ok: int = 0
    shots: int = 0
    on_target: int = 0
    xg: float = 0.0
    goals: int = 0
    tackles: int = 0
    interceptions: int = 0
    fouls: int = 0
    carries: int = 0
    carry_m: float = 0.0
    top_speed: float = 0.0
    sprints: int = 0


@dataclass
class _Phase:
    active: bool = False
    last_start: float = -1e9


def _attacking_x(team: Side, period: int, x: float) -> float:
    attacks_right = (team == "H") == (period == 1)
    return x if attacks_right else PITCH_L - x


class FactEngine:
    def __init__(self, meta: MatchMeta):
        self.meta = meta
        self.names = {p.id: p.name for t in meta.teams.values() for p in t.players}
        self.team_names = {s: t.name for s, t in meta.teams.items()}
        self.t = 0.0
        self.last_t = 0.0
        self.clock = "1"
        self.period = 1
        self.stop1 = 120.0
        self.finished = False
        self.score = {"H": 0, "A": 0}
        self.was_behind = {"H": False, "A": False}
        self.team = {"H": TeamStats(), "A": TeamStats()}
        self.players: dict[str, PlayerStats] = {}
        self.poss: Side = "H"
        self.facts: list[Fact] = []
        self.wp_series: list[tuple[float, float, float, float]] = []
        self.heat = {s: [[0] * HEAT_COLS for _ in range(HEAT_ROWS)] for s in ("H", "A")}
        self._threat: dict[Side, deque[tuple[float, float]]] = {"H": deque(), "A": deque()}
        self._shots_win: dict[Side, deque[float]] = {"H": deque(), "A": deque()}
        self._poss_win: deque[tuple[float, Side, float]] = deque()
        self._turnovers: deque[float] = deque()
        self._phase = {"H": _Phase(), "A": _Phase()}
        self._sprint_last: dict[str, float] = {}
        self._last_wp = -1e9

    # ---------- helpers ----------
    def _pstats(self, pid: str | None) -> PlayerStats | None:
        if pid is None:
            return None
        return self.players.setdefault(pid, PlayerStats())

    def _remaining_s(self) -> float:
        if self.finished:
            return 0.0
        return max(0.0, 5400 + self.stop1 + 240 - self.t)

    def _elapsed_s(self) -> float:
        return max(1.0, self.t - (self.stop1 if self.period == 2 else 0.0))

    def _probs(self, hg: int | None = None, ag: int | None = None,
               reds: dict[str, int] | None = None) -> tuple[float, float, float]:
        reds = reds or {s: self.team[s].red for s in ("H", "A")}
        rem = self._remaining_s()
        lam = {
            s: rate_per_s(self.team[s].xg, self._elapsed_s()) * rem
            * red_multiplier(reds[s], reds["A" if s == "H" else "H"])
            for s in ("H", "A")
        }
        return win_probs(self.score["H"] if hg is None else hg,
                         self.score["A"] if ag is None else ag, lam["H"], lam["A"])

    def _add_fact(self, ev: Event, kind: str, importance: float, side: Side | None = None,
                  player: str | None = None, data: dict | None = None,
                  tags: list[str] | None = None) -> Fact:
        d = dict(data or {})
        if player:
            d.setdefault("player_name", self.names.get(player, player))
        if side:
            d.setdefault("team", self.team_names[side])
        fact = Fact(id=len(self.facts), t=ev.t, clock=ev.clock, kind=kind, side=side, player=player,
                    importance=round(max(0.0, min(1.0, importance)), 3), data=d,
                    evidence=[ev.i], tags=tags or [])
        self.facts.append(fact)
        return fact

    def _prune(self) -> None:
        cut = self.t - WINDOW_S
        for s in ("H", "A"):
            q = self._threat[s]
            while q and q[0][0] < cut:
                q.popleft()
            sq = self._shots_win[s]
            while sq and sq[0] < cut:
                sq.popleft()
        while self._poss_win and self._poss_win[0][0] < cut:
            self._poss_win.popleft()
        while self._turnovers and self._turnovers[0] < self.t - 180:
            self._turnovers.popleft()

    def _heat(self, ev: Event) -> None:
        col = min(HEAT_COLS - 1, int(ev.x / (PITCH_L / HEAT_COLS)))
        row = min(HEAT_ROWS - 1, int(ev.y / (PITCH_W / HEAT_ROWS)))
        self.heat[ev.team][row][col] += 1

    # ---------- derived state ----------
    def momentum(self) -> float:
        h = sum(w for _, w in self._threat["H"])
        a = sum(w for _, w in self._threat["A"])
        return round((h - a) / (h + a + 1.0), 3)

    def rhythm(self) -> str:
        per_min = len(self._turnovers) / 3.0
        return "chaotic" if per_min >= 3.5 else "controlled" if per_min <= 1.5 else "balanced"

    def win_probs(self) -> tuple[float, float, float]:
        """(home, draw, away) win probability for the match as ingested so far."""
        return self._probs()

    def snapshot(self) -> dict:
        total = max(1.0, self.team["H"].poss_s + self.team["A"].poss_s)
        stats = {}
        for s in ("H", "A"):
            t = self.team[s]
            stats[s] = {
                "possession": round(100 * t.poss_s / total), "shots": t.shots, "on_target": t.on_target,
                "xg": round(t.xg, 2), "passes": t.passes,
                "pass_acc": round(100 * t.passes_ok / t.passes) if t.passes else 0,
                "corners": t.corners, "fouls": t.fouls, "yellow": t.yellow, "red": t.red,
                "tackles": t.tackles,
            }
        h, d, a = self._probs()
        return {"t": self.t, "clock": self.clock, "period": self.period,
                "score": [self.score["H"], self.score["A"]], "stats": stats,
                "momentum": self.momentum(), "rhythm": self.rhythm(),
                "win": [round(h, 3), round(d, 3), round(a, 3)]}

    def so_far(self, upto_t: float, clock: str) -> dict:
        """The match so far as of match second `upto_t` (a moment's time, its own goal included), from the facts of the events
        ingested: the booth's memory of a broadcast it may have joined late. Minute, score, every goal (minute, scorer, team, the score it
        made), how the score got here in one plain sentence, red cards, and `late` from the 80th minute. Pure: the same events give the
        same block, so a prompt built from it keeps its cache key."""
        score = {"H": 0, "A": 0}
        goals, story = [], []
        led_since: dict[str, str] = {}  # side -> the minute of the goal that put it in front, while it still is
        for f in self.facts:
            if f.t > upto_t + 1e-9 or f.kind != "goal" or f.side is None:
                continue
            side, other = f.side, "A" if f.side == "H" else "H"
            before = score[side] - score[other]
            score[side] += 1
            made = f"{score['H']}-{score['A']}"
            who = (self.names.get(f.player or "", "") or "").split()[-1:] or ["?"]
            scorer, team, minute = who[0], self.team_names[side], f.clock
            goals.append({"minute": minute, "scorer": scorer, "team": team, "made_it": made})
            what = ("took the lead" if score["H"] + score["A"] == 1 else "equalised" if before == -1 else
                    "went ahead" if before == 0 else "made it" if before > 0 else "pulled one back")
            story.append(f"{team} {what} {made} through {scorer} ({minute}')")
            if before == 0:
                led_since[side] = minute
            elif before == -1:
                led_since.pop(other, None)
        h, a = score["H"], score["A"]
        if h == a == 0:
            state = "Still goalless."
        elif h == a:
            state = f"Level since {goals[-1]['minute']}'."
        else:
            lead = "H" if h > a else "A"
            state = f"{self.team_names[lead]} have led since {led_since.get(lead, goals[-1]['minute'])}'."
        out: dict = {"minute": clock, "score_home_away": f"{h}-{a}", "goals": goals, "how_it_got_here": " ".join([*(s + "." for s in story), state])}
        reds = [{"minute": f.clock, "player": (self.names.get(f.player or "", "") or "?").split()[-1], "team": self.team_names[f.side]}
                for f in self.facts if f.kind == "red_card" and f.t <= upto_t + 1e-9 and f.side is not None]
        if reds:
            out["red_cards"] = reds
        if minute_of(clock) >= 80:
            out["late"] = True
        return out

    def player_stats(self, pid: str) -> dict:
        p = self.players.get(pid, PlayerStats())
        return {"id": pid, "name": self.names.get(pid, pid), "passes": p.passes, "passes_ok": p.passes_ok,
                "shots": p.shots, "on_target": p.on_target, "xg": round(p.xg, 2), "goals": p.goals,
                "tackles": p.tackles, "interceptions": p.interceptions, "fouls": p.fouls,
                "carry_m": round(p.carry_m), "top_speed": round(p.top_speed, 1), "sprints": p.sprints}

    # ---------- ingestion ----------
    def ingest(self, ev: Event) -> list[Fact]:
        before = len(self.facts)
        dt = ev.t - self.last_t
        if 0 <= dt < 120:
            self.team[self.poss].poss_s += dt
            self._poss_win.append((ev.t, self.poss, dt))
        self.last_t = self.t = ev.t
        self.clock, self.period = ev.clock, ev.period
        side = ev.team
        ts, ps = self.team[side], self._pstats(ev.player)
        ax = _attacking_x(side, ev.period, ev.x)
        aex = _attacking_x(side, ev.period, ev.end_x) if ev.end_x is not None else ax

        if ev.type in (EventType.PASS, EventType.CARRY, EventType.SHOT, EventType.KICKOFF):
            self._heat(ev)
            self.poss = side

        if ev.type == EventType.PASS:
            ts.passes += 1
            ps.passes += 1
            if ev.outcome == "complete":
                ts.passes_ok += 1
                ps.passes_ok += 1
                if aex >= 70 > ax:
                    self._threat[side].append((ev.t, 0.25))
            if ev.set_piece == "corner":
                ts.corners += 1
                self._threat[side].append((ev.t, 0.6))
        elif ev.type == EventType.CARRY:
            ps.carries += 1
            ps.carry_m += ev.length or 0.0
            speed = ev.speed or 0.0
            ps.top_speed = max(ps.top_speed, speed)
            if aex >= 70 > ax:
                self._threat[side].append((ev.t, 0.2))
            if speed >= SPRINT_KMH and ev.t - self._sprint_last.get(ev.player or "", -1e9) > 600:
                self._sprint_last[ev.player or ""] = ev.t
                ps.sprints += 1
                self._add_fact(ev, "sprint", 0.10, side, ev.player, {"speed_kmh": round(speed, 1)})
        elif ev.type == EventType.SHOT:
            self._on_shot(ev, side, ts, ps)
        elif ev.type == EventType.TACKLE:
            ts.tackles += 1
            ps.tackles += 1
        elif ev.type == EventType.INTERCEPTION:
            ts.interceptions += 1
            ps.interceptions += 1
        elif ev.type == EventType.FOUL:
            ts.fouls += 1
            ps.fouls += 1
        elif ev.type == EventType.CARD:
            self._on_card(ev, side, ts)
        elif ev.type == EventType.PRESSURE:
            if ax >= 50:
                self._threat[side].append((ev.t, 0.05))
        elif ev.type == EventType.POSSESSION_CHANGE:
            self.poss = side
            if ev.reason in ("interception", "tackle"):
                self._turnovers.append(ev.t)
        elif ev.type == EventType.PERIOD_END:
            if ev.outcome == "half_time":
                self.stop1 = ev.t - 2700.0
            else:
                self.finished = True
        self._prune()
        self._update_phase(ev)
        self._sample_win(ev)
        return self.facts[before:]

    def _on_shot(self, ev: Event, side: Side, ts: TeamStats, ps: PlayerStats) -> None:
        xg = ev.xg or 0.0
        opp: Side = "A" if side == "H" else "H"
        ts.shots += 1
        ts.xg += xg
        ps.shots += 1
        ps.xg += xg
        self._shots_win[side].append(ev.t)
        self._threat[side].append((ev.t, 1.0 + 4.0 * xg))
        if ev.outcome in ("goal", "saved"):
            ts.on_target += 1
            ps.on_target += 1
        base = {"xg": round(xg, 2), "shot_speed_kmh": ev.shot_speed or 0, "body_part": ev.body_part or "foot"}

        if ev.outcome == "goal":
            before = self._probs()
            hg, ag = self.score["H"], self.score["A"]
            own_before, opp_before = self.score[side], self.score[opp]
            self.score[side] += 1
            ps.goals += 1
            after = self._probs()
            delta = abs(expected_points(after, side) - expected_points(before, side))
            tags = []
            if hg + ag == 0:
                tags.append("opener")
            if self.score[side] == self.score[opp]:
                tags.append("equaliser")
            elif own_before == opp_before:
                tags.append("go_ahead")
                if self.was_behind[side]:
                    tags.append("comeback")
            if minute_of(ev.clock) >= 80:
                tags.append("late")
            self.was_behind["H"] |= self.score["H"] < self.score["A"]
            self.was_behind["A"] |= self.score["A"] < self.score["H"]
            self._add_fact(ev, "goal", max(0.25, delta / 2.0), side, ev.player,
                           {**base, "score": f"{self.score['H']}-{self.score['A']}",
                            "win_before": round(before[0] if side == "H" else before[2], 3),
                            "win_after": round(after[0] if side == "H" else after[2], 3)}, tags)
            return
        if xg >= BIG_CHANCE_XG:
            now = expected_points(self._probs(), side)
            if_scored = expected_points(
                self._probs(self.score["H"] + (side == "H"), self.score["A"] + (side == "A")), side)
            leverage = abs(if_scored - now)
            imp = xg * leverage / 1.2
            if ev.outcome == "saved":
                self._add_fact(ev, "big_save", max(0.15, imp), opp, ev.keeper, {**base, "shooter": self.names.get(ev.player or "", "")})
            elif imp >= 0.12:
                self._add_fact(ev, "big_chance", imp, side, ev.player, {**base, "outcome": ev.outcome or ""})
        if ps.shots in (3, 5):
            self._add_fact(ev, "shot_milestone", 0.25, side, ev.player, {"shots": ps.shots})

    def _on_card(self, ev: Event, side: Side, ts: TeamStats) -> None:
        if ev.card == "yellow":
            ts.yellow += 1
            self._add_fact(ev, "yellow_card", 0.15, side, ev.player)
            return
        before = self._probs()
        ts.red += 1
        after = self._probs()
        delta = abs(expected_points(after, side) - expected_points(before, side))
        self._add_fact(ev, "red_card", max(0.6, delta / 2.0), side, ev.player,
                       {"reason": ev.reason or "", "men_left": 11 - ts.red})

    def _update_phase(self, ev: Event) -> None:
        th = {s: sum(w for _, w in self._threat[s]) for s in ("H", "A")}
        total = th["H"] + th["A"]
        if total < 3.0 or ev.t < 240:
            return
        for s in ("H", "A"):
            share = th[s] / total
            ph = self._phase[s]
            if not ph.active and share >= 0.75 and ev.t - ph.last_start > 240:
                ph.active, ph.last_start = True, ev.t
                psum = sum(d for _, side, d in self._poss_win if side == s)
                ptot = sum(d for _, _, d in self._poss_win) or 1.0
                self._add_fact(ev, "momentum_phase", 0.35 + 0.25 * min(1.0, total / 8.0), s, None, {
                    "share": round(share, 2), "shots": len(self._shots_win[s]),
                    "possession": round(100 * psum / ptot), "minutes": 5})
            elif ph.active and share < 0.55:
                ph.active = False

    def _sample_win(self, ev: Event) -> None:
        important = bool(self.facts) and self.facts[-1].evidence == [ev.i] and self.facts[-1].kind in ("goal", "red_card")
        if ev.t - self._last_wp >= 30 or important or self.finished:
            h, d, a = self._probs()
            self.wp_series.append((round(ev.t, 1), round(h, 3), round(d, 3), round(a, 3)))
            self._last_wp = ev.t


def analyse(meta: MatchMeta, events: list[Event]) -> FactEngine:
    engine = FactEngine(meta)
    for ev in events:
        engine.ingest(ev)
    return engine
