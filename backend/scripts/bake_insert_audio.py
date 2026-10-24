"""Bake the recorded insert's voice: one mp3 per spoken line of ui/public/insert/replay.json, made once with ElevenLabs.

    .venv/bin/python backend/scripts/bake_insert_audio.py            # dry run: lines, characters, credits, no call
    .venv/bin/python backend/scripts/bake_insert_audio.py --go       # synthesise what is missing (spends credits)

Files land in ui/public/insert/audio/<ch>-<m>.mp3 and are skipped when they exist, so a rerun costs nothing. A hard cap
(--max-credits) stops the run before it spends more. Voices: Charlie calls the play in English, Daniel does the colour and
all of German and French (docs/VOICES.md). Energy per line: goal peak, analyst calm, the rest rising (commentary/delivery.py).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from matchvoice.config import elevenlabs_api_key  # noqa: E402
from matchvoice.commentary.delivery import shape_for_tts, voice_settings  # noqa: E402
from matchvoice.tts.client import ElevenLabsClient  # noqa: E402
from matchvoice.tts.voices import CREDITS_PER_CHAR, MODEL  # noqa: E402

CHARLIE = "IKne3meq5aSn9XLyUdCD"
DANIEL = "onwK4e9ZLuTAKqWW03F9"
REPLAY = ROOT / "ui/public/insert/replay.json"
OUT = ROOT / "ui/public/insert/audio"


def voice_of(lang: str, role: str) -> str:
    return CHARLIE if lang == "en" and role == "pbp" else DANIEL


def energy_of(say: dict) -> str:
    if say["kind"].startswith("shot_goal") or say["kind"] == "goal":
        return "peak"
    return "calm" if say["voice"] == "analyst" else "rising"


def lines() -> list[dict]:
    data = json.loads(REPLAY.read_text())
    lang_of = {c["id"]: c["lang"] for c in data["hello"]["channels"]}
    seen: dict[tuple[int, int], dict] = {}
    for msg in data["messages"]:
        if msg.get("k") == "say" and msg["text"]:
            seen[(msg["ch"], msg["m"])] = {**msg, "lang": lang_of[msg["ch"]]}
    return list(seen.values())


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--max-credits", type=float, default=900.0)
    args = ap.parse_args()
    todo = [s for s in lines() if not (OUT / f"{s['ch']}-{s['m']}.mp3").exists()]
    chars = sum(len(shape_for_tts(s["text"], s["lang"])) for s in todo)
    credits = chars * CREDITS_PER_CHAR[MODEL]
    print(f"{len(todo)} lines to make, {chars} characters, about {credits:.0f} credits")
    if not args.go:
        return
    if credits > args.max_credits:
        sys.exit(f"over the cap of {args.max_credits:.0f} credits, nothing sent")
    key = elevenlabs_api_key()
    if not key:
        sys.exit("no ELEVENLABS_API_KEY")
    client = ElevenLabsClient(key)
    OUT.mkdir(parents=True, exist_ok=True)
    spent = 0.0
    for s in todo:
        text = shape_for_tts(s["text"], s["lang"])
        audio, cost = await client.synth(text, voice_of(s["lang"], s["voice"]), s["lang"],
                                         voice_settings=voice_settings(energy_of(s), MODEL))
        (OUT / f"{s['ch']}-{s['m']}.mp3").write_bytes(audio)
        spent += cost if cost is not None else len(text) * CREDITS_PER_CHAR[MODEL]
        print(f"  {s['ch']}-{s['m']} {s['lang']} {energy_of(s)} {len(audio)} bytes, cost reported {cost}")
    print(f"done, {spent:.0f} credits")


asyncio.run(main())
