"""GuardedTTS: disk cache, hard credit budget, usage ledger. The TTS twin of GuardedLLM.

A line is synthesised at most once per (model, voice, language, text). A call that would take the budget over its
limit is refused before any request is made, so spending never overshoots. The budget counts every entry of the
ledger file, so a restart does not reset it. An optional daily cap counts only the ledger rows of the current UTC day (their
`at` field), so it rolls over at midnight UTC. The key is never logged and never part of an error message.
"""
from __future__ import annotations

import asyncio
import hashlib
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

import orjson

from ..commentary.delivery import shape_for_tts, voice_settings
from ..config import ROOT, elevenlabs_api_key
from .client import ElevenLabsClient, UpstreamError
from .voices import CREDITS_PER_CHAR, MAX_CHARS, MODEL, voice_for

DEFAULT_CREDITS = 300
DEFAULT_DAILY_CREDITS = 3000  # the server's cap per UTC day (env MATCHVOICE_TTS_DAILY_CREDITS); GuardedTTS itself has none unless given
Synth = Callable[..., Awaitable[tuple[bytes, float | None]]]  # text, voice id, lang, model [, voice_settings=...] -> mp3, reported cost


class TTSError(RuntimeError):
    code = "tts_error"


class TTSUnavailable(TTSError):
    code = "tts_unavailable"


class TTSBudgetExceeded(TTSError):
    code = "tts_over_budget"


class TTSDailyExceeded(TTSBudgetExceeded):
    code = "tts_daily_limit"


