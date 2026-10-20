"""Languages, styles and speech-time estimates."""
from __future__ import annotations

LANGS = ("en", "de", "fr")
STYLES = ("beginner", "expert")

# Characters spoken per second at a broadcast pace. Rough values, to be calibrated against the TTS voices.
CPS = {"en": 15.0, "de": 14.0, "fr": 15.5}
PAUSE_S = 0.3


def est_seconds(text: str, lang: str) -> float:
    return len(text) / CPS[lang] + PAUSE_S


def fmt_num(value: float, lang: str, digits: int = 2) -> str:
    s = f"{value:.{digits}f}"
    return s.replace(".", ",") if lang in ("de", "fr") else s
