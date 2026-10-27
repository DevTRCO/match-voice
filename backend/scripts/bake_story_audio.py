"""Bake the voice of the story insert: one mp3 per spoken line of ui/public/insert/story.json, every channel, eleven_v4.

    .venv/bin/python backend/scripts/bake_story_audio.py              # dry run: lines, characters, credits, files to delete; no call
    .venv/bin/python backend/scripts/bake_story_audio.py --go         # synthesise what is missing or stale (spends credits)
    .venv/bin/python backend/scripts/bake_story_audio.py --channel 6  # only one channel, to listen first

Files land in ui/public/insert/story-audio/<ch>-<m>.mp3 (the URL scheme of ui/src/feed.ts and ui/public/mock4.html).
story-audio/manifest.json keeps a hash per file of what was sent (voice, model, settings, spoken text) and the caption it speaks:
a file whose hash still matches is skipped, a stale one is made again, and a file no line needs any more is deleted.
The player plays a file only when the manifest caption equals the subtitle, so a stale file is never heard.

Cast: each line is voiced by its speaker (the `who` field of the say; the lead or the co of a two-person booth, the solo
commentator of a world booth), the voice ids below. Delivery as approved in the v4 audition: short bracketed tags,
the goal call shouted ([shouting], low stability, high style), lifted lines [excited], the rest untagged.
At most two requests run at a time (the account allows three). A hard cap (--max-credits) stops before it is passed;
the credits counted are the API's `character-cost` header.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from matchvoice.config import elevenlabs_api_key  # noqa: E402
from matchvoice.commentary.delivery import hype_for_tts, shape_for_tts, voice_settings  # noqa: E402
from matchvoice.tts.client import ElevenLabsClient  # noqa: E402
from matchvoice.tts.voices import CREDITS_PER_CHAR  # noqa: E402

STORY = ROOT / "ui/public/insert/story.json"
OUT = ROOT / "ui/public/insert/story-audio"
MANIFEST = OUT / "manifest.json"
MODEL = "eleven_v4"
CONCURRENCY = 2

# person -> ElevenLabs voice id (premade or account voices; none is added or removed by this script)
CAST: dict[str, str] = {
    "Charlie Hale": "IKne3meq5aSn9XLyUdCD",   # Charlie
    "Owen Carter": "TX3LPaxmHKxFdv7VOQHJ",    # Liam
    "Jonas Weber": "vGWWh1bodhwwi4yHd6qZ",    # Marcus
    "Felix Brandt": "iQ5dS7juUUF7zgIVf8ET",   # Leo
    "Hugo Martin": "JBFqnCBsd6RMkjVDRZzb",    # George
    "Théo Laurent": "bIHbv24MWmeRgasZH58o",   # Will
    "Daniel Price": "onwK4e9ZLuTAKqWW03F9",   # Daniel
    "Kim Berger": "DEZHhPbmb8LVZmWufkCh",     # Anna
    "Sacha Morel": "pqHfZKP75CvOlQylNhV4",    # Bill
    # the six solo world commentators: distinct premade voices of matching gender and age (GET /v2/voices)
    "Lucía Romero": "EXAVITQu4vr4xnSDxMaL",   # Sarah, female, young, verified es
    "Giulia Conti": "XrExE9yKIg1WjnnlVkGX",   # Matilda, female, upbeat, verified it
    "Rafael Souza": "cjVigY5qzO86Huf0OWal",   # Eric, male, middle aged, verified pt
    "Sanne de Vries": "pFZP5JQG7iQjIQuC4Bku", # Lily, female, middle aged, verified nl
    "Emre Aydın": "nPczCjzI2devNBz1zQrb",     # Brian, male, middle aged, deep
    "Yuki Tanaka": "cgSgspJ2msm6clMCkdW9",    # Jessica, female, young, verified ja
}

GOAL_KINDS = {"shot_goal", "goal"}
LIFT_KINDS = {"shot_saved", "shot_post", "big_save_analysis", "big_chance_analysis", "goal_analysis", "red"}
# v4 delivery: the goal call with low stability and high style (the audition); the others from commentary/delivery.py
PEAK_V4 = {"stability": 0.25, "style": 0.8}


def energy_of(say: dict) -> str:
    """The goal call is shouted; the pay-off and a line the caller ends on "!" are lifted; ordinary play is calm."""
    if say["kind"] in GOAL_KINDS:
        return "peak"
    if say["kind"] in LIFT_KINDS or say["text"].rstrip().endswith(("!", "！")):
        return "rising"
    return "calm"


def settings_of(energy: str) -> dict:
    s = voice_settings(energy, MODEL)
    if energy == "peak":
        s.update(PEAK_V4)
    return s


def who_of(say: dict) -> str:
    w = say.get("who")
    return w["name"] if isinstance(w, dict) else str(w)


def plan() -> list[dict]:
    """Every say with text, keyed by channel and moment, with what will be sent and its hash."""
    data = json.loads(STORY.read_text(encoding="utf-8"))
    lang_of = {c["id"]: c["lang"] for c in data["hello"]["channels"]}
    seen: dict[str, dict] = {}
    for msg in data["messages"]:
        if msg.get("k") != "say" or not msg.get("text"):
            continue
        lang, e = lang_of[msg["ch"]], energy_of(msg)
        who = who_of(msg)
        if who not in CAST:
            sys.exit(f"no voice for {who!r} (channel {msg['ch']}, moment {msg['m']})")
        shaped = shape_for_tts(msg["text"], lang)
        shaped = shaped[:1].upper() + shaped[1:]  # a spoken score at the start ("1-1, e ..." -> "uno a uno, e ...") opens the sentence
        text = hype_for_tts(shaped, lang, e, MODEL)
        vs = settings_of(e)
        key = f"{msg['ch']}-{msg['m']}"
        sha = hashlib.sha256(json.dumps([CAST[who], MODEL, lang, vs, text], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
        seen[key] = {"key": key, "ch": msg["ch"], "m": msg["m"], "lang": lang, "who": who, "voice": CAST[who], "energy": e,
                     "send": text, "caption": msg["text"], "settings": vs, "sha": sha}
    return list(seen.values())


def load_manifest() -> dict:
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"model": MODEL, "files": {}}


def save_manifest(man: dict) -> None:
    MANIFEST.write_text(json.dumps(man, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--max-credits", type=float, default=11000.0)
    ap.add_argument("--channel", type=int, default=None, help="only this channel id")
    ap.add_argument("--limit", type=int, default=None, help="make at most this many files (a first probe)")
    ap.add_argument("--quiet", action="store_true", help="do not print every line")
    args = ap.parse_args()
    lines = plan()
    man = load_manifest()
    files = man.setdefault("files", {})
    wanted = {s["key"] for s in lines}
    todo = [s for s in lines if (args.channel is None or s["ch"] == args.channel)
            and not ((OUT / f"{s['key']}.mp3").exists() and files.get(s["key"], {}).get("sha") == s["sha"])]
    todo.sort(key=lambda s: (s["ch"], s["m"]))
    stale = len(todo)
    if args.limit is not None:
        todo = todo[:args.limit]
    orphans = sorted(p.name for p in OUT.iterdir() if p.name != MANIFEST.name and p.stem not in wanted) if OUT.exists() else []
    chars = sum(len(s["send"]) for s in todo)
    rate = CREDITS_PER_CHAR[MODEL]
    if not args.quiet:
        for s in todo:
            print(f"  {s['key']:>11} {s['lang']} {s['who']:<15} {s['energy']:<6} {len(s['send']):>3} | {s['send']}")
    print(f"{len(lines)} lines in the insert, {len(lines) - stale} up to date; {len(todo)} to make, {chars} characters, "
          f"about {chars * rate:.0f} credits ({MODEL}, {rate} a character)")
    if orphans:
        print(f"{len(orphans)} files no line needs, deleted with --go: {', '.join(orphans)}")
    if not args.go:
        return
    if chars * rate > args.max_credits:
        sys.exit(f"over the cap of {args.max_credits:.0f} credits, nothing sent")
    key = elevenlabs_api_key()
    if not key:
        sys.exit("no ELEVENLABS_API_KEY")
    OUT.mkdir(parents=True, exist_ok=True)
    for name in orphans:
        (OUT / name).unlink()
    for k in [k for k in files if k not in wanted]:
        del files[k]
    man["model"] = MODEL
    save_manifest(man)
    client = ElevenLabsClient(key, timeout_s=90.0)
    gate = asyncio.Semaphore(CONCURRENCY)
    state = {"spent": 0.0, "reserved": 0.0, "made": 0, "stop": None}

    async def one(s: dict) -> None:
        async with gate:
            est = len(s["send"]) * rate
            if state["stop"]:
                return
            if state["spent"] + state["reserved"] + est > args.max_credits:
                state["stop"] = f"cap {args.max_credits:.0f} reached before {s['key']}"
                return
            state["reserved"] += est
            try:
                audio, cost = await client.synth(s["send"], s["voice"], s["lang"], model=MODEL, voice_settings=s["settings"])
            except Exception as exc:  # no retry: a retry would bill again
                state["stop"] = f"{s['key']}: {exc}"
                return
            finally:
                state["reserved"] -= est
            state["spent"] += cost if cost is not None else est
            (OUT / f"{s['key']}.mp3").write_bytes(audio)
            files[s["key"]] = {"sha": s["sha"], "caption": s["caption"], "who": s["who"], "voice": s["voice"], "lang": s["lang"],
                               "energy": s["energy"], "sent": s["send"], "cost": cost}
            save_manifest(man)
            state["made"] += 1
            print(f"  {s['key']:>11} {s['lang']} {s['who']:<15} {len(audio):>6} bytes, character-cost {cost}, total {state['spent']:.0f}", flush=True)

    await asyncio.gather(*(one(s) for s in todo))
    print(f"done: {state['made']} files, {state['spent']:.0f} credits (sum of character-cost)")
    if state["stop"]:
        sys.exit(f"stopped: {state['stop']}")


if __name__ == "__main__":
    asyncio.run(main())
