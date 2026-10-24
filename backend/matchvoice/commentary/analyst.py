"""Analyst agent: writes the slow-path commentary lines with a model.

The model sees only the facts of one moment and must answer with one line per
language and style. Everything it writes is checked by the verifier afterwards.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from ..config import ROOT
from ..schema import MatchMeta
from .delivery import energy_of
from .lang import LANGS, STYLES
from .moments import Moment, render_params

PROMPT_VERSION = "v4"  # v4: the colour analyst never repeats the caller's reaction, a go-ahead example that is not the demo goal, no calques; v3: named booth, voice guide, few-shot, number discipline, energy, continuity
MAX_CHARS = 150
KEYS = [f"{lang}/{style}" for lang in LANGS for style in STYLES]
RECENT_LINES = 3  # lines a channel spoke last that the analyst sees, so it does not repeat itself and can call back

CALLER = "Ewan Marsh"  # play-by-play: the template fast path
ANALYST = "Nadia Rowe"  # colour: the model writes her lines

SYSTEM = f"""You write the spoken lines for a two-person football commentary booth in a synthetic, fictional league.

The booth
- {CALLER}, play-by-play caller. Present tense, short, urgent, with rhythm. He names the player, names the action, reacts. He never explains.
- {ANALYST}, colour analyst. She speaks just after the play and reads the game in ONE sharp thought: what it changes, what it shows. Dry, certain, never a list, never a recital of numbers.
You write what they SAY, out loud, about one moment of a match, using ONLY the facts you are given. Moments with voice "analyst" are {ANALYST}'s, moments with voice "pbp" are {CALLER}'s. Never write their names into a line.

Voice, per language. Write each line natively, the way a broadcaster in that language talks. Never translate from English.
- en: British broadcast cadence. Understated until the moment lifts. Contractions, fragments, a clipped reaction ("Great stop."). Football words: keeper, leveller, front foot, the net. No American words.
- de: German TV commentator register. Direct, present tense, short hard sentences, plain Umgangssprache with Reporter-Ausrufe ("Und der ist drin!", "Was für eine Parade!"). No Zahlenvorlesen, no Fremdwortketten. Say "die Siegchance", the way a reporter would, never "Siegwahrscheinlichkeit".
- fr: French broadcast pace. Quick, rhythmic, nominal phrases and exclamations ("Et c'est dedans !", "Quelle parade !"). Spoken French, not written French. Never a calque of English: say "fait trembler les filets", not "trouve le filet".

Style
- beginner: for a casual viewer. Plain words, any football term explained in a few words. No xG, no percentages, no stats.
- expert: for a fan who knows the game. One sharp analytical thought. xG or win probability only if it IS the thought.

Number discipline
- At most ONE number per line. A scoreline counts as that one number. Beginner lines carry no number except the score, and not even that when the thought does not need it.
- Never read the match clock as a number ("in the 14th minute") unless it is the one number. Never list shots, shares and probabilities together. A line that recites statistics is wrong.
- Use digits for the number you do write, and only a number that appears in the facts. Never invent statistics, players, minutes or results, and never predict the future.

Facts and names
- Scores are always written home-away: the first number is the home team's goals, the second is the away team's, whoever scored last. Copy "score_home_away" exactly as given and never swap it. A match that is 0-1 is a lead for the away team.
- Refer to players by surname only and avoid gendered pronouns for players. A club can be named by its first word ("Wexmoor"), as a broadcaster would.

Energy (given with the moment)
- calm: low and conversational. A dry observation. No exclamation marks.
- rising: quicker, shorter, one exclamation at most. The booth leans in.
- peak: the biggest moment. {CALLER}'s lines open with a fragment of pure reaction, then one thought. {ANALYST}'s lines never open with a reaction: the caller has already shouted it, so she starts with the thought. Exclamation marks allowed, fragments welcome.

Length: aim for 60 to 110 characters, never more than {MAX_CHARS}. One sentence, or two short ones, because they are spoken. No emojis, no markdown, no stage directions.

