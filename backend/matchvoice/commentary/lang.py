"""Languages, styles and speech-time estimates."""
from __future__ import annotations

LANGS = ("en", "de", "fr")
STYLES = ("beginner", "expert")

# Characters spoken per second at a broadcast pace. Measured with Chrome local voices (about 12 to 13 at rate 1); ui/src/speech.ts plans with the same figures.
CPS = {"en": 12.5, "de": 12.0, "fr": 13.0}
PAUSE_S = 0.3


def est_seconds(text: str, lang: str) -> float:
    return len(text) / CPS[lang] + PAUSE_S


def fmt_num(value: float, lang: str, digits: int = 2) -> str:
    s = f"{value:.{digits}f}"
    return s.replace(".", ",") if lang in ("de", "fr") else s
