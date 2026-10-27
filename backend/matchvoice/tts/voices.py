"""Model, credit factor and the language to voice table. Voice ids are public premade voices, not secrets."""
from __future__ import annotations

from dataclasses import dataclass

MODEL = "eleven_flash_v2_5"
# Credits billed per character, per model. Flash is documented at 0.5; the first real call is checked against the
# subscription counter (docs/PROTOCOL.md, "Spoken lines"), and GuardedTTS also records the cost the API reports.
CREDITS_PER_CHAR: dict[str, float] = {MODEL: 0.5, "eleven_v3": 1.0, "eleven_v4": 1.0}  # v3: expressive, audio tags, not low latency; 1.0 is an assumption to check on the counter
HYPE_MODEL = "eleven_v3"  # recorded peak lines (a goal) are made with this model; live stays on Flash
OUTPUT_FORMAT = "mp3_44100_64"
MAX_CHARS = 220  # a commentary line is at most 150 characters (analyst.MAX_CHARS); anything longer is refused


@dataclass(frozen=True)
class Voice:
    id: str
    name: str


# English is the commentator chosen for this build: Daniel, "Steady Broadcaster", British male (premade voice, GET /v1/voices).
# A line without a known speaker falls back to its language's voice: Daniel for en, de and fr (Flash v2.5 speaks all three, and the
# cache keys of lines made so far stay as they were), the solo commentator's voice for each world language.
_DANIEL = Voice("onwK4e9ZLuTAKqWW03F9", "Daniel")

# One voice per person in the booth (commentary/lang.py BOOTH), the cast of backend/scripts/bake_story_audio.py CAST: the same
# premade voices, here on Flash (eleven_flash_v2_5) for live lines. backend/tests/test_public.py keeps the two casts equal.
CAST: dict[str, Voice] = {
    "Charlie Hale": Voice("IKne3meq5aSn9XLyUdCD", "Charlie"),
    "Owen Carter": Voice("TX3LPaxmHKxFdv7VOQHJ", "Liam"),
    "Jonas Weber": Voice("vGWWh1bodhwwi4yHd6qZ", "Marcus"),
    "Felix Brandt": Voice("iQ5dS7juUUF7zgIVf8ET", "Leo"),
    "Hugo Martin": Voice("JBFqnCBsd6RMkjVDRZzb", "George"),
    "Théo Laurent": Voice("bIHbv24MWmeRgasZH58o", "Will"),
    "Daniel Price": _DANIEL,
    "Kim Berger": Voice("DEZHhPbmb8LVZmWufkCh", "Anna"),
    "Sacha Morel": Voice("pqHfZKP75CvOlQylNhV4", "Bill"),
    "Lucía Romero": Voice("EXAVITQu4vr4xnSDxMaL", "Sarah"),
    "Giulia Conti": Voice("XrExE9yKIg1WjnnlVkGX", "Matilda"),
    "Rafael Souza": Voice("cjVigY5qzO86Huf0OWal", "Eric"),
    "Sanne de Vries": Voice("pFZP5JQG7iQjIQuC4Bku", "Lily"),
    "Emre Aydın": Voice("nPczCjzI2devNBz1zQrb", "Brian"),
    "Yuki Tanaka": Voice("cgSgspJ2msm6clMCkdW9", "Jessica"),
}
VOICES: dict[str, Voice] = {"en": _DANIEL, "de": _DANIEL, "fr": _DANIEL,
                            "es": CAST["Lucía Romero"], "it": CAST["Giulia Conti"], "pt": CAST["Rafael Souza"],
                            "nl": CAST["Sanne de Vries"], "tr": CAST["Emre Aydın"], "ja": CAST["Yuki Tanaka"]}
LANGUAGE_CODES = {"en": "en", "de": "de", "fr": "fr", "es": "es", "it": "it", "pt": "pt", "nl": "nl", "tr": "tr", "ja": "ja"}


def voice_for(lang: str, who: str | None = None) -> Voice:
    """The speaker's own voice when `who` is in the cast, else the language's voice. KeyError when neither exists."""
    if who and who in CAST:
        return CAST[who]
    try:
        return VOICES[lang]
    except KeyError:
        raise KeyError(f"no voice for language {lang!r}") from None
