"""Moments: things worth saying, detected from events and facts.

A moment says what happened and how much it matters. It carries raw values only;
the words come later, from templates (fast path) or the analyst agent (slow path).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..facts.engine import FactEngine, _attacking_x
from ..facts.models import Fact
from ..schema import Event, EventType
from .lang import fmt_num
from .templates import variants

MEN_DE = {11: "elft", 10: "zehnt", 9: "neunt", 8: "acht", 7: "siebt"}
MEN_FR = {11: "à onze", 10: "à dix", 9: "à neuf", 8: "à huit", 7: "à sept"}


@dataclass
class Moment:
    id: int
    t: float  # match time of the event
    clock: str
    kind: str  # key into the template bank
    voice: str  # pbp (play-by-play) | analyst
    priority: int  # 0..100
    ttl: float  # match seconds the moment stays worth saying
    params: dict
    evidence: list[int] = field(default_factory=list)
    fact_id: int | None = None
    ready_t: float = 0.0  # when its words are available (later than t if a model writes them)

    def __post_init__(self) -> None:
        if not self.ready_t:
            self.ready_t = self.t


def surname(full: str) -> str:
    return full.split()[-1]


def render_params(m: Moment, lang: str) -> dict:
    """Localise the raw values of a moment for a template."""
    p = dict(m.params)
    for key in ("xg",):
        if key in p:
            p[key] = fmt_num(p[key], lang)
    for key in ("win_before", "win_after", "share"):
        if key in p:
            p[key] = round(100 * p[key])
    if "shots" in p and m.kind == "momentum":
        n = int(p["shots"])
        if lang == "en":
            p["shots_n"] = f"{n} shot" if n == 1 else f"{n} shots"
        elif lang == "de":
            p["shots_n"] = f"{n} Schuss" if n == 1 else f"{n} Schüsse"
            p["shots_n_dat"] = f"{n} Schuss" if n == 1 else f"{n} Schüssen"
        else:
            p["shots_n"] = f"{n} tir" if n == 1 else f"{n} tirs"
    if "length" in p:
        p["length"] = round(p["length"])
    if "men" in p:
        p["men_de"] = f"zu {MEN_DE.get(p['men'], p['men'])}"
        p["men_fr"] = MEN_FR.get(p["men"], f"à {p['men']}")
    return p


def render_variants(m: Moment, lang: str, style: str) -> list[str]:
    p = render_params(m, lang)
    return [v.format(**p) for v in variants(m.kind, lang, style)]


class MomentBuilder:
    def __init__(self, engine: FactEngine):
        self.eng = engine
        self._next = 0

    def _m(self, ev: Event, kind: str, voice: str, priority: int, ttl: float, params: dict,
           fact: Fact | None = None) -> Moment:
        m = Moment(id=self._next, t=ev.t, clock=ev.clock, kind=kind, voice=voice, priority=priority,
                   ttl=ttl, params=params, evidence=list(fact.evidence) if fact else [ev.i],
                   fact_id=fact.id if fact else None)
        self._next += 1
        return m

    def _name(self, pid: str | None) -> str:
        return surname(self.eng.names.get(pid or "", ""))

    def feed(self, ev: Event, new_facts: list[Fact]) -> list[Moment]:
        """Call after FactEngine.ingest(ev), with the facts that call returned."""
        e, names = self.eng, self.eng.team_names
        out: list[Moment] = []
        side = ev.team
        opp = "A" if side == "H" else "H"

        if ev.type == EventType.KICKOFF and ev.t == 0:
            out.append(self._m(ev, "kickoff_start", "pbp", 60, 20, {"home": names["H"], "away": names["A"]}))
        elif ev.type == EventType.SHOT:
            xg = ev.xg or 0.0
            player = self._name(ev.player)
            if ev.outcome == "goal":
                score = next((f.data["score"] for f in new_facts if f.kind == "goal"), f"{e.score['H']}-{e.score['A']}")
                out.append(self._m(ev, "shot_goal", "pbp", 100, 20,
                                   {"player": player, "team": names[side], "score": score, "xg": xg}))
            elif ev.outcome == "saved":
                out.append(self._m(ev, "shot_saved", "pbp", 70 if xg >= 0.15 else 45, 10,
                                   {"player": player, "keeper": self._name(ev.keeper), "xg": xg}))
            elif ev.outcome == "post":
                out.append(self._m(ev, "shot_post", "pbp", 65, 10, {"player": player, "xg": xg}))
            elif ev.outcome == "blocked":
                out.append(self._m(ev, "shot_blocked", "pbp", 35, 8, {"player": player}))
            else:
                out.append(self._m(ev, "shot_off", "pbp", 50 if xg >= 0.10 else 30, 8, {"player": player, "xg": xg}))
        elif ev.type == EventType.PASS and ev.set_piece == "corner":
            out.append(self._m(ev, "corner", "pbp", 45, 8, {"team": names[side]}))
        elif ev.type == EventType.PASS and ev.outcome == "complete" and ev.receiver and ev.set_piece is None:
            ax = _attacking_x(side, ev.period, ev.x)
            aex = _attacking_x(side, ev.period, ev.end_x)
            if (ev.length or 0) >= 35:
                out.append(self._m(ev, "long_ball", "pbp", 26, 5, {
                    "player": self._name(ev.player), "receiver": self._name(ev.receiver), "length": ev.length}))
            elif aex >= 70 > ax:
                out.append(self._m(ev, "pass_final_third", "pbp", 28, 5, {
                    "player": self._name(ev.player), "receiver": self._name(ev.receiver)}))
        elif ev.type == EventType.TACKLE and ev.outcome == "won":
            out.append(self._m(ev, "tackle_won", "pbp", 28, 5, {"player": self._name(ev.player), "team": names[side]}))
        elif ev.type == EventType.FOUL:
            out.append(self._m(ev, "foul", "pbp", 30, 6, {"team": names[opp]}))
        elif ev.type == EventType.CARD:
            if ev.card == "yellow":
                out.append(self._m(ev, "yellow", "pbp", 60, 10, {"player": self._name(ev.player), "team": names[side]}))
            else:
                men = 11 - e.team[side].red
                out.append(self._m(ev, "red", "pbp", 95, 25,
                                   {"player": self._name(ev.player), "team": names[side], "men": men}))
        elif ev.type == EventType.PERIOD_END:
            kind, prio = ("half_time", 85) if ev.outcome == "half_time" else ("full_time", 90)
            out.append(self._m(ev, kind, "pbp", prio, 30, {
                "home": names["H"], "away": names["A"], "hg": e.score["H"], "ag": e.score["A"]}))

        for f in new_facts:
            d = f.data
            if f.kind == "sprint":
                out.append(self._m(ev, "sprint", "pbp", 35, 6,
                                   {"player": self._name(f.player), "speed": round(d["speed_kmh"])}, f))
            elif f.kind == "goal":
                out.append(self._m(ev, "goal_analysis", "analyst", 70, 40, {
                    "player": self._name(f.player), "team": d["team"], "score": d["score"],
                    "win_before": d["win_before"], "win_after": d["win_after"], "xg": d["xg"],
                    "tags": ",".join(f.tags)}, f))
            elif f.kind == "momentum_phase":  # five-minute pressure phase
                out.append(self._m(ev, "momentum", "analyst", 55, 40, {
                    "team": d["team"], "share": d["share"], "shots": d["shots"], "minutes": d["minutes"]}, f))
            elif f.kind == "big_save" and f.importance >= 0.3:
                out.append(self._m(ev, "big_save_analysis", "analyst", 50, 25, {
                    "keeper": self._name(f.player), "player": d.get("shooter", "").split(" ")[-1], "xg": d["xg"]}, f))
            elif f.kind == "big_chance" and f.importance >= 0.3:
                out.append(self._m(ev, "big_chance_analysis", "analyst", 45, 25,
                                   {"player": self._name(f.player), "xg": d["xg"]}, f))
            elif f.kind == "shot_milestone":
                out.append(self._m(ev, "shot_milestone", "analyst", 35, 20,
                                   {"player": self._name(f.player), "shots": d["shots"]}, f))
        return out
