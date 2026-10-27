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

from ..commentary.analyst import AFTER, KEYS, LLM, RECENT_LINES, SETUP, BudgetExceeded, CallBudget, GuardedLLM, build_prompt, claude_llm
from ..commentary.delivery import energy_of
from ..commentary.director import ChannelDirector
from ..commentary.lang import ALL_KEYS, WORLD_KEYS, who_of
from ..commentary.world import WORLD_PROMPT_VERSION, WORLD_SYSTEM, build_world_prompt, world_moment
from ..commentary.fast import REPLACED_KINDS, build_layers, continuity_id, layer_of
from ..commentary.moments import Moment, MomentBuilder, goal_facet, render_variants
from ..commentary.newsroom import Published, write_moment
from ..commentary.patterns import PatternFeed, is_pattern_id
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
SCORE_LINE_BASE = 900_000  # derived id of the lead's score line after a goal analysis (skeleton range, under the fast layer's 1,000,000)
SCORE_LINE = {"priority": 60, "ttl": 30.0, "voice_wait": 20.0}  # after the co-commentator's line (70) and before any context note (30 to 45)
WORLD_CONTEXT_WAIT_S = 6.0  # world channels: a context line (the story) may wait this long for the voice (the core lead waits 3 s for the co)
SHORT_IN_PLAY = frozenset({"tackle_won", "sprint", "shot_blocked"})  # skeleton play-by-play that takes its shortest wording while the ball is in play (fast layer on)
WORLD_CALL_GUESS_S = 3.0  # world_skip_late: the expected length of a world call until one has been measured in this run
RUN_LEAD_S = 2.5  # rows on: a pass's `run` cue goes out this many match seconds before the kick, when its receiver may set off (board only)
ROWS_CATCH_UP_S = 15.0  # rows on: the catch-up keeps the frames and enriched rows of this many match seconds before start, the rest is folded


