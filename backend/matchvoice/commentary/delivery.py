"""Delivery: how a line should be said, decided from the moment, and how its text is shaped for a speech engine.

Nothing here talks to a network. Three small pieces:
  energy_of        calm | rising | peak, from the moment's priority and tags (the analyst prompt and the voice settings share it)
  VOICE_SETTINGS   ElevenLabs voice_settings per energy level, applied only when the API is called (tts/guarded.py)
  shape_for_tts    a pure function: short sentences, punctuation for pauses, numbers and abbreviations in spoken form
"""
from __future__ import annotations

import re
from typing import Literal

from .moments import Moment

Energy = Literal["calm", "rising", "peak"]
ENERGIES: tuple[Energy, ...] = ("calm", "rising", "peak")

PEAK_PRIORITY = 90  # goal 100, red card 95, full time 90
RISING_PRIORITY = 55  # kick-off 60, yellow card 60, big saves with a big chance, goal analysis 70
BUMP_TAGS = {"equaliser", "go_ahead", "comeback", "late"}  # a goal with one of these tags is one level higher
BIG_CHANCE_XG = 0.4
WHISTLES = {"half_time", "full_time"}  # a whistle is never the loudest thing in the match


def energy_of(m: Moment) -> Energy:
    """How loud the booth is for this moment. Priority sets the base; a story tag or a very big chance lifts it one level."""
    level = 2 if m.priority >= PEAK_PRIORITY else 1 if m.priority >= RISING_PRIORITY else 0
    tags = {t for t in str(m.params.get("tags", "")).split(",") if t}
    if tags & BUMP_TAGS:
        level += 1
    elif m.kind in ("big_save_analysis", "big_chance_analysis", "shot_saved", "shot_post") and float(m.params.get("xg") or 0) >= BIG_CHANCE_XG:
        level += 1
    if m.kind in WHISTLES:
        level = min(level, 1)
    return ENERGIES[min(level, 2)]


# ---------- ElevenLabs voice_settings per energy level ----------
# stability: lower is more expressive. style: exaggeration, raises latency. speed: 0.7 to 1.2 on the API, 1.0 is natural.
# Not exercised yet (no credits are spent in this build step): the values are a starting point to tune by ear.
VOICE_SETTINGS: dict[Energy, dict[str, float]] = {
    "calm": {"stability": 0.62, "similarity_boost": 0.80, "style": 0.00, "speed": 0.97},
    "rising": {"stability": 0.45, "similarity_boost": 0.80, "style": 0.25, "speed": 1.04},
    "peak": {"stability": 0.30, "similarity_boost": 0.75, "style": 0.55, "speed": 1.12},
}
STYLE_MODELS: set[str] = {"eleven_v3", "eleven_v4"}  # models that get `style`; Flash is low-latency and `style` adds latency, so it is left out until a listening test says otherwise


def voice_settings(energy: Energy, model: str) -> dict[str, float | bool]:
    """The `voice_settings` object of a text-to-speech request for this energy level and model."""
    s: dict[str, float | bool] = dict(VOICE_SETTINGS[energy])
    if model not in STYLE_MODELS:
        s.pop("style")
    s["use_speaker_boost"] = True
    return s


# ---------- text shaping for speech ----------
_UNITS = {
    "en": ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
           "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"],
    "de": ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwölf", "dreizehn",
           "vierzehn", "fünfzehn", "sechzehn", "siebzehn", "achtzehn", "neunzehn"],
    "fr": ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze", "treize",
           "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf"],
}
_TENS = {
    "en": ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"],
    "de": ["", "", "zwanzig", "dreißig", "vierzig", "fünfzig", "sechzig", "siebzig", "achtzig", "neunzig"],
    "fr": ["", "", "vingt", "trente", "quarante", "cinquante", "soixante", "soixante", "quatre-vingt", "quatre-vingt"],
}


def number_words(n: int, lang: str) -> str:
    """0 to 99 in words. Larger numbers stay digits (a scoreline or a minute never needs them)."""
    if not 0 <= n <= 99:
        return str(n)
    if n < 20 and not (lang == "fr" and n >= 70):
        return _UNITS[lang][n]
    t, u = divmod(n, 10)
    if lang == "en":
        return _TENS["en"][t] + (f"-{_UNITS['en'][u]}" if u else "")
    if lang == "de":
        if not u:
            return _TENS["de"][t]
        unit = "ein" if u == 1 else _UNITS["de"][u]
        return f"{unit}und{_TENS['de'][t]}"
    # French
    if t in (7, 9):  # soixante-dix, quatre-vingt-dix: tens 6 and 8 plus 10 to 19
        base = _TENS["fr"][t]
        rest = 10 + u
        return f"{base}{' et ' if (t == 7 and rest == 11) else '-'}{_UNITS['fr'][rest]}"
    base = _TENS["fr"][t]
    if not u:
        return base + ("s" if t == 8 else "")
    return f"{base}{' et ' if (u == 1 and t != 8) else '-'}{_UNITS['fr'][u]}"


