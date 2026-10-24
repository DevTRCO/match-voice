"""The pipeline runner: one event stream in, overlay messages out, in two modes.

    live    the analyst newsroom writes while the match streams; needs a key and a CallBudget
    replay  the same flow, analyst lines read from data/replays/<match>/analyst.json; needs nothing

Events -> facts -> moments -> (newsroom for the slow ones) -> one director per channel -> messages.
`paced` plays the stream by wall clock at `speed` match seconds per second, unpaced runs as fast
as the machine allows (tests, static export). A replay hands the directors every moment up front,
like a tape-delayed broadcast, so they can pick wordings that fit before the next big moment; a live
run only knows what has happened so far. A paced live run can begin at `start` match seconds: the
earlier events are folded into the facts and sent at once as catch-up frames, without commentary.
Live messages carry wall-clock data: `w` (wall seconds since the stream started) and, on a `say`, `lat`
(wall seconds from the event to the line). Message shapes are in docs/PROTOCOL.md.
"""
from __future__ import annotations

import asyncio
import heapq
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timezone
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import AsyncIterator, Callable, Literal

from ..commentary.analyst import KEYS, LLM, RECENT_LINES, CallBudget, GuardedLLM, build_prompt, claude_llm
from ..commentary.delivery import energy_of
from ..commentary.director import ChannelDirector
from ..commentary.fast import REPLACED_KINDS, build_layers, continuity_id, layer_of
from ..commentary.moments import Moment, MomentBuilder, render_variants
from ..commentary.newsroom import Published, write_moment
from ..commentary.precompute import MODEL, MODEL_KINDS
from ..config import anthropic_api_key
from ..facts.engine import FactEngine
from ..schema import Event
from ..sim.micro.enrich import enrich
from . import protocol as proto
from .insights import InsightFeed
from .library import MatchBundle

Mode = Literal["live", "replay"]
DEFAULT_SPEED = 30.0
LIVE_PBP_TTL_S = 4.0  # live fast-path lines and template fallbacks older than this (viewer seconds) are stale, goals and red cards excepted
STANDIN_BEHIND_GOAL_S = 6.0  # the template stand-in of a goal analysis queues behind the goal call (up to 5 s on a beginner channel): its freshness starts when the call ends
LIVE_VOICE_WAIT_S = {"pbp": 3.0, "analyst": 6.0}  # live: the voice starts a captioned line at most this long (viewer seconds) after its caption
LIVE_URGENT = 90  # priority from which a moment is always worth saying (goal, red card, half and full time)
HEARTBEAT_S = 0.25  # wall seconds of silence before a live stream sends a heartbeat
DRAIN_S = 20.0  # viewer seconds the commentary may run on after the final whistle
SHORT_IN_PLAY = frozenset({"tackle_won", "sprint", "shot_blocked"})  # skeleton play-by-play that takes its shortest wording while the ball is in play (fast layer on)


