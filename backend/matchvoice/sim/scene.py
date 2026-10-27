"""A generated live scene: the 89' winner of comeback-135, played differently on every "New run".

The plain simulation (sim/engine.py) is a possession chain with no players off the ball, so its late phase of comeback-135 sticks the
ball to the corner flag for half a minute. The public demo's "New run" needs a phase a football viewer finds logical. `ScenePlan`
hooks into `Sim.step` at the first dead ball after `fork_after` (the Tamsworth goal kick at 5408.6, event 1836) and plays the rest of
the scene itself, through the Sim's own `emit`, `_flip`, `_shot` and `_kickoff`, so event indices, the score, truth, the clock and the
posture schedule stay one consistent match:

  A  Tamsworth's goal kick and build-up from the back (3 to 8 passes, at least one back or square, a carry now and then, a switch
     sometimes), Wexmoor pressing (`pressure` events by the nearest presser, passes under pressure);
  B  the turnover: an interception in midfield, or a high regain near Tamsworth's box after a press; sometimes a counter-press loss
     and regain 3 to 6 s later (always interceptions: the page has no tackle);
  C  Wexmoor's attack and the winner, one finish of five: counter (through ball), patient (switch, carry, cross, header),
     cutback, edge (one-two and a shot from 16 to 22 m), overlap (the full back's cross).

Receivers are picked first, then the pass end is where the demo page already draws that player (sim/sceneshape.py) plus a run of
the player's role. Passes are 6 to 50 m with flight times from their length; nothing sits on the touchline or byline. The scene
draws from its own stream (`Random(f"{arc}-{seed}:scene:{variant}:{retry}:{k}")`) and gives the Sim its own generator back after
the kick-off, so the match after the scene is a plain simulation again. Nothing here runs unless a ScenePlan is passed to Sim.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from ..schema import EventType, MatchMeta, TruthItem
from .sceneshape import clamp, defend_spot, hash01, mirror, shape_spot
from .micro.enrich import CROSS_MIN_LEN_M

X_MIN, X_MAX, Y_MIN, Y_MAX = 4.0, 101.0, 3.0, 65.0
BOX_X, BOX_Y0, BOX_Y1 = 105 - 16.5, 34 - 20.16, 34 + 20.16
SIX_Y0, SIX_Y1 = 34 - 9.16, 34 + 9.16
PATTERNS = ("counter", "patient", "cutback", "edge", "overlap")
FINAL_TYPE = {"counter": "through", "patient": "cross", "cutback": "cut_back", "overlap": "cross"}  # enrich pass_type of the final ball
MAX_K = 40
COUNTER_PRESS_P = 0.0  # a mid turnover lost and won back 3 to 6 s later: off for the demo (three turnovers in 7 s swung the whole board)
ONSIDE_GAP, ONSIDE_STAGGER = 0.6, 1.6  # = mock4: the page holds a player off the ball 0.6 m plus his own 0 to 1.6 m behind the line
RUN_V = 8.5  # m/s a receiver held on the line covers between the kick and the ball's arrival (the page caps every player at 10)
LEAD_REACH = 13.0  # m a receiver covers before the kick (the page's run cue: up to 2 s at 6.5 m/s)


class Fail(Exception):
    """This draw cannot make a scene that keeps every rule: the next draw is tried."""


class TooShort(Fail):
    """The play ends before the goal window even with the slowest holds: the same draw is tried with more passes."""


@dataclass
class Item:
    kind: str  # pass | carry | press | win | shot
    side: str
    pid: str
    x0: float
    y0: float
    x1: float = 0.0
    y1: float = 0.0
    rid: str | None = None
    ok: bool = True
    v: float = 0.0  # m/s: ball speed of a pass, player speed of a carry
    under: bool = False
    set_piece: str | None = None
    hold: float = 0.0  # base hold of the player who has the ball next (receiver, ball winner)
    gap: float = 0.0  # a pass: arrival slack; a win: the time from the kick to the interception
    fixed: bool = False  # a first-time touch: the hold is not scaled
    min_hold: float = 0.0
    header: bool = False
    pre: float = 0.0  # a press: seconds before the pass it belongs to
    tag: str = ""
    t: float = 0.0

    @property
    def length(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)


def ground_speed(length: float) -> float:
    return clamp(9 + .3 * length, 11, 22)


@dataclass
class ScenePlan:
    """The live scene of one New run. `variant` picks the play; the same variant gives the same events."""
    variant: int
    side: str = "H"  # the side that scores the winner
    fork_after: float = 5400.0
    kick_at: tuple[float, float] = (5416.0, 5417.5)
    goal_window: tuple[float, float] = (5462.0, 5471.5)
    retry: int = 0
    base_meta: MatchMeta | None = None  # the plain match's meta: the opponent's planned last line for a through ball
    played: bool = False
    info: dict = field(default_factory=dict)

    def should_fork(self, sim) -> bool:
        return (not self.played and sim.t >= self.fork_after and sim.set_piece == "goal_kick" and sim.poss != self.side
                and any(b.kind == "goal" and b.side == self.side for _, b in sim.pending))

    def play(self, sim) -> None:
        self.played = True
        saved = sim.rng
        i = next(n for n, (_, b) in enumerate(sim.pending) if b.kind == "goal" and b.side == self.side)
        _, beat = sim.pending.pop(i)  # the scene scores this beat; left in the list it would add a second goal after the scene
        sim.set_piece = None
        key = f"{sim.arc.name}-{sim.seed}:scene:{self.variant}:{self.retry}"
        items = None
        macro = draw_macro(random.Random(f"{key}:macro"))
        for k in range(MAX_K):
            extra = 0
            while extra <= 4:  # a draw that ends too early gets more passes (the same draw with one more each time)
                planner = _Planner(sim, self, random.Random(f"{key}:{k}:{extra}"), extra, macro)
                try:
                    items = planner.build()
                except TooShort:
                    extra += 1
                    continue
                except Fail:
                    pass
                break
            if items is not None:
                self.info.update(planner.info, k=k, extra=extra)
                break
        if items is None:  # the caller falls back to a frozen variant (tests pin that this stays rare)
            self.info["failed"] = True
        sim.rng = random.Random(f"{key}:commit")
        if items is not None:
            _commit(sim, items, beat)
        else:
            sim.t = self.kick_at[0]
            sim.forced, sim.forced_beat, sim.forced_since = beat.side, beat, sim.t  # the plain scripted attack as a last resort
        sim.rng = saved


def draw_macro(r: random.Random) -> tuple[str, str, bool]:
    """The shape of the scene, drawn once per variant: the turnover, the finish and a counter-press. Every retry keeps them."""
    turnover = "high" if r.random() < .4 else "mid"
    pats = {"mid": {"counter": .22, "patient": .18, "cutback": .2, "edge": .22, "overlap": .18},
            "high": {"cutback": .33, "edge": .37, "overlap": .3}}[turnover]
    pattern = r.choices(list(pats), list(pats.values()))[0]
    return turnover, pattern, turnover == "mid" and r.random() < COUNTER_PRESS_P


class _Planner:
    def __init__(self, sim, plan: ScenePlan, rng: random.Random, extra: int = 0, macro: tuple | None = None):
        self.sim, self.plan, self.r, self.extra = sim, plan, rng, extra
        self.macro = macro or draw_macro(random.Random(0))
        self.H = plan.side
        self.A = "A" if plan.side == "H" else "H"
        self.items: list[Item] = []
        self.info: dict = {}
        ctx = None
        if plan.base_meta is not None:
            from .micro.enrich import Context
            ctx = Context(plan.base_meta, [])
        self.ctx = ctx

    # ---------- geometry ----------
    def team(self, side):
        return self.sim.teams[side]

    def p(self, pid):
        for t in self.sim.teams.values():
            for pl in t.players:
                if pl.id == pid:
                    return pl
        raise KeyError(pid)

    def spot(self, side, pl, ball, pw=1.0):
        t = self.team(side)
        return shape_spot(t.formation, t.players.index(pl), pl.group, pl.number, side, ball, pw)

    def dspot(self, side, pl, ball_att, po=0.0):
        """A defender of `side`, the ball in the attacker's frame; returned in the attacker's frame."""
        t = self.team(side)
        return defend_spot(t.formation, t.players.index(pl), pl.group, pl.number, side, ball_att, po)

    def prev_ball(self, side):
        """Where the ball was played from before (the last pass, carry or ball win), in `side`'s frame; None at the start."""
        for it in reversed(self.items):
            if it.kind in ("pass", "carry", "win"):
                return (it.x0, it.y0) if it.side == side else mirror((it.x0, it.y0))
        return None

    def onside_x(self, side, ball):
        """The offside line for `side` at a kick from `ball` (x in `side`'s frame): the second-last opponent (the keeper counts) as
        the page draws the defending side, the ball or the halfway line, whichever is nearest the goal. The page's defenders react
        about a second late (to the ball halfway back to where it was played from before), so the higher of the two lines counts."""
        dside = "A" if side == "H" else "H"
        prev = self.prev_ball(side)
        lines = []
        for b in (ball,) if prev is None else (ball, ((ball[0] + prev[0]) / 2, (ball[1] + prev[1]) / 2)):
            xs = sorted((self.dspot(dside, pl, b, po=1.0)[0] for pl in self.team(dside).active()), reverse=True)
            lines.append(xs[1])
        return max(min(lines), ball[0], 52.5)

    def onside_reach(self, side, ball, rec, end, v, ox=None, s=None):
        """True when `rec` can stay onside until the kick and still meet the ball at `end`: the page holds him on the line until the
        ball is played, his own ONSIDE_GAP plus stagger behind it (mock4 `onside`), so what lies beyond is run after the kick."""
        ox = (self.onside_x(side, ball) if ox is None else ox) - ONSIDE_GAP - ONSIDE_STAGGER * hash01(rec.number + (0 if side == "H" else 50), 33)
        s = self.spot(side, rec, ball) if s is None else s
        on = (min(s[0], ox), s[1])
        flight = math.hypot(end[0] - ball[0], end[1] - ball[1]) / v
        after = max(end[0] - ox, math.hypot(end[0] - on[0], end[1] - on[1]) - LEAD_REACH)
        return after <= RUN_V * flight + 1.0

    def nearest_def(self, dside, ball_att, exclude=()):
        best = None
        for pl in self.team(dside).active():
            if pl.group == "GK" or pl.id in exclude:
                continue
            d = self.dspot(dside, pl, ball_att)
            dist = math.hypot(d[0] - ball_att[0], d[1] - ball_att[1])
            if best is None or dist < best[0]:
                best = (dist, pl, d)
        return best

    def presser(self, dside, ball_att, exclude=()):
        """Who of `dside` closes the ball down (ball in the attacker's frame): one of the few nearest where the page draws them, by role
        and flank. A striker presses a centre back, a wide player or full back takes the ball on his own flank, a centre back stays home."""
        cands = []
        for pl in self.team(dside).active():
            if pl.group == "GK" or pl.id in exclude:
                continue
            d = self.dspot(dside, pl, ball_att)
            cands.append((math.hypot(d[0] - ball_att[0], d[1] - ball_att[1]), pl))
        if not cands:
            return None
        near = min(c[0] for c in cands)
        px, py = mirror(ball_att)  # the ball in the presser's own frame
        wide = abs(py - 34) > 12
        right = py >= 34  # y grows to the right as a side attacks
        best = None
        for dist, pl in cands:
            if dist > near + 8:
                continue
            pos = pl.pos
            pen = 0.0
            if pos == "ST":
                pen = (3.0 if wide else 0.0) + (6.0 if px < 50 else 0.0)
            elif pos in ("RM", "RW", "RB", "LM", "LW", "LB"):
                own = pos.startswith("R") == right
                pen = (-1.5 if own else 6.0) if wide else 1.0
                if pos in ("RB", "LB") and px > 70:
                    pen += 3.0
            elif pos == "CB":
                pen = 4.0 if px > 40 else 0.0
            score = dist + pen + self.r.uniform(0, 2.5)
            if best is None or score < best[0]:
                best = (score, pl)
        return best[1]

    def line(self, ax0, t=5440.0):
        if self.ctx is None:
            return 66.0
        v = self.ctx.opp_line_ax(self.H, ax0, t)
        return 66.0 if v is None else v

    def run_of(self, pl, ball, spot, intent):
        r = self.r
        pos = pl.pos
        if intent == "gk_short":
            return r.uniform(0, 4), (1 if spot[1] >= 34 else -1) * r.uniform(4, 9)
        if pos == "CB":
            return r.uniform(-1, 2), (1 if spot[1] >= 34 else -1) * r.uniform(0, 3)
        if pos in ("RB", "LB"):
            if intent in ("overlap", "switch", "wide"):
                return r.uniform(10, 13), (1 if spot[1] >= 34 else -1) * r.uniform(0, 3)
            return r.uniform(1, 4), (1 if spot[1] >= 34 else -1) * r.uniform(0, 2)
        if pos in ("CM", "DM", "AM"):
            dx, dy = ball[0] - spot[0], ball[1] - spot[1]
            d = math.hypot(dx, dy) or 1.0
            m = r.uniform(2.5, 4.5) if pos != "AM" else r.uniform(1.5, 3)
            m = min(m, max(0.0, d - 7))
            return dx / d * m, dy / d * m
        if pos == "ST":
            if intent == "through":
                return r.uniform(6, 10), r.uniform(-2, 2)
            dx, dy = ball[0] - spot[0], ball[1] - spot[1]
            d = math.hypot(dx, dy) or 1.0
            m = min(r.uniform(1, 3), max(0.0, d - 8))
            return dx / d * m, dy / d * m
        if intent in ("switch", "wide"):  # a winger holds the width for the ball across
            return r.uniform(2, 6), (1 if spot[1] >= 34 else -1) * r.uniform(8, 14)
        return r.uniform(1, 3), 0.0  # wide midfielders and wingers

    def options(self, side, holder, ball, intent, lo=6.0, hi=50.0, xmin=X_MIN, xmax=X_MAX, pool=None, gk=False):
        out = []
        prev = next((it for it in reversed(self.items) if it.kind == "pass" and it.side == side and it.ok and it.rid == holder.id), None)
        ox = self.onside_x(side, ball)
        for pl in self.team(side).active():
            if pl is holder or (pl.group == "GK" and not gk) or (pool is not None and pl.id not in pool):
                continue
            s = self.spot(side, pl, ball)
            rx, ry = self.run_of(pl, ball, s, intent)
            ex = s[0] + rx + self.r.gauss(0, 1.5)
            lo_x, hi_x = max(X_MIN, xmin), min(X_MAX, xmax)
            if ex > hi_x + 3 or ex < lo_x - 3:
                continue  # that player is not where this pass can go; the page would show him sprinting back for it
            ex = clamp(ex, lo_x, hi_x)
            ey = clamp(s[1] + ry + self.r.gauss(0, 1.5), Y_MIN, Y_MAX)
            L = math.hypot(ex - ball[0], ey - ball[1])
            dx = ex - ball[0]
            if not lo <= L <= hi:
                continue
            if intent == "forward" and dx < 4:
                continue
            if intent == "recycle" and not -12 <= dx <= 2:
                continue
            if intent == "back" and not -30 <= dx <= -6:
                continue
            if intent == "any" and dx < -15:
                continue
            if intent == "square" and dx < -3:
                continue
            if intent == "switch" and abs(ey - ball[1]) < 40:
                continue
            if not self.onside_reach(side, ball, pl, (ex, ey), 19.0 if intent in ("switch", "long") else ground_speed(L), ox, s):
                continue  # he would have to stand offside to get there
            w = math.exp(-abs(L - 16) / 10)
            if intent in ("forward", "any"):
                w *= (1 + dx / 15) if dx > 0 else (.4 if dx < -3 else 1.0)
            if prev is not None and intent != "switch":
                if pl.id == prev.pid:
                    w *= .12  # straight back to the passer: a one-two, rare in a build-up
                pdy = prev.y1 - prev.y0
                if abs(pdy) > 8 and abs(ey - ball[1]) > 8 and (ey - ball[1]) * pdy < 0:
                    w *= .25  # the ball goes back across the way it came: the whole shape would swing back
            out.append((w, pl, (ex, ey)))
        return out

    def choose(self, opts, why: str = ""):
        if not opts:
            raise Fail(f"no receiver {why}")
        w = [o[0] for o in opts]
        return self.r.choices(opts, w)[0]

    # ---------- items ----------
    def hold(self):
        return self.r.uniform(.9, 2.0)

    def first(self):
        return self.r.uniform(.35, .55)

    def pass_(self, side, holder, ball, rec, end, v=None, under=False, set_piece=None, first=False, tag="", lofted=False):
        L = math.hypot(end[0] - ball[0], end[1] - ball[1])
        if not 6 <= L <= 50:
            raise Fail("pass length")
        if v is None:
            v = self.r.uniform(15, 19) if lofted else ground_speed(L)
        if not self.onside_reach(side, ball, rec, end, v):
            raise Fail("offside: the run cannot wait for the kick")
        it = Item("pass", side, holder.id, ball[0], ball[1], end[0], end[1], rid=rec.id, v=v, under=under, set_piece=set_piece,
                  hold=self.first() if first else self.hold(), gap=self.r.uniform(.15, .45), fixed=first, tag=tag,
                  min_hold=1.6 if L >= 25 and not first else 0.0)  # after a long ball the page's shape needs a moment to catch up
        self.items.append(it)
        return rec, end

    def press(self, side, ball, n=1):
        """Pressure on the holder of `side` by the nearest presser (n = 1 or 2 events). Returns True when pressed."""
        dside = "A" if side == "H" else "H"
        used = []
        for _ in range(n):
            pl = self.presser(dside, ball, used)
            if pl is None:
                break
            used.append(pl.id)
            self.items.append(Item("press", dside, pl.id, *mirror(ball), pre=self.r.uniform(.3, .9)))
        return bool(used)

    def carry(self, side, holder, ball, end, under=False, v=None):
        L = math.hypot(end[0] - ball[0], end[1] - ball[1])
        if not 6 <= L <= 18:
            raise Fail("carry length")
        self.items.append(Item("carry", side, holder.id, ball[0], ball[1], end[0], end[1], v=v or self.r.uniform(4.5, 7.5), under=under,
                               gap=self.r.uniform(.2, .5)))
        return end

    def intercept(self, side, holder, ball, target_end, xrange_new, under=False, exclude=(), min_len=6.0, max_gap=7.0):
        """`side` plays towards `target_end`; the other side cuts it out. Returns (taker, point in the taker's frame)."""
        new = "A" if side == "H" else "H"
        high = xrange_new[0] >= 60  # a regain near the other box: the front players win it; in midfield the midfielders and full backs do
        pens = ({"ST": 0.0, "AM": 0.0, "RM": .5, "LM": .5, "RW": .5, "LW": .5, "CM": 1.0, "DM": 2.0, "RB": 3.0, "LB": 3.0, "CB": 6.0} if high else
                {"ST": 6.0, "AM": 1.5, "CM": -1.5, "DM": -1.5, "RM": .5, "LM": .5, "RW": 1.0, "LW": 1.0, "RB": .5, "LB": .5, "CB": 2.5})
        reach = {} if high else {"CM": 2.5, "DM": 2.5}  # a central midfielder steps further across to cut a pass out
        best = None
        for f in (.4, .5, .6, .7, .8, .9):
            P = (ball[0] + (target_end[0] - ball[0]) * f, ball[1] + (target_end[1] - ball[1]) * f)
            for pl in self.team(new).active():
                if pl.group == "GK" or pl.id in exclude:
                    continue
                D = self.dspot(new, pl, P)
                Q = (P[0] + .5 * (D[0] - P[0]), P[1] + .5 * (D[1] - P[1]))
                Qn = mirror(Q)
                if not (xrange_new[0] <= Qn[0] <= xrange_new[1]) or not (X_MIN <= Q[0] <= X_MAX and Y_MIN <= Q[1] <= Y_MAX):
                    continue
                L = math.hypot(Q[0] - ball[0], Q[1] - ball[1])
                if L < min_len or L > 40:
                    continue
                gapd = math.hypot(D[0] - Q[0], D[1] - Q[1])
                if gapd > max_gap + reach.get(pl.pos, 0.0):
                    continue
                score = gapd + pens.get(pl.pos, 1.0) + self.r.uniform(0, 1.0)
                if best is None or score < best[0]:
                    best = (score, pl, Q)
        if best is None:
            raise Fail("no interceptor")
        _, pl, Q = best
        L = math.hypot(Q[0] - ball[0], Q[1] - ball[1])
        self.items.append(Item("pass", side, holder.id, ball[0], ball[1], Q[0], Q[1], ok=False, v=ground_speed(L), under=under))
        self.items.append(Item("win", new, pl.id, *mirror(Q), hold=self.r.uniform(.9, 1.5), gap=self.r.uniform(.35, .55), min_hold=1.3))
        return pl, mirror(Q)

    # ---------- phases ----------
    def build(self) -> list[Item]:
        r = self.r
        H, A = self.H, self.A
        turnover, pattern, b2 = self.macro
        if turnover == "high":  # a high regain is finished quickly: the extra time goes to Tamsworth's build-up
            n_a, n_c = r.randint(6, 9) + self.extra, r.randint(1, 2)
        else:
            n_a, n_c = r.randint(5, 8) + (self.extra + 1) // 2, r.randint(2, 5) + self.extra // 2
        self.info = {"turnover": turnover, "pattern": pattern, "counter_press": b2}

        # A: the goal kick
        gk = self.sim._keeper(self.team(A))
        ball = (5.0, 34.0)
        if r.random() < .6 or turnover == "high":
            opts = self.options(A, gk, ball, "gk_short", lo=10, hi=22, pool={p.id for p in self.team(A).players if p.pos == "CB"})
            w, rec, end = self.choose(opts)
            holder, ball = self.pass_(A, gk, ball, rec, end, set_piece="goal_kick")
        else:
            opts = self.options(A, gk, ball, "long", lo=30, hi=48,
                                pool={p.id for p in self.team(A).players if p.group in ("MID", "FWD") and p.pos != "DM"})
            w, rec, end = self.choose(opts)
            holder, ball = self.pass_(A, gk, ball, rec, end, set_piece="goal_kick", lofted=True)
        # A: build-up
        xmax = 55.0 if turnover == "high" else 66.0  # a high regain: Tamsworth get to the middle third, then a pressed ball back is cut out
        recycled = False
        switched = False
        for i in range(n_a):
            if turnover == "mid" and not switched and i >= 1 and r.random() < .2:
                opts = self.options(A, holder, ball, "switch", lo=40, hi=50, xmax=xmax)
                if opts:
                    w, rec, end = self.choose(opts)
                    holder, ball = self.pass_(A, holder, ball, rec, end, lofted=True, tag="switch")
                    switched = True
                    continue
            if holder.group in ("DEF", "MID") and r.random() < .2 and ball[0] < xmax - 12:
                end = (clamp(ball[0] + r.uniform(7, 13), X_MIN, xmax), clamp(ball[1] + r.gauss(0, 3), 6, 62))
                if 6 <= math.hypot(end[0] - ball[0], end[1] - ball[1]) <= 18:
                    ball = self.carry(A, holder, ball, end)
            need = not recycled and (i == n_a - 1 or r.random() < .3)
            intent = "recycle" if need else "forward"  # one ball back in the build-up: more and the whole board swings back and forth
            under = False
            if r.random() < (.45 if turnover == "high" else .25):
                under = self.press(A, ball, 1 + (r.random() < .35))
            opts = self.options(A, holder, ball, intent, lo=7, hi=38, xmax=xmax)
            if not opts and intent == "forward":
                opts = self.options(A, holder, ball, "square", lo=7, hi=38, xmax=xmax)  # across before back
            if not opts:
                opts = self.options(A, holder, ball, "any", lo=7, hi=38, xmax=xmax)
            w, rec, end = self.choose(opts)
            if end[0] - ball[0] <= 2:
                recycled = True
            holder, ball = self.pass_(A, holder, ball, rec, end, under=under)
        if not recycled:
            raise Fail("no recycle pass")
        if ball[0] < 30:
            raise Fail("build-up stayed deep")

        # B: the turnover
        if turnover == "high":
            self.press(A, ball, 1 + (r.random() < .5))
            opts = self.options(A, holder, ball, "back", lo=10, hi=34, pool={p.id for p in self.team(A).players if p.group == "DEF"})
            w, rec, end = self.choose(opts, "ball back")
            taker, ball = self.intercept(A, holder, ball, end, (66, 94), under=True, max_gap=9.0)
        else:
            pressed = any(it.kind == "press" for it in self.items)
            under = (not pressed or r.random() < .5) and self.press(A, ball, 1)
            opts = self.options(A, holder, ball, "forward", lo=12, hi=35)
            w, rec, end = self.choose(opts)
            taker, ball = self.intercept(A, holder, ball, end, (35, 50) if pattern == "counter" else (35, 62), under=under)
        holder = taker
        win_item = self.items[-1]
        if b2:
            opts = self.options(H, holder, ball, "forward", lo=12, hi=22)
            w, rec, end = self.choose(opts)
            taker2, ball = self.intercept(H, holder, ball, end, (35, 75), min_len=9, exclude=(holder.id,))
            loss = self.items[-1]
            self.press(A, ball, 1)
            opts = self.options(A, taker2, ball, "any", lo=12, hi=22)
            w, rec, end = self.choose(opts)
            taker3, ball = self.intercept(A, taker2, ball, end, (35, 50) if pattern == "counter" else (35, 64), under=True, min_len=9,
                                          exclude=(holder.id, taker2.id))
            loss.min_hold = 2.6  # the regain comes 3 to 6 s after the loss
            holder = taker3
            win_item = self.items[-1]
            self.info["counter_press"] = True

        # C: the attack
        self.attack(pattern, holder, ball, n_c, win_item)
        return self.items

    def attack(self, pattern, holder, ball, n_c, win_item):
        r, H = self.r, self.H
        team = self.team(H)
        by_pos = lambda *ps: [p for p in team.active() if p.pos in ps]  # noqa: E731
        sts = by_pos("ST")
        mids = by_pos("CM", "DM", "AM")
        tav = team.players[6]  # H7, the playmaker of comeback-135 (any side: the seventh player)

        lo0 = max(30.0, ball[0] - 12)  # the attack does not go back further than this: after a high regain it stays high
        high = ball[0] >= 68

        def progress(n, xlo, xhi, pool=None, intent="forward", allow_switch=True):
            nonlocal holder, ball
            xlo, xhi = max(xlo, lo0), max(xhi, min(X_MAX - 10, lo0 + 20))
            allow_switch = allow_switch and not high
            for _ in range(n):
                if allow_switch and not self.info.get("switch") and r.random() < .35 and ball[0] < 75:
                    opts = self.options(H, holder, ball, "switch", lo=40, hi=50, xmax=xhi)
                    if opts:
                        w, rec, end = self.choose(opts)
                        holder, ball = self.pass_(H, holder, ball, rec, end, lofted=True, tag="switch")
                        self.info["switch"] = True
                        continue
                if r.random() < .25 and ball[0] < xhi - 12:
                    end = (clamp(ball[0] + r.uniform(7, 14), X_MIN, xhi), clamp(ball[1] + r.gauss(0, 4), 6, 62))
                    if 6 <= math.hypot(end[0] - ball[0], end[1] - ball[1]) <= 18:
                        ball = self.carry(H, holder, ball, end)
                under = r.random() < .4 and self.press(H, ball, 1)  # Tamsworth close the ball down: the pass goes under pressure
                opts = self.options(H, holder, ball, intent, lo=8, hi=35, xmin=xlo, xmax=xhi, pool=pool)
                if not opts:
                    opts = self.options(H, holder, ball, "any", lo=8, hi=35, xmin=max(xlo - 8, lo0), xmax=xhi, pool=pool)
                w, rec, end = self.choose(opts)
                holder, ball = self.pass_(H, holder, ball, rec, end, under=under)

        if pattern == "counter":
            if ball[0] < 44:  # a pass or two to get out of the press, then the ball in behind from about the halfway line
                progress(min(2, max(0, n_c - 1)), 30, 52, pool={p.id for p in mids + by_pos("RM", "LM", "RW", "LW")}, allow_switch=False)
            line = self.line(ball[0])
            if ball[0] >= line - 3:
                raise Fail("no room for a through ball")
            found = []
            for st in sts:
                if st is holder:
                    continue  # the ball winner does not play the ball in behind to himself
                s = self.spot(H, st, ball)
                lo_x, hi_x = max(line + 11, s[0] + 7), min(96.0, s[0] + 20)  # the run in behind: 7 to 20 m from where he stands
                if lo_x > hi_x:
                    continue
                for _ in range(10):
                    ex = r.uniform(lo_x, hi_x)
                    ey = clamp(s[1] + r.gauss(0, 4), 18, 50)
                    L = math.hypot(ex - ball[0], ey - ball[1])
                    if (40 <= L <= 50 and math.hypot(ex - s[0], ey - s[1]) <= 6.5 * (2 + L / ground_speed(L)) - 2
                            and self.onside_reach(H, ball, st, (ex, ey), ground_speed(L))):  # he waits on the line until the ball is played
                        found.append((st, ex, ey, L))
                        break
            if not found:
                raise Fail("through ball geometry")
            st, ex, ey, L = r.choice(found)
            holder, ball = self.pass_(H, holder, ball, st, (ex, ey), v=ground_speed(L), first=True, tag="final")
            end = (clamp(ball[0] + r.uniform(5, 9), 92, 98), clamp(34 + (ball[1] - 34) * .6 + r.gauss(0, 2), 26, 42))
            if math.hypot(end[0] - ball[0], end[1] - ball[1]) < 6:
                end = (min(99, ball[0] + 6.2), end[1])
            ball = self.carry(H, holder, ball, end, v=r.uniform(7, 8.5))  # in his stride, at a sprint
            self.shot(holder, ball, r.random() < .5)
        elif pattern in ("patient", "overlap"):
            flank = 1 if r.random() < .5 else -1  # +1: the right (y 68 side in the attacking frame)
            wide_pos = ("RM", "RW") if flank > 0 else ("LM", "LW")
            fb_pos = "RB" if flank > 0 else "LB"
            if pattern == "patient":
                # build on the far side, then the switch to the chosen flank
                progress(max(0, n_c - 1), 35, 72, pool={p.id for p in mids + by_pos("CB")}, allow_switch=False)
                far = {p.id for p in by_pos("RB" if flank < 0 else "LB", "LM" if flank > 0 else "RM", "LW" if flank > 0 else "RW")}
                opts = [o for o in self.options(H, holder, ball, "wide", lo=8, hi=35, xmin=35, xmax=72, pool=far)
                        if (o[2][1] - 34) * flank < -16]
                w, rec, end = self.choose(opts, "far side")
                holder, ball = self.pass_(H, holder, ball, rec, end)
                opts = [o for o in self.options(H, holder, ball, "switch", lo=40, hi=50, xmax=82,
                                                pool={p.id for p in by_pos(*wide_pos, fb_pos)}) if (o[2][1] - 34) * flank > 0]
                w, rec, end = self.choose(opts, "switch")
                holder, ball = self.pass_(H, holder, ball, rec, end, lofted=True, tag="switch")
                self.info["switch"] = True
                wide = holder
            else:
                progress(n_c, 35, 80, pool={p.id for p in mids + by_pos("CB", *wide_pos)}, allow_switch=True)
                wing = by_pos(*wide_pos)
                if not wing:
                    raise Fail("no winger")
                opts = [o for o in self.options(H, holder, ball, "any", lo=8, hi=32, xmax=84, pool={wing[0].id})]
                if holder in wing:
                    opts = []
                if holder not in wing:
                    w, rec, end = self.choose(opts)
                    holder, ball = self.pass_(H, holder, ball, rec, end)
                fb = by_pos(fb_pos)[0]
                s = self.spot(H, fb, ball)
                ex = min(93.0, ball[0] + r.uniform(6, 10))
                ey = (r.uniform(58, 63) if flank > 0 else r.uniform(5, 10))
                L = math.hypot(ex - ball[0], ey - ball[1])
                if math.hypot(ex - s[0], ey - s[1]) <= 6.5 * (2 + L / ground_speed(L)) - 2:
                    holder, ball = self.pass_(H, holder, ball, fb, (ex, ey), tag="overlap")
                    wide = fb
                else:  # the full back cannot get there in time: the winger goes on alone
                    wide = holder
                    self.info["overlap"] = "winger"
            if (ball[1] - 34) * flank < (20.5 if ball[0] >= 86 else 12):
                raise Fail("not wide")
            under = r.random() < .6 and self.press(H, ball, 1)  # the full back comes out to the winger, who carries on past him and crosses
            for _ in range(3):
                if ball[0] >= 86 and (ball[1] - 34) * flank >= 20.5:
                    break
                ex = min(r.uniform(86, 92), ball[0] + r.uniform(12, 18))
                ey = 34 + flank * clamp(abs(ball[1] - 34) + r.gauss(0, 1.5), 21, 29)
                ball = self.carry(H, wide, ball, (ex, ey))
            for _ in range(12):  # the target and the spot: 4.5 to 11 m out, anywhere across the six-yard box and a little wider
                target = r.choices([*sts, tav], [.36] * len(sts) + [.28])[0]  # the playmaker arrives late now and then
                sp = self.spot(H, target, ball)
                tx, ty = 105 - r.uniform(4.5, 11), sp[1] + r.gauss(0, 3)
                L = math.hypot(tx - ball[0], ty - ball[1])
                if (26.5 <= ty <= 41.5 and -2 <= tx - sp[0] <= 14 and L >= 15
                        and math.hypot(tx - sp[0], ty - sp[1]) <= 6.5 * (2 + L / 21) - 2
                        and self.onside_reach(H, ball, target, (tx, ty), 24.0)):  # onside at the cross, at the fastest ball below
                    break
            else:
                raise Fail("cross target")
            header = pattern == "patient" or r.random() < .5
            holder, ball = self.pass_(H, wide, ball, target, (tx, ty), v=r.uniform(19, 24), first=True, tag="final", under=under)
            self.shot(holder, ball, r.random() < .7, header=header)
        elif pattern == "cutback":
            pool = {p.id for p in mids + by_pos("RM", "LM", "RB", "LB", "CB", "RW", "LW")}
            progress(n_c, 45, 82, pool=pool)
            for _ in range(3):
                if ball[0] >= 72:
                    break
                progress(1, ball[0] + 4, 84, pool=pool, allow_switch=False)
            if not 72 <= ball[0] <= 88:
                raise Fail("cutback: no progress")
            for more in range(3):  # nobody can wait on the line and still reach the channel: one more pass up the pitch first
                flank = 1 if ball[1] >= 34 else -1
                runs = []
                for p in team.active():
                    if p is holder or p.pos not in (("RM", "RW", "RB") if flank > 0 else ("LM", "LW", "LB")) + ("ST",):
                        continue
                    sp = self.spot(H, p, ball)
                    for _ in range(3):
                        ex = r.uniform(96, 100.5)
                        ey = 34 + flank * r.uniform(10.5, 19.5)
                        L = math.hypot(ex - ball[0], ey - ball[1])
                        d = math.hypot(ex - sp[0], ey - sp[1])
                        wide = (ball[1] < BOX_Y0 or ball[1] > BOX_Y1) and ball[0] > 70
                        if (6 <= L <= (CROSS_MIN_LEN_M - 1 if wide else 32) and d <= 6.5 * (2 + L / ground_speed(L)) - 2  # a ball from out wide this long is a cross
                                and self.onside_reach(H, ball, p, (ex, ey), ground_speed(L))):
                            runs.append((1.0 / (1 + d / 15), p, (ex, ey)))  # the nearer runner is likelier, any who can make it may go
                            break
                if runs or more == 2 or ball[0] >= 84:
                    break
                progress(1, ball[0] + 3, 88, pool=pool, allow_switch=False)
            if not runs:
                raise Fail("ball into the channel")
            _, run, (ex, ey) = self.choose(runs)
            under = r.random() < .5 and self.press(H, ball, 1)
            holder, ball = self.pass_(H, holder, ball, run, (ex, ey), first=r.random() < .3, tag="channel", under=under)
            shots = []
            for shooter, wt in ((tav, 1.6), (team.players[7], 1.2), *((st, .7) for st in sts)):
                if shooter is holder or any(shooter is o[1] for o in shots):
                    continue
                sp = self.spot(H, shooter, ball)
                late = shooter.pos != "ST"  # a midfielder arrives late, at the penalty spot or the edge of the box
                sx = clamp(sp[0] + r.uniform(4, 8), 82 if late else 85, ball[0] - 3)
                sy = sp[1] + r.gauss(0, 2.5)
                L = math.hypot(sx - ball[0], sy - ball[1])
                if (26 <= sy <= 42 and 6 <= L <= (17 if late else 14) and math.hypot(sx - sp[0], sy - sp[1]) <= 6.5 * (2 + L / 15) - 2
                        and self.onside_reach(H, ball, shooter, (sx, sy), 17.0)):
                    shots.append((wt, shooter, (sx, sy)))
            if not shots or (all(o[1] is not tav for o in shots) and tav is not holder and r.random() < .35):
                raise Fail("cutback geometry")  # the playmaker is not there yet: most often the move is drawn again rather than finished without him
            _, shooter, (sx, sy) = self.choose(shots)
            holder, ball = self.pass_(H, holder, ball, shooter, (sx, sy), v=r.uniform(13, 17), first=True, tag="final")
            self.shot(holder, ball, r.random() < .7)
        else:  # edge
            if r.random() < .2 and team.players[7] in mids:
                tav = team.players[7]  # the other central midfielder arrives at the edge this time
            pool = {p.id for p in mids + by_pos("RM", "LM", "RB", "LB", "CB", "RW", "LW") if p is not tav}
            progress(max(1, n_c - 1), 45, 80, pool=pool)
            for _ in range(3):
                if ball[0] >= 58:
                    break
                progress(1, ball[0] + 4, 80, pool=pool, allow_switch=False)
            if ball[0] < 58:
                raise Fail("edge: no progress")
            w, rec, end = self.choose(self.options(H, holder, ball, "any", lo=7, hi=30, pool={tav.id}), "to the playmaker")
            holder, ball = self.pass_(H, holder, ball, tav, end)
            while ball[0] < 76:
                end = (min(84.0, ball[0] + r.uniform(9, 15)), clamp(ball[1] + (34 - ball[1]) * .3 + r.gauss(0, 2), 22, 46))
                ball = self.carry(H, tav, ball, end)
            if ball[0] > 86:
                raise Fail("edge: too deep")
            under = r.random() < .5 and self.press(H, ball, 1)
            st = r.choice(sts)
            s = self.spot(H, st, ball)
            ex, ey = clamp(ball[0] + r.uniform(6, 10), 82, 93), clamp(s[1] + r.gauss(0, 2), 24, 44)
            L = math.hypot(ex - ball[0], ey - ball[1])
            if not 6 <= L <= 14:
                raise Fail("one-two out")
            kick = ball
            holder, ball = self.pass_(H, tav, ball, st, (ex, ey), first=True, tag="one_two", under=under)
            for _ in range(10):
                sx = r.uniform(84, 89)
                sy = 34 + r.choice((-1, 1)) * r.uniform(2, 9)
                d = math.hypot(105 - sx, 34 - sy)
                L = math.hypot(sx - ball[0], sy - ball[1])
                if 16 <= d <= 22 and 6 <= L <= 12 and math.hypot(sx - kick[0], sy - kick[1]) <= 6.5 * (2 + L / ground_speed(L)) - 3:
                    break  # the return reaches him where his run from the one-two can take him
            else:
                raise Fail("edge geometry")
            holder, ball = self.pass_(H, st, ball, tav, (sx, sy), first=True, tag="final")
            self.shot(tav, ball, r.random() < .6)
        self.info["scorer"] = self.items[-1].pid
        # a pass of 30 m or more by the ball winner leaves at least 2.1 s after the win (enrich would call it a clearance)
        for a, b in zip(self.items, self.items[1:]):
            if a.kind == "win" and b.kind == "pass" and b.pid == a.pid and b.length >= 30:
                a.min_hold = max(a.min_hold, 2.15)
        self._check_points()
        self._fit()

    def shot(self, shooter, ball, under, header=False):
        self.items.append(Item("shot", self.H, shooter.id, ball[0], ball[1], header=header, under=under))

    def _check_points(self):
        for it in self.items:
            if it.kind == "press":
                continue
            pts = [(it.x0, it.y0)] if it.kind in ("win", "shot") else [(it.x0, it.y0), (it.x1, it.y1)]
            for n, (x, y) in enumerate(pts):
                xmax = 100.5 if it.tag in ("final", "channel") else X_MAX
                if not (X_MIN - 1e-9 <= x <= xmax + 1e-9 and Y_MIN - 1e-9 <= y <= Y_MAX + 1e-9):
                    if it.set_piece == "goal_kick" and n == 0:
                        continue
                    raise Fail(f"point off the pitch interior {it.kind} {x:.1f},{y:.1f}")

    # ---------- timing ----------
    def times(self, scale: float) -> float:
        t = self.t0
        last = t
        ready = t  # a press is an event: it may not come before the ball has arrived (+0.3 s), or enrich squeezes the arrival
        pending_press: list[Item] = []
        for n, it in enumerate(self.items):
            if it.kind == "press":
                pending_press.append(it)
                continue
            if it.kind == "pass":
                for pr in pending_press:
                    pr.t = min(t, max(last + .05, ready, t - pr.pre))
                    last = pr.t
                pending_press = []
                it.t = t
                last = t
                flight = it.length / it.v
                if it.ok:
                    h = it.hold if it.fixed else max(it.min_hold, it.hold * scale)
                    ready = t + flight + .35
                    t = t + flight + it.gap + h
                else:
                    t = t + flight  # the win item adds its own slack
            elif it.kind == "win":
                t += it.gap
                it.t = t
                last = ready = t
                t += max(it.min_hold, it.hold * scale)
            elif it.kind == "carry":
                for pr in pending_press:  # a defender closes him down as he sets off
                    pr.t = min(t, max(last + .05, ready, t - pr.pre))
                    last = pr.t
                pending_press = []
                it.t = t
                last = t
                t += it.length / it.v + it.gap
                ready = t - it.gap
            elif it.kind == "shot":
                it.t = t
        return self.items[-1].t

    def _fit(self):
        lo, hi = self.plan.goal_window
        self.t0 = self.r.uniform(*self.plan.kick_at)
        target = self.r.uniform(lo + .4, hi - .4)
        a, b = .75, 1.3
        ta, tb = self.times(a), self.times(b)
        if tb < lo:
            raise TooShort(f"timing {ta:.1f}..{tb:.1f}")
        if ta > hi:
            raise Fail(f"timing {ta:.1f}..{tb:.1f}")
        for _ in range(40):
            m = (a + b) / 2
            if self.times(m) < target:
                a = m
            else:
                b = m
        T = self.times((a + b) / 2)
        if not lo <= T <= hi:
            raise Fail("timing fit")
        self.info["scale"] = round((a + b) / 2, 3)


