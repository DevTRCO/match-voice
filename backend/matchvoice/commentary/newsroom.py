"""The newsroom: Analyst and Verifier as a Microsoft Agent Framework workflow.

    request -> Analyst -> Verifier --(all lines pass)------------> Publisher -> lines
                   ^          |
                   +----------+--(some fail, retries left)

Lines that still fail after the retries are replaced by the template fallback, so the
commentary never goes out unchecked and never goes missing. The world booth (commentary/world.py) runs the
same workflow with its own keys and prompt; it has no templates, so a world line that still fails is not said.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, replace

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler
from typing_extensions import Never

from ..schema import MatchMeta
from .analyst import KEYS, MAX_CHARS, BudgetExceeded, GuardedLLM, build_prompt, parse_lines
from .moments import Moment, render_variants
from .lang import WORLD_KEYS
from .verifier import Verifier, allowed_for
from .world import build_world_prompt

MAX_RETRIES = 1


@dataclass
class WriteRequest:
    moment: Moment
    snapshot: dict
    attempt: int = 0
    accepted: dict[str, str] = field(default_factory=dict)
    feedback: dict[str, str] = field(default_factory=dict)
    trail: list[dict] = field(default_factory=list)
    latency_s: float = 0.0
    recent: dict[str, list[str]] = field(default_factory=dict)  # channel key -> the last lines it spoke, for continuity (never facts)
    failed_hard: str | None = None  # model unavailable: skip straight to the fallback
    calls: int = 0  # answers that needed a real model call
    hits: int = 0  # answers served from the disk cache
    keys: tuple[str, ...] = tuple(KEYS)  # the channels this request writes for
    world: bool = False  # the world booth: its prompt, no template fallback, and the beginner no-count rule only for analysis lines
    written: dict[str, str] = field(default_factory=dict)  # the first answer as the model wrote it, before the check


@dataclass
class Draft:
    request: WriteRequest
    lines: dict[str, str]


@dataclass(frozen=True)
class Reviewed:
    """Immutable snapshot, so edge conditions never see state that changes later."""

    request: WriteRequest
    failing: tuple[str, ...]
    retry: bool


@dataclass
class Published:
    moment_id: int
    lines: dict[str, list[str]]  # "en/expert" -> wordings, short to long
    sources: dict[str, str]  # "en/expert" -> analyst | template
    trail: list[dict]
    latency_s: float
    cached: bool = False  # every analyst answer came from the disk cache, no model call was made for this moment
    written: dict[str, str] = field(default_factory=dict)  # the first answer as written (the world booth's continuity, see runner._world_done)


def _log(req: WriteRequest, step: str, **detail) -> None:
    req.trail.append({"step": step, "moment": req.moment.id, "attempt": req.attempt, "at": round(time.time(), 3), **detail})


class AnalystExecutor(Executor):
    def __init__(self, llm: GuardedLLM, meta: MatchMeta, id: str = "analyst"):
        super().__init__(id=id)
        self.llm, self.meta = llm, meta

    async def _run(self, req: WriteRequest, ctx: WorkflowContext[Draft]) -> None:
        wanted = [k for k in req.keys if k not in req.accepted]
        prompt = (build_world_prompt if req.world else build_prompt)(req.moment, req.snapshot, self.meta, wanted, req.feedback or None,
                                                                    req.recent or None)
        t0 = time.monotonic()
        try:
            raw = await self.llm(prompt)
            lines = parse_lines(raw, wanted)
            if req.attempt == 0:
                req.written = dict(lines)
            req.latency_s += self.llm.last_latency_s
            req.hits += self.llm.last_cached
            req.calls += not self.llm.last_cached
            # latency_s is what the model call took when it was made, wall_s is what this run waited
            _log(req, "analyst_wrote", lines=len(lines), cached=self.llm.last_cached,
                 latency_s=round(self.llm.last_latency_s, 2), wall_s=round(time.monotonic() - t0, 2))
        except BudgetExceeded as exc:
            lines, req.failed_hard = {}, str(exc)
            _log(req, "analyst_unavailable", reason=str(exc))
        except Exception as exc:  # model error or unreadable answer: recover through the fallback
            self.llm.discard(prompt)  # never keep an answer we could not use
            lines, req.failed_hard = {}, f"{type(exc).__name__}: {exc}"
            _log(req, "analyst_error", reason=req.failed_hard)
        await ctx.send_message(Draft(req, lines))

    @handler
    async def write(self, req: WriteRequest, ctx: WorkflowContext[Draft]) -> None:
        await self._run(req, ctx)

    @handler
    async def retry(self, reviewed: Reviewed, ctx: WorkflowContext[Draft]) -> None:
        req = replace(reviewed.request, attempt=reviewed.request.attempt + 1)
        _log(req, "retry", failing=list(reviewed.failing))
        await self._run(req, ctx)


class VerifierExecutor(Executor):
    def __init__(self, meta: MatchMeta, id: str = "verifier"):
        super().__init__(id=id)
        self.meta, self.verifier = meta, Verifier(meta)

    @handler
    async def check(self, draft: Draft, ctx: WorkflowContext[Reviewed]) -> None:
        req = draft.request
        allowed = allowed_for(req.moment, req.snapshot, self.meta)
        accepted, feedback = dict(req.accepted), {}
        for key in req.keys:
            if key in accepted:
                continue
            text = draft.lines.get(key)
            if text is None:
                feedback[key] = "no line was returned for this key"
                continue
            lang, style = key.split("/")
            # the beginner no-count rule is the analysis's: a world lead's story note may say its one season count, as the core template does
            counted = style if not req.world or req.moment.voice == "analyst" else None
            verdict = self.verifier.check(text, lang, allowed, max_s=MAX_CHARS / 12, style=counted, spelled=True)
            if verdict.ok:
                accepted[key] = text
            else:
                feedback[key] = verdict.feedback()
                _log(req, "rejected", key=key, text=text, why=verdict.feedback())
        failing = tuple(k for k in req.keys if k not in accepted)
        _log(req, "verified", accepted=len(accepted), failing=len(failing))
        snap = replace(req, accepted=accepted, feedback=feedback)
        retry = bool(failing) and req.attempt < MAX_RETRIES and req.failed_hard is None
        await ctx.send_message(Reviewed(snap, failing, retry))


END_MARKS = ".!?…\"'»)。！？」"


def finish_line(text: str, lang: str = "en", names: frozenset[str] = frozenset()) -> str:
    """An accepted line ends like a spoken sentence: a model line that stops on a bare word ("... Level") gets a full stop,
    so the caption reads finished and the voice falls at the end. Turkish: a roster name written with the Turkish capital "İ"
    ("İbsen") gets its roster spelling back ("Ibsen"), as Turkish TV graphics write a foreign name; Turkish words keep their "İ"."""
    t = text.rstrip()
    if lang == "tr" and "İ" in t and names:
        t = re.sub(r"İ\w*", lambda w: "I" + w.group(0)[1:] if "I" + w.group(0)[1:] in names else w.group(0), t)
    return t if not t or t[-1] in END_MARKS else t + ("。" if lang == "ja" else ".")


def roster_names(meta: MatchMeta | None) -> frozenset[str]:
    """Every first name and surname of both squads, as the roster spells them."""
    if meta is None:
        return frozenset()
    return frozenset(w for team in meta.teams.values() for p in team.players for w in re.split(r"[\s-]+", p.name) if w)


class PublisherExecutor(Executor):
    def __init__(self, id: str = "publisher", meta: MatchMeta | None = None):
        super().__init__(id=id)
        self.names = roster_names(meta)

    @handler
    async def publish(self, reviewed: Reviewed, ctx: WorkflowContext[Never, Published]) -> None:
        req = reviewed.request
        lines: dict[str, list[str]] = {}
        sources: dict[str, str] = {}
        for key in req.keys:
            lang, style = key.split("/")
            if req.world:  # no templates: the model's line or nothing
                lines[key] = [finish_line(req.accepted[key], lang, self.names)] if key in req.accepted else []
                sources[key] = "analyst" if key in req.accepted else "none"
                continue
            fallback = render_variants(req.moment, lang, style)
            if key in req.accepted:
                lines[key], sources[key] = fallback + [finish_line(req.accepted[key])], "analyst"
            else:
                lines[key], sources[key] = fallback, "template"
        if reviewed.failing:
            _log(req, "dropped" if req.world else "fallback", keys=list(reviewed.failing))
        await ctx.yield_output(Published(req.moment.id, lines, sources, req.trail, req.latency_s,
                                         cached=req.hits > 0 and req.calls == 0, written=dict(req.written)))


def build_newsroom(llm: GuardedLLM, meta: MatchMeta):
    analyst, verifier, publisher = AnalystExecutor(llm, meta), VerifierExecutor(meta), PublisherExecutor(meta=meta)

    return (
        WorkflowBuilder(start_executor=analyst, name="newsroom", max_iterations=20)
        .add_edge(analyst, verifier)
        .add_edge(verifier, analyst, condition=lambda r: r.retry)
        .add_edge(verifier, publisher, condition=lambda r: not r.retry)
        .build()
    )


async def write_moment(llm: GuardedLLM, meta: MatchMeta, moment: Moment, snapshot: dict,
                       recent: dict[str, list[str]] | None = None, world: bool = False) -> Published:
    """One moment through the newsroom. `world`: the world booth writes the line of every world channel (llm must carry its prompt version)."""
    req = WriteRequest(moment, snapshot, recent=dict(recent or {}), keys=WORLD_KEYS if world else tuple(KEYS), world=world)
    events = await build_newsroom(llm, meta).run(req)
    return events.get_outputs()[0]
