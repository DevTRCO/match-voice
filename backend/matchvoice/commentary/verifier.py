"""Verifier: checks a commentary line against the facts it was allowed to use.

Deterministic, no model. A line is rejected when it contains
  - a number the facts do not support (a made-up xG, minute, speed, percentage),
  - a scoreline that is not the real one,
  - a player who is not part of the moment,
  - a tactical claim (high line, low block, pressing, in behind, a switch, between the lines, a counter) the moment's facts do not carry (7.5),
  - a trait word (pace, aerial threat, ...) in a sentence that names no player who has the trait,
  - the wrong language,
  - more words than the time slot allows.
Rejection reasons go back to the agent that wrote the line, which gets a retry.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..schema import MatchMeta
from .lang import est_seconds
from .moments import Moment, render_params, surname
from .templates import NAME_KEYS

NUM_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")
SCORE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[-–:]\s*(\d{1,2})(?!\d)")
WORD_RE = re.compile(r"[a-zàâäçéèêëîïôöùûüßœ']+", re.I)

STOPWORDS = {
    "en": {"the", "and", "is", "are", "to", "of", "a", "in", "for", "with", "it", "that", "on", "they", "have", "has"},
    "de": {"der", "die", "das", "und", "ist", "mit", "den", "ein", "eine", "nicht", "auf", "für", "von", "im", "hat", "sie"},
    "fr": {"le", "la", "les", "et", "est", "un", "une", "des", "du", "de", "pour", "avec", "que", "dans", "ce", "sur", "a", "cette", "au", "aux", "en"},  # "a" is English too; a French sentence of two perfects ("a réussi ... a disputé") was read as English
}


# ---- the claims lexicon (docs/DATA-MODEL.md 7.5). Tactical words are allowed only when the moment's facts carry the claim; trait words
# only in a sentence that names a player who has the trait (the roster in meta.json is the fact). The patterns are deliberately narrow:
# an everyday use of a word ("at pace", "deep in their half", "the switch of play" in a build-up) must not be rejected, so only the
# phrases a colour analyst uses for the tactical idea are listed. ----
CLAIMS: dict[str, dict[str, str]] = {
    "high_line": {
        "en": r"high line|(?:pushed|pushing|push|moved|moving) (?:the|their) (?:back )?line (?:right |well )?up|defend(?:s|ing)? high|high block",
        "de": r"hohe(?:n)? (?:Abwehr)?[kK]ette|Abwehrkette weit nach vorn|hoch im Feld|verteidigt hoch|hohe(?:n)? Block",
        "fr": r"ligne haute|relev\w* sa ligne|défend(?:ent)? (?:très )?haut|bloc haut",
    },
    "press_high": {
        "en": r"press(?:es|ing|ed)? high|high press|pressing in numbers|in numbers",
        "de": r"press(?:t|en|ing) hoch|hohes Pressing|mit vielen Leuten|läuft früh an",
        "fr": r"press(?:e|ent|ing) haut|pressing haut|à plusieurs",
    },
    "press_passive": {
        "en": r"happy to let the ball go|not pressing|sit(?:s|ting)? off|passive press",
        "de": r"presst kaum|lässt den Gegner kommen|passives Pressing",
        "fr": r"laisse(?:nt)? volontiers le ballon|ne presse(?:nt)? pas|pressing passif",
    },
    "low_block": {
        "en": r"low block|sit(?:s|ting)? deep|dropped deep|drop(?:s|ping)? deep|defend(?:s|ing)? deep|deep block|retreat(?:s|ed|ing)? deep",
        "de": r"tiefe(?:n)? Block|steht tief|zieht sich tief|tief zurück|verteidigt tief",
        "fr": r"bloc bas|attend bas|replié|défend(?:ent)? bas",
    },
    "in_behind": {
        "en": r"in behind|beyond the (?:back )?line|runs? in behind",
        "de": r"in den Rücken|hinter die Kette|hinter die Abwehr",
        "fr": r"dans le dos de la défense|derrière la défense",
    },
    "switch": {
        "en": r"\bswitch(?:es|ed|ing)?\b|switch of play",
        "de": r"Seitenwechsel|verlagert|verlagert das Spiel",
        "fr": r"renvers\w+|changement d'aile",
    },
    "line_break": {
        "en": r"between the lines|splits? the lines|break(?:s|ing)? the lines|line-breaking",
        "de": r"zwischen den Linien|durchbricht die Linie|überspielt die Linie",
        "fr": r"entre les lignes|casse les lignes|brise la ligne",
    },
    "tempo_slow": {
        "en": r"slow(?:ing|s)? (?:the game|it) (?:right )?down|in no hurry|tak(?:e|es|ing) their time|slow and patient",
        "de": r"nimmt das Tempo|Tempo raus|lässt sich Zeit|ruhig und geduldig",
        "fr": r"ralenti\w*|prend(?:ent)? son temps|prend(?:ent)? leur temps|calmement et patiemment",
    },
    "tempo_high": {
        "en": r"real tempo|high tempo|quick tempo|at tempo|ball quickly",
        "de": r"mit (?:richtig )?Tempo|hohem Tempo|hohes Tempo|schnell laufen",
        "fr": r"vrai rythme|rythme (?:élevé|soutenu)|circuler vite",
    },
    "counter": {
        "en": r"counter-?attack|on the break|break(?:s|ing)? at speed|\bcounters?\b",
        "de": r"Konter|Umschaltspiel",
        "fr": r"contre-attaque|en contre|jaillir en contre",
    },
}
TRAIT_WORDS: dict[str, dict[str, str]] = {  # trait code (schema.Trait) -> pattern per language
    "rapid": {"en": r"real pace|blistering pace|\bpacy\b|\brapid\b|great pace", "de": r"enormes Tempo|blitzschnell", "fr": r"vraie vitesse|vitesse folle"},
    "quick_off_the_mark": {"en": r"quick off the mark|sharp first step", "de": r"sofort auf Touren", "fr": r"démarre très vite"},
    "aerial_threat": {"en": r"dominant in the air|aerial threat|strong in the air", "de": r"stark in der Luft|Kopfballstark|Kopfballungeheuer", "fr": r"dominant dans les airs|redoutable de la tête"},
    "long_range": {"en": r"from distance|long-range|from range", "de": r"aus der Distanz|Fernschuss|Fernschütze", "fr": r"de loin|frappe de loin"},
    "set_piece_taker": {"en": r"dead-ball specialist|set[- ]piece specialist|set[- ]piece taker", "de": r"Standardspezialist", "fr": r"spécialiste des coups de pied arrêtés|coups de pied arrêtés"},
    "press_resistant": {"en": r"calm under pressure|so calm under pressure|press-resistant", "de": r"unter Druck ganz ruhig|druckresistent", "fr": r"calme sous la pression|très calme sous la pression"},
    "engine": {"en": r"never stops running|the engine", "de": r"läuft unermüdlich|Motor", "fr": r"ne s'arrête jamais de courir|le moteur"},
    "two_footed": {"en": r"either foot|both feet|two-footed", "de": r"beiden Füßen|beidfüßig", "fr": r"des deux pieds|ambidextre"},
    "tough_tackler": {"en": r"tough tackler|hard tackler|combative", "de": r"harter Zweikämpfer|zweikampfstark", "fr": r"défenseur teigneux|teigneux"},
    "visionary": {"en": r"sees the pass early|visionary|great vision", "de": r"erkennt den Pass früh|Spielübersicht", "fr": r"voit la passe très tôt|grande vision"},
    "dribbler": {"en": r"take a man on|loves to dribble|dribbler", "de": r"ins Dribbling|Dribbler", "fr": r"éliminer son vis-à-vis|dribbleur"},
}
_CLAIM_RX = {c: {lang: re.compile(p, re.I) for lang, p in langs.items()} for c, langs in CLAIMS.items()}
_TRAIT_RX = {c: {lang: re.compile(p, re.I) for lang, p in langs.items()} for c, langs in TRAIT_WORDS.items()}
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _walk(value):
    """Every scalar inside nested params (the facts block of phase 7 nests dicts and lists)."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _walk(v)
    elif isinstance(value, (list, tuple, set)):
        for v in value:
            yield from _walk(v)
    else:
        yield value


