"""python -m matchvoice.server --port 8000 [--live-calls 12]

Replay always works. Live needs --live-calls N (the server-wide model call budget) and a key
in the environment or the git-ignored .env. Containers set MATCHVOICE_HOST, PORT and MATCHVOICE_LIVE_CALLS.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from ..pipeline.library import Library
from ..pipeline.runner import LiveConfig, LiveLimits, LiveUnavailable
from ..tts import from_env as tts_from_env
from .app import create_app


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("MATCHVOICE_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--live-calls", type=int, default=int(os.environ.get("MATCHVOICE_LIVE_CALLS", "0")),
                    help="model call budget for live mode, 0 disables it (env MATCHVOICE_LIVE_CALLS)")
    ap.add_argument("--live-fresh", action="store_true", default=os.environ.get("MATCHVOICE_LIVE_FRESH") == "1",
                    help="live mode never reads the answer cache, every analyst line is a real call (env MATCHVOICE_LIVE_FRESH=1)")
    ap.add_argument("--live-max-seconds", type=float, default=float(os.environ.get("MATCHVOICE_LIVE_MAX_SECONDS", "75")),
                    help="longest live run in match seconds (until - start); a live run without until is refused, 0 turns the cap off (env MATCHVOICE_LIVE_MAX_SECONDS)")
    ap.add_argument("--live-runs-per-day", type=int, default=int(os.environ.get("MATCHVOICE_LIVE_RUNS_PER_DAY", "150")),
                    help="live runs that may start per UTC day, 0 turns the cap off; counted in memory, a restart resets it (env MATCHVOICE_LIVE_RUNS_PER_DAY)")
    ap.add_argument("--tts-credits", type=float, default=None,
                    help="ElevenLabs credit budget for spoken lines, counted from the ledger in data/cache/tts (default 300, env MATCHVOICE_TTS_CREDITS)")
    ap.add_argument("--tts-delivery", action="store_true",
                    help="send ElevenLabs text shaped for speech and voice settings per energy level (env MATCHVOICE_TTS_DELIVERY=1); off by default")
    ap.add_argument("--no-tts", action="store_true", help="never use ElevenLabs, the browser voice speaks")
    ap.add_argument("--data", type=Path, default=None, help="data folder, default <repo>/data")
    ap.add_argument("--ui", type=Path, default=None, help="built UI folder, default <repo>/ui/dist")
    a = ap.parse_args()
    live, live_error = None, None
    try:
        live = LiveConfig.from_env(a.live_calls, fresh=a.live_fresh,
                                   limits=LiveLimits(a.live_max_seconds, a.live_runs_per_day))
    except LiveUnavailable as exc:
        live_error = exc
    print("replay: ready" if live is None else f"live: ready, budget {live.budget.max_calls} calls"
          + (", fresh (no answer cache)" if live.fresh else ", answer cache on (cached lines are marked)")
          + f", max {live.limits.max_seconds:g} s per run, {live.limits.runs_per_day} runs per UTC day (in memory)")
    if live_error:
        print(f"live: off ({live_error.code}): {live_error}")
    tts = None if a.no_tts else tts_from_env(a.tts_credits, delivery=True if a.tts_delivery else None)
    print("voice: browser only (no ELEVENLABS_API_KEY)" if tts is None else
          f"voice: ElevenLabs {tts.model}, budget {tts.max_credits:.0f} credits ({tts.remaining:.0f} left)")
    uvicorn.run(create_app(Library(a.data), live, live_error, a.ui, tts), host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()
