"""Thin async ElevenLabs client (httpx). Knows nothing about budgets: GuardedTTS decides whether a call may happen."""
from __future__ import annotations

import httpx

from .voices import LANGUAGE_CODES, MODEL, OUTPUT_FORMAT

API = "https://api.elevenlabs.io"


class UpstreamError(RuntimeError):
    """The API answered with an error or could not be reached. The message never contains the key."""


class ElevenLabsClient:
    def __init__(self, api_key: str, timeout_s: float = 30.0):
        self._headers = {"xi-api-key": api_key}
        self._timeout = timeout_s

    async def synth(self, text: str, voice_id: str, lang: str, model: str = MODEL,
                    voice_settings: dict | None = None) -> tuple[bytes, float | None]:
        """One plain (non-streaming) request: Flash answers in well under a second and the whole mp3 is cached.
        Returns the mp3 and the cost in characters the API reports (`character-cost`), if it does. No retry: a retry would bill again."""
        body = {"text": text, "model_id": model, "language_code": LANGUAGE_CODES.get(lang, lang)}
        if voice_settings:  # per-energy delivery (commentary/delivery.py), only when GuardedTTS runs with delivery on
            body["voice_settings"] = voice_settings
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                res = await http.post(f"{API}/v1/text-to-speech/{voice_id}", params={"output_format": OUTPUT_FORMAT},
                                      headers={**self._headers, "accept": "audio/mpeg"}, json=body)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"speech service unreachable ({type(exc).__name__})") from None
        if res.status_code != 200:
            raise UpstreamError(f"speech service answered HTTP {res.status_code}")
        cost = res.headers.get("character-cost")
        return res.content, float(cost) if cost and cost.replace(".", "", 1).isdigit() else None

    async def subscription(self) -> dict:
        """Free: the plan and its character counter."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                res = await http.get(f"{API}/v1/user/subscription", headers=self._headers)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"speech service unreachable ({type(exc).__name__})") from None
        if res.status_code != 200:
            raise UpstreamError(f"speech service answered HTTP {res.status_code}")
        return res.json()