def _ordinal_en(n: int) -> str:
    irregular = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}
    words = number_words(n, "en")
    if n > 99:
        return words
    head, sep, last = words.rpartition("-")
    if not sep:
        head, last = "", words
    if last in irregular:
        last = irregular[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return f"{head}-{last}" if head else last


def _ordinal_de(n: int, dative: bool) -> str:
    special = {1: "erste", 3: "dritte", 7: "siebte", 8: "achte"}
    if n in special:
        w = special[n]
    else:
        w = number_words(n, "de") + ("te" if n < 20 else "ste")
    return w + "n" if dative else w


def _ordinal_fr(n: int, feminine: bool = False) -> str:
    if n == 1:
        return "première" if feminine else "premier"
    w = number_words(n, "fr")
    if w.endswith("quatre-vingts"):
        w = w[:-1]
    if w.endswith("cinq"):
        w += "u"
    elif w.endswith("neuf"):
        w = w[:-1] + "v"
    elif w.endswith("e"):
        w = w[:-1]
    return w + "ième"


_DATIVE_DE = re.compile(r"(?:\bin der|\bnach der|\bvor der|\bseit der|\bab der|\bbis zur|\bzur|\bin den|\bnach den) $", re.I)
SCORE_RE = re.compile(r"(?<![\d.,])(\d{1,2})\s*[-–:]\s*(\d{1,2})(?!\d|[.,]\d)")
DECIMAL_RE = re.compile(r"(?<![\d.,])(\d{1,3})[.,](\d{1,3})(?![\d])")
PERCENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|percent\b|Prozent\b|pour cent\b)", re.I)
ORD_EN_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\b")
ORD_FR_RE = re.compile(r"\b(\d{1,2})(?:er|re|e|ème)\b")
ORD_DE_RE = re.compile(r"(?<![\d.,])(\d{1,2})\.(?=\s+(?:Minute|Spielminute|Tor|Treffer|Schuss|Ecke)\b)")

_ABBREV = {
    "en": [(r"\bxG\b", "expected goals"), (r"\bkm/h\b", "kilometres per hour"), (r"\bvs\.?(?=\s)", "versus"), (r"\bFC\b", "F C"), (r"\bmins?\b", "minutes")],
    "de": [(r"\bxG\b", "erwartete Tore"), (r"\bkm/h\b", "Stundenkilometer"), (r"\bvs\.?(?=\s)", "gegen"), (r"\bFC\b", "F C"), (r"\bMin\.", "Minuten")],
    "fr": [(r"\bxG\b", "buts attendus"), (r"\bkm/h\b", "kilomètres-heure"), (r"\bvs\.?(?=\s)", "contre"), (r"\bFC\b", "F C"), (r"\bmin\b", "minutes")],
}
_PERCENT_WORD = {"en": "percent", "de": "Prozent", "fr": "pour cent"}
_POINT = {"en": "point", "de": "Komma", "fr": "virgule"}


def _score_words(a: int, b: int, lang: str) -> str:
    if lang == "en":
        if a == b:
            return "nil-nil" if a == 0 else f"{number_words(a, 'en')}-all"
        w = lambda n: "nil" if n == 0 else number_words(n, "en")
        return f"{w(a)}-{w(b)}"
    sep = " zu " if lang == "de" else " à "
    return f"{number_words(a, lang)}{sep}{number_words(b, lang)}"