def claims_of(m: Moment) -> set[str]:
    """The tactical claims a moment's facts carry (7.5): its own kind and facet, and the `shape` and `build_up` blocks of an analyst
    moment (DATA-MODEL 7.3), whatever it brings. Nothing else is allowed."""
    p, out = m.params, set()
    facet = p.get("facet")
    if m.kind == "press_on" and facet == "high":
        out.add("press_high")
    elif m.kind == "shape_note":
        out |= {"chase": {"high_line"}, "protect": {"low_block"}}.get(facet, set())
    elif m.kind == "press_note":
        out |= {"intense": {"press_high"}, "passive": {"press_passive"}}.get(facet, set())
    elif m.kind == "phase_note":
        out |= {"high": {"high_line"}, "low": {"low_block"}, "counter": {"counter"}}.get(facet, set())
    elif m.kind == "tempo_note":
        out |= {"slow": {"tempo_slow"}, "high": {"tempo_high"}}.get(re.sub(r"_\d+$", "", facet or ""), set())  # slow_2 and high_2 are the second wording
    elif m.kind == "in_behind":
        out.add("in_behind")
    elif m.kind == "line_break":
        out.add("line_break")
    elif m.kind == "pass_kind" and p.get("pass_type") == "switch":
        out.add("switch")
    for side in (p.get("shape") or {}).values():  # {"home": {"posture", "block", "press", ...}, "away": {...}}
        if not isinstance(side, dict):
            continue
        out |= {"high": {"high_line"}, "low": {"low_block"}}.get(side.get("block"), set())
        out |= {"intense": {"press_high"}, "passive": {"press_passive"}}.get(side.get("press"), set())
        out |= {"chase": {"high_line"}, "protect": {"low_block"}}.get(side.get("posture"), set())
    build = p.get("build_up") or {}
    if isinstance(build, dict):
        if "switch" in set(_walk(build.get("chain"))):
            out.add("switch")
        if build.get("line_break"):
            out.add("line_break")
        if build.get("run_in_behind"):
            out.add("in_behind")
    return out