class GuardedTTS:
    def __init__(self, synth: Synth, max_credits: float = DEFAULT_CREDITS, model: str = MODEL,
                 cache_dir: Path | None = None, ledger: Path | None = None, delivery: bool = False,
                 daily_credits: float | None = None, clock=time.time):
        if model not in CREDITS_PER_CHAR:
            raise ValueError(f"no credit factor for model {model!r}")
        self._synth, self.max_credits, self.model = synth, float(max_credits), model
        # delivery: speak(text, lang, energy) sends the text shaped for speech and the voice_settings of that energy level
        # (commentary/delivery.py). Off by default, so the text and the cache keys are exactly what they were before.
        self.delivery = delivery
        self.cache_dir = cache_dir if cache_dir is not None else ROOT / "data" / "cache" / "tts"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ledger = ledger if ledger is not None else self.cache_dir / "ledger.jsonl"
        self._reserved = 0.0  # credits of calls under way
        self._inflight: dict[str, asyncio.Task] = {}
        self.calls = 0  # real requests made by this process
        self.daily_credits = float(daily_credits) if daily_credits else None  # None: no daily cap, the lifetime budget only
        self._clock = clock  # epoch seconds, as in the ledger's `at`
        self.hits = 0  # lines served from the disk cache by this process

    # ---------- accounting ----------
    @property
    def spent(self) -> float:
        """Credits billed so far, from the ledger (all runs of this ledger file)."""
        if not self.ledger.exists():
            return 0.0
        total = 0.0
        for line in self.ledger.read_bytes().splitlines():
            if line.strip():
                total += float(orjson.loads(line)["credits"])
        return total

    def _rows(self) -> list[dict]:
        if not self.ledger.exists():
            return []
        return [orjson.loads(line) for line in self.ledger.read_bytes().splitlines() if line.strip()]

    @property
    def spent_today(self) -> float:
        """Credits billed since midnight UTC, from the ledger rows' `at`."""
        now = datetime.fromtimestamp(self._clock(), timezone.utc)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        return sum(float(r["credits"]) for r in self._rows() if float(r.get("at", 0.0)) >= midnight)

    @property
    def remaining_today(self) -> float | None:
        if self.daily_credits is None:
            return None
        return max(0.0, self.daily_credits - self.spent_today - self._reserved)

    @property
    def remaining(self) -> float:
        left = max(0.0, self.max_credits - self.spent - self._reserved)
        today = self.remaining_today
        return left if today is None else min(left, today)

    def cost(self, text: str) -> float:
        return math.ceil(len(text) * CREDITS_PER_CHAR[self.model])

    def status(self) -> dict:
        """What /api/health shows: no key, no text."""
        out = {"available": self.remaining > 0, "model": self.model, "credits_max": self.max_credits,
               "credits_spent": self.spent, "credits_left": self.remaining}
        if self.daily_credits is not None:
            out.update(credits_per_day=self.daily_credits, credits_today_left=self.remaining_today)
        return out


    # ---------- cache ----------
    def _path(self, text: str, voice_id: str, lang: str, energy: str | None = None) -> Path:
        key = f"{self.model}|{voice_id}|{lang}|{text}" + (f"|{energy}" if energy else "")
        return self.cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()[:32]}.mp3"

    def _prepare(self, text: str, lang: str, energy: str | None) -> tuple[str, str | None]:
        """The text that is sent (shaped for speech when delivery is on) and the energy that is part of the cache key."""
        if self.delivery and energy:
            return shape_for_tts(text, lang), energy
        return text, None

    def cached(self, text: str, lang: str, energy: str | None = None, who: str | None = None) -> bool:
        sent, key_energy = self._prepare(text.strip(), lang, energy)
        return self._path(sent, voice_for(lang, who).id, lang, key_energy).exists()

    def cost_of(self, text: str, lang: str, energy: str | None = None, who: str | None = None) -> float:
        """What speak() would bill for this line now: 0 when it is cached. Raises KeyError when no voice exists."""
        voice_for(lang, who)
        if self.cached(text, lang, energy, who):
            return 0.0
        return self.cost(self._prepare(text.strip(), lang, energy)[0])

    def _record(self, text: str, voice_id: str, lang: str, credits: float, reported: float | None) -> None:
        row = {"at": round(self._clock(), 1), "model": self.model, "voice": voice_id, "lang": lang, "chars": len(text),
               "credits": credits, "reported_chars": reported}
        with self.ledger.open("ab") as fh:
            fh.write(orjson.dumps(row) + b"\n")

    # ---------- the one entry point ----------
    async def speak(self, text: str, lang: str, energy: str | None = None, who: str | None = None) -> tuple[bytes, bool]:
        """The mp3 for `text` and whether it came from the cache. Raises TTSBudgetExceeded without making a request.
        With delivery on and an `energy` (calm | rising | peak) the line is shaped for speech and sent with that level's
        voice settings; the credits are counted on the text actually sent. `who`: the speaker, whose own voice is used (voices.CAST);
        without it the language's voice. Raises KeyError when there is no voice for either."""
        text = text.strip()
        if not text or len(text) > MAX_CHARS:
            raise TTSError(f"text must be 1 to {MAX_CHARS} characters")
        voice = voice_for(lang, who)
        text, energy = self._prepare(text, lang, energy)
        path = self._path(text, voice.id, lang, energy)
        if path.exists():
            self.hits += 1
            return path.read_bytes(), True
        task = self._inflight.get(path.name)
        if task is None:
            need = self.cost(text)
            today = self.remaining_today
            if today is not None and need > today and need <= max(0.0, self.max_credits - self.spent - self._reserved):
                raise TTSDailyExceeded(f"today's voice credits are used ({today:.0f} of {self.daily_credits:.0f} left, "
                                       f"this line needs {need:.0f}); back after midnight UTC")
            if need > self.remaining:  # all or nothing: never a partial spend
                raise TTSBudgetExceeded(f"voice credit budget reached ({self.remaining:.0f} of {self.max_credits:.0f} left, "
                                        f"this line needs {need:.0f})")
            self._reserved += need
            task = self._inflight[path.name] = asyncio.ensure_future(self._fetch(text, voice.id, lang, path, need, energy))
            task.add_done_callback(lambda t, name=path.name: self._settled(name, t))
        return await asyncio.shield(task), False  # a second request for a line under way waits for it, one bill

    async def _fetch(self, text: str, voice_id: str, lang: str, path: Path, need: float, energy: str | None = None) -> bytes:
        extra = {"voice_settings": voice_settings(energy, self.model)} if energy else {}  # nothing extra without energy: the call is what it always was
        try:
            audio, reported = await self._synth(text, voice_id, lang, self.model, **extra)
        except UpstreamError as exc:
            raise TTSUnavailable(str(exc)) from None
        finally:
            self._reserved -= need
        self.calls += 1
        billed = need  # the estimate; `reported` (the API's own character-cost header) is kept in the ledger as evidence
        self._record(text, voice_id, lang, billed, reported)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(audio)
        os.replace(tmp, path)
        return audio

    def _settled(self, name: str, task: asyncio.Task) -> None:
        self._inflight.pop(name, None)
        if not task.cancelled():
            task.exception()  # a call nobody waits for any more may fail quietly


def from_env(max_credits: float | None = None, model: str = MODEL, cache_dir: Path | None = None,
             delivery: bool | None = None, daily_credits: float | None = None) -> GuardedTTS | None:
    """The real thing when ELEVENLABS_API_KEY is set, else None (the UI then uses the browser voice)."""
    key = elevenlabs_api_key()
    if not key:
        return None
    if max_credits is None:
        max_credits = float(os.environ.get("MATCHVOICE_TTS_CREDITS", DEFAULT_CREDITS))
    if delivery is None:
        delivery = os.environ.get("MATCHVOICE_TTS_DELIVERY") == "1"
    if daily_credits is None:
        daily_credits = float(os.environ.get("MATCHVOICE_TTS_DAILY_CREDITS", DEFAULT_DAILY_CREDITS))
    return GuardedTTS(ElevenLabsClient(key).synth, max_credits, model, cache_dir, delivery=delivery, daily_credits=daily_credits or None)