# The world languages say small scores only (0 to 10): "uno a uno", "um a um", "één-één", "bir bir"; Japanese keeps the written 1対1, which a
# Japanese voice reads as itti tai itti.
_WORLD_UNITS = {
    "es": ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez"],
    "it": ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci"],
    "pt": ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez"],
    "nl": ["nul", "één", "twee", "drie", "vier", "vijf", "zes", "zeven", "acht", "negen", "tien"],
    "tr": ["sıfır", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz", "on"],
}
_WORLD_SEP = {"es": " a ", "it": " a ", "pt": " a ", "nl": "-", "tr": " "}


def score_said(a: int, b: int, lang: str) -> str:
    """A scoreline the way a caller says it: "one-all", "eins zu eins", and in French "un partout" for a level score ("deux à un" otherwise);
    "uno a uno" (es, it), "um a um" (pt), "één-één" (nl), "bir bir" (tr), and 1対1 in Japanese."""
    if lang == "ja":
        return f"{a}対{b}"
    if lang in _WORLD_UNITS:
        units = _WORLD_UNITS[lang]
        w = lambda n: units[n] if 0 <= n < len(units) else str(n)
        return f"{w(a)}{_WORLD_SEP[lang]}{w(b)}"
    if lang == "fr" and a == b:
        return f"{number_words(a, 'fr')} partout"
    return _score_words(a, b, lang)


def _decimal_words(whole: str, frac: str, lang: str) -> str:
    return f"{number_words(int(whole), lang)} {_POINT[lang]} " + " ".join(number_words(int(c), lang) for c in frac)


def shape_for_tts(text: str, lang: str) -> str:
    """Rewrite a commentary line so a speech engine says it the way a broadcaster would.

    Scorelines, decimals, percentages and ordinals become words, abbreviations are spelled out, dashes and colons become
    sentence breaks and commas (the pauses), repeated exclamation marks collapse, and the line always ends on a stop.
    Plain whole numbers stay digits: engines read those correctly. The wording itself is never changed."""
    t = " ".join(text.split())
    t = t.replace("…", "...")
    t = SCORE_RE.sub(lambda m: score_said(int(m.group(1)), int(m.group(2)), lang), t)  # German 1:1 is "eins zu eins", French 1-1 "un partout"
    if lang not in _UNITS:  # a world language: the score and the pauses only; its lines carry no percentages, decimals or abbreviations (verifier)
        t = re.sub(r"\s*[—–]\s*|\s+-\s+", ", ", t)
        t = re.sub(r"([!?！？])\s*(?:[!?！？])+", r"\1", t)
        t = re.sub(r"\s+([,.!?])", r"\1", t).strip(" ,")
        if t and t[-1] not in ".!?。！？":
            t += "。" if lang == "ja" else "."
        return t
    t = PERCENT_RE.sub(lambda m: _num_phrase(m.group(1), lang) + " " + _PERCENT_WORD[lang], t)
    for pattern, repl in _ABBREV[lang]:
        t = re.sub(pattern, repl, t)
    t = DECIMAL_RE.sub(lambda m: _decimal_words(m.group(1), m.group(2), lang), t)
    if lang == "en":
        t = ORD_EN_RE.sub(lambda m: _ordinal_en(int(m.group(1))), t)
    elif lang == "fr":
        t = ORD_FR_RE.sub(lambda m: _ordinal_fr(int(m.group(1)), feminine=_feminine_next(t, m.end())), t)
    else:
        t = ORD_DE_RE.sub(lambda m: _ordinal_de(int(m.group(1)), bool(_DATIVE_DE.search(t[:m.start()]))), t)
    # pauses: dashes and colons become sentence breaks or commas, brackets become commas
    t = re.sub(r"\s*[—–]\s*|\s+-\s+", ", ", t)
    t = re.sub(r"\s*:\s*", ". ", t)
    t = re.sub(r"\s*;\s*", ". ", t)
    t = re.sub(r"\s*\(\s*([^)]*?)\s*\)", r", \1,", t)
    t = re.sub(r"([!?])\s*(?:[!?])+", r"\1", t)
    t = re.sub(r"\.{2,}", "...", t)
    t = re.sub(r",\s*([.!?,])", r"\1", t)
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    t = re.sub(r"([.!?])(?=[A-ZÀ-ÖØ-Þ])", r"\1 ", t)
    t = re.sub(r"\.\s+\.", ".", t).strip(" ,")
    if t and t[-1] not in ".!?":
        t += "."
    return t


# ---------- hype: how a peak line is shouted ----------
# Applied after shape_for_tts, only to the text sent to the speech engine; the caption keeps the written line.
# eleven_v3 and eleven_v4 read audio tags in square brackets ([excited], [shouting]); other models would read them aloud, so they get none.
TAG_MODELS = {"eleven_v3", "eleven_v4"}
_SHOUT = {"en": ("GOAL", "GOOOAL"), "de": ("TOR", "TOOOR"), "fr": ("BUT", "BUUUT")}  # the world booth writes its own shout ("¡GOOOL!", "ゴール！")
_TAGS: dict[Energy, str] = {"calm": "", "rising": "[excited] ", "peak": "[shouting] "}


def hype_for_tts(text: str, lang: str, energy: Energy, model: str) -> str:
    """A peak line is called, not read: the shout word is stretched ("GOOOAL!"), it stands alone as its own exclamation,
    and the line ends on an exclamation mark. With a tag model the energy also goes in as an audio tag."""
    t = text
    if energy == "peak" and lang in _SHOUT:
        word, long = _SHOUT[lang]
        # the recorded script writes "GOAL", the live templates "Goal!": a mixed-case word is a shout only with its "!" ("Goal kick" is not)
        m = re.match(rf"{word}(?![A-Za-z])\s*[!.,]?\s*", t) or re.match(rf"{word}(?![A-Za-z])\s*!\s*", t, re.I)
        if m:
            rest = re.sub(rf"(?<![A-Za-z]){word}(?![A-Za-z])", word.capitalize(), t[m.end():])  # a second shout word ("BUT de Fontaine") is read
            t = f"{long}! " + rest[:1].upper() + rest[1:]  # as a word, not spelled out or taken for English "but": only the first is stretched
        t = re.sub(r"[.]$", "!", t)
    if model in TAG_MODELS:
        t = _TAGS[energy] + t
    return t


def _num_phrase(s: str, lang: str) -> str:
    whole, _, frac = s.replace(",", ".").partition(".")
    return _decimal_words(whole, frac, lang) if frac else number_words(int(whole), lang)


def _feminine_next(text: str, pos: int) -> bool:
    return text[pos:].lstrip().lower().startswith(("minute", "mi-temps", "période"))
