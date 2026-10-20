"""Settings from the environment and a git-ignored .env file."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
_ENV = dotenv_values(ROOT / ".env")


def anthropic_api_key() -> str | None:
    """First key found: ANTHROPIC_API_KEY_2, ANTHROPIC_API_KEY, ANTHROPIC_KEY."""
    for name in ("ANTHROPIC_API_KEY_2", "ANTHROPIC_API_KEY", "ANTHROPIC_KEY"):
        value = os.environ.get(name) or _ENV.get(name)
        if value:
            return value.strip()
    return None
