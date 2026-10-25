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
from matchvoice.commentary.delivery import hype_for_tts, shape_for_tts, voice_settings  # noqa: E402
from matchvoice.tts.client import ElevenLabsClient  # noqa: E402
from matchvoice.tts.voices import CREDITS_PER_CHAR, HYPE_MODEL, MODEL  # noqa: E402

CHARLIE = "IKne3meq5aSn9XLyUdCD"
DANIEL = "onwK4e9ZLuTAKqWW03F9"
INSERTS = {"goal": (ROOT / "ui/public/insert/replay.json", ROOT / "ui/public/insert/audio"),
           "story": (ROOT / "ui/public/insert/story.json", ROOT / "ui/public/insert/story-audio")}
REPLAY, OUT = INSERTS["goal"]


def voice_of(lang: str, role: str) -> str:
    """Two people in the booth in every language: Charlie calls the play, Daniel is the co-commentator."""
    return CHARLIE if role == "pbp" else DANIEL


GOAL_KINDS = {"shot_goal", "goal"}
LIFT_KINDS = {"shot_saved", "shot_post", "big_save_analysis", "big_chance_analysis", "goal_analysis", "red"}


def energy_of(say: dict) -> str:
    """The goal call is shouted; what follows a goal or a big chance is still up; ordinary play is calm."""
    if say["kind"] in GOAL_KINDS:
        return "peak"
    return "rising" if say["kind"] in LIFT_KINDS else "calm"


def model_of(energy: str) -> str:
    return HYPE_MODEL if energy != "calm" else MODEL


def text_of(s: dict) -> str:
    e = energy_of(s)
    return hype_for_tts(shape_for_tts(s["text"], s["lang"]), s["lang"], e, model_of(e))


def lines() -> list[dict]:
    data = json.loads(REPLAY.read_text(encoding="utf-8"))
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
    ap.add_argument("--insert", choices=sorted(INSERTS), default="goal", help="goal: the 21 s insert, story: the two-part story insert")
    ap.add_argument("--channel", type=int, default=None, help="only this channel id (1 = en/expert), to listen before baking all six")
    args = ap.parse_args()
    global REPLAY, OUT
    REPLAY, OUT = INSERTS[args.insert]
    todo = [s for s in lines() if not (OUT / f"{s['ch']}-{s['m']}.mp3").exists() and (args.channel is None or s["ch"] == args.channel)]
    chars = sum(len(text_of(s)) for s in todo)
    credits = sum(len(text_of(s)) * CREDITS_PER_CHAR[model_of(energy_of(s))] for s in todo)
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
        e = energy_of(s)
        text, model = text_of(s), model_of(e)
        audio, cost = await client.synth(text, voice_of(s["lang"], s["voice"]), s["lang"], model=model,
                                         voice_settings=voice_settings(e, model))
        (OUT / f"{s['ch']}-{s['m']}.mp3").write_bytes(audio)
        spent += cost if cost is not None else len(text) * CREDITS_PER_CHAR[model]
        print(f"  {s['ch']}-{s['m']} {s['lang']} {energy_of(s)} {len(audio)} bytes, cost reported {cost}")
    print(f"done, {spent:.0f} credits")


if __name__ == "__main__":
    asyncio.run(main())