def _commit(sim, items: list[Item], beat) -> None:
    def pl(pid):
        for t in sim.teams.values():
            for p in t.players:
                if p.id == pid:
                    return p
        raise KeyError(pid)

    for it in items:
        sim.t = it.t
        if it.kind == "press":
            sim.emit(EventType.PRESSURE, it.side, pl(it.pid), it.x0, it.y0)
        elif it.kind == "pass":
            L = it.length
            depth = max(0.0, it.x1 - it.x0)
            sim.poss = it.side
            sim.bx, sim.by, sim.carrier = it.x0, it.y0, pl(it.pid)
            sim.emit(EventType.PASS, it.side, pl(it.pid), it.x0, it.y0, end=(it.x1, it.y1),
                     outcome="complete" if it.ok else "incomplete", receiver=it.rid if it.ok else None, set_piece=it.set_piece,
                     length=round(L, 1), difficulty=round(clamp(0.04 + L / 70 + (0.2 if it.under else 0) + depth / 150, 0.0, 1.0), 2),
                     ball_speed=round(it.v * 3.6, 1), under_pressure=True if it.under else None)
            if it.ok:
                sim.bx, sim.by, sim.carrier = it.x1, it.y1, pl(it.rid)
            else:
                sim.bx, sim.by = it.x1, it.y1
        elif it.kind == "win":
            taker = pl(it.pid)
            sim.emit(EventType.INTERCEPTION, it.side, taker, it.x0, it.y0)
            ox, oy = mirror((it.x0, it.y0))
            sim._flip("interception", ox, oy, taker)
        elif it.kind == "carry":
            L = it.length
            sim.emit(EventType.CARRY, it.side, pl(it.pid), it.x0, it.y0, end=(it.x1, it.y1), length=round(L, 1),
                     speed=round(it.v * 3.6, 1), under_pressure=True if it.under else None)
            sim.bx, sim.by = it.x1, it.y1
        elif it.kind == "shot":
            team = sim.teams[it.side]
            opp = sim.teams["A" if it.side == "H" else "H"]
            sim.poss = it.side
            sim.bx, sim.by, sim.carrier = it.x0, it.y0, pl(it.pid)
            sim._shot(team, opp, pl(it.pid), it.under, header=it.header, force_goal=True)
            shot = next(e for e in reversed(sim.events) if e.type == EventType.SHOT)
            sim.truth.append(TruthItem(t=shot.t, clock=shot.clock, kind="goal", side=beat.side, note=beat.note, importance=beat.importance))
    sim.forced = None
    sim.forced_beat = None