class LiveUnavailable(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code  # no_key | no_budget | no_runs_today | no_calls_today | no_world, and the public gate's codes (server/public.py)


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


def _utc_day(clock: Callable[[], datetime]) -> str:
    return clock().strftime("%Y-%m-%d")


@dataclass
class DailyCalls:
    """Model calls per UTC day, core and world booth together; rolls over at midnight UTC like LiveLimits. In memory: a restart
    resets it. 0 turns it off. A call over the cap raises BudgetExceeded, which the newsroom treats like a spent budget."""

    per_day: int = 0
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    _day: str = field(default="", init=False, repr=False)
    _used: int = field(default=0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def _roll(self) -> None:
        day = _utc_day(self.clock)
        if day != self._day:
            self._day, self._used = day, 0

    @property
    def used(self) -> int:
        with self._lock:
            self._roll()
            return self._used

    @property
    def left(self) -> int | None:
        if not self.per_day:
            return None
        with self._lock:
            self._roll()
            return max(0, self.per_day - self._used)

    def check(self) -> None:
        if self.per_day and self.left == 0:
            raise BudgetExceeded(f"the {self.per_day} model calls of today are used")

    def take(self) -> None:
        with self._lock:
            self._roll()
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
    # the world booth (commentary/world.py): its own agent and, when set, its own call budget, so world lines can never starve the core analysis
    world_call: LLM | None = None
    world_budget: CallBudget | None = None
    daily: DailyCalls | None = None  # model calls per UTC day, core and world (None: no daily cap, the lifetime budget only)
    # paced live runs: the world booth calls the most important waiting moment first (a goal before older fragments) and never pays for one
    # that would be too old to say when the answer comes back (its ttl). Off by default, so recordings and tests keep the calling order;
    # the server turns it on (with real model latency the calling-order queue falls behind and every world line arrives stale)
    world_skip_late: bool = False

    def guarded(self, budget: CallBudget | None = None) -> GuardedLLM:
        # one wrapper per job: GuardedLLM keeps the last latency, which concurrent jobs would overwrite
        return GuardedLLM(self.call, budget or self.budget, self.model, self.cache_dir, use_cache=not self.fresh,
                          inflight=self.inflight)

    def world_guarded(self, budget: CallBudget) -> GuardedLLM:
        return GuardedLLM(self.world_call, budget, self.model, self.cache_dir, use_cache=not self.fresh,
                          inflight=self.inflight, version=WORLD_PROMPT_VERSION)

    @property
    def calls_left(self) -> int:
        """Core calls this server may still make: the lifetime budget and, when set, today's cap."""
        left = self.budget.max_calls - self.budget.used
        today = self.daily.left if self.daily else None
        return max(0, left if today is None else min(left, today))

    @property
    def world_left(self) -> int | None:
        """World booth calls still possible, None when this server has no world booth."""
        if self.world_call is None:
            return None
        own = self.world_budget if self.world_budget is not None else self.budget
        left = own.max_calls - own.used
        today = self.daily.left if self.daily else None
        return max(0, left if today is None else min(left, today))

    @classmethod
    def from_env(cls, max_calls: int, model: str = MODEL, fresh: bool = False,
                 limits: LiveLimits | None = None, world_calls: int = 0, daily_calls: int = 0,
                 world_on_demand: bool = False) -> "LiveConfig":
        """`world_calls` > 0 switches the world channels on with their own budget (one call per moment the English booth calls).
        `world_on_demand`: the world booth exists without its own budget (its calls come from the core budget and the daily cap), and
        a run gets it only when it asks for it (`Runner(world=True)`; the public server passes `world` on every run)."""
        if max_calls <= 0:
            raise LiveUnavailable("no_budget", "live mode needs a call budget, set a positive number of model calls")
        key = anthropic_api_key()
        if not key:
            raise LiveUnavailable("no_key", "live mode needs an Anthropic API key, none is configured")
        world: dict = {}
        if world_calls > 0:
            world = dict(world_call=claude_llm(model, key, WORLD_SYSTEM, "WorldBooth"), world_budget=CallBudget(world_calls))
        elif world_on_demand:
            world = dict(world_call=claude_llm(model, key, WORLD_SYSTEM, "WorldBooth"))
        return cls(claude_llm(model, key), CallBudget(max_calls), model, fresh=fresh, limits=limits or LiveLimits(),
                   daily=DailyCalls(daily_calls) if daily_calls > 0 else None, **world)


class _RunBudget(CallBudget):
    """Counts the calls of one run and spends them from the server-wide budget (and today's cap, when the server has one)."""

    def __init__(self, shared: CallBudget, daily: DailyCalls | None = None):
        super().__init__(shared.max_calls)
        self._shared, self._daily = shared, daily

    def take(self) -> None:
        if self._daily is not None:
            self._daily.check()  # raises BudgetExceeded when today's calls are used, before anything is counted
        self._shared.take()  # raises BudgetExceeded when the server-wide budget is spent
        if self._daily is not None:
            self._daily.take()
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


def score_line_for(m: Moment, meta, duration: float) -> Moment:
    """Back to play after the co-commentator's line on a goal: the lead says the score once, in its spoken form, and the time left
    (docs/INSERT-SCRIPT.md, real TV order: call, co line, score). It becomes known when the analysis does, so it is voiced after it."""
    p = m.params
    side = "H" if p.get("team") == meta.teams["H"].name else "A"
    other = meta.teams["A" if side == "H" else "H"].name
    minute, _, extra = m.clock.partition("+")
    half = 1 if m.t < duration / 2 and int(minute) <= 45 else 2
    params = {"team": p.get("team"), "short": str(p.get("team", "")).split()[0], "other": other.split()[0],
              "score": p.get("score"), "goal_facet": goal_facet(p["score"], side), "half": half}
    if not extra:
        params["left_min"] = max(0, (45 if half == 1 else 90) - int(minute))
    return Moment(id=SCORE_LINE_BASE + m.id, t=m.t, clock=m.clock, kind="score_line", voice="pbp", ready_t=m.ready_t + 1e-3,
                  params=params, evidence=list(m.evidence), voice_wait=SCORE_LINE["voice_wait"],
                  priority=SCORE_LINE["priority"], ttl=SCORE_LINE["ttl"])


def _is_model_moment(m: Moment) -> bool:
    return m.voice == "analyst" and m.kind in MODEL_KINDS


class Runner:
    def __init__(self, bundle: MatchBundle, mode: Mode, speed: float = DEFAULT_SPEED, paced: bool = True,
                 live: LiveConfig | None = None, start: float = 0.0, analyst_from: float | None = None,
                 until: float | None = None, fast: bool = False, booth: dict | None = None, patterns: bool | None = None,
                 world: bool | None = None, rows: bool = False):
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
        self.speakers: dict[tuple[int, int], str] = {}  # (channel, moment id) -> the person who says it (the voice is theirs)
        # rows: stream the enriched rows (`row` messages) as each becomes known, and fold the catch-up to its last ROWS_CATCH_UP_S
        self.rows = rows
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
        # the world channels (ids 6..11): live runs whose LiveConfig has the world booth; every line is the model's (commentary/world.py)
        has_world = live_mode and live is not None and live.world_call is not None
        if world and not has_world:
            raise ValueError("the world channels need a live run with a world booth (LiveConfig.world_call)")
        self.world = has_world if world is None else bool(world)
        self.keys = list(ALL_KEYS) if self.world else list(KEYS)
        wait = lambda m: LIVE_VOICE_WAIT_S[m.voice] if m.voice_wait is None else m.voice_wait
        self._dirs = [ChannelDirector(self._variants(k), k.split("/")[0], speed, captions_first=live_mode,
                                      voice_wait_s=wait, has_model_line=self._model_line_of(k), dense=fast,
                                      short_kinds=SHORT_IN_PLAY if fast else frozenset()) for k in KEYS]
        # a solo booth says the set-up and then the story itself, with no hand-over: the story waits for its own set-up to end
        world_wait = lambda m: max(wait(m), WORLD_CONTEXT_WAIT_S) if m.layer == "context" else wait(m)
        self._dirs += [ChannelDirector(self._world_variants(k), k.split("/")[0], speed, captions_first=live_mode, voice_wait_s=world_wait,
                                       has_model_line=lambda m: True, dense=fast, short_kinds=frozenset())
                       for k in self.keys[len(KEYS):]]
        self.wpubs: dict[int, Published] = {}  # world booth: moment id -> its published lines
        self._moments: dict[int, Moment] = {}  # every moment pushed, by id (the world booth writes for the ones the English booth called)
        self._wq: list[int] = []  # world: moments waiting for their call, in the order the English booth called them
        self._wseen: set[int] = set()
        self._wtask: tuple[Moment, asyncio.Task] | None = None  # world: the one call under way (calls run one after another)
        self._wlat = WORLD_CALL_GUESS_S  # world_skip_late: the last measured world call, wall seconds
        self._wstart = 0.0
        self._layers: list[Moment] = []  # fast and context moments in time order, released as the stream reaches their time of knowledge
        self._li = 0
        self._done: list[tuple[float, int, Moment, Published]] = []  # moments waiting for their log release
        self._tasks: dict[int, tuple[Moment, asyncio.Task]] = {}
        self._jobs: list[tuple[Moment, dict]] = []  # model moments of the current event group, not started yet
        self._out: list[dict] = []
        self._horizon = 0.0
        self._says = 0
        self._clock = _Clock(speed, paced)
        self._said: list[deque[str]] = [deque(maxlen=RECENT_LINES) for _ in self.keys]  # per channel: lines shown or spoken, newest last
        self._energy: dict[int, str] = {}  # moment id -> calm | rising | peak
        self.energies: dict[tuple[int, int], str] = {}  # (channel, moment id) -> calm | rising | peak, for the voice settings
        self._moment_t: dict[int, float] = {}  # live: moment id -> match time of the event
        self._detected: dict[int, float] = {}  # live: moment id -> wall seconds since start when it was detected
        self._last_send = 0.0
        self._budget = _RunBudget(live.budget, live.daily) if live else None
        self._wbudget = (_RunBudget(live.world_budget, live.daily) if live.world_budget is not None else self._budget) if self.world else None
        self._rows: list[dict] | None = None  # the enriched rows of the match (fast runs): the scoring move carries how each ball was played
        # the booth's memory of this broadcast: the pattern set-ups it said ((side, half) -> id, time, lines per channel) and the habits it
        # fired. One dict per run, or one shared by the parts of a broadcast cut (the story insert), so a goal in part 2 can pay off part 1
        self.booth = booth if booth is not None else {}
        self.booth.setdefault("setups", {})
        self.booth.setdefault("fired", set())
        self.booth.setdefault("world_lines", {k: [] for k in WORLD_KEYS})  # world: the lines published per channel, in order (its continuity)
        self.booth.setdefault("world_pubs", {})  # world: moment id -> {key: line} (a goal in part 2 pays off the set-up of part 1)
        self._pat: PatternFeed | None = None  # the pattern detector: live runs with the dense voice only, so recordings and replays are unchanged
        self.patterns = (fast and mode == "live") if patterns is None else (patterns and mode == "live")
        self._ins: dict[int, dict] = {}  # moment id -> the insight's evidence for the overlay (`say.ins`)

    def _model_line_of(self, key: str):
        def has(m: Moment) -> bool:
            pub = self.pubs.get(m.id)
            return pub is not None and pub.sources.get(key) == "analyst"
        return has

    def _world_variants(self, key: str):
        def variants(m: Moment) -> list[str]:
            pub = self.wpubs.get(m.id)
            return pub.lines.get(key, []) if pub else []
        return variants

    def _variants(self, key: str):
        lang, style = key.split("/")

        def variants(m: Moment) -> list[str]:
            pub = self.pubs.get(m.id)
            return pub.lines[key] if pub else render_variants(m, lang, style)
        return variants

    # ---------- public ----------
    def hello(self) -> dict:
        channels = proto.ALL_CHANNELS[:len(self.keys)] if self.world else None
        msg = proto.hello(self.meta, self.mode, self.speed, self.dt, self.bundle.duration, self.start, self.until, self.run_id, channels)
        if self.bundle.variant is not None:  # a generated live scene: the seed of its play (additive)
            msg["scene_seed"] = int(self.bundle.variant)
        return msg

    async def collect(self) -> list[dict]:
        return [msg async for msg in self.stream()]

    async def stream(self) -> AsyncIterator[dict]:
        yield self.hello()
        eng = self._eng = FactEngine(self.meta)
        if self.fast:
            self._rows = enrich(self.meta, self.bundle.events).rows
        if self.rows:  # the board's motion source, released by time of knowledge (a pass at its kick, the receipt at its arrival)
            feed = self._rows if self._rows is not None else enrich(self.meta, self.bundle.events).rows
            self._row_feed = sorted((r for r in feed if self.until is None or r["t"] <= self.until), key=lambda r: (r["t"], r["eid"]))
            self._ri = 0
            self._cue_feed = self._run_cues(self._row_feed)
            self._ci = 0
        mb = MomentBuilder(eng, self._rows)
        if self.patterns:
            self._pat = PatternFeed(self.meta, fired=self.booth["fired"])
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
            if self.bundle.variant is not None:  # says only that the play is new, nothing about what comes
                self._out.append(self._log(self.start, self.start, "facts", "scene", None,
                                           f"Play generated for this run, seed {self.bundle.variant}", {"seed": int(self.bundle.variant)}))
            past = [e for e in self.bundle.events if e.t < self.start]
            future = [e for e in self.bundle.events if e.t >= self.start and (self.until is None or e.t <= self.until)]
            ft = 0.0
            groups = list(self._groups(past))
            fold = self.start - ROWS_CATCH_UP_S if self.rows else None
            for gi, group in enumerate(groups):  # catch-up: state only, no commentary, sent without waiting
                for ev in group:
                    facts = eng.ingest(ev)
                    if self._pat:
                        self._pat.feed(ev)
                    for m in mb.feed(ev, facts):  # keeps moment ids identical to a run from kick-off
                        if self.paced and m.t >= self.analyst_from and _is_model_moment(m):
                            self._write_late(m, eng)
                ft = group[-1].t
                if fold is not None and ft < fold and gi < len(groups) - 1:
                    continue  # folded: the encoder sends stat deltas against the last frame it made, so the next kept frame carries them
                yield enc.frame(eng.snapshot(), group)
            if self.rows:
                early = self._take_rows(self.start, inclusive=False)
                early = [r for r in early if r["t"] >= self.start - ROWS_CATCH_UP_S]
                if early:  # stamped at the newest of them: still before start, never ahead of a row
                    yield proto.rows(max(ft, early[-1]["t"]), early)
                cues = [c for c in self._take_cues(self.start) if c["t"] >= self.start - ROWS_CATCH_UP_S]
                if cues:
                    yield proto.runs(max(ft, self.start - RUN_LEAD_S), cues)
            clock = self._clock = _Clock(self.speed, self.paced, self.start)
            ft = self.start
            for group in self._groups(future):
                gt = group[-1].t
                while ft + self.dt < gt:  # idle frames: lines and newsroom results do not wait for the next event
                    ft += self.dt
                    await clock.until(ft)
                    self._send_rows(ft)
                    self._release_layers(ft)
                    await self._quiet(ft, eng)
                    await self._tick(ft)
                    await self._start_jobs(ft)
                    for msg in self._flush(ft):
                        yield msg
                ft = gt
                await clock.until(ft)
                for ev in group:
                    before = eng.win_probs()
                    facts = eng.ingest(ev)
                    if self._pat:
                        self._pat.feed(ev)
                    for m in mb.feed(ev, facts):
                        await self._on_moment(m, eng, ft)
                    if self.mode == "live":  # real facts of this instant for the log, no model and nothing from later events
                        for ins in insights.observe(eng, ev, before, facts):
                            self._out.append(self._log(ft, ev.t, "facts", "insight", None, ins.msg, ins.d))
                self._out.insert(0, enc.frame(eng.snapshot(), group))
                self._send_rows(ft, at=1)  # right after the frame of the same instant
                self._release_layers(ft)
                await self._tick(ft)
                await self._start_jobs(ft)  # after the tick: the lines this event's play-by-play just captioned are part of the analyst's continuity
                for msg in self._flush(ft):
                    yield msg
            while self.until is not None and ft + self.dt <= self.until:  # a quiet stretch at the end still plays out: the run lasts its whole window
                ft += self.dt
                await clock.until(ft)
                self._send_rows(ft)
                self._release_layers(ft)
                await self._quiet(ft, eng)
                await self._tick(ft)
                await self._start_jobs(ft)
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
            if self._wbudget is not None and self._wbudget is not self._budget:
                calls += self._wbudget.used
            yield proto.end(ft, snap["score"], len(self.bundle.events), self._says, calls)
        finally:
            for _, task in self._tasks.values():
                task.cancel()

    # ---------- internals ----------
    def _take_rows(self, ft: float, inclusive: bool = True) -> list[dict]:
        out = []
        while self._ri < len(self._row_feed) and (self._row_feed[self._ri]["t"] <= ft if inclusive else self._row_feed[self._ri]["t"] < ft):
            out.append(self._row_feed[self._ri])
            self._ri += 1
        return out

    def _run_cues(self, feed: list[dict]) -> list[dict]:
        """One cue per pass that names a target: who sets off, from whom, to which spot (the receipt's, else the pass end) and
        when the ball is due. The board starts the receiver's run before the kick; the booth never sees a cue."""
        rec = {r["pass_eid"]: r for r in feed if r["type"] == "receipt" and r.get("pass_eid") is not None}
        evs = self.bundle.events
        out = []
        for r in feed:
            if r["type"] != "pass" or not r.get("target"):
                continue
            ev = evs[r["i"]] if r.get("k") == 0 and 0 <= r["i"] < len(evs) else None
            rc = rec.get(r["eid"])
            if rc is not None:
                x, y = rc["x"], rc["y"]
            elif r.get("end_x") is not None:
                x, y = r["end_x"], r["end_y"]
            elif ev is not None and ev.end_x is not None:
                x, y = ev.end_x, ev.end_y
            else:
                continue
            sx = r["x"] if r.get("x") is not None else (ev.x if ev is not None else None)
            sy = r["y"] if r.get("y") is not None else (ev.y if ev is not None else None)
            out.append({"eid": r["eid"], "t": r["t"], "t_arr": r.get("t_arr"), "player": r["target"],
                        "by": r.get("player") or (ev.player if ev is not None else None), "pass_type": r.get("pass_type"),
                        "under": bool((r.get("pressure") or {}).get("under")),
                        "x": round(x, 1), "y": round(y, 1), "sx": None if sx is None else round(sx, 1), "sy": None if sy is None else round(sy, 1)})
        out.sort(key=lambda c: (c["t"], c["eid"]))
        return out

    def _take_cues(self, ft: float) -> list[dict]:
        out = []
        while self._ci < len(self._cue_feed) and self._cue_feed[self._ci]["t"] - RUN_LEAD_S <= ft:
            out.append(self._cue_feed[self._ci])
            self._ci += 1
        return out

    def _send_rows(self, ft: float, at: int | None = None) -> None:
        """Rows on: one `row` message with the enriched rows whose time has come (no lookahead), then one `run` message with
        the cues of passes due within RUN_LEAD_S (the receiver's run starts before the kick; board only)."""
        if not self.rows:
            return
        w = self._clock.since() if self.real else None
        batch = self._take_rows(ft)
        if batch:
            msg = proto.rows(ft, batch, w=w)
            if at is None:
                self._out.append(msg)
            else:
                self._out.insert(at, msg)
                at += 1
        cues = self._take_cues(ft)
        if cues:
            msg = proto.runs(ft, cues, w=w)
            if at is None:
                self._out.append(msg)
            else:
                self._out.insert(at, msg)

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
        return not self._tasks and not self._done and not self._wq and self._wtask is None and all(d.idle for d in self._dirs)

    def _prepass(self) -> None:
        """Replay: every moment is known up front, analyst lines come from the recording."""
        rec = {p.moment_id: p for p in self.bundle.recorded or []}
        kinds = self.bundle.recorded_kinds or {}
        eng = FactEngine(self.meta)
        mb = MomentBuilder(eng, self._rows)
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
        moments = build_layers(self.meta, events, self._rows if self._rows is not None else enrich(self.meta, events).rows,
                               scene_at=self.start if self.bundle.variant is not None else None)
        if self.mode == "live":
            moments = [m for m in moments if m.t >= self.start and (self.until is None or m.t <= self.until)]
        return moments

    def _release_layers(self, ft: float) -> None:
        while self._li < len(self._layers) and self._layers[self._li].t <= ft:
            m = self._layers[self._li]
            self._li += 1
            self._moment_t[m.id] = m.t
            self._push(m)

    async def _quiet(self, ft: float, eng: FactEngine) -> None:
        """A quiet spell: the pattern detector may have a habit to point out (from the events so far, no lookahead)."""
        if self._pat is None:
            return
        for m, ev in self._pat.quiet(ft):
            m.t = max(m.t, self.start)
            side, half = ev["side"], ev["half"]
            self._ins[m.id] = ev
            self.booth["setups"][(side, half)] = {"id": m.id, "t": m.t, "clock": m.clock, "what": m.params["what"], "lines": {}}
            who = f"{m.params['player']} keeps winning it, " if m.params.get("player") else ""
            self._out.append(self._log(ft, m.t, "detector", "pattern", m.id,
                                       f"Pattern found: {who}{ev['team']} won the ball in their own half {ev['wins']} times since "
                                       f"{m.params['since']}, the first pass went short every time, 0 balls across", ev))
            await self._on_moment(m, eng, ft)

    def _attach_payoff(self, m: Moment, ft: float) -> None:
        """A goal analysis: if this broadcast said a set-up for the scoring side's habit and this goal broke it, the analyst is told so
        (`pays_off`) and the overlay gets the break's evidence. A goal that did not break it gets nothing (the prompt says not to refer back)."""
        if self._pat is None or self._pat.last is None:
            return
        side = "H" if m.params.get("team") == self.meta.teams["H"].name else "A"
        setup = self.booth["setups"].get((side, self._pat.last.period))
        if not setup or not setup["lines"]:
            return
        brk = self._pat.broken_by(side)
        if brk is None:
            return
        m.params["pays_off"] = {"habit": setup["what"], **brk["facts"]}
        self._ins[m.id] = {**brk["evidence"], "of": setup["id"], "setup_t": setup["t"], "setup_clock": setup["clock"]}
        self._out.append(self._log(ft, m.t, "detector", "payoff", m.id,
                                   f"Goal breaks the pattern from {setup['clock']}': {brk['facts']['this_time']}", self._ins[m.id]))

    def _no_recording(self, m: Moment) -> None:
        """A model moment without a recorded entry: the publisher uses the templates, so `queued` still gets its `ready`."""
        lines = {k: render_variants(m, *k.split("/")) for k in KEYS}
        step = {"step": "fallback", "moment": m.id, "attempt": 0, "at": 0.0, "keys": list(KEYS)}
        self._complete(m, Published(m.id, lines, {k: "template" for k in KEYS}, [step], 0.0))

    def _push(self, m: Moment) -> None:
        if self.fast and m.kind in REPLACED_KINDS:  # the fast layer calls the kick and the receipt instead (7.1)
            return
        self._energy[m.id] = energy_of(m)
        self._moments[m.id] = m
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
        if m.kind == "goal_analysis":
            self._push_score_line(m)

    def _push_score_line(self, m: Moment) -> None:
        line = score_line_for(m, self.meta, self.bundle.duration)
        self._moment_t[line.id] = m.t
        self._push(line)

    async def _on_moment(self, m: Moment, eng: FactEngine, ft: float) -> None:
        self._moment_t[m.id] = m.t
        if m.kind == "goal_analysis":
            self._attach_payoff(m, ft)
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
        key = (self.meta.id, self.bundle.variant, m.id)  # a generated scene (variant) is another match after its fork
        if key not in memo:
            if len(memo) >= 4096:
                memo.pop(next(iter(memo)))
            memo[key] = {k: list(d) for k, d in zip(KEYS, self._said)}
            if m.kind == "goal_analysis" and self._pat is not None and self._pat.last is not None:  # v7: the set-up this broadcast said for the scoring side
                side = "H" if m.params.get("team") == self.meta.teams["H"].name else "A"
                setup = self.booth["setups"].get((side, self._pat.last.period))
                for k, line in (setup or {}).get("lines", {}).items():
                    memo[key][f"{SETUP}{k}"] = [line]
            if m.kind == "goal_analysis":  # v6: the lead's score line comes right after the co line; the analyst must not say its idiom first
                line = score_line_for(m, self.meta, self.bundle.duration)
                for k in KEYS:
                    variants = render_variants(line, *k.split("/"))
                    if variants:  # the live director takes the last (longest) wording of the first score line
                        memo[key][f"{AFTER}{k}"] = [variants[-1]]
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

    # ---------- the world booth ----------
    def _world_want(self, mid: int) -> None:
        """The English booth just called this moment: the world booth writes it too (once, in calling order)."""
        if mid not in self._wseen and mid in self._moments:
            self._wseen.add(mid)
            self._wq.append(mid)

    def _world_recent(self, m: Moment) -> dict[str, list[str]]:
        """The world prompt's continuity: per world channel the lines this broadcast published on it (fixed by calling order, so a cached
        re-run builds the same prompt), the set-up line a goal may pay off, and the lead's score line is written after, so it is not given."""
        recent = {k: list(v[-RECENT_LINES:]) for k, v in self.booth["world_lines"].items()}
        if m.kind == "goal_analysis" and self._pat is not None and self._pat.last is not None:
            side = "H" if m.params.get("team") == self.meta.teams["H"].name else "A"
            setup = self.booth["setups"].get((side, self._pat.last.period))
            lines = self.booth["world_pubs"].get(setup["id"], {}) if setup else {}
            for k, line in lines.items():
                recent[f"{SETUP}{k}"] = [line]
        return recent

    async def _world_write(self, m: Moment, snapshot: dict, recent: dict[str, list[str]]) -> Published:
        try:
            return await asyncio.wait_for(write_moment(self.live.world_guarded(self._wbudget), self.meta, m, snapshot, recent, world=True),
                                          self.live.job_timeout_s)
        except Exception as exc:  # the stream never stops for one moment; a world line without its call is simply not said
            step = {"step": "analyst_error", "reason": f"{type(exc).__name__}: {exc}", "moment": m.id, "attempt": 0, "at": time.time()}
            return Published(m.id, {k: [] for k in WORLD_KEYS}, {k: "none" for k in WORLD_KEYS}, [step], 0.0)

    async def _world_pump(self, ft: float) -> None:
        """Run the world calls one after another. A finished call is pushed to the world channels; a cached prompt is answered at once
        (no call, same tick); otherwise the next call starts and the pump waits for it."""
        while True:
            if self._wtask is not None:
                m, task = self._wtask
                if not task.done():
                    return
                self._wtask = None
                self._wlat = max(0.5, time.monotonic() - self._wstart)
                self._world_done(m, task.result(), ft)
            if not self._wq:
                return
            mid = self._world_next(ft) if self.live.world_skip_late and self.real else self._wq.pop(0)
            if mid is None:
                return
            m = world_moment(self._moments[mid])
            snapshot, recent = self._eng.snapshot(), self._world_recent(m)  # the match as it stands when the English booth called it
            guarded = self.live.world_guarded(self._wbudget)
            cached = guarded.has(build_world_prompt(m, snapshot, self.meta, recent=recent))
            self._out.append(self._log(ft, m.t, "analyst", "lookup" if cached else "writing", m.id,
                                       f"World booth {'looks up' if cached else 'is writing'} moment {m.id} for "
                                       f"{', '.join(k.split('/')[0] for k in WORLD_KEYS)} ({'answer cache, no model call' if cached else 'model call started'})",
                                       {"world": True}))
            if cached or not self.paced:
                self._world_done(m, await self._world_write(m, snapshot, recent), ft)
            else:
                self._wstart = time.monotonic()
                self._wtask = (m, asyncio.create_task(self._world_write(m, snapshot, recent)))

    def _world_next(self, ft: float) -> int | None:
        """world_skip_late: drop the waiting moments whose answer would come back too old to be said (no call is made for them, each
        gets a `too_late` log), then take the most important one left, the newest first among equals."""
        def late(m: Moment) -> bool:
            return ft + self._wlat * self.speed > m.t + m.ttl * self.speed
        for mid in [i for i in self._wq if late(self._moments[i])]:
            self._wq.remove(mid)
            m = self._moments[mid]
            self._out.append(self._log(ft, m.t, "director", "too_late", mid,
                                       f"World booth skips moment {mid} ({m.kind}): it would be too old to say when written, no model call",
                                       {"world": True}))
        if not self._wq:
            return None
        mid = max(self._wq, key=lambda i: (self._moments[i].priority, self._moments[i].t))
        self._wq.remove(mid)
        return mid

    def _world_done(self, m: Moment, pub: Published, ft: float) -> None:
        self.wpubs[m.id] = pub
        said = {}
        for k in WORLD_KEYS:
            if pub.lines.get(k):
                said[k] = pub.lines[k][-1]
            # continuity is what the booth wrote first, before the check: a line the verifier stops (or a rule added later) then changes
            # nothing in the prompts of the moments after it, so their answers stay valid; the prompt calls it the channel's last lines
            line = pub.written.get(k) or said.get(k)
            if line:
                self.booth["world_lines"][k].append(line)
        self.booth["world_pubs"][m.id] = said
        for step in pub.trail:
            detail = {**{k: v for k, v in step.items() if k not in ("step", "moment", "at")}, "world": True}
            msg = proto.describe(step).replace("Analyst", "World booth", 1)
            self._out.append(self._log(ft, ft, proto.AGENTS.get(step["step"], "analyst"), step["step"], m.id, msg, detail,
                                       wall=step["at"] if self.real else None))
        self._out.append(self._log(ft, ft, "publisher", "ready", m.id, f"Moment {m.id} ready on the world channels: {len(said)} of "
                                   f"{len(WORLD_KEYS)} lines by the analyst" + (" (cached, not written in this run)" if pub.cached and said else ""),
                                   {"world": True, **({"cached": True} if pub.cached and said else {})}))
        if not said:
            return
        wm = replace(m, ready_t=ft)  # a copy: the core directors hold the original moment
        for key, d in zip(self.keys[len(KEYS):], self._dirs[len(KEYS):]):
            if pub.lines.get(key):
                d.push(wm)

    async def _tick(self, ft: float) -> None:
        self._horizon = ft
        for mid, (m, task) in list(self._tasks.items()):
            if task.done():
                del self._tasks[mid]
                self._complete(m, task.result())
        self._release(ft)
        core = len(KEYS)
        notes = []
        for ch, d in enumerate(self._dirs[:core]):
            d.advance(ft)
            notes += [(ch, kind, sp) for kind, sp in d.drain()]
        self._emit(ft, notes)
        if self.world:  # the world booth writes for what the English booth just called, then its channels advance in the same tick
            await self._world_pump(ft)
            notes = []
            for ch, d in enumerate(self._dirs[core:], core):
                d.advance(ft)
                notes += [(ch, kind, sp) for kind, sp in d.drain()]
            self._emit(ft, notes)

    def _emit(self, ft: float, notes: list) -> None:
        """The messages of one tick's director notes: captions, voice starts, cuts and skips."""
        captioned: dict[tuple[int, int], dict] = {}  # live: captions made in this tick, which a voice start at the same instant folds into
        for ch, kind, sp in sorted(notes, key=lambda n: (n[2].end if n[1] == "cut" else n[2].start, n[0])):
            key = self.keys[ch]
            pub = self.pubs.get(sp.moment_id) if ch < len(KEYS) else self.wpubs.get(sp.moment_id)
            from_analyst = pub is not None and pub.sources.get(key) == "analyst" and bool(pub.lines[key]) and sp.text == pub.lines[key][-1]
            if self.world and key.startswith("en/") and kind in ("caption", "start"):
                self._world_want(sp.moment_id)
            wall = lat = None
            if self.real:  # wall seconds since the stream started, and since the event was due
                wall = self._clock.since()
                due = self._moment_t.get(sp.moment_id)
                lat = None if due is None else max(0.0, time.monotonic() - self._clock.wall(due))

            if self.run_id is not None:
                self.lines[(ch, sp.moment_id)] = (sp.text, key.split("/")[0])
                self.speakers[(ch, sp.moment_id)] = who_of(key, sp.voice)
                self.energies[(ch, sp.moment_id)] = self._energy.get(sp.moment_id, "calm")
            if is_pattern_id(sp.moment_id) and (kind == "caption" or (kind == "start" and not self._captions_first)):
                for setup in self.booth["setups"].values():  # the set-up as this channel showed it: the pay-off refers back to these words
                    if setup["id"] == sp.moment_id:
                        setup["lines"][key] = sp.text
            if kind == "caption" or (kind == "start" and not self._captions_first):  # continuity for the analyst: what this channel just said
                if not self.fast or continuity_id(sp.moment_id):  # v5 (7.3): fast and context wording never enters a prompt
                    self._said[ch].append(sp.text)
            elif kind == "skip" and not self.fast and sp.text in self._said[ch]:  # shown but never spoken: not part of what the booth said
                self._said[ch].remove(sp.text)  # (v5 keeps it: a skip depends on how busy the voice was)
            def say(cut: bool) -> dict:
                return proto.say(ft, ch, sp.moment_id, sp.kind, sp.voice, sp.text, sp.start, sp.end, cut,
                                 "analyst" if from_analyst else "template", w=wall, lat=lat, cached=from_analyst and pub.cached,
                                 who=who_of(key, sp.voice), ins=self._ins.get(sp.moment_id))

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
