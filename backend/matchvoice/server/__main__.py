"""python -m matchvoice.server --port 8000 [--live-calls 12]

Replay always works. Live needs --live-calls N (the server-wide model call budget) and a key
in the environment or the git-ignored .env. Containers set MATCHVOICE_HOST, PORT and MATCHVOICE_LIVE_CALLS.

The public server (MATCHVOICE_PUBLIC=1, docs/DEPLOY.md) adds the scene whitelist, sessions and the caps of server/public.py.
Every cap is counted in memory: one replica keeps them true, a restart resets them.
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
from .public import PublicGate


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


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
    ap.add_argument("--world-calls", type=int, default=int(os.environ.get("MATCHVOICE_WORLD_CALLS", "0")),
                    help="live: the six world channels (es, it, pt, nl, tr, ja; ids 6..11) with their own call budget, one call per moment the English booth calls; 0 (default) leaves them off (env MATCHVOICE_WORLD_CALLS)")
    ap.add_argument("--tts-credits", type=float, default=None,
                    help="ElevenLabs credit budget for spoken lines, counted from the ledger in data/cache/tts (default 300, env MATCHVOICE_TTS_CREDITS)")
    ap.add_argument("--tts-delivery", action="store_true",
                    help="send ElevenLabs text shaped for speech and voice settings per energy level (env MATCHVOICE_TTS_DELIVERY=1); off by default")
    ap.add_argument("--daily-calls", type=int, default=_env_int("MATCHVOICE_DAILY_CALLS", 600),
                    help="model calls per UTC day, core and world together, 0 turns it off; in memory (env MATCHVOICE_DAILY_CALLS)")
    ap.add_argument("--tts-daily-credits", type=float, default=float(os.environ.get("MATCHVOICE_TTS_DAILY_CREDITS", "3000")),
                    help="ElevenLabs credits per UTC day, from the ledger's timestamps, 0 turns it off (env MATCHVOICE_TTS_DAILY_CREDITS)")
    ap.add_argument("--public", action="store_true", default=os.environ.get("MATCHVOICE_PUBLIC") == "1",
                    help="public server: live only for the whitelisted scenes and a browser session, with the session, IP, concurrency "
                         "and voice caps (env MATCHVOICE_PUBLIC=1; MATCHVOICE_SESSION_SECRET, MATCHVOICE_SESSION_RUNS, MATCHVOICE_IP_RUNS, "
                         "MATCHVOICE_LIVE_CONCURRENT, MATCHVOICE_SESSION_CREDITS, MATCHVOICE_IP_CREDITS, MATCHVOICE_RUN_VOICE_CHANNELS; "
                         "behind a proxy also MATCHVOICE_TRUSTED_HOPS)")
    ap.add_argument("--trusted-hops", type=int, default=_env_int("MATCHVOICE_TRUSTED_HOPS", 0),
                    help="proxies in front of the server that append the client address to X-Forwarded-For (Container Apps: 1); the "
                         "per-IP caps count the entry that many places from the right, never the client-written ones; 0 (default) "
                         "counts the socket peer (env MATCHVOICE_TRUSTED_HOPS)")
    ap.add_argument("--no-tts", action="store_true", help="never use ElevenLabs, the browser voice speaks")
    ap.add_argument("--data", type=Path, default=None, help="data folder, default <repo>/data")
    ap.add_argument("--ui", type=Path, default=None, help="built UI folder, default <repo>/ui/dist")
    a = ap.parse_args()
    live, live_error = None, None
    try:
        live = LiveConfig.from_env(a.live_calls, fresh=a.live_fresh,
                                   limits=LiveLimits(a.live_max_seconds, a.live_runs_per_day), world_calls=a.world_calls,
                                   daily_calls=a.daily_calls, world_on_demand=a.public and a.daily_calls > 0)
        live.world_skip_late = True  # a served live run: the world booth never pays for a line that would come back too old to say
    except LiveUnavailable as exc:
        live_error = exc
    print("replay: ready" if live is None else f"live: ready, budget {live.budget.max_calls} calls"
          + (", fresh (no answer cache)" if live.fresh else ", answer cache on (cached lines are marked)")
          + f", max {live.limits.max_seconds:g} s per run, {live.limits.runs_per_day} runs per UTC day (in memory)"
          + (f", {live.daily.per_day} calls per UTC day" if live.daily else "")
          + (", world booth on request" if live.world_call is not None else ""))
    if live_error:
        print(f"live: off ({live_error.code}): {live_error}")
    tts = None if a.no_tts else tts_from_env(a.tts_credits, delivery=True if a.tts_delivery else None, daily_credits=a.tts_daily_credits)
    print("voice: browser only (no ELEVENLABS_API_KEY)" if tts is None else
          f"voice: ElevenLabs {tts.model}, budget {tts.max_credits:.0f} credits ({tts.remaining:.0f} left)"
          + (f", {tts.daily_credits:.0f} per UTC day" if tts.daily_credits else ""))
    public = PublicGate.from_env() if a.public else None
    if public is not None:
        print("public: scenes only, " + ("sessions on" if public.secret else "NO MATCHVOICE_SESSION_SECRET, live is refused")
              + f", {public.session_runs} runs per session, {public.ip_runs} per IP per UTC day, {public.concurrent} at once"
              + f", voice {public.session_credits:g} credits per session, {public.ip_credits:g} per IP per UTC day, "
                f"{public.run_channels} channels per run"
              + ("" if live is None or live.fresh else "; warning: MATCHVOICE_LIVE_FRESH is not 1, cached answers are served"))
    origins = [o.strip() for o in os.environ.get("MATCHVOICE_ALLOWED_ORIGINS", "").split(",") if o.strip()] or None
    print("origins: any (MATCHVOICE_ALLOWED_ORIGINS unset)" if origins is None else f"origins: {', '.join(origins)}")
    print("client address: socket peer" if a.trusted_hops <= 0 else
          f"client address: X-Forwarded-For, entry {a.trusted_hops} from the right (MATCHVOICE_TRUSTED_HOPS)")
    if os.environ.get("FORWARDED_ALLOW_IPS", "").strip() == "*":
        print("warning: FORWARDED_ALLOW_IPS=* makes uvicorn take the LEFTMOST, client-written X-Forwarded-For entry as the client; "
              "the per-IP caps do not use it (they use MATCHVOICE_TRUSTED_HOPS), but unset it")
    # the per-IP caps take the address from app.client_ip (MATCHVOICE_TRUSTED_HOPS), not from uvicorn: with FORWARDED_ALLOW_IPS=*
    # uvicorn trusts the leftmost X-Forwarded-For entry, which the client writes. uvicorn's proxy_headers stay on for the default
    # 127.0.0.1 (a local reverse proxy).
    uvicorn.run(create_app(Library(a.data), live, live_error, a.ui, tts, public=public, allowed_origins=origins,
                           trusted_hops=a.trusted_hops),
                host=a.host, port=a.port, log_level="info", proxy_headers=True,
                forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"))


if __name__ == "__main__":
    main()