def scene_goal(events, plan: ScenePlan):
    """The goals after the fork."""
    return [e for e in events if e.t >= plan.fork_after and e.type == EventType.SHOT and e.outcome == "goal"]


def validate(meta: MatchMeta, events, plan: ScenePlan) -> list[str]:
    """Why this generated match is not a good scene (an empty list when it is). Reads the enriched rows the page will draw."""
    from .micro.enrich import enrich
    if plan.info.get("failed") or not plan.played:
        return ["not played"]
    bad: list[str] = []
    goals = scene_goal(events, plan)
    if len(goals) != 1:
        return [f"{len(goals)} goals after the fork"]
    g = goals[0]
    lo, hi = plan.goal_window
    if not (g.team == plan.side and lo <= g.t <= hi and g.score == [2, 1] and g.clock == "89"):
        bad.append(f"goal {g.team} {g.t} {g.score} {g.clock}")
    if any(e.type == EventType.PASS and e.receiver is not None and e.receiver == e.player for e in events if e.t >= plan.fork_after):
        return ["a pass to the passer himself"]  # before enrich, which cannot time a pass to oneself
    fork = next(e for e in events if e.t >= plan.fork_after and e.type == EventType.POSSESSION_CHANGE and e.reason == "goal_kick")
    en = enrich(meta, events, t0=fork.t, t1=g.t + 0.01)
    rows = [r for r in en.rows if r["t"] > fork.t]
    if any(r.get("implicit") for r in rows):
        bad.append("implicit rows")
    if en.stats.unrepaired or en.stats.squeezed:
        bad.append(f"unrepaired {en.stats.unrepaired} squeezed {en.stats.squeezed}")
    want = FINAL_TYPE.get(plan.info.get("pattern", ""))
    final = [r for r in rows if r["type"] == "pass" and r["t"] < g.t]
    if want and (not final or final[-1].get("pass_type") != want):
        bad.append(f"final ball {final[-1].get('pass_type') if final else None} not {want}")
    return bad
