"""Model, credit factor and the language to voice table. Voice ids are public premade voices, not secrets."""
from __future__ import annotations

from dataclasses import dataclass

MODEL = "eleven_flash_v2_5"
# Credits billed per character, per model. Flash is documented at 0.5; the first real call is checked against the
# subscription counter (docs/PROTOCOL.md, "Spoken lines"), and GuardedTTS also records the cost the API reports.
CREDITS_PER_CHAR: dict[str, float] = {MODEL: 0.5}
OUTPUT_FORMAT = "mp3_44100_64"
MAX_CHARS = 220  # a commentary line is at most 150 characters (analyst.MAX_CHARS); anything longer is refused


@dataclass(frozen=True)
class Voice:
    id: str
    name: str


# English is the commentator chosen for this build: Daniel, "Steady Broadcaster", British male (premade voice, GET /v1/voices).
# German and French use the same multilingual voice (Flash v2.5 speaks both); they are wired but not exercised yet.
_DANIEL = Voice("onwK4e9ZLuTAKqWW03F9", "Daniel")
VOICES: dict[str, Voice] = {"en": _DANIEL, "de": _DANIEL, "fr": _DANIEL}
LANGUAGE_CODES = {"en": "en", "de": "de", "fr": "fr"}


def voice_for(lang: str) -> Voice:
    try:
        return VOICES[lang]
    except KeyError:
        raise KeyError(f"no voice for language {lang!r}") from None
