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
    pron = PRONOUNS.get(p.get("squad") or "", {}).get(lang)
    if pron:  # a squad whose gender is known: wordings with a pronoun for a player become usable (also inside the clauses below)
        p.update(pron)
        p.update({k[:1].upper() + k[1:]: v[:1].upper() + v[1:] for k, v in pron.items()})
    if "facet" in p and m.kind in WORDS:  # a clause that fills the template, the same in both styles
        p["note"] = WORDS[m.kind][lang][p["facet"]].format(**p)
        for suffix in ("bare", "why", "plain", "bare_plain"):  # the name-less clause, the beginner's explanation of a restart, the beginner's words
            table = f"{m.kind}_{suffix}_pron" if pron and f"{m.kind}_{suffix}_pron" in WORDS else f"{m.kind}_{suffix}"
            if table in WORDS:
                p[suffix] = WORDS[table][lang][p["facet"]].format(**p)
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
    if p.get("pass_type") in WORDS["pass_call"][lang] and p.get("target"):  # the caller's fragment for this pass type, per style
        p["pass_call"] = WORDS["pass_call"][lang][p["pass_type"]].format(**p)
        p["pass_call_plain"] = WORDS["pass_call_plain"][lang][p["pass_type"]].format(**p)
    if "goal_facet" in p and "short" in p:  # the goal call and the score line: what the goal means, the hit, the state
        p["meaning"] = WORDS["goal_meaning"][lang][p["goal_facet"]].format(**p)
        state = WORDS["score_state"][lang].get(p["goal_facet"])
        if state:
            p["state_call"] = state.format(**p)
    if p.get("strike"):
        p["strike_call"] = WORDS["goal_strike"][lang]["strike"]
    if m.kind == "score_line" and "score" in p:
        from .delivery import score_said
        a, b = (int(x) for x in str(m.params["score"]).split("-"))
        said = score_said(a, b, lang)
        p["score_words"], p["Score_words"] = said, said[:1].upper() + said[1:]
        left = time_left(int(p["left_min"]), lang) if p.get("left_min") else None
        if left:
            p["left" if p.get("half", 2) == 2 else "left_ht"] = left
    if lang == "de" and "score" in p:  # German writes a score 1:1 (and says "eins zu eins")
        p["score"] = str(p["score"]).replace("-", ":")
    return p


PRONOUNS = {  # the player pronouns a wording may use, only when the squad's gender is known (TeamMeta.gender)
    "men": {"en": {"he": "he", "him": "him", "his": "his", "himself": "himself"}, "de": {"er": "er", "ihn": "ihn", "sein": "sein"},
            "fr": {"il": "il", "lui": "lui"}},
    "women": {"en": {"he": "she", "him": "her", "his": "her", "himself": "herself"}, "de": {"er": "sie", "ihn": "sie", "sein": "ihr"},
              "fr": {"il": "elle", "lui": "elle"}},
}
_FR_LEFT = {5: "cinq minutes", 10: "une dizaine de minutes", 15: "un quart d'heure", 20: "une vingtaine de minutes", 25: "vingt-cinq minutes",
            30: "une demi-heure", 35: "trente-cinq minutes", 40: "une quarantaine de minutes", 45: "trois quarts d'heure"}


def time_left(minutes: int, lang: str) -> str | None:
    """The time left in a half, the way a caller rounds it ("twenty minutes or so", "knapp zwanzig Minuten", "une vingtaine de minutes").
    True to the clock: 19 minutes is "knapp zwanzig" in German, never "zwanzig". None under five minutes (the score stands alone then)."""
    if minutes < 5:
        return None
    from .delivery import number_words
    n5 = 5 * round(minutes / 5)
    if lang == "en":
        return f"{number_words(n5, 'en')} minutes"
    if lang == "de":
        return f"{'knapp ' if minutes < n5 else 'gut ' if minutes > n5 else ''}{number_words(n5, 'de')} Minuten"
    return _FR_LEFT.get(n5, f"{number_words(n5, 'fr')} minutes")


def _tidy(text: str) -> str:
    """A clause that carries its own end ("Und heute?", "Contrôle poitrine...") inside a template that adds a stop."""
    text = re.sub(r"\.{4,}", "...", text)
    text = re.sub(r"([!?])\.", r"\1", text)
    text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)
    return text.replace("..., ", ", ")


def goal_facet(score: str, side: str) -> str:
    """What a goal means, from the score after it (home-away) and the side that scored: equaliser | opener | go_ahead | more | back."""
    h, a = (int(x) for x in str(score).split("-"))
    own, opp = (h, a) if side == "H" else (a, h)
    if own == opp:
        return "equaliser"
    if own == opp + 1:
        return "opener" if own == 1 else "go_ahead"
    return "more" if own > opp else "back"


