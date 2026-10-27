"""Where the demo page (ui/public/mock4.html) draws a player who is not on the ball, ported to Python for the live scene generator.

The page draws on-ball players from the rows and everyone else from its own shape model (`FORM`, `profOf`, `shapeOf`, the live
close-up). A generated pass that ends where the page already has the receiver needs no sprint on the board, so sim/scene.py picks
receivers and end points from these spots. Everything here is in the attacking frame of the player's side (x 0 = own goal line,
y 0 = the left touchline as that side attacks), which is the frame the simulation works in; the page's formulas are frame-free.

`FORM` must equal the literal in mock4.html (a test parses the page)."""
from __future__ import annotations

import math

PITCH_L, PITCH_W = 105.0, 68.0

FORM: dict[str, list[tuple[float, float]]] = {  # [depth from own goal 0..1, lateral -1 left .. +1 right], in the order of the players list
    "4-4-2": [(0, 0), (.27, .8), (.2, .27), (.2, -.27), (.27, -.8), (.5, .76), (.45, .23), (.45, -.23), (.5, -.76), (.73, .2), (.75, -.18)],
    "4-2-3-1": [(0, 0), (.27, .8), (.2, .27), (.2, -.27), (.27, -.8), (.4, .2), (.4, -.2), (.63, .74), (.6, 0), (.63, -.74), (.79, 0)],
}
GRP = {"GK": (0.0, 0.0), "DEF": (.22, 0.0), "MID": (.47, 0.0), "FWD": (.74, 0.0)}
G_DEPTH = {"DEF": .7, "MID": .95, "FWD": 1.15}


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def smooth(k: float) -> float:
    k = clamp(k, 0.0, 1.0)
    return k * k * (3 - 2 * k)


def hash01(a: float, b: float) -> float:
    s = math.sin(a * 127.1 + b * 311.7) * 43758.5453
    return s - math.floor(s)


def profile(number: int, side: str, group: str) -> tuple[float, float]:
    """(gD, gS) of the page's `profOf`: how far the player follows the ball up and down, and across."""
    seed = number + (0 if side == "H" else 50)
    gd = G_DEPTH.get(group, 1.0) * (.75 + .5 * hash01(seed, 10))
    gs = .4 + 1.0 * hash01(seed, 11)
    return gd, gs


def shape_spot(formation: str, k: int, group: str, number: int, side: str, ball: tuple[float, float], pw: float,
               live: bool = True, po: float = 0.0) -> tuple[float, float]:
    """The page's `shapeOf` for player `k` of a side, with the ball at `ball` (same frame) and `pw` the share of the ball that side
    had over the last second (1 on the ball, 0 without it). `po` is the other side's share: with the ball near its own box a side
    that does not have it defends the box (the page's `deep`); 0 leaves that out."""
    gd, gs = profile(number, side, group)
    form = FORM.get(formation)
    f = form[k] if form is not None and k < len(form) else GRP.get(group, (.45, 0.0))
    bx, by = ball
    bd = clamp(bx / PITCH_L, 0.0, 1.0)
    if group == "GK" or k == 0:
        dp = .012 + clamp(bd * .14, 0.0, .12)
    else:
        span = .42 + .18 * pw
        base = clamp(bd * .62 * gd - .12 + pw * .08, .06, .55)
        dp = min(.95, base + f[0] * span)
    wd = 22 + 8 * pw
    lat = f[1] * wd
    bs = by - PITCH_W / 2
    tuck = 1 - .4 * math.tanh(lat * bs / 120)
    shift = bs * (.45 - .2 * pw) * (.3 if group == "GK" else gs * tuck)
    x, y = PITCH_L * dp, PITCH_W / 2 + lat + shift
    if not live or group == "GK":
        return x, y
    deep = po * smooth((34 - bx) / 14) if group in ("DEF", "MID") else 0.0
    if deep > 0:  # the back four drop between the six-yard line and the penalty spot and narrow to the posts, the midfield to the edge
        hb = hash01(number + (0 if side == "H" else 50), 31)
        back = group == "DEF"
        dd = 6 + 6 * abs(f[1]) + 1.5 * hb if back else 14 + 4 * abs(f[1]) + 2 * hb
        ty = clamp(PITCH_W / 2 + lat * (.42 if back else .6) + bs * .3, PITCH_W / 2 - (14 if back else 19), PITCH_W / 2 + (14 if back else 19))
        x, y = x + (dd - x) * deep, y + (ty - y) * deep
    dx, dy = x - bx, y - by
    dd = math.hypot(dx, dy)
    bump = smooth(dd / 14) * (1 - smooth((dd - 28) / 18)) * (1 - deep * (.85 if group == "DEF" else .5))
    sq = 1 - (.4 * pw + .28 * (1 - pw)) * bump
    return bx + dx * sq, by + dy * sq


def mirror(p: tuple[float, float]) -> tuple[float, float]:
    """A point in one side's attacking frame, in the other side's."""
    return PITCH_L - p[0], PITCH_W - p[1]


def defend_spot(formation: str, k: int, group: str, number: int, side: str, ball_att: tuple[float, float],
                po: float = 0.0) -> tuple[float, float]:
    """Where a player of the side WITHOUT the ball stands, given the ball in the attacking side's frame; returned in that same frame.
    `po` 1: the attackers have had the ball for a second, so near the box the page draws the side defending it."""
    return mirror(shape_spot(formation, k, group, number, side, mirror(ball_att), 0.0, po=po))