@dataclass
class Violation:
    code: str
    detail: str


@dataclass
class Verdict:
    ok: bool
    violations: list[Violation] = field(default_factory=list)

    def feedback(self) -> str:
        return "; ".join(f"{v.code}: {v.detail}" for v in self.violations)


@dataclass
class Allowed:
    numbers: set[float]
    scores: set[tuple[int, int]]
    names: set[str]  # lower-case surnames and team names the line may mention
    claims: set[str] = field(default_factory=set)  # tactical claims the moment's facts carry (CLAIMS keys, 7.5)


def _num_set(values) -> set[float]:
    out: set[float] = set()
    for v in values:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        out.add(round(float(v), 2))
        out.add(round(float(v), 1))
        if 0 <= v <= 1:
            out.add(float(round(100 * v)))
        out.add(float(round(v)))
    return out


def allowed_for(m: Moment, snapshot: dict, meta: MatchMeta) -> Allowed:
    """Everything a line about moment m may legitimately mention."""
    p = render_params(m, "en")
    raw = dict(m.params)
    nums = _num_set(raw.values()) | _num_set(v for v in p.values() if isinstance(v, (int, float)))
    nums |= {float(int(m.clock.split("+")[0]))}
    scores: set[tuple[int, int]] = set()
    for source in (raw.get("score"), f"{snapshot['score'][0]}-{snapshot['score'][1]}"):
        if source:
            a, b = (int(x) for x in str(source).split("-"))
            scores.add((a, b))
            nums |= {float(a), float(b)}
    if "hg" in raw:
        scores.add((raw["hg"], raw["ag"]))
    st = snapshot["stats"]
    for s in ("H", "A"):
        nums |= _num_set([st[s]["possession"], st[s]["shots"], st[s]["on_target"], st[s]["xg"], st[s]["pass_acc"]])
    wp = snapshot["win"]
    nums |= {float(round(100 * x)) for x in wp}
    names = {meta.teams[s].name.lower() for s in ("H", "A")}
    for key in ("player", "keeper", "receiver", "team", "home", "away", *NAME_KEYS):  # the fast layer may name every player in its params (7.5)
        if key in raw and raw[key]:
            names.add(str(raw[key]).lower())
    names |= {str(n).lower() for n in raw.get("chain") or ()}  # the players of a move
    return Allowed(numbers=nums, scores=scores, names=names, claims=claims_of(m))


