"""Optional spoken commentary through ElevenLabs. The key stays on the server; the browser voice is the fallback."""
from .guarded import GuardedTTS, TTSBudgetExceeded, TTSDailyExceeded, TTSError, TTSUnavailable, from_env
from .voices import CREDITS_PER_CHAR, MODEL, voice_for

__all__ = ["CREDITS_PER_CHAR", "GuardedTTS", "MODEL", "TTSBudgetExceeded", "TTSDailyExceeded", "TTSError", "TTSUnavailable", "from_env", "voice_for"]
