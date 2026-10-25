"""Moments: things worth saying, detected from events and facts.

A moment says what happened and how much it matters. It carries raw values only;
the words come later, from templates (fast path) or the analyst agent (slow path).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..facts.engine import FactEngine, _attacking_x
from ..facts.models import Fact
from ..schema import Event, EventType
from .lang import fmt_num
from .templates import NAME_KEYS, WORDS, variants

MEN_EN = {11: "eleven", 10: "ten", 9: "nine", 8: "eight", 7: "seven"}
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
    ttl: float  # viewer seconds (times speed in match seconds) the moment stays worth saying
    params: dict
    evidence: list[int] = field(default_factory=list)
    fact_id: int | None = None
    ready_t: float = 0.0  # when its words are available (later than t if a model writes them)
    layer: str = "skeleton"  # skeleton | fast | context (docs/DATA-MODEL.md 7.1 and 7.2): the director applies the dense-layer rules to the last two
    voice_wait: float | None = None  # viewer seconds the voice may wait before it gives up on the line; None = the runner's default for the voice

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
    if "chain" in p:  # the players of a move, "A, B and C"
        and_ = {"en": "and", "de": "und", "fr": "et"}[lang]
        names = list(p["chain"])
        p["chain_text"] = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} {and_} {names[-1]}"
    for key, table in (("dir", "dir"), ("side", "side"), ("lane", "lane"), ("pass_type", "pass"), ("third", "third"), ("wing", "wing")):  # a localised word for a code, plain and capitalised
        if key in p:
            word = WORDS[table][lang][p[key]]
            p[f"{table}_word"] = word
            p[f"{table.capitalize()}_word"] = word[:1].upper() + word[1:]
    if "pass_type" in p:
        p["pass_verb"] = WORDS["pass_verb"][lang][p["pass_type"]]
        done = WORDS["pass_done"][lang][p["pass_type"]]  # the kick as a fragment, capitalised (it opens the line)
        p["Pass_done"] = done[:1].upper() + done[1:]
        prep = WORDS["pass_prep"][lang][p["pass_type"]]  # what takes the target: "goes long for X", "switches it to X"
        p["pass_prep"], p["Pass_prep"] = prep, prep[:1].upper() + prep[1:]
    extra = WORDS["extra"][lang]  # what the kick or the receipt shows besides its type
    if p.get("pressed"):
        p["pressed_word"] = extra["pressed"]
        p["Pressed_word"] = extra["pressed"][:1].upper() + extra["pressed"][1:]
    if p.get("driven"):
        p["driven_word"], p["driven_bare"], p["driven_alt"] = extra["driven"], extra["driven_bare"], extra["driven_alt"]  # the bare form is for a kick whose kicker was named a moment ago
    if p.get("facing") == "own_goal":
        p["back_word"] = extra["back"]
    if "nth" in p:
        p["nth_word"] = WORDS["nth"][lang][str(p["nth"])]
    if any(k in p for k in ("n", "m", "sh", "so", "season_goals", "count", "goals_h")):
        from .delivery import _score_words, number_words  # delivery imports this module, so it cannot be imported at the top
        for key in ("n", "m", "sh", "so"):
            if key in p:
                p[f"{key}_word"] = number_words(int(p[key]), lang)
        if "m_word" in p:
            p["m_times"] = "once" if int(p["m"]) == 1 else f"{p['m_word']} times"  # English plural agreement ("one times")
        if "sh_word" in p:
            p["sh_shots"] = "one shot" if int(p["sh"]) == 1 else f"{p['sh_word']} shots"
        if "n_word" in p:
            p["N_word"] = p["n_word"][:1].upper() + p["n_word"][1:]  # a sentence that opens on the number
        if "season_goals" in p:
            p["goals_word"] = number_words(int(p["season_goals"]), lang)
        if "count" in p:
            p["count_word"] = number_words(int(p["count"]), lang)
        if "goals_h" in p:  # the score in words ("two-one"): a fast or context line carries no digits
            p["score_words"] = _score_words(int(p["goals_h"]), int(p["goals_a"]), lang)
    if "place" in p:  # a table place, as an ordinal word
        from .delivery import _ordinal_de, _ordinal_en, _ordinal_fr
        n = int(p["place"])
        p["place_word"] = {"en": _ordinal_en(n), "de": _ordinal_de(n, False), "fr": _ordinal_fr(n, True)}[lang]
        from .delivery import number_words
        p["place_n"] = number_words(n, lang)  # German says the place as "Platz zwei"
    if "club" in p:  # French elides "de" before a vowel: "d'Aldermoor City"
        c = str(p["club"])
        p["de_club"] = (f"d'{c}" if c[:1].lower() in "aeiouh" else f"de {c}") if lang == "fr" else c
    if "facet" in p and m.kind in WORDS:  # a clause that fills the template, the same in both styles
        p["note"] = WORDS[m.kind][lang][p["facet"]].format(**p)
        for suffix in ("bare", "why"):  # the name-less clause, and the beginner's explanation of a restart
            if f"{m.kind}_{suffix}" in WORDS:
                p[suffix] = WORDS[f"{m.kind}_{suffix}"][lang][p["facet"]].format(**p)
        for k, name in (("2", "also"), ("3", "more")):  # a second and a third fact of the same player in the same sentence: their own numbers (count2, season_goals2)
            if f"facet{k}" in p:
                from .delivery import number_words
                q = dict(p, facet=p[f"facet{k}"])
                if f"count{k}" in p:
                    q["count"], q["count_word"] = p[f"count{k}"], number_words(int(p[f"count{k}"]), lang)
                if f"season_goals{k}" in p:
                    q["season_goals"], q["goals_word"] = p[f"season_goals{k}"], number_words(int(p[f"season_goals{k}"]), lang)
                p[name] = WORDS[m.kind][lang][p[f"facet{k}"]].format(**q)
        longer = WORDS.get(f"{m.kind}_long", {}).get(lang, {})  # the dead-ball sentence, when the facts hold one (a `_2` facet shares its base facet's)
        text = longer.get(p["facet"]) or longer.get(re.sub(r"_\d+$", "", p["facet"]))
        if text:
            try:
                p["note_long"] = text.format(**p)
            except KeyError:  # it needs a fact this moment lacks (no assist, say): the short sentence stands
                pass
    if "men" in p:
        p["men_en"] = MEN_EN.get(p["men"], str(p["men"]))
        p["men_de"] = f"zu {MEN_DE.get(p['men'], p['men'])}"
        p["men_fr"] = MEN_FR.get(p["men"], f"à {p['men']}")
    return p


def is_named(text: str) -> bool:
    """Does a template wording name a player?"""
    return any("{" + k + "}" in text for k in NAME_KEYS)


def render_variants(m: Moment, lang: str, style: str) -> list[str]:
    p = render_params(m, lang)
    vs = variants(m.kind, lang, style)
    if m.params.get("named") is not None:  # name rationing (7.1): the builder decides, the wording follows
        vs = [v for v in vs if is_named(v) == bool(m.params["named"])] or vs
        if m.kind == "pass_kind" and m.params["named"] and "target" in m.params:  # a pass that names a player names the one it is for
            vs = [v for v in vs if "{target}" in v] or vs
    if m.kind == "pass_kind" and "pass_type" in m.params:  # a pass with a type says it ("Long ball for X"), not just "X to Y"
        vs = [v for v in vs if re.search(r"{[Pp]ass_(done|word|verb|prep)}", v)] or vs
    usable = [v for v in vs if all(k in p for k in re.findall(r"{(\w+)}", v))]  # a wording needs every fact it names (no `dir` for a back-pass)
    if m.kind == "pass_kind" and m.params.get("kicker_said"):  # a receipt or a call named the kicker a moment ago: the kick goes without him when a wording allows
        usable = [v for v in usable if "{player}" not in v] or usable
    return [v.format(**p) for v in usable or vs]


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
