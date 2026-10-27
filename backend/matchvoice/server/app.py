"""FastAPI app: match list, WebSocket and SSE streams, static replay export, built UI.

Every stream carries the messages of docs/PROTOCOL.md. Replay needs no key. Live needs a key and a
call budget, and tells the client why when it has neither.

A public server (`public=PublicGate`, MATCHVOICE_PUBLIC=1) runs live only for the whitelisted scenes (pipeline/scenes.py), only for a
browser session (GET /api/session), and under the session, IP, concurrency and daily caps of server/public.py. `allowed_origins`
(MATCHVOICE_ALLOWED_ORIGINS) limits CORS and the WebSocket Origin; unset, both stay open as before (local development).
"""
from __future__ import annotations

import random
import secrets
from collections import OrderedDict
from urllib.parse import urlsplit
from pathlib import Path
from typing import Callable

import orjson
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from starlette.requests import HTTPConnection
from starlette.responses import Response

from ..config import ROOT
from ..pipeline import protocol as proto
from ..pipeline.demo import demo_insert
from ..pipeline.export import build_replay
from ..pipeline.guided import guided_live
from ..pipeline.library import Library
from ..pipeline.runner import DEFAULT_SPEED, LiveConfig, LiveUnavailable, Runner
from ..pipeline.scenes import SCENES, find_scene, scene_info
from ..tts import GuardedTTS, TTSBudgetExceeded, TTSError, TTSUnavailable
from ..tts.voices import voice_for
from .public import PublicGate

MIN_SPEED, MAX_SPEED = 0.1, 600.0
REPLAY_CACHE_SIZE = 8  # built replays kept in memory, about 280 KB each
RUNS_KEPT = 16  # live runs whose published lines the voice endpoint can still look up
# close codes: 4000 bad request, 4001 live is off (use the recorded run), 4003 no valid session, 4004 not found, 4029 a cap is reached
WS_CODES = {"not_found": 4004, "bad_request": 4000, "no_key": 4001, "no_budget": 4001, "no_runs_today": 4001,
            "no_world": 4001, "no_session_secret": 4001, "session_required": 4003,
            "no_calls_today": 4029, "session_limit": 4029, "ip_limit": 4029, "busy": 4029}
HTTP_CODES = {"not_found": 404, "bad_request": 400, "no_runs_today": 429, "session_required": 401,
              "no_calls_today": 429, "session_limit": 429, "ip_limit": 429, "busy": 503}  # anything else (no_key, no_budget, no_world) is 409
ORIGIN_REFUSED = 4003  # WebSocket closed before accept: the handshake is answered with HTTP 403 (a browser sees close 1006, no message)
VOICE_HEADERS = ["X-Voice-Cached", "X-Voice-Credits-Left", "X-Voice-Credits-Spent", "X-Voice-Name", "X-Voice-Fallback"]


def _noop() -> None:
    return None


def _dumps(msg: dict) -> str:
    return orjson.dumps(msg).decode()


def client_ip(conn: HTTPConnection, trusted_hops: int = 0) -> str | None:
    """The visitor's address for the per-IP caps. `trusted_hops` 0: the socket peer. N > 0 (behind N proxies that each append the address
    they saw to X-Forwarded-For, Container Apps' Envoy is one): the N-th entry from the RIGHT. Entries to its left were written by the
    client and are never trusted, so a forged header cannot pick the address that is counted. No header: the socket peer."""
    peer = conn.client.host if conn.client else None
    if trusted_hops <= 0:
        return peer
    hops = [h.strip() for raw in conn.headers.getlist("x-forwarded-for") for h in raw.split(",") if h.strip()]
    return hops[-trusted_hops] if len(hops) >= trusted_hops else peer


class _ReleasingSSE(EventSourceResponse):
    """An SSE response that frees its live run's concurrency slot when the response ends however it ends, also when sending fails before
    the body generator ever starts (its own `finally` would then never run)."""

    def __init__(self, content, release: Callable[[], None]):
        super().__init__(content)
        self._release = release

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._release()