def is_named(text: str) -> bool:
    """Does a template wording name a player?"""
    return any("{" + k + "}" in text for k in NAME_KEYS)


def render_variants(m: Moment, lang: str, style: str) -> list[str]:
    p = render_params(m, lang)
    vs = variants(m.kind, lang, style)
    if m.kind == "pass_kind" and "pass_call" in p and m.params.get("named"):  # a type the caller has a fragment for: always that fragment
        return [_tidy(v.format(**p)) for v in vs if "{pass_call" in v]  # ("Long ball for Tavares."), it may run on as the ball lands (CALL_SLACK_S)
    if m.params.get("named") is not None:  # name rationing (7.1): the builder decides, the wording follows
        vs = [v for v in vs if is_named(v) == bool(m.params["named"])] or vs
        if m.kind == "pass_kind" and m.params["named"] and "target" in m.params:  # a pass that names a player names the one it is for
            vs = [v for v in vs if "{target}" in v] or vs
    if m.kind == "pass_kind" and "pass_type" in m.params:  # a pass with a type says it ("Long ball for X"), not just "X to Y"
        vs = [v for v in vs if re.search(r"{[Pp]ass_(done|word|verb|prep)}", v)] or vs
    usable = [v for v in vs if all(k in p for k in re.findall(r"{(\w+)}", v))]  # a wording needs every fact it names (no `dir` for a back-pass)
    if m.kind == "pass_kind" and m.params.get("kicker_said"):  # a receipt or a call named the kicker a moment ago: the kick goes without him when a wording allows
        usable = [v for v in usable if "{player}" not in v] or usable
    return [_tidy(v.format(**p)) for v in usable or vs]


