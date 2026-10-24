"""Settings from the environment and a git-ignored .env file."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
# MATCHVOICE_NO_DOTENV=1 ignores the file, e.g. to test or run the public demo without any key
_ENV = {} if os.environ.get("MATCHVOICE_NO_DOTENV") else dotenv_values(ROOT / ".env")


def anthropic_api_key() -> str | None:
    """First key found: ANTHROPIC_API_KEY_2, ANTHROPIC_API_KEY, ANTHROPIC_KEY."""
    for name in ("ANTHROPIC_API_KEY_2", "ANTHROPIC_API_KEY", "ANTHROPIC_KEY"):
        value = os.environ.get(name) or _ENV.get(name)
        if value:
            return value.strip()
    return None


def elevenlabs_api_key() -> str | None:
    """ELEVENLABS_API_KEY from the environment or the .env file. Optional: without it the UI uses the browser voice."""
    value = os.environ.get("ELEVENLABS_API_KEY") or _ENV.get("ELEVENLABS_API_KEY")
    return value.strip() if value else None
