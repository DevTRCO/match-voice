"""FastAPI app: match list, WebSocket and SSE streams, static replay export, built UI.

Every stream carries the messages of docs/PROTOCOL.md. Replay needs no key. Live needs a key and a
call budget, and tells the client why when it has neither.
"""
from __future__ import annotations

import random
import secrets
from collections import OrderedDict
from pathlib import Path

import orjson
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from starlette.responses import Response

from ..config import ROOT
from ..pipeline import protocol as proto
from ..pipeline.demo import demo_insert
from ..pipeline.export import build_replay
from ..pipeline.guided import guided_live
from ..pipeline.library import Library
from ..pipeline.runner import DEFAULT_SPEED, LiveConfig, LiveUnavailable, Runner
from ..tts import GuardedTTS, TTSBudgetExceeded, TTSError, TTSUnavailable

MIN_SPEED, MAX_SPEED = 0.1, 600.0
REPLAY_CACHE_SIZE = 8  # built replays kept in memory, about 280 KB each
RUNS_KEPT = 16  # live runs whose published lines the voice endpoint can still look up
WS_CODES = {"not_found": 4004, "bad_request": 4000, "no_key": 4001, "no_budget": 4001, "no_runs_today": 4001}
HTTP_CODES = {"not_found": 404, "bad_request": 400, "no_runs_today": 429}  # anything else (no_key, no_budget) is 409


def _dumps(msg: dict) -> str:
    return orjson.dumps(msg).decode()


