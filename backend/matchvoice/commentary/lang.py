"""Languages, styles, the booths and speech-time estimates."""
from __future__ import annotations

from dataclasses import dataclass

LANGS = ("en", "de", "fr")  # the core languages: instant templates for play-by-play, the analyst writes the analysis
STYLES = ("beginner", "expert")
CORE_KEYS = tuple(f"{lang}/{style}" for lang in LANGS for style in STYLES)  # channel ids 0..5
# The world channels (approved by the user on 2026-10-26): one level each, a solo booth, and every line, play-by-play included, comes from
# the model (commentary/world.py), checked by the same verifier. Channel ids 6..11, after the core ones, so nothing existing moves.
WORLD = (("es", "expert"), ("it", "beginner"), ("pt", "expert"), ("nl", "beginner"), ("tr", "expert"), ("ja", "beginner"))
WORLD_LANGS = tuple(lang for lang, _ in WORLD)
WORLD_KEYS = tuple(f"{lang}/{style}" for lang, style in WORLD)
ALL_LANGS = LANGS + WORLD_LANGS
ALL_KEYS = CORE_KEYS + WORLD_KEYS

# Characters spoken per second at a broadcast pace. en/de/fr measured with Chrome local voices (about 12 to 13 at rate 1); ui/src/speech.ts plans
# with the same figures. The world figures are estimates (Japanese counts kana and kanji, about 7 a second), not measured on a voice yet.
CPS = {"en": 12.5, "de": 12.0, "fr": 13.0, "es": 13.5, "it": 13.0, "pt": 13.0, "nl": 12.5, "tr": 12.0, "ja": 7.0}
PAUSE_S = 0.3


@dataclass(frozen=True)
class Person:
    name: str
    gender: str  # man | woman


@dataclass(frozen=True)
class Booth:
    """The booth of one channel: the lead (play-by-play, story notes, the score line) and the co-commentator (the analyst's lines and the
    context layer). A solo booth has no co-commentator: the lead says every line."""
    lang: str
    level: str
    lead: Person
    co: Person | None = None

    @property
    def solo(self) -> bool:
        return self.co is None


_DANIEL, _KIM, _SACHA = Person("Daniel Price", "man"), Person("Kim Berger", "woman"), Person("Sacha Morel", "man")
# Fictional names. Core co names are unisex first names that work in every language.
BOOTH: dict[str, Booth] = {
    "en/beginner": Booth("en", "beginner", Person("Owen Carter", "man"), _DANIEL),
    "en/expert": Booth("en", "expert", Person("Charlie Hale", "man"), _DANIEL),
    "de/beginner": Booth("de", "beginner", Person("Felix Brandt", "man"), _KIM),
    "de/expert": Booth("de", "expert", Person("Jonas Weber", "man"), _KIM),
    "fr/beginner": Booth("fr", "beginner", Person("Théo Laurent", "man"), _SACHA),
    "fr/expert": Booth("fr", "expert", Person("Hugo Martin", "man"), _SACHA),
    "es/expert": Booth("es", "expert", Person("Lucía Romero", "woman")),
    "it/beginner": Booth("it", "beginner", Person("Giulia Conti", "woman")),
    "pt/expert": Booth("pt", "expert", Person("Rafael Souza", "man")),
    "nl/beginner": Booth("nl", "beginner", Person("Sanne de Vries", "woman")),
    "tr/expert": Booth("tr", "expert", Person("Emre Aydın", "man")),
    "ja/beginner": Booth("ja", "beginner", Person("Yuki Tanaka", "woman")),
}
assert tuple(BOOTH) == ALL_KEYS
CO_PRONOUN = {"Daniel Price": "he", "Kim Berger": "she", "Sacha Morel": "he"}  # how the prompt speaks of the co-commentator
PRONOUN = {"man": "he", "woman": "she"}


def who_of(key: str, voice: str) -> str:
    """The person in the booth who says a line of this voice (pbp: the lead, analyst: the co-commentator, or the lead of a solo booth)."""
    b = BOOTH[key]
    return b.co.name if voice == "analyst" and b.co else b.lead.name


def est_seconds(text: str, lang: str) -> float:
    return len(text) / CPS[lang] + PAUSE_S


def fmt_num(value: float, lang: str, digits: int = 2) -> str:
    s = f"{value:.{digits}f}"
    return s.replace(".", ",") if lang in ("de", "fr", "es", "it", "pt", "nl", "tr") else s