class LiveUnavailable(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code  # no_key | no_budget | no_runs_today


class ReplayMismatch(RuntimeError):
    pass


@dataclass
class LiveLimits:
    """Caps a visitor cannot talk their way around: how long one live run may be and how many runs a UTC day may start.

    Both are 0 (off) by default, so tools and tests are unaffected; the server sets them from its flags. The daily count lives
    in memory only: a restart resets it, so a restart is the operator's way to give the day back."""

    max_seconds: float = 0.0  # live: longest `until - start` in match seconds; when set, a live run without `until` is refused
    runs_per_day: int = 0  # live runs that may start per UTC day
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    _day: str = field(default="", init=False, repr=False)
    _used: int = field(default=0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def check_span(self, start: float, until: float | None) -> None:
        if not self.max_seconds:
            return
        if until is None:
            raise ValueError(f"a live run needs until: this server allows at most {self.max_seconds:g} match seconds per run")
        if until - start > self.max_seconds + 1e-9:
            raise ValueError(f"a live run may last at most {self.max_seconds:g} match seconds, until - start was {until - start:g}")

    def check_carry(self, start: float, analyst_from: float) -> None:
        """analyst_from resumes moments a restart still owed, which cost a call when nothing cached them. Under a cap it may
        reach back as far as one run may last, so a fresh id cannot start model calls for the whole match before start."""
        if self.max_seconds and analyst_from < start - self.max_seconds - 1e-9:
            raise ValueError(f"analyst_from may lie at most {self.max_seconds:g} match seconds before start")

    def _roll(self) -> None:
        day = self.clock().strftime("%Y-%m-%d")
        if day != self._day:
            self._day, self._used = day, 0

    @property
    def runs_left(self) -> int | None:
        if not self.runs_per_day:
            return None
        with self._lock:
            self._roll()
            return max(0, self.runs_per_day - self._used)

    def claim_run(self) -> None:
        """Count one live run, or raise LiveUnavailable(no_runs_today). Check and count happen under one lock, so
        concurrent starts can never exceed the cap."""
        if not self.runs_per_day:
            return
        with self._lock:
            self._roll()
            if self._used >= self.runs_per_day:
                raise LiveUnavailable("no_runs_today", f"all {self.runs_per_day} live runs of today are used, "
                                      "the recorded run still works and live is back after midnight UTC")
            self._used += 1


@dataclass
class LiveConfig:
    """Everything live mode needs. Without a key or a positive call budget it cannot exist."""

    call: LLM
    budget: CallBudget
    model: str = MODEL
    cache_dir: Path | None = None
    fresh: bool = False  # never read or write the answer cache: every analyst line is a real call made during the run
    job_timeout_s: float = 90.0
    limits: LiveLimits = field(default_factory=LiveLimits)
    inflight: dict = field(default_factory=dict)  # model calls under way, shared by every run of this server
    # (match id, moment id) -> the continuity lines the analyst was given. Fixed on first use, so a restarted stream or a second
    # run of the same moment builds the identical prompt and finds the answer in the cache or the call under way
    recent_memo: dict = field(default_factory=dict)

    def guarded(self, budget: CallBudget | None = None) -> GuardedLLM:
        # one wrapper per job: GuardedLLM keeps the last latency, which concurrent jobs would overwrite
        return GuardedLLM(self.call, budget or self.budget, self.model, self.cache_dir, use_cache=not self.fresh,
                          inflight=self.inflight)

    @classmethod
    def from_env(cls, max_calls: int, model: str = MODEL, fresh: bool = False,
                 limits: LiveLimits | None = None) -> "LiveConfig":
        if max_calls <= 0:
            raise LiveUnavailable("no_budget", "live mode needs a call budget, set a positive number of model calls")
        key = anthropic_api_key()
        if not key:
            raise LiveUnavailable("no_key", "live mode needs an Anthropic API key, none is configured")
        return cls(claude_llm(model, key), CallBudget(max_calls), model, fresh=fresh, limits=limits or LiveLimits())


class _RunBudget(CallBudget):
    """Counts the calls of one run and spends them from the server-wide budget."""

    def __init__(self, shared: CallBudget):
        super().__init__(shared.max_calls)
        self._shared = shared

    def take(self) -> None:
        self._shared.take()  # raises BudgetExceeded when the server-wide budget is spent
        self.used += 1


class _Clock:
    """Maps match time to wall time: match second `start` is now, every second after it lasts 1/speed."""

    def __init__(self, speed: float, paced: bool, start: float = 0.0):
        self.speed, self.paced, self.start = speed, paced, start
        self.t0 = time.monotonic()
        self.epoch0 = time.time()

    def wall(self, match_t: float) -> float:
        """Monotonic time at which match second `match_t` is due."""
        return self.t0 + (match_t - self.start) / self.speed

    def since(self) -> float:
        return time.monotonic() - self.t0

    async def until(self, match_t: float) -> None:
        if self.paced:
            delay = self.wall(match_t) - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)


def _is_model_moment(m: Moment) -> bool:
    return m.voice == "analyst" and m.kind in MODEL_KINDS


class Runner:
    def __init__(self, bundle: MatchBundle, mode: Mode, speed: float = DEFAULT_SPEED, paced: bool = True,
                 live: LiveConfig | None = None, start: float = 0.0, analyst_from: float | None = None,
                 until: float | None = None, fast: bool = False):
        if speed <= 0:
            raise ValueError("speed must be positive")
        if not 0.0 <= start < bundle.duration:
            raise ValueError("start must be inside the match")
        if mode == "live" and (live is None or live.budget is None or live.budget.max_calls <= 0):
            raise LiveUnavailable("no_budget", "live mode needs a key and a positive call budget")
        self.bundle, self.mode, self.speed, self.paced, self.live = bundle, mode, speed, paced, live
        # fast: the dense voice (docs/DATA-MODEL.md 7): fast and context layers, v5 continuity, the two skeleton pass calls replaced.
        # Off by default, so every recording, cache key and test stays as it was until the layer is switched on on purpose
        self.fast = fast
        self.start = start if mode == "live" else 0.0  # a recording always plays from kick-off, a replay client seeks
        if analyst_from is not None and not 0.0 <= analyst_from <= self.start:
            raise ValueError("analyst_from must be between kick-off and start")
        if until is not None and not (mode == "live" and self.start < until <= bundle.duration):
            raise ValueError("until works in live mode only and must lie between start and the end of the match")
        if mode == "live":
            live.limits.check_span(self.start, until)
            if analyst_from is not None:
                live.limits.check_carry(self.start, analyst_from)
        self.until = until  # live insert: events after this match second are not fed, the stream drains and ends
        # a live run gets an id and remembers the lines it published, so the voice endpoint can synthesise those and nothing else
        self.run_id: str | None = secrets.token_hex(8) if mode == "live" else None
        self.lines: dict[tuple[int, int], tuple[str, str]] = {}  # (channel, moment id) -> (text, language)
        # a restarted stream asks for the analyst moments that were still being written: they come from the answer
        # cache or the call under way, so the restart costs no second call
        self.analyst_from = self.start if analyst_from is None or mode != "live" else analyst_from
        self.real = mode == "live" and paced  # wall-clock data on the messages
        # match seconds per frame, about 20 frames per wall second; live also keeps frames short at 1x
        self.dt = max(0.2 if mode == "live" else 0.5, speed / 20.0)
        self.meta = bundle.meta
        self.pubs: dict[int, Published] = {}
        live_mode = mode == "live"  # live captions a line at once and lets only the voice queue; a recording schedules it whole
        self._captions_first = live_mode
        self._dirs = [ChannelDirector(self._variants(k), k.split("/")[0], speed, captions_first=live_mode,
                                      voice_wait_s=lambda m: LIVE_VOICE_WAIT_S[m.voice] if m.voice_wait is None else m.voice_wait,
                                      has_model_line=self._model_line_of(k), dense=fast,
                                      short_kinds=SHORT_IN_PLAY if fast else frozenset()) for k in KEYS]
        self._layers: list[Moment] = []  # fast and context moments in time order, released as the stream reaches their time of knowledge
        self._li = 0
        self._done: list[tuple[float, int, Moment, Published]] = []  # moments waiting for their log release
        self._tasks: dict[int, tuple[Moment, asyncio.Task]] = {}
        self._jobs: list[tuple[Moment, dict]] = []  # model moments of the current event group, not started yet
        self._out: list[dict] = []
        self._horizon = 0.0
        self._says = 0
        self._clock = _Clock(speed, paced)
        self._said: list[deque[str]] = [deque(maxlen=RECENT_LINES) for _ in KEYS]  # per channel: lines shown or spoken, newest last
        self._energy: dict[int, str] = {}  # moment id -> calm | rising | peak
        self.energies: dict[tuple[int, int], str] = {}  # (channel, moment id) -> calm | rising | peak, for the voice settings
        self._moment_t: dict[int, float] = {}  # live: moment id -> match time of the event
        self._detected: dict[int, float] = {}  # live: moment id -> wall seconds since start when it was detected
        self._last_send = 0.0
        self._budget = _RunBudget(live.budget) if live else None

    def _model_line_of(self, key: str):
        def has(m: Moment) -> bool:
            pub = self.pubs.get(m.id)
            return pub is not None and pub.sources.get(key) == "analyst"
        return has

    def _variants(self, key: str):
        lang, style = key.split("/")

        def variants(m: Moment) -> list[str]:
            pub = self.pubs.get(m.id)
            return pub.lines[key] if pub else render_variants(m, lang, style)
        return variants

    # ---------- public ----------
    def hello(self) -> dict:
        return proto.hello(self.meta, self.mode, self.speed, self.dt, self.bundle.duration, self.start, self.until, self.run_id)

    async def collect(self) -> list[dict]:
        return [msg async for msg in self.stream()]

    async def stream(self) -> AsyncIterator[dict]:
        yield self.hello()
        eng = FactEngine(self.meta)
        mb = MomentBuilder(eng)
        enc = proto.FrameEncoder(self.meta)
        insights = InsightFeed()
        if self.mode == "replay":
            self._prepass()
        if self.fast:
            self._layers = self._build_layers()
            if self.mode == "replay":  # a recording hands the directors everything up front, like the skeleton moments
                for m in self._layers:
                    self._moment_t[m.id] = m.t
                    self._push(m)
                self._li = len(self._layers)
        try:
            past = [e for e in self.bundle.events if e.t < self.start]
            future = [e for e in self.bundle.events if e.t >= self.start and (self.until is None or e.t <= self.until)]
            ft = 0.0
            for group in self._groups(past):  # catch-up: state only, no commentary, sent without waiting
                for ev in group:
                    for m in mb.feed(ev, eng.ingest(ev)):  # keeps moment ids identical to a run from kick-off
                        if self.paced and m.t >= self.analyst_from and _is_model_moment(m):
                            self._write_late(m, eng)
                ft = group[-1].t
                yield enc.frame(eng.snapshot(), group)
            clock = self._clock = _Clock(self.speed, self.paced, self.start)
            ft = self.start
            for group in self._groups(future):
                gt = group[-1].t
                while ft + self.dt < gt:  # idle frames: lines and newsroom results do not wait for the next event
                    ft += self.dt
                    await clock.until(ft)
                    self._release_layers(ft)
                    await self._tick(ft)
                    for msg in self._flush(ft):
                        yield msg
                ft = gt
                await clock.until(ft)
                for ev in group:
                    before = eng.win_probs()
                    facts = eng.ingest(ev)
                    for m in mb.feed(ev, facts):
                        await self._on_moment(m, eng, ft)
                    if self.mode == "live":  # real facts of this instant for the log, no model and nothing from later events
                        for ins in insights.observe(eng, ev, before, facts):
                            self._out.append(self._log(ft, ev.t, "facts", "insight", None, ins.msg, ins.d))
                self._out.insert(0, enc.frame(eng.snapshot(), group))
                self._release_layers(ft)
                await self._tick(ft)
                await self._start_jobs(ft)  # after the tick: the lines this event's play-by-play just captioned are part of the analyst's continuity
                for msg in self._flush(ft):
                    yield msg
            while self.until is not None and ft + self.dt <= self.until:  # a quiet stretch at the end still plays out: the run lasts its whole window
                ft += self.dt
                await clock.until(ft)
                self._release_layers(ft)
                await self._tick(ft)
                for msg in self._flush(ft):
                    yield msg
            last = ft
            while not self._finished() and ft < last + DRAIN_S * self.speed:
                ft += self.dt
                await clock.until(ft)
                self._release_layers(ft)
                await self._tick(ft)
                for msg in self._flush(ft):
                    yield msg
            snap = eng.snapshot()
            calls = self._budget.used if self._budget else None
            yield proto.end(ft, snap["score"], len(self.bundle.events), self._says, calls)
        finally:
            for _, task in self._tasks.values():
                task.cancel()

    # ---------- internals ----------
    def _groups(self, events: list[Event]):
        group: list[Event] = []
        for ev in events:
            if group and ev.t - group[0].t >= self.dt:
                yield group
                group = []
            group.append(ev)
        if group:
            yield group

    def _flush(self, ft: float) -> list[dict]:
        """Hand out what the last tick produced. A paced live stream adds a heartbeat whenever it was quiet, so
        the clock of a client keeps moving between events."""
        out, self._out = self._out, []
        if self.real:
            now = self._clock.since()
            if out:
                self._last_send = now
            elif now - self._last_send >= HEARTBEAT_S:
                self._last_send = now
                out = [proto.heartbeat(ft, now)]
        return out

    def _finished(self) -> bool:
        return not self._tasks and not self._done and all(d.idle for d in self._dirs)

    def _prepass(self) -> None:
        """Replay: every moment is known up front, analyst lines come from the recording."""
        rec = {p.moment_id: p for p in self.bundle.recorded or []}
        kinds = self.bundle.recorded_kinds or {}
        eng = FactEngine(self.meta)
        mb = MomentBuilder(eng)
        times = self.bundle.recorded_times or {}
        seen: set[int] = set()
        for ev in self.bundle.events:
            for m in mb.feed(ev, eng.ingest(ev)):
                seen.add(m.id)
                pub = rec.get(m.id) if _is_model_moment(m) else None
                if pub is None:
                    if _is_model_moment(m):
                        self._no_recording(m)
                    else:
                        self._push(m)
                    continue
                if kinds.get(m.id, m.kind) != m.kind or abs(times.get(m.id, m.t) - m.t) >= 0.05:
                    raise ReplayMismatch(f"recording does not match moment {m.id} ({m.kind} at {m.t:.1f}s); "
                                         "record the replay again")
                self._complete(m, pub)
        stale = sorted(i for i in set(rec) - seen if times.get(i, 0.0) <= self.bundle.duration)  # a cut-short match is fine
        if stale:
            raise ReplayMismatch(f"recording has moments this build does not produce: {stale}; record the replay again")

    def _build_layers(self) -> list[Moment]:
        """The fast and context moments of the stretch this run plays. Built from the whole skeleton (generation may know the
        future); each moment is stamped with its time of knowledge and released to the directors only when the stream reaches it."""
        events = self.bundle.events
        moments = build_layers(self.meta, events, enrich(self.meta, events).rows)
        if self.mode == "live":
            moments = [m for m in moments if m.t >= self.start and (self.until is None or m.t <= self.until)]
        return moments

    def _release_layers(self, ft: float) -> None:
        while self._li < len(self._layers) and self._layers[self._li].t <= ft:
            m = self._layers[self._li]
            self._li += 1
            self._moment_t[m.id] = m.t
            self._push(m)

    def _no_recording(self, m: Moment) -> None:
        """A model moment without a recorded entry: the publisher uses the templates, so `queued` still gets its `ready`."""
        lines = {k: render_variants(m, *k.split("/")) for k in KEYS}
        step = {"step": "fallback", "moment": m.id, "attempt": 0, "at": 0.0, "keys": list(KEYS)}
        self._complete(m, Published(m.id, lines, {k: "template" for k in KEYS}, [step], 0.0))

    def _push(self, m: Moment) -> None:
        if self.fast and m.kind in REPLACED_KINDS:  # the fast layer calls the kick and the receipt instead (7.1)
            return
        self._energy[m.id] = energy_of(m)
        pub = self.pubs.get(m.id)
        for key, d in zip(KEYS, self._dirs):
            if self.mode == "live" and pub is not None and pub.sources.get(key) == "template" and m.priority < LIVE_URGENT:
                # the analyst gave up: its template stand-in is as perishable as play-by-play, except that a goal analysis only starts after the goal call
                d.push(replace(m, ttl=min(m.ttl, LIVE_PBP_TTL_S + (STANDIN_BEHIND_GOAL_S if m.kind == "goal_analysis" else 0.0))))
            else:
                d.push(m)

    def _complete(self, m: Moment, pub: Published) -> None:
        """Lines exist. They become ready after the time the newsroom needed, in match seconds."""
        # a paced live run is ready the moment the newsroom finished, a cache hit is not delayed to look like a call
        m.ready_t = self._horizon if self.real else max(m.t + pub.latency_s * self.speed, self._horizon)
        self.pubs[m.id] = pub
        self._push(m)
        heapq.heappush(self._done, (m.ready_t, m.id, m, pub))

    async def _on_moment(self, m: Moment, eng: FactEngine, ft: float) -> None:
        self._moment_t[m.id] = m.t
        if self.mode == "live" and not _is_model_moment(m) and m.priority < LIVE_URGENT:
            m.ttl = min(m.ttl, LIVE_PBP_TTL_S)  # template lines (also analyst-voice ones like shot_milestone) that would start late are dropped, not queued
        if not _is_model_moment(m):
            if self.mode == "live":
                self._push(m)
            return
        self._out.append(self._log(ft, m.t, "detector", "queued", m.id,
                                   f"Moment {m.id} ({m.kind}, {m.clock}') queued for the analyst"))
        if self.mode == "replay":
            return
        self._jobs.append((m, eng.snapshot()))  # started once the event group has been captioned, see _start_jobs

    async def _start_jobs(self, ft: float) -> None:
        """Start the newsroom for the model moments of the event group that was just ticked. A goal and its analysis come
        from one event: the caller's goal line is captioned by the tick, so it is already in `_said` when the analyst's
        prompt is built and the analyst does not repeat it."""
        jobs, self._jobs = self._jobs, []
        for m, snapshot in jobs:
            if self.paced:
                self._start_job(m, snapshot, ft)
            else:  # unpaced: wait for the answer, so a run is the same every time
                self._complete(m, await self._write(m, snapshot, self._recent_for(m)))

    def _start_job(self, m: Moment, snapshot: dict, ft: float) -> None:
        """Paced: start the newsroom for a moment and say whether it is a lookup or a model call."""
        recent = self._recent_for(m)
        if self.live.guarded(self._budget).has(build_prompt(m, snapshot, self.meta, recent=recent)):  # cached: no call, say so
            self._out.append(self._log(ft, m.t, "analyst", "lookup", m.id,
                                       f"Analyst looks up moment {m.id} in the answer cache (no model call)"))
        else:
            self._out.append(self._log(ft, m.t, "analyst", "writing", m.id,
                                       f"Analyst is writing moment {m.id} (model call started)"))
        self._tasks[m.id] = (m, asyncio.create_task(self._write(m, snapshot, recent)))

    def _write_late(self, m: Moment, eng: FactEngine) -> None:
        """A restarted stream picks up a moment its predecessor was still writing. Its age before the restart does
        not count against it, and there is no latency to report: the event happened in the old stream."""
        m.ttl += (self.start - m.t) / self.speed
        self._start_job(m, eng.snapshot(), self.start)

    def _log(self, ft: float, at: float, agent: str, step: str, moment: int | None, msg: str,
             detail: dict | None = None, channel: int | None = None, wall: float | None = None) -> dict:
        """A log message. A paced live run stamps it with wall seconds since the stream started, `wall` being
        the epoch time of the step when it happened earlier than now."""
        if self.real:
            w = self._clock.since() if wall is None else wall - self._clock.epoch0
            return proto.log(ft, at, agent, step, moment, msg, detail, channel, w=w)
        return proto.log(ft, at, agent, step, moment, msg, detail, channel)

    def _recent_for(self, m: Moment) -> dict[str, list[str]]:
        """The last lines each channel showed or spoke, as the analyst's continuity. Fixed per moment on first use."""
        memo = self.live.recent_memo
        key = (self.meta.id, m.id)
        if key not in memo:
            if len(memo) >= 4096:
                memo.pop(next(iter(memo)))
            memo[key] = {k: list(d) for k, d in zip(KEYS, self._said)}
        return memo[key]

    async def _write(self, m: Moment, snapshot: dict, recent: dict[str, list[str]]) -> Published:
        t0 = time.monotonic()
        try:
            return await asyncio.wait_for(write_moment(self.live.guarded(self._budget), self.meta, m, snapshot, recent),
                                          self.live.job_timeout_s)
        except Exception as exc:  # the stream must never stop because one moment failed
            timeout = isinstance(exc, asyncio.TimeoutError)
            step = ({"step": "timeout", "after_s": round(time.monotonic() - t0)} if timeout
                    else {"step": "analyst_error", "reason": f"{type(exc).__name__}: {exc}"})
            lines = {k: render_variants(m, *k.split("/")) for k in KEYS}
            return Published(m.id, lines, {k: "template" for k in KEYS},
                             [{**step, "moment": m.id, "attempt": 0, "at": time.time()}], time.monotonic() - t0)

    def _release(self, ft: float) -> None:
        """Log the agent steps of every moment whose lines are ready by now."""
        while self._done and self._done[0][0] <= ft:
            ready_t, _, m, pub = heapq.heappop(self._done)
            first = pub.trail[0] if pub.trail else None
            start = first["at"] - first.get("latency_s", 0.0) if first else 0.0
            for step in pub.trail:
                if self.real:  # the steps carry the real time they happened at
                    at = min(max(self.start + (step["at"] - self._clock.epoch0) * self.speed, m.t), ready_t)
                    wall = step["at"]
                else:
                    at, wall = min(max(m.t + (step["at"] - start) * self.speed, m.t), ready_t), None
                detail = {k: v for k, v in step.items() if k not in ("step", "moment", "at")}
                self._out.append(self._log(ft, at, proto.AGENTS.get(step["step"], "analyst"), step["step"], m.id,
                                           proto.describe(step), detail, wall=wall))
            n = sum(1 for s in pub.sources.values() if s == "analyst")
            self._out.append(self._log(ft, ready_t, "publisher", "ready", m.id,
                                       f"Moment {m.id} ready: {n} of {len(KEYS)} lines by the analyst"
                                       + (" (cached, not written in this run)" if pub.cached and n else ""),
                                       {"cached": True} if pub.cached and n else None))

    async def _tick(self, ft: float) -> None:
        self._horizon = ft
        for mid, (m, task) in list(self._tasks.items()):
            if task.done():
                del self._tasks[mid]
                self._complete(m, task.result())
        self._release(ft)
        notes = []
        for ch, d in enumerate(self._dirs):
            d.advance(ft)
            notes += [(ch, kind, sp) for kind, sp in d.drain()]
        captioned: dict[tuple[int, int], dict] = {}  # live: captions made in this tick, which a voice start at the same instant folds into
        for ch, kind, sp in sorted(notes, key=lambda n: (n[2].end if n[1] == "cut" else n[2].start, n[0])):
            key, pub = KEYS[ch], self.pubs.get(sp.moment_id)
            from_analyst = pub is not None and pub.sources.get(key) == "analyst" and sp.text == pub.lines[key][-1]
            wall = lat = None
            if self.real:  # wall seconds since the stream started, and since the event was due
                wall = self._clock.since()
                due = self._moment_t.get(sp.moment_id)
                lat = None if due is None else max(0.0, time.monotonic() - self._clock.wall(due))

            if self.run_id is not None:
                self.lines[(ch, sp.moment_id)] = (sp.text, key.split("/")[0])
                self.energies[(ch, sp.moment_id)] = self._energy.get(sp.moment_id, "calm")
            if kind == "caption" or (kind == "start" and not self._captions_first):  # continuity for the analyst: what this channel just said
                if not self.fast or continuity_id(sp.moment_id):  # v5 (7.3): fast and context wording never enters a prompt
                    self._said[ch].append(sp.text)
            elif kind == "skip" and not self.fast and sp.text in self._said[ch]:  # shown but never spoken: not part of what the booth said
                self._said[ch].remove(sp.text)  # (v5 keeps it: a skip depends on how busy the voice was)
            def say(cut: bool) -> dict:
                return proto.say(ft, ch, sp.moment_id, sp.kind, sp.voice, sp.text, sp.start, sp.end, cut,
                                 "analyst" if from_analyst else "template", w=wall, lat=lat, cached=from_analyst and pub.cached)

            if kind == "caption":  # live: the line is on screen now, the voice has its own schedule
                captioned[(ch, sp.moment_id)] = msg = say(False)
                self._out.append(msg)
                self._says += 1
            elif kind == "start":
                shown = captioned.pop((ch, sp.moment_id), None)
                if not self._captions_first:  # a recording: the line is shown when it is spoken
                    self._out.append(say(False))
                    self._says += 1
                elif shown is not None and shown["s"] == round(sp.start, 2):  # the voice took it at once: one `say` carries both
                    shown["e"] = round(sp.end, 2)
                elif shown is None and layer_of(sp.moment_id) != "skeleton":  # fast and context lines are captioned when the voice takes them
                    self._out.append(say(False))
                    self._says += 1
                else:
                    self._out.append(proto.voice(ft, ch, sp.moment_id, sp.start, sp.end, w=wall, lat=lat))
            elif kind == "cut":
                self._out.append(proto.voice(ft, ch, sp.moment_id, sp.start, sp.end, cut=True, w=wall, lat=lat)
                                 if self._captions_first else say(True))
                self._out.append(self._log(ft, sp.end, "director", "cut", sp.moment_id,
                                           f"{key}: {sp.kind} cut for a bigger moment", channel=ch))
            else:  # skip: captioned, never spoken
                self._out.append(proto.voice(ft, ch, sp.moment_id, sp.start, sp.end, skip=True, w=wall, lat=lat))