def create_app(library: Library | None = None, live: LiveConfig | None = None,
               live_error: LiveUnavailable | None = None, ui_dist: Path | None = None,
               tts: GuardedTTS | None = None, rng: random.Random | None = None,
               public: PublicGate | None = None, allowed_origins: list[str] | None = None, trusted_hops: int = 0) -> FastAPI:
    lib = library if library is not None else Library()
    dist = ui_dist if ui_dist is not None else ROOT / "ui" / "dist"
    if live is None and live_error is None:
        live_error = LiveUnavailable("no_budget", "live mode is not configured, start the server with --live-calls N")
    app = FastAPI(title="match-voice", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=allowed_origins or ["*"], allow_methods=["GET"], expose_headers=VOICE_HEADERS)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    replay_cache: OrderedDict[tuple[str, float], bytes] = OrderedDict()
    runs: OrderedDict[str, dict[tuple[int, int], tuple[str, str]]] = OrderedDict()  # run id -> (channel, moment) -> (text, language)
    energies: dict[str, dict[tuple[int, int], str]] = {}  # run id -> (channel, moment) -> calm | rising | peak, used when the voice runs with delivery on
    speakers: dict[str, dict[tuple[int, int], str]] = {}  # run id -> (channel, moment) -> the person who says it (their own voice)

    def origin_ok(origin: str | None, host: str | None = None) -> bool:
        """No allow-list: every origin (local development). With one: only those, plus this server's own origin (the page it serves
        itself, whose Origin host is the request's Host); a WebSocket without an Origin is refused too."""
        if not allowed_origins or (origin is not None and origin in allowed_origins):
            return True
        return origin is not None and host is not None and urlsplit(origin).netloc.lower() == host.lower()

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

    def parse_flag(raw: str | None, name: str, mode: str) -> bool | None:
        if raw is None:
            return None
        flag = raw.lower()
        if flag not in ("true", "false", "1", "0"):
            raise ValueError(f"{name} must be 1 or 0")
        if mode != "live":
            raise ValueError(f"{name} works in live mode only")
        return flag in ("true", "1")

    def make_runner(match: str | None, mode: str | None, speed: str | None, paced: str | None,
                    start: str | None = None, analyst_from: str | None = None, until: str | None = None,
                    fast: str | None = None, world: str | None = None, rows: str | None = None,
                    token: str | None = None, ip: str | None = None, seed: str | None = None) -> tuple[Runner, Callable[[], None]]:
        """Raises KeyError (no such match), ValueError (bad query) or LiveUnavailable. Returns the runner and the release of its
        concurrency slot (call it when the stream ends).

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
        want_fast, want_world, want_rows = (parse_flag(fast, "fast", mode), parse_flag(world, "world", mode),
                                            parse_flag(rows, "rows", mode))
        sid = None
        if public is not None and mode == "live":  # the public server: its scenes only, at match pace, for a session
            if find_scene(match, t0, end_at) is None:
                raise ValueError("this server runs only its prepared scenes live (see /api/scene), with their exact match, start and until")
            if carry is not None or flag not in ("true", "1") or spd != 1.0:
                raise ValueError("a public live run plays at match pace (speed 1, paced) and takes no analyst_from")
            sid = public.session_id(token)
            want_world = bool(want_world)  # the world booth only when the viewer asks for it
        scene = find_scene(match, t0, end_at) if mode == "live" else None
        if seed is not None:  # a fixed play for a generated scene: tests and local checks only, never on the public server
            if public is not None:
                raise ValueError("this server picks the play of a scene itself and takes no seed")
            if not (seed.isdigit() and len(seed) <= 6):
                raise ValueError("seed must be a whole number from 0 to 999999")
            if scene is None or not scene.generated:
                raise ValueError("seed works only with the exact match, start and until of a generated scene (see /api/scene)")
        generated = scene is not None and scene.generated
        bundle = None if generated else lib.bundle(match)
        if mode == "live" and live is None:
            raise live_error
        if mode == "live" and live.budget.used >= live.budget.max_calls:
            raise LiveUnavailable("no_budget", "the live call budget is spent")
        if mode == "live" and live.daily is not None and live.daily.left == 0:
            raise LiveUnavailable("no_calls_today", f"the {live.daily.per_day} model calls of today are used; the recorded run "
                                  "still works and live is back after midnight UTC")
        if want_world and (live.world_call is None or not live.world_left):
            raise LiveUnavailable("no_world", "the world channels (es, it, pt, nl, tr, ja) are not available on this server now, "
                                  "the six core channels are")
        if sid is not None:
            public.check(sid, ip)  # session, IP and concurrency caps, before anything is counted
        if generated:  # every run of a generated scene plays a new variant, unless a seed is given; made only once every check has passed
            bundle = lib.scene_bundle(scene, int(seed) if seed is not None else secrets.randbelow(10**6))
        runner = Runner(bundle, mode, spd, flag in ("true", "1"), live if mode == "live" else None, t0, carry, end_at,  # also enforces the run length cap
                        fast=bool(want_fast), world=want_world, rows=bool(want_rows or want_fast))
        release = _noop
        if mode == "live":
            live.limits.claim_run()  # last, after every check that can refuse: a refused request costs no run. No await since the checks, so it is atomic
            if sid is not None:
                release = public.claim(sid, ip)  # cannot refuse: checked above, and nothing awaited since
        if runner.run_id:  # the voice endpoint may synthesise the lines of this run, and only those
            runs[runner.run_id] = runner.lines
            energies[runner.run_id] = runner.energies
            speakers[runner.run_id] = runner.speakers
            if sid is not None:
                public.own(runner.run_id, sid)
            while len(runs) > RUNS_KEPT:
                gone = runs.popitem(last=False)[0]
                energies.pop(gone, None)
                speakers.pop(gone, None)
        return runner, release

    def problem(exc: Exception) -> tuple[str, str]:
        if isinstance(exc, KeyError):
            return "not_found", f"no such match: {exc.args[0]}"
        if isinstance(exc, LiveUnavailable):
            return exc.code, str(exc)
        return "bad_request", str(exc)

    @app.get("/api/health")
    def health() -> dict:
        left = None if live is None else live.calls_left
        spent = live is not None and live.budget.used >= live.budget.max_calls
        no_calls = not spent and left is not None and left <= 0  # the lifetime budget is fine, today's cap is not
        runs = None if live is None else live.limits.runs_left
        no_runs = runs == 0
        lim = None if live is None else live.limits
        no_secret = public is not None and not public.secret
        code = (live_error.code if live is None else "no_budget" if spent else "no_calls_today" if no_calls
                else "no_runs_today" if no_runs else "no_session_secret" if no_secret else "ok")
        reason = {"no_budget": "the live call budget is spent",
                  "no_calls_today": "the model calls of today are used, the recorded run still works",
                  "no_runs_today": "all live runs of today are used, the recorded run still works",
                  "no_session_secret": "this server issues no sessions, the recorded run still works"}
        out = {"ok": True, "protocol": proto.VERSION, "replay": True,
               "live": {"available": code == "ok",
                        "code": code,
                        "reason": str(live_error) if live is None else reason.get(code),
                        "calls_left": left, "fresh": bool(live and live.fresh),
                        "runs_left": runs, "runs_per_day": (lim.runs_per_day or None) if lim else None,
                        "max_seconds": (lim.max_seconds or None) if lim else None},
               "tts": tts_status()}
        out["today"] = today()
        out["public"] = {"on": public is not None, "sessions": bool(public and public.secret),
                         "session_runs": (public.session_runs or None) if public else None,
                         "ip_runs": (public.ip_runs or None) if public else None,
                         "concurrent": (public.concurrent or None) if public else None,
                         "active": public.active if public else None,
                         "busy": bool(public and public.concurrent and public.active >= public.concurrent),
                         "scenes": sorted(SCENES) if public else None}
        return out

    def today() -> dict:
        """What a page needs to offer a live run: today's runs, model calls and voice credits left, and whether the world channels can
        be asked for. None where this server has no such cap."""
        st = tts.status() if tts is not None else None
        return {"runs_left": None if live is None else live.limits.runs_left,
                "calls_left": None if live is None else live.calls_left,
                "calls_per_day": live.daily.per_day if live is not None and live.daily is not None else None,
                "voice_credits_left": None if st is None else st["credits_left"],
                "voice_credits_per_day": None if st is None else st.get("credits_per_day"),
                "world": bool(live is not None and live.world_call is not None and live.world_left),
                "world_calls_left": None if live is None else live.world_left}

    @app.get("/api/session")
    def session(request: Request, token: str | None = None) -> dict:
        """A browser session for the public server's live runs: a signed token the page keeps in sessionStorage and sends as `token=`.
        A valid token comes back as it is, with what is left; anything else gets a new one. A server that is not public issues none
        (`enforced` false) and needs none."""
        ip = client_ip(request, trusted_hops)
        if public is None:
            return {"token": None, "id": None, "day": None, "enforced": False, "session_runs_left": None, "session_runs": None,
                    "ip_runs_left": None, "session_credits_left": None, "ip_credits_left": None, "busy": False}
        sid = public.verify(token)
        try:
            issued = {"token": token, "id": sid, "day": token.split(".")[1]} if sid else public.issue()
        except LiveUnavailable as exc:
            raise HTTPException(503, detail={"code": exc.code, "message": str(exc)})
        return {**issued, "enforced": True, **public.left(issued["id"], ip)}

    @app.get("/api/scene")
    def scene(request: Request, id: str | None = None, token: str | None = None) -> dict:
        """The scene a "New run" starts (pipeline/scenes.py): window, clock, score, goal time and title, plus what the caller has left:
        runs in their session and from their address, and today's runs, calls and voice credits. No model call."""
        sid = public.verify(token) if public is not None else None
        ip = client_ip(request, trusted_hops)
        key = id or next(iter(SCENES))
        if key not in SCENES:
            raise HTTPException(404, detail={"code": "not_found", "message": f"no such scene: {key}"})
        mine = public.left(sid, ip) if public is not None else {"session_runs_left": None, "session_runs": None,
                                                                 "ip_runs_left": None, "session_credits_left": None, "ip_credits_left": None, "busy": False}
        return {**scene_info(lib, key), "session": bool(sid), **mine, "today": today(), "fresh": bool(live and live.fresh)}

    def tts_status() -> dict:
        """Spoken-voice state for the client. Never the key, never a text."""
        if tts is None:
            return {"available": False, "reason": "no ElevenLabs key is configured, the browser voice is used",
                    "voice": None, "model": None, "credits_left": None, "credits_max": None}
        st = tts.status()
        out = {"available": st["available"], "reason": None if st["available"] else "the voice credit budget is spent, the browser voice is used",
               "voice": "ElevenLabs", "model": st["model"], "credits_left": st["credits_left"], "credits_max": st["credits_max"]}
        if "credits_per_day" in st:  # a daily cap: what is left of today (credits_left is already the smaller of both)
            out.update(credits_per_day=st["credits_per_day"], credits_today_left=st["credits_today_left"])
        return out

    @app.get("/api/tts")
    async def speak(request: Request, run: str | None = None, ch: str | None = None, m: str | None = None,
                    token: str | None = None) -> Response:
        """The mp3 of one line this server published in a live run, found by run id, channel and moment id, in the voice of the person
        who says it. Any other text cannot be asked for, so the key cannot be used to say or spend anything else. Every answer the page
        should meet with the browser voice (no voice service, no voice for this line, credits out, the service failing) carries
        `fallback: "browser"` in its detail and the header X-Voice-Fallback: browser."""
        def refuse(status: int, code: str, message: str, fallback: bool = True) -> HTTPException:
            detail = {"code": code, "message": message, **({"fallback": "browser"} if fallback else {})}
            return HTTPException(status, detail=detail, headers={"X-Voice-Fallback": "browser"} if fallback else None)
        if tts is None:
            raise refuse(503, "tts_off", "spoken commentary is not configured on this server")
        sid, ip = None, None
        if public is not None:  # a public server voices a run only for the session that started it
            sid = public.verify(token, any_day=True)  # the run's owner binds it; a run crossing midnight keeps its voice
            if sid is None:
                raise refuse(401, "session_required", "the voice needs the session token of the run")
            if public.owner(run) != sid:
                raise refuse(404, "unknown_line", "no such line in a live run of this session", fallback=False)
        try:
            line_key = (int(ch or ""), int(m or ""))
            line = runs.get(run or "", {}).get(line_key)
        except ValueError:
            line = None
        if line is None:
            raise refuse(404, "unknown_line", "no such line in a live run of this server", fallback=False)
        if sid is not None and not public.voice_channel(run, line_key[0]):
            raise refuse(409, "tts_channel_limit", "this run already has its voiced channels, the browser voice speaks this one")
        text, lang = line
        who = speakers.get(run or "", {}).get(line_key)
        energy = energies.get(run or "", {}).get(line_key)
        try:
            voice = voice_for(lang, who)
            need = tts.cost_of(text, lang, energy, who)
        except KeyError:
            raise refuse(409, "no_voice", f"no voice for this line ({lang}), the browser voice speaks it")
        except TTSError as exc:
            raise refuse(400, exc.code, str(exc))
        if sid is not None:
            ip = client_ip(request, trusted_hops)
            capped = public.reserve_credits(sid, need, ip)
            if capped == "tts_session_limit":
                raise refuse(402, capped, "this session has used its voice credits, the browser voice speaks the rest")
            if capped:
                raise refuse(402, capped, "this address has used its voice credits of today, the browser voice speaks the rest")
        try:
            audio, hit = await tts.speak(text, lang, energy, who)
        except BaseException as exc:
            if sid is not None:
                public.refund_credits(sid, need, ip)
            if isinstance(exc, KeyError):
                raise refuse(409, "no_voice", f"no voice for this line ({lang}), the browser voice speaks it")
            if isinstance(exc, TTSBudgetExceeded):
                raise refuse(402, exc.code, str(exc))
            if isinstance(exc, TTSUnavailable):
                raise refuse(502, exc.code, str(exc))
            if isinstance(exc, TTSError):
                raise refuse(400, exc.code, str(exc))
            raise
        if hit and sid is not None:  # cached meanwhile (another request made it): nothing billed for this session
            public.refund_credits(sid, need, ip)
        return Response(audio, media_type="audio/mpeg", headers={
            "Cache-Control": "no-store", "X-Voice-Cached": "1" if hit else "0", "X-Voice-Name": voice.name,
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
                 until: str | None = None, fast: str | None = None, world: str | None = None, rows: str | None = None,
                 token: str | None = None, seed: str | None = None) -> None:
        if not origin_ok(sock.headers.get("origin"), sock.headers.get("host")):  # before accept: the browser sees a refused handshake (HTTP 403)
            await sock.close(ORIGIN_REFUSED)
            return
        await sock.accept()
        try:
            runner, release = make_runner(match, mode, speed, paced, start, analyst_from, until, fast, world, rows,
                                          token, client_ip(sock, trusted_hops), seed)
        except (KeyError, ValueError, LiveUnavailable) as exc:
            code, message = problem(exc)
            await sock.send_text(_dumps(proto.error(code, message)))
            await sock.close(WS_CODES.get(code, 4001))
            return
        stream = runner.stream()
        try:
            async for msg in stream:
                await sock.send_text(_dumps(msg))
            await sock.close(1000)
        except WebSocketDisconnect:
            pass
        finally:
            release()
            await stream.aclose()

    @app.get("/sse")
    async def sse(request: Request, match: str | None = None, mode: str | None = None, speed: str | None = None,
                  paced: str | None = None, start: str | None = None,
                  analyst_from: str | None = None, until: str | None = None, fast: str | None = None,
                  world: str | None = None, rows: str | None = None, token: str | None = None,
                  seed: str | None = None) -> EventSourceResponse:
        origin = request.headers.get("origin")
        if origin is not None and not origin_ok(origin, request.headers.get("host")):  # a same-origin GET carries no Origin; a foreign page's EventSource does
            raise HTTPException(403, detail={"code": "origin_refused", "message": "this origin may not open streams here"})
        try:
            runner, release = make_runner(match, mode, speed, paced, start, analyst_from, until, fast, world, rows,
                                          token, client_ip(request, trusted_hops), seed)
        except (KeyError, ValueError, LiveUnavailable) as exc:
            code, message = problem(exc)
            raise HTTPException(HTTP_CODES.get(code, 409), detail={"code": code, "message": message})

        async def events():
            try:
                async for msg in runner.stream():
                    yield {"event": msg["k"], "data": _dumps(msg)}
            finally:
                release()
        return _ReleasingSSE(events(), release)  # release is idempotent: whichever runs first frees the slot

    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    else:
        @app.get("/")
        def index() -> dict:
            return {"name": "match-voice", "ui": "not built (ui/dist missing)", "matches": "/api/matches",
                    "stream": "/ws?match=<id>&mode=replay&speed=30", "docs": "/docs"}
    return app