Good lines (another fixture, Harbour Rovers at home to Ashby Town; never reuse its names or numbers)
peak, goal_analysis, go_ahead, 2-1, Okoro scores, chance of a win now 58 percent:
{{"en/beginner": "Harbour lead 2-1 now, and Ashby suddenly have a lot of work to do.", "en/expert": "Harbour's chance of a win is up to 58 percent, and Ashby have to chase it.", "de/beginner": "Harbour führt 2-1, und Ashby muss jetzt etwas riskieren.", "de/expert": "Okoro dreht das Spiel, und die Siegchance von Harbour liegt bei 58 Prozent.", "fr/beginner": "Harbour mène 2-1, et Ashby va devoir se découvrir.", "fr/expert": "Okoro fait basculer le match : Harbour monte à 58 % de chances de gagner."}}
rising, big_save_analysis, Brandt saves from Valdis, chance worth 0.58 xG:
{{"en/expert": "Brandt keeps out a chance worth 0.44 expected goals. A huge stop.", "de/beginner": "Was für eine Parade von Brandt! Das war schon fast ein Tor.", "fr/expert": "Brandt repousse une occasion à 0,44 but attendu. Énorme."}}
calm, momentum, Ashby on top, still 0-0:
{{"en/beginner": "Ashby are pushing now, but it's still 0-0.", "de/expert": "Ashby drückt, und Harbour findet keinen Ausweg.", "fr/beginner": "Ashby met la pression, mais le score reste 0-0."}}

Bad lines. These were written for earlier versions of this booth. Every one recites numbers like a spreadsheet, none sounds spoken. Never write like this:
- "Marlow Bay United own 83% of the momentum over the last 5 minutes, with 2 shots and 0.06 xG, while the game stays 0-0 and they sit at 42% to win."  (six numbers in one breath)
- "Marlow Bay dominiert mit 84 Prozent Momentum über 5 Minuten, 0,42 xG gegen 0,02 und 84 Prozent Siegchance. Stand: 0-1."  (stat list, no voice)
- "Marlow Bay United a pris le contrôle, avec 84 % de l'élan, c'est-à-dire la domination du jeu, sur les 5 dernières minutes et 2 tirs. Le score 0-1 leur est favorable."  (a report, not a call)
- "Lemaire's 14th-minute opener (0-1) came from a 0.25 xG chance, lifting Marlow Bay's win probability from 61 to 84 percent."  (clock, score, xG and two probabilities in one line)
- "Trevino makes a huge save at 65 minutes to deny Rahimi, a chance that looked almost certain to be a goal. Tamsworth United trail 0-1."  (a log entry with a clock, too long, no reaction)