class Verifier:
    def __init__(self, meta: MatchMeta):
        self.meta = meta
        self.players = {surname(p.name).lower(): p.name
                        for t in meta.teams.values() for p in t.players}
        self.team_names = {t.name.lower() for t in meta.teams.values()}
        self.traits: dict[str, set[str]] = {}  # lower-case surname -> trait codes in the roster
        for t in meta.teams.values():
            for p in t.players:
                self.traits.setdefault(surname(p.name).lower(), set()).update(getattr(tr, "value", tr) for tr in (p.traits or []))

    def detect_lang(self, text: str) -> str | None:
        words = [w.lower() for w in WORD_RE.findall(text)]
        if len(words) < 5:
            return None
        score = {lang: sum(w in sw for w in words) for lang, sw in STOPWORDS.items()}
        best = max(score, key=score.get)
        return best if score[best] >= 2 and list(score.values()).count(score[best]) == 1 else None

    def claim_violations(self, text: str, lang: str, allowed: Allowed) -> list[Violation]:
        """The claims lexicon (7.5): a tactical phrase needs the matching claim in the facts; a trait phrase needs a player with that
        trait named in the same sentence."""
        out: list[Violation] = []
        for claim, langs in _CLAIM_RX.items():
            m = langs[lang].search(text)
            if m and claim not in allowed.claims:
                out.append(Violation("claim_unsupported", f"'{m.group(0)}' ({claim}) is not in the facts of this moment"))
        for sentence in SENTENCE_RE.split(text):
            named = {sur for sur in self.traits if re.search(rf"(?<!\w){re.escape(sur)}(?!\w)", sentence.lower())}
            for trait, langs in _TRAIT_RX.items():
                m = langs[lang].search(sentence)
                if m and not any(trait in self.traits[sur] for sur in named):
                    out.append(Violation("trait_unsupported", f"'{m.group(0)}' ({trait}) is said of nobody who has that trait"))
        return out

    def check(self, text: str, lang: str, allowed: Allowed, max_s: float | None = None) -> Verdict:
        v: list[Violation] = []
        if not text.strip():
            return Verdict(False, [Violation("empty", "no text")])
        low = text.lower()

        # scorelines first, so their digits are not judged as loose numbers
        masked = text
        for m in SCORE_RE.finditer(text):
            pair = (int(m.group(1)), int(m.group(2)))
            if pair not in allowed.scores:
                if pair[::-1] in allowed.scores:
                    v.append(Violation("score_swapped", f"{m.group(0)} has home and away reversed; scores are always "
                                       f"home-away, the real scoreline is {pair[1]}-{pair[0]}"))
                else:
                    v.append(Violation("score_mismatch", f"{m.group(0)} is not a real scoreline of this moment"))
            masked = masked.replace(m.group(0), " ")
        for m in NUM_RE.finditer(masked):
            value = float(m.group(0).replace(",", "."))
            if not any(abs(value - a) < 0.006 for a in allowed.numbers):
                v.append(Violation("number_unsupported", f"{m.group(0)} is not in the facts"))

        for sur, full in self.players.items():
            if re.search(rf"(?<!\w){re.escape(sur)}(?!\w)", low) and sur not in allowed.names \
                    and not any(sur in t for t in self.team_names):
                v.append(Violation("player_unsupported", f"{full} is not part of this moment"))

        v.extend(self.claim_violations(text, lang, allowed))

        detected = self.detect_lang(text)
        if detected and detected != lang:
            v.append(Violation("language_mismatch", f"expected {lang}, text looks like {detected}"))
        if max_s is not None and est_seconds(text, lang) > max_s:
            v.append(Violation("too_long", f"{est_seconds(text, lang):.1f}s speech, slot is {max_s:.1f}s"))
        return Verdict(not v, v)
