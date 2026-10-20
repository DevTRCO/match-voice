"""Analyst agent: writes the slow-path commentary lines with a model.

The model sees only the facts of one moment and must answer with one line per
language and style. Everything it writes is checked by the verifier afterwards.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from ..config import ROOT
from ..schema import MatchMeta
from .lang import LANGS, STYLES
from .moments import Moment, render_params

PROMPT_VERSION = "v1"
MAX_CHARS = 150
KEYS = [f"{lang}/{style}" for lang in LANGS for style in STYLES]

SYSTEM = f"""You are the Analyst on a live football commentary desk for a synthetic, fictional league. \
You write short spoken commentary lines about one moment of a match, using ONLY the facts you are given.

Rules:
- Write every line natively in its own language, the way a good commentator in that language would say it. Do not translate from English.
- Use digits for every number. Use only numbers that appear in the facts. Never invent statistics, players, minutes or results, and never predict the future.
- Refer to players by surname only and avoid gendered pronouns for players.
- beginner style: for a casual viewer. Plain words, explain any football term in a few words, no xG and no percentages unless you explain them.
- expert style: for a fan who knows the game. Analytical, you may use xG, win probability, shares and speeds from the facts.
- Each line is one spoken sentence, or two short ones, at most {MAX_CHARS} characters. No emojis, no markdown, no stage directions.
- Answer with a single JSON object and nothing else."""


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class CallBudget:
    max_calls: int
    used: int = 0

    def take(self) -> None:
        if self.used >= self.max_calls:
            raise BudgetExceeded(f"call budget of {self.max_calls} reached")
        self.used += 1


LLM = Callable[[str], Awaitable[str]]


def build_prompt(m: Moment, snapshot: dict, meta: MatchMeta, only: list[str] | None = None,
                 feedback: dict[str, str] | None = None) -> str:
    p = render_params(m, "en")
    p.pop("tags", None)
    st = snapshot["stats"]
    facts = {
        "moment": {"kind": m.kind, "match_clock": m.clock, **p, "tags": m.params.get("tags", "")},
        "match": {
            "home": meta.teams["H"].name, "away": meta.teams["A"].name,
            "score": f"{snapshot['score'][0]}-{snapshot['score'][1]}",
            "possession_pct": {"home": st["H"]["possession"], "away": st["A"]["possession"]},
            "shots": {"home": st["H"]["shots"], "away": st["A"]["shots"]},
            "xg": {"home": st["H"]["xg"], "away": st["A"]["xg"]},
            "win_probability_pct": {"home": round(100 * snapshot["win"][0]), "draw": round(100 * snapshot["win"][1]),
                                    "away": round(100 * snapshot["win"][2])},
        },
    }
    keys = only or KEYS
    parts = [
        "Facts (the only source you may use):", json.dumps(facts, ensure_ascii=False, indent=1),
        "", "Write one line for each of these keys (language/style): " + ", ".join(keys) + ".",
        'Answer as JSON like {"en/beginner": "...", "en/expert": "..."} with exactly those keys.',
    ]
    if feedback:
        parts += ["", "Your previous lines were rejected by the fact checker. Fix exactly these problems:"]
        parts += [f"- {k}: {v}" for k, v in feedback.items()]
    return "\n".join(parts)


def parse_lines(raw: str, wanted: list[str]) -> dict[str, str]:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in answer")
    data = json.loads(raw[start:end + 1])
    return {k: str(data[k]).strip() for k in wanted if k in data and str(data[k]).strip()}


class GuardedLLM:
    """Wraps a model call with a disk cache and a hard call budget."""

    def __init__(self, call: LLM, budget: CallBudget, model: str, cache_dir: Path | None = None):
        self._call, self.budget, self.model = call, budget, model
        self.cache_dir = cache_dir if cache_dir is not None else ROOT / "data" / "cache" / "analyst"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.last_latency_s = 0.0
        self.last_cached = False

    def _path(self, prompt: str) -> Path:
        h = hashlib.sha256(f"{PROMPT_VERSION}|{self.model}|{prompt}".encode()).hexdigest()[:24]
        return self.cache_dir / f"{h}.json"

    def discard(self, prompt: str) -> None:
        """Forget a cached answer that turned out to be unusable."""
        self._path(prompt).unlink(missing_ok=True)

    async def __call__(self, prompt: str) -> str:
        path = self._path(prompt)
        if path.exists():
            hit = json.loads(path.read_text(encoding="utf-8"))
            self.last_cached, self.last_latency_s = True, hit["latency_s"]
            return hit["text"]
        self.budget.take()
        t0 = time.perf_counter()
        text = await self._call(prompt)
        self.last_latency_s, self.last_cached = time.perf_counter() - t0, False
        path.write_text(json.dumps({"text": text, "latency_s": round(self.last_latency_s, 2), "model": self.model},
                                   ensure_ascii=False), encoding="utf-8")
        return text


def claude_llm(model: str, api_key: str) -> LLM:
    """The analyst as a Microsoft Agent Framework agent backed by Claude."""
    from agent_framework.anthropic import AnthropicClient

    agent = AnthropicClient(model=model, api_key=api_key).as_agent(
        name="Analyst", instructions=SYSTEM, default_options={"max_tokens": 2048})

    async def call(prompt: str) -> str:
        return (await agent.run(prompt)).text

    return call
