"""Local dev server for the live "New run" in ui/public/mock4.html: the public API with a FAKE model and a fake voice.

No key, no network, no cost: the core booth and the world booth answer with canned lines after a delay, and the voice returns a
baked mp3 of the recorded insert (so the page's audio path really plays). The page is served from a second port, so CORS and
the WebSocket Origin check run as on the deployed pair (Static Web Apps page, Container Apps API).

    .venv/bin/python docs/live/devserver.py                    # API on 8790, page on 8791
    open "http://127.0.0.1:8791/mock4.html?api=http://127.0.0.1:8790"

Switches for the refusal paths: --session-runs 1, --concurrent 1, --tts off|over|fail, --no-secret, --delay 2.0.
A fixed play of the generated scene: --not-public, then add &seed=N to the page URL (the public server refuses a seed).
"""
from __future__ import annotations

import argparse
import asyncio
import functools
import http.server
import json
import os
import re
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("MATCHVOICE_NO_DOTENV", "1")  # never read .env

import uvicorn  # noqa: E402

from matchvoice.commentary.analyst import KEYS, CallBudget  # noqa: E402
from matchvoice.pipeline.library import Library  # noqa: E402
from matchvoice.pipeline.runner import DailyCalls, LiveConfig, LiveLimits  # noqa: E402
from matchvoice.server.app import create_app  # noqa: E402
from matchvoice.server.public import PublicGate  # noqa: E402
from matchvoice.tts import MODEL, GuardedTTS  # noqa: E402

GOOD = {"en": "That is the move of the night, and Wexmoor have turned this round late.",
        "de": "Das ist der Spielzug des Abends, und Wexmoor dreht die Partie spät.",
        "fr": "C'est le mouvement de la soirée, et Wexmoor renverse tout en fin de match."}
GOAL_WORLD = {"es/expert": "¡GOOOL! ¡{n}! ¡Wexmoor por delante!", "it/beginner": "GOOOL! {n}! Wexmoor in vantaggio!",
              "pt/expert": "GOOOL! {n}! Wexmoor na frente!", "nl/beginner": "GOAL! {n}! Wexmoor op voorsprong!",
              "tr/expert": "GOOOL! {n}! Wexmoor öne geçti!", "ja/beginner": "ゴール！{ja}！ウェックスムーア、勝ち越し！"}
KATAKANA = {"Tavares": "タバレス", "Dacosta": "ダコスタ", "Fontaine": "フォンテーヌ", "Abara": "アバラ"}  # the scene's attackers
PLAIN_WORLD = {"es/expert": "Sigue la jugada.", "it/beginner": "Si gioca.", "pt/expert": "Segue o jogo.", "nl/beginner": "Er wordt gespeeld.",
               "tr/expert": "Oyun sürüyor.", "ja/beginner": "プレー続行。"}


def fake_core(delay: float):
    async def call(prompt: str) -> str:
        await asyncio.sleep(delay)
        return json.dumps({k: GOOD[k.split("/")[0]] for k in KEYS})
    return call


def fake_world(delay: float):
    async def call(prompt: str) -> str:
        await asyncio.sleep(delay * 0.6)
        m = re.search(r"Moment kind (\w+)", prompt)
        if not (m and m.group(1) == "shot_goal"):
            return json.dumps(PLAIN_WORLD, ensure_ascii=False)
        who = re.search(r'"player": "([^"]+)"', prompt)  # the scorer of this run's goal: the scene's play changes per run
        n = who.group(1) if who else "Wexmoor"
        return json.dumps({k: v.format(n=n, ja=KATAKANA.get(n, n)) for k, v in GOAL_WORLD.items()}, ensure_ascii=False)
    return call


class DevSynth:
    """Stands in for ElevenLabs: a real mp3 from the recorded insert, so the browser plays something; or a failure."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.mp3 = (ROOT / "ui/public/insert/story-audio/0-1189569.mp3").read_bytes()

    async def __call__(self, text, voice_id, lang, model, voice_settings=None):
        from matchvoice.tts.client import UpstreamError
        await asyncio.sleep(0.4)
        if self.fail:
            raise UpstreamError("speech service answered HTTP 500")
        return self.mp3, None


def serve_page(port: int) -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "ui/public"))
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--page-port", type=int, default=8791, help="0: do not serve ui/public")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds the fake model takes per call")
    ap.add_argument("--session-runs", type=int, default=3)
    ap.add_argument("--concurrent", type=int, default=3)
    ap.add_argument("--tts", choices=["ok", "off", "over", "fail"], default="ok")
    ap.add_argument("--no-secret", action="store_true")
    ap.add_argument("--live-off", action="store_true", help="no live config at all (health says live off)")
    ap.add_argument("--not-public", action="store_true", help="no PublicGate: no sessions or caps, and the page's ?seed= picks the play")
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="mv-dev-"))
    live = None if a.live_off else LiveConfig(fake_core(a.delay), CallBudget(500), "fake", tmp / "analyst", fresh=True,
                                              limits=LiveLimits(75, 150), world_call=fake_world(a.delay), daily=DailyCalls(600))
    if live is not None:
        live.world_skip_late = True
    tts = None
    if a.tts != "off":
        tts = GuardedTTS(DevSynth(fail=a.tts == "fail"), 5 if a.tts == "over" else 3000, MODEL, tmp / "tts", daily_credits=3000)
    gate = None if a.not_public else PublicGate(None if a.no_secret else b"dev-secret-not-real", session_runs=a.session_runs,
                                                  concurrent=a.concurrent)
    origins = [f"http://127.0.0.1:{a.page_port}", f"http://localhost:{a.page_port}"]
    app = create_app(Library(), live, None, ROOT / "nonexistent-dist", tts, public=gate, allowed_origins=origins)
    if a.page_port:
        serve_page(a.page_port)
        print(f"page: http://127.0.0.1:{a.page_port}/mock4.html?api=http://127.0.0.1:{a.port}")
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
