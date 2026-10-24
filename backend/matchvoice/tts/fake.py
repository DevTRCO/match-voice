"""A TTS that never touches the network, for tests. It returns a few bytes that look like an mp3 frame header."""
from __future__ import annotations

FAKE_MP3 = b"\xff\xfb\x90\x00" + b"\x00" * 60


class FakeSynth:
    def __init__(self, fail: bool = False, reported: float | None = None):
        self.fail, self.reported = fail, reported
        self.calls: list[tuple[str, str, str]] = []
        self.settings: list[dict | None] = []

    async def __call__(self, text: str, voice_id: str, lang: str, model: str,
                       voice_settings: dict | None = None) -> tuple[bytes, float | None]:
        from .client import UpstreamError
        self.calls.append((text, voice_id, lang))
        self.settings.append(voice_settings)
        if self.fail:
            raise UpstreamError("speech service answered HTTP 500")
        return FAKE_MP3 + text.encode(), self.reported