class MomentBuilder:
    def __init__(self, engine: FactEngine, rows: list[dict] | None = None):
        """`rows` are the enriched rows of the match (sim/micro, `enrich(...).rows`), when the run has them: the scoring move then carries
        how each ball was played (pass type, touch, first time, foot, technique, pressure). Only rows of events already fed are read."""
        self.eng = engine
        self._next = 0
        self._move: tuple[str | None, list[Event]] = (None, [])  # the side on the ball and its events in this possession, oldest first
        self._rows: dict[int, list[dict]] = {}
        for r in rows or ():
            self._rows.setdefault(r["i"], []).append(r)

    MOVE_TYPES = (EventType.PASS, EventType.INTERCEPTION, EventType.CARRY, EventType.TACKLE)
    LONG_PASS_M = 30.0
    MOVE_STEPS = 6  # the last steps of a scoring move the analyst sees

    def _track_move(self, ev: Event) -> None:
        """The events of this possession, oldest first, from past events only (no lookahead). A turnover starts a new move;
        a press or a foul by the other side does not."""
        side, steps = self._move
        if ev.type == EventType.KICKOFF or (ev.team != side and ev.type in (*self.MOVE_TYPES, EventType.POSSESSION_CHANGE)):
            side, steps = ev.team, []
        if ev.type in self.MOVE_TYPES and ev.player:
            steps.append(ev)
        self._move = (side, steps)

    @staticmethod
    def _foot(body_part: str | None) -> str | None:
        return {"left_foot": "left", "right_foot": "right"}.get(body_part or "")

    def _skeleton_step(self, ev: Event) -> dict:
        who = self._name(ev.player)
        if ev.type == EventType.PASS:
            step = {"player": who, "action": "long ball" if (ev.length or 0) >= self.LONG_PASS_M else "pass"}
            if ev.outcome == "complete" and ev.receiver:
                step["to"] = self._name(ev.receiver)
            return step
        if ev.type in (EventType.INTERCEPTION, EventType.TACKLE):
            own = _attacking_x(ev.team, ev.period, ev.x) < 52.5
            return {"player": who, "action": "wins the ball", "where": "in their own half" if own else "in the other half"}
        return {"player": who, "action": "carries it forward"}

    def _enriched_steps(self, ev: Event) -> list[dict] | None:
        """How the ball was played in this event, from its enriched rows: the kick, the receipt worth a word, an implicit pass."""
        rows = self._rows.get(ev.i)
        if not rows:
            return None
        out: list[dict] = []
        for r in sorted(rows, key=lambda r: r["eid"]):
            if r.get("team") != ev.team:
                continue
            if r["type"] == "pass":
                step = {"player": self._name(r.get("player") or ev.player), "action": "pass", "pass_type": r.get("pass_type"),
                        "height": r.get("height"), "foot": self._foot(r.get("body_part")), "first_time": bool(r.get("first_time"))}
                if r.get("target"):
                    step["to"] = self._name(r["target"])
                if (r.get("pressure") or {}).get("under") is not None:
                    step["under_pressure"] = bool(r["pressure"]["under"])
                out.append({k: v for k, v in step.items() if v is not None})
            elif r["type"] == "receipt" and r.get("touch") and r["touch"] != "control":
                out.append({"player": self._name(r.get("player")), "action": "takes it", "touch": r["touch"]})
            elif r["type"] in ("interception", "tackle"):
                out.append(self._skeleton_step(ev))
            elif r["type"] == "carry":
                out.append({"player": self._name(r.get("player") or ev.player), "action": "carries it forward"})
        return out

    def _move_of(self, scorer: str, shot: Event | None) -> tuple[list[str], list[dict], float | None]:
        """The scoring move: the other players in it (in order), its last steps (dicts the analyst can picture: who, what, how), and its
        length in seconds from the first step to the goal. Every name in the steps is in the chain, so the verifier allows it."""
        steps: list[dict] = []
        for ev in self._move[1]:
            steps += self._enriched_steps(ev) or [self._skeleton_step(ev)]
        if shot is not None:
            shot_rows = [r for r in self._rows.get(shot.i, []) if r["type"] == "shot"]
            s = {"player": scorer, "action": "header" if shot.body_part == "head" else "shot", "distance": self._finish(shot)}
            if shot_rows:
                r = shot_rows[0]
                s |= {k: v for k, v in {"foot": self._foot(r.get("body_part")), "technique": r.get("technique"),
                                        "first_time": bool(r.get("first_time"))}.items() if v is not None}
                if (r.get("pressure") or {}).get("under") is not None:
                    s["under_pressure"] = bool(r["pressure"]["under"])
            steps.append(s)
        steps = steps[-self.MOVE_STEPS:]
        names: list[str] = []
        for st in steps:
            for n in (st.get("player"), st.get("to")):
                if n and n != scorer and n not in names:
                    names.append(n)
        first = self._move[1][0].t if self._move[1] else None
        length = round(shot.t - first, 1) if (shot is not None and first is not None) else None
        return names, steps, length

    @staticmethod
    def _finish(ev: Event) -> str:
        """Where the goal was scored from, in words (no number)."""
        if ev.body_part == "head":
            return "a header"
        gx = ev.end_x if ev.end_x is not None else (0.0 if ev.x < 52.5 else 105.0)
        d = ((ev.x - gx) ** 2 + (ev.y - 34.0) ** 2) ** 0.5
        return "from close range" if d < 8 else "inside the box" if d < 17 else "from outside the box"

    def _m(self, ev: Event, kind: str, voice: str, priority: int, ttl: float, params: dict,
           fact: Fact | None = None) -> Moment:
        team = self.eng.meta.teams.get(ev.team) if ev.team else None
        if team is not None and team.gender:  # the squad's gender: a wording may say "he" (render_params, PRONOUNS)
            params = {**params, "squad": team.gender}
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
        self._track_move(ev)

        if ev.type == EventType.KICKOFF and ev.t == 0:
            out.append(self._m(ev, "kickoff_start", "pbp", 60, 20, {"home": names["H"], "away": names["A"]}))
        elif ev.type == EventType.SHOT:
            xg = ev.xg or 0.0
            player = self._name(ev.player)
            if ev.outcome == "goal":
                score = next((f.data["score"] for f in new_facts if f.kind == "goal"), f"{e.score['H']}-{e.score['A']}")
                params = {"player": player, "player_full": e.names.get(ev.player or "", player) or player, "team": names[side],
                          "short": names[side].split()[0], "other": names[opp].split()[0], "score": score, "xg": xg,
                          "goal_facet": goal_facet(score, side)}
                if ev.body_part != "head" and self._finish(ev) == "from outside the box":
                    params["strike"] = True  # a strike from range: the call may react to the hit
                out.append(self._m(ev, "shot_goal", "pbp", 100, 20, params))
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
                scorer = self._name(f.player)
                params = {"player": scorer, "team": d["team"], "score": d["score"],
                          "win_before": d["win_before"], "win_after": d["win_after"], "xg": d["xg"],
                          "tags": ",".join(f.tags), "scorer_goals": self.eng.player_stats(f.player)["goals"] if f.player else 0}
                move, steps, length = self._move_of(scorer, ev if ev.type == EventType.SHOT else None)
                if move:
                    params["chain"] = move  # the players of the move, so the colour line may name who made it (the verifier allows them)
                if steps:
                    params["move"] = steps
                if length is not None and length > 0:
                    params["move_seconds"] = round(length)
                if ev.type == EventType.SHOT:
                    params["finish"] = self._finish(ev)
                out.append(self._m(ev, "goal_analysis", "analyst", 70, 40, params, f))
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