Answer with a single JSON object and nothing else."""

ANGLE = {
    "goal_analysis": "What this goal changes for the game, in one thought. The caller has already shouted the goal, so do not react again and do not open with an exclamation: start with the thought.",
    "momentum": "Who is on top and what that is doing to the other side. A read of the game, not a count.",
    "big_save_analysis": "The keeper's moment. Why it mattered. The caller has already reacted, so start with the thought.",
    "big_chance_analysis": "The miss. What it leaves open. No blame words.",
    "shot_milestone": "One shooter keeps trying. What that says about the game.",
}
TAG_MEANING = "tags: opener = first goal of the match, equaliser = made it level, go_ahead = took the lead, late = final minutes, comeback = turned a deficit around"
ENERGY_NOTE = {
    "calm": "calm: low, conversational, a dry observation, no exclamation marks.",
    "rising": "rising: quicker and shorter, the booth leans in, at most one exclamation mark.",
    "peak": "peak: the biggest moment of the match. Open with a fragment of pure reaction, then one thought.",
}
ENERGY_NOTE_ANALYST = {
    **ENERGY_NOTE,
    "rising": "rising: quicker and shorter, at most one exclamation mark. The caller has already reacted: do not open with an exclamation, start with the thought.",
    "peak": "peak: the biggest moment of the match. The caller has already shouted it, so do not open with a reaction or an exclamation: start with the thought. One exclamation mark at most.",
}


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
                 feedback: dict[str, str] | None = None, recent: dict[str, list[str]] | None = None) -> str:
    """The user message for one moment. `recent` maps a channel key to the lines that channel spoke last (oldest first):
    the booth's own continuity, taken from lines already shown or spoken, never a source of facts."""
    p = render_params(m, "en")
    p.pop("tags", None)
    if "score" in p:  # the moment's own score is home-away too; name it so the model cannot read it as scorer-first
        p["score_home_away"] = p.pop("score")
    st = snapshot["stats"]
    facts = {
        "moment": {"kind": m.kind, "voice": m.voice, "match_clock": m.clock, **p, "tags": m.params.get("tags", "")},
        "match": {
            "home": meta.teams["H"].name, "away": meta.teams["A"].name,
            "score_home_away": f"{snapshot['score'][0]}-{snapshot['score'][1]}",
            "possession_pct": {"home": st["H"]["possession"], "away": st["A"]["possession"]},
            "shots": {"home": st["H"]["shots"], "away": st["A"]["shots"]},
            "xg": {"home": st["H"]["xg"], "away": st["A"]["xg"]},
            "win_probability_pct": {"home": round(100 * snapshot["win"][0]), "draw": round(100 * snapshot["win"][1]),
                                    "away": round(100 * snapshot["win"][2])},
        },
    }
    keys = only or KEYS
    speaker = ANALYST if m.voice == "analyst" else CALLER
    energy = energy_of(m)
    parts = [
        f"This moment is {speaker}'s ({'colour analyst' if m.voice == 'analyst' else 'play-by-play caller'}). Energy: {energy}. {(ENERGY_NOTE_ANALYST if m.voice == 'analyst' else ENERGY_NOTE)[energy]}",
        f"Angle: {ANGLE.get(m.kind, 'One sharp thought about what just happened.')}",
        "", "Facts (the only source you may use; " + TAG_MEANING + "):", json.dumps(facts, ensure_ascii=False, indent=1),
    ]
    said = {k: [t for t in (recent or {}).get(k, [])[-RECENT_LINES:] if t] for k in keys}
    if any(said.values()):
        parts += ["", "Continuity. The booth just said these lines on each channel, oldest first. Do not repeat their wording, do not open "
                  "like the last one, and do not copy a number from them (numbers come from the facts only). You may nod back to one of them:"]
        for k in keys:
            if said[k]:
                parts.append(f"{k}:")
                parts += [f'  - "{t}"' for t in said[k]]
    parts += [
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
    """Wraps a model call with a disk cache and a hard call budget.

    A call that is under way is shared: a second request for the same prompt (a live stream that restarted, for
    example) waits for it instead of paying again, and it finishes and is cached even if its first caller went away."""

    def __init__(self, call: LLM, budget: CallBudget, model: str, cache_dir: Path | None = None,
                 use_cache: bool = True, inflight: dict[str, asyncio.Task] | None = None):
        """`use_cache=False` is fresh mode: the disk cache is neither read nor written, every prompt is a real call.
        `inflight` is shared between the wrappers of one server, so calls under way are visible to all of them."""
        self._call, self.budget, self.model, self.use_cache = call, budget, model, use_cache
        self.inflight = inflight if inflight is not None else {}
        self.cache_dir = cache_dir if cache_dir is not None else ROOT / "data" / "cache" / "analyst"
        if use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.last_latency_s = 0.0
        self.last_cached = False

    def _path(self, prompt: str) -> Path:
        h = hashlib.sha256(f"{PROMPT_VERSION}|{self.model}|{prompt}".encode()).hexdigest()[:24]
        return self.cache_dir / f"{h}.json"

    def has(self, prompt: str) -> bool:
        """True when this prompt would be answered from the disk cache, without a model call."""
        return self.use_cache and self._path(prompt).exists()

    def discard(self, prompt: str) -> None:
        """Forget a cached answer that turned out to be unusable."""
        self._path(prompt).unlink(missing_ok=True)

    async def __call__(self, prompt: str) -> str:
        path = self._path(prompt)
        if self.use_cache and path.exists():
            hit = json.loads(path.read_text(encoding="utf-8"))
            self.last_cached, self.last_latency_s = True, hit["latency_s"]
            return hit["text"]
        task = self.inflight.get(path.name)
        if task is None:
            self.budget.take()
            task = self.inflight[path.name] = asyncio.ensure_future(self._fetch(prompt, path))
            task.add_done_callback(lambda t, name=path.name: self._settled(name, t))
        text, self.last_latency_s = await asyncio.shield(task)  # a cancelled caller does not cancel the call
        self.last_cached = False
        return text

    async def _fetch(self, prompt: str, path: Path) -> tuple[str, float]:
        t0 = time.perf_counter()
        text = await self._call(prompt)
        latency = time.perf_counter() - t0
        if self.use_cache:
            path.write_text(json.dumps({"text": text, "latency_s": round(latency, 2), "model": self.model},
                                       ensure_ascii=False), encoding="utf-8")
        return text, latency

    def _settled(self, name: str, task: asyncio.Task) -> None:
        self.inflight.pop(name, None)
        if not task.cancelled():
            task.exception()  # mark as retrieved: a call nobody waits for any more may fail quietly


def claude_llm(model: str, api_key: str) -> LLM:
    """The analyst as a Microsoft Agent Framework agent backed by Claude."""
    from agent_framework.anthropic import AnthropicClient

    agent = AnthropicClient(model=model, api_key=api_key).as_agent(
        name="Analyst", instructions=SYSTEM, default_options={"max_tokens": 2048})

    async def call(prompt: str) -> str:
        return (await agent.run(prompt)).text

    return call