def create_app(library: Library | None = None, live: LiveConfig | None = None,
               live_error: LiveUnavailable | None = None, ui_dist: Path | None = None,
               tts: GuardedTTS | None = None, rng: random.Random | None = None) -> FastAPI:
    lib = library if library is not None else Library()
    dist = ui_dist if ui_dist is not None else ROOT / "ui" / "dist"
    if live is None and live_error is None:
        live_error = LiveUnavailable("no_budget", "live mode is not configured, start the server with --live-calls N")
    app = FastAPI(title="match-voice", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    replay_cache: OrderedDict[tuple[str, float], bytes] = OrderedDict()
    runs: OrderedDict[str, dict[tuple[int, int], tuple[str, str]]] = OrderedDict()  # run id -> (channel, moment) -> (text, language)
    energies: dict[str, dict[tuple[int, int], str]] = {}  # run id -> (channel, moment) -> calm | rising | peak, used when the voice runs with delivery on

    def parse_speed(raw: str | None) -> float:
        try:
            speed = DEFAULT_SPEED if raw is None else float(raw)
        except ValueError:
            speed = float("nan")
        if not MIN_SPEED <= speed <= MAX_SPEED:  # also false for nan
            raise ValueError(f"speed must be a number between {MIN_SPEED} and {MAX_SPEED}")
        return speed

    def parse_start(raw: str | None, mode: str) -> float:
        try:
            start = 0.0 if raw is None else float(raw)
        except ValueError:
            start = float("nan")
        if not 0.0 <= start < 1e6:  # false for nan; the runner checks the match length
            raise ValueError("start must be a number of match seconds, 0 or more")
        if start and mode != "live":
            raise ValueError("start works in live mode only, a recorded run is scrubbed by the client")
        return start

    def parse_analyst_from(raw: str | None, start: float, mode: str) -> float | None:
        if raw is None:
            return None
        try:
            value = float(raw)
        except ValueError:
            value = float("nan")
        if not 0.0 <= value <= start:  # false for nan
            raise ValueError("analyst_from must be a number of match seconds between 0 and start")
        if mode != "live":
            raise ValueError("analyst_from works in live mode only")
        return value

    def parse_until(raw: str | None, start: float, mode: str) -> float | None:
        if raw is None:
            return None
        try:
            value = float(raw)
        except ValueError:
            value = float("nan")
        if not start < value < 1e6:  # false for nan; the runner checks the match length
            raise ValueError("until must be a number of match seconds after start")
        if mode != "live":
            raise ValueError("until works in live mode only")
        return value

    def make_runner(match: str | None, mode: str | None, speed: str | None, paced: str | None,
                    start: str | None = None, analyst_from: str | None = None, until: str | None = None) -> Runner:
        """Raises KeyError (no such match), ValueError (bad query) or LiveUnavailable.

        The query values arrive as plain strings, so every bad one is answered with the protocol's own error."""
        if not match:
            raise ValueError("match is required")
        mode = mode or "replay"
        if mode not in ("live", "replay"):
            raise ValueError("mode must be live or replay")
        flag = (paced or "true").lower()
        if flag not in ("true", "false", "1", "0"):
            raise ValueError("paced must be true or false")
        spd = parse_speed(speed)
        t0 = parse_start(start, mode)
        carry = parse_analyst_from(analyst_from, t0, mode)
        end_at = parse_until(until, t0, mode)
        bundle = lib.bundle(match)
        if mode == "live" and live is None:
            raise live_error
        if mode == "live" and live.budget.used >= live.budget.max_calls:
            raise LiveUnavailable("no_budget", "the live call budget is spent")
        runner = Runner(bundle, mode, spd, flag in ("true", "1"), live if mode == "live" else None, t0, carry, end_at)  # also enforces the run length cap
        if mode == "live":
            live.limits.claim_run()  # last, after every check that can refuse: a refused request costs no run. No await since the checks, so it is atomic
        if runner.run_id:  # the voice endpoint may synthesise the lines of this run, and only those
            runs[runner.run_id] = runner.lines
            energies[runner.run_id] = runner.energies
            while len(runs) > RUNS_KEPT:
                energies.pop(runs.popitem(last=False)[0], None)
        return runner

    def problem(exc: Exception) -> tuple[str, str]:
        if isinstance(exc, KeyError):
            return "not_found", f"no such match: {exc.args[0]}"
        if isinstance(exc, LiveUnavailable):
            return exc.code, str(exc)
        return "bad_request", str(exc)

    @app.get("/api/health")
    def health() -> dict:
        left = None if live is None else live.budget.max_calls - live.budget.used
        spent = left is not None and left <= 0
        runs = None if live is None else live.limits.runs_left
        no_runs = runs == 0
        lim = None if live is None else live.limits
        return {"ok": True, "protocol": proto.VERSION, "replay": True,
                "live": {"available": live is not None and not spent and not no_runs,
                         "code": live_error.code if live is None else "no_budget" if spent else "no_runs_today" if no_runs else "ok",
                         "reason": str(live_error) if live is None else "the live call budget is spent" if spent
                         else "all live runs of today are used, the recorded run still works" if no_runs else None,
                         "calls_left": left, "fresh": bool(live and live.fresh),
                         "runs_left": runs, "runs_per_day": (lim.runs_per_day or None) if lim else None,
                         "max_seconds": (lim.max_seconds or None) if lim else None},
                "tts": tts_status()}

    def tts_status() -> dict:
        """Spoken-voice state for the client. Never the key, never a text."""
        if tts is None:
            return {"available": False, "reason": "no ElevenLabs key is configured, the browser voice is used",
                    "voice": None, "model": None, "credits_left": None, "credits_max": None}
        st = tts.status()
        return {"available": st["available"], "reason": None if st["available"] else "the voice credit budget is spent, the browser voice is used",
                "voice": "ElevenLabs", "model": st["model"], "credits_left": st["credits_left"], "credits_max": st["credits_max"]}

    @app.get("/api/tts")
    async def speak(run: str | None = None, ch: str | None = None, m: str | None = None) -> Response:
        """The mp3 of one line this server published in a live run, found by run id, channel and moment id.
        Any other text cannot be asked for, so the key cannot be used to say or spend anything else."""
        def refuse(status: int, code: str, message: str) -> HTTPException:
            return HTTPException(status, detail={"code": code, "message": message})
        if tts is None:
            raise refuse(503, "tts_off", "spoken commentary is not configured on this server")
        try:
            line_key = (int(ch or ""), int(m or ""))
            line = runs.get(run or "", {}).get(line_key)
        except ValueError:
            line = None
        if line is None:
            raise refuse(404, "unknown_line", "no such line in a live run of this server")
        text, lang = line
        try:
            audio, hit = await tts.speak(text, lang, energies.get(run or "", {}).get(line_key))
        except TTSBudgetExceeded as exc:
            raise refuse(402, exc.code, str(exc))
        except TTSUnavailable as exc:
            raise refuse(502, exc.code, str(exc))
        except TTSError as exc:
            raise refuse(400, exc.code, str(exc))
        return Response(audio, media_type="audio/mpeg", headers={
            "Cache-Control": "no-store", "X-Voice-Cached": "1" if hit else "0",
            "X-Voice-Credits-Left": f"{tts.remaining:.0f}", "X-Voice-Credits-Spent": f"{tts.spent:.0f}"})

    @app.get("/api/demo-insert")
    def demo() -> dict:
        """The preset live window around one goal: match id, start and until in match seconds."""
        return demo_insert(lib)

    @app.get("/api/guided-live")
    async def guided() -> dict:
        """A fresh random match and its most eventful 60 second window, for a guided live run. Picking costs no model call
        and no live run: only starting the stream counts. Async on purpose, so the simulation never races the stream handlers."""
        return {**guided_live(lib, rng), "fresh": bool(live and live.fresh),
                "runs_left": None if live is None else live.limits.runs_left}

    @app.get("/api/matches")
    def matches() -> list[dict]:
        return [lib.summary(i) for i in lib.ids()]

    @app.get("/api/matches/{match_id}")
    def match(match_id: str) -> dict:
        try:
            summary = lib.summary(match_id)
        except KeyError:
            raise HTTPException(404, f"no such match: {match_id}")
        b = lib.bundle(match_id)
        return {**summary, "hello": proto.hello(b.meta, "replay", DEFAULT_SPEED, Runner(b, "replay").dt, b.duration)}

    @app.get("/api/matches/{match_id}/replay.json")
    async def replay_json(match_id: str, speed: str | None = None) -> Response:
        try:
            spd = parse_speed(speed)
            lib.bundle(match_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(404 if isinstance(exc, KeyError) else 400, problem(exc)[1])
        key = (match_id, spd)
        if key in replay_cache:
            replay_cache.move_to_end(key)
        else:
            replay_cache[key] = orjson.dumps(await build_replay(lib.bundle(match_id), spd))
            while len(replay_cache) > REPLAY_CACHE_SIZE:
                replay_cache.popitem(last=False)
        return Response(replay_cache[key], media_type="application/json")

    @app.websocket("/ws")
    async def ws(sock: WebSocket, match: str | None = None, mode: str | None = None, speed: str | None = None,
                 paced: str | None = None, start: str | None = None, analyst_from: str | None = None,
                 until: str | None = None) -> None:
        await sock.accept()
        try:
            runner = make_runner(match, mode, speed, paced, start, analyst_from, until)
        except (KeyError, ValueError, LiveUnavailable) as exc:
            code, message = problem(exc)
            await sock.send_text(_dumps(proto.error(code, message)))
            await sock.close(WS_CODES[code])
            return
        stream = runner.stream()
        try:
            async for msg in stream:
                await sock.send_text(_dumps(msg))
            await sock.close(1000)
        except WebSocketDisconnect:
            pass
        finally:
            await stream.aclose()

    @app.get("/sse")
    async def sse(match: str | None = None, mode: str | None = None, speed: str | None = None,
                  paced: str | None = None, start: str | None = None,
                  analyst_from: str | None = None, until: str | None = None) -> EventSourceResponse:
        try:
            runner = make_runner(match, mode, speed, paced, start, analyst_from, until)
        except (KeyError, ValueError, LiveUnavailable) as exc:
            code, message = problem(exc)
            raise HTTPException(HTTP_CODES.get(code, 409), detail={"code": code, "message": message})

        async def events():
            async for msg in runner.stream():
                yield {"event": msg["k"], "data": _dumps(msg)}
        return EventSourceResponse(events())

    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    else:
        @app.get("/")
        def index() -> dict:
            return {"name": "match-voice", "ui": "not built (ui/dist missing)", "matches": "/api/matches",
                    "stream": "/ws?match=<id>&mode=replay&speed=30", "docs": "/docs"}
    return app
