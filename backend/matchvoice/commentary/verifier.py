"""Verifier: checks a commentary line against the facts it was allowed to use.

Deterministic, no model. A line is rejected when it contains
  - a number the facts do not support (a made-up xG, minute, speed, percentage),
  - a scoreline that is not the real one,
  - a player who is not part of the moment,
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

NUM_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")
SCORE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[-–:]\s*(\d{1,2})(?!\d)")
WORD_RE = re.compile(r"[a-zàâäçéèêëîïôöùûüßœ']+", re.I)

STOPWORDS = {
    "en": {"the", "and", "is", "are", "to", "of", "a", "in", "for", "with", "it", "that", "on", "they", "have", "has"},
    "de": {"der", "die", "das", "und", "ist", "mit", "den", "ein", "eine", "nicht", "auf", "für", "von", "im", "hat", "sie"},
    "fr": {"le", "la", "les", "et", "est", "un", "une", "des", "du", "de", "pour", "avec", "que", "dans", "ce", "sur"},
}


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
    for key in ("player", "keeper", "receiver", "team", "home", "away"):
        if key in raw and raw[key]:
            names.add(str(raw[key]).lower())
    return Allowed(numbers=nums, scores=scores, names=names)


class Verifier:
    def __init__(self, meta: MatchMeta):
        self.meta = meta
        self.players = {surname(p.name).lower(): p.name
                        for t in meta.teams.values() for p in t.players}
        self.team_names = {t.name.lower() for t in meta.teams.values()}

    def detect_lang(self, text: str) -> str | None:
        words = [w.lower() for w in WORD_RE.findall(text)]
        if len(words) < 5:
            return None
        score = {lang: sum(w in sw for w in words) for lang, sw in STOPWORDS.items()}
        best = max(score, key=score.get)
        return best if score[best] >= 2 and list(score.values()).count(score[best]) == 1 else None

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

        detected = self.detect_lang(text)
        if detected and detected != lang:
            v.append(Violation("language_mismatch", f"expected {lang}, text looks like {detected}"))
        if max_s is not None and est_seconds(text, lang) > max_s:
            v.append(Violation("too_long", f"{est_seconds(text, lang):.1f}s speech, slot is {max_s:.1f}s"))
        return Verdict(not v, v)
