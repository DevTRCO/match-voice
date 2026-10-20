"""The newsroom: Analyst and Verifier as a Microsoft Agent Framework workflow.

    request -> Analyst -> Verifier --(all lines pass)------------> Publisher -> lines
                   ^          |
                   +----------+--(some fail, retries left)

Lines that still fail after the retries are replaced by the template fallback, so the
commentary never goes out unchecked and never goes missing.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler
from typing_extensions import Never

from ..schema import MatchMeta
from .analyst import KEYS, MAX_CHARS, BudgetExceeded, GuardedLLM, build_prompt, parse_lines
from .moments import Moment, render_variants
from .verifier import Verifier, allowed_for

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
    failed_hard: str | None = None  # model unavailable: skip straight to the fallback


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


def _log(req: WriteRequest, step: str, **detail) -> None:
    req.trail.append({"step": step, "moment": req.moment.id, "attempt": req.attempt, "at": round(time.time(), 3), **detail})


class AnalystExecutor(Executor):
    def __init__(self, llm: GuardedLLM, meta: MatchMeta, id: str = "analyst"):
        super().__init__(id=id)
        self.llm, self.meta = llm, meta

    async def _run(self, req: WriteRequest, ctx: WorkflowContext[Draft]) -> None:
        wanted = [k for k in KEYS if k not in req.accepted]
        prompt = build_prompt(req.moment, req.snapshot, self.meta, wanted, req.feedback or None)
        try:
            raw = await self.llm(prompt)
            lines = parse_lines(raw, wanted)
            req.latency_s += self.llm.last_latency_s
            _log(req, "analyst_wrote", lines=len(lines), cached=self.llm.last_cached,
                 latency_s=round(self.llm.last_latency_s, 2))
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
        for key in KEYS:
            if key in accepted:
                continue
            text = draft.lines.get(key)
            if text is None:
                feedback[key] = "no line was returned for this key"
                continue
            verdict = self.verifier.check(text, key.split("/")[0], allowed, max_s=MAX_CHARS / 12)
            if verdict.ok:
                accepted[key] = text
            else:
                feedback[key] = verdict.feedback()
                _log(req, "rejected", key=key, text=text, why=verdict.feedback())
        failing = tuple(k for k in KEYS if k not in accepted)
        _log(req, "verified", accepted=len(accepted), failing=len(failing))
        snap = replace(req, accepted=accepted, feedback=feedback)
        retry = bool(failing) and req.attempt < MAX_RETRIES and req.failed_hard is None
        await ctx.send_message(Reviewed(snap, failing, retry))


class PublisherExecutor(Executor):
    def __init__(self, id: str = "publisher"):
        super().__init__(id=id)

    @handler
    async def publish(self, reviewed: Reviewed, ctx: WorkflowContext[Never, Published]) -> None:
        req = reviewed.request
        lines: dict[str, list[str]] = {}
        sources: dict[str, str] = {}
        for key in KEYS:
            lang, style = key.split("/")
            fallback = render_variants(req.moment, lang, style)
            if key in req.accepted:
                lines[key], sources[key] = fallback + [req.accepted[key]], "analyst"
            else:
                lines[key], sources[key] = fallback, "template"
        if reviewed.failing:
            _log(req, "fallback", keys=list(reviewed.failing))
        await ctx.yield_output(Published(req.moment.id, lines, sources, req.trail, req.latency_s))


def build_newsroom(llm: GuardedLLM, meta: MatchMeta):
    analyst, verifier, publisher = AnalystExecutor(llm, meta), VerifierExecutor(meta), PublisherExecutor()

    return (
        WorkflowBuilder(start_executor=analyst, name="newsroom", max_iterations=20)
        .add_edge(analyst, verifier)
        .add_edge(verifier, analyst, condition=lambda r: r.retry)
        .add_edge(verifier, publisher, condition=lambda r: not r.retry)
        .build()
    )


async def write_moment(llm: GuardedLLM, meta: MatchMeta, moment: Moment, snapshot: dict) -> Published:
    events = await build_newsroom(llm, meta).run(WriteRequest(moment, snapshot))
    return events.get_outputs()[0]
