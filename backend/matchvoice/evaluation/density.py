"""The density report (docs/DATA-MODEL.md 7.6 and 8.4, docs/PLAN-DATA.md phase 3): how close the voice is to a broadcast.

    python -m matchvoice.evaluation.density [--out data/eval/density.json] [--report docs/DENSITY.md]

Runs the real pipeline (unpaced live mode at 1x, the dense layers on, all six channels) over the recorded insert, 20 guided windows
(seeds 1001..1020, arcs from a fixed stream) and the three demo matches, with a model call that always raises: 0 calls, 0 credits, no key.
Analyst moments therefore fall back to their templates, so the numbers are a lower bound for the analyst share. Every metric is a pure function
of the overlay messages (`say` and `voice`), the spoken segments being the voice's own slots (`s`, `e`), cut or skipped lines included as they happened.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import re
import statistics
import tempfile
from dataclasses import dataclass
from pathlib import Path

import orjson

from ..commentary.analyst import KEYS, CallBudget
from ..commentary.fast import layer_of
from ..commentary.moments import render_variants
from ..commentary.newsroom import Published
from ..commentary.verifier import surname
from ..config import ROOT
from ..pipeline.demo import demo_insert
from ..pipeline.guided import pick_window
from ..pipeline.library import Library, MatchBundle
from ..pipeline.runner import LiveConfig, Runner
from ..sim.arcs import ARCS

GUIDED_SEEDS = range(1001, 1021)
FULL_MATCHES = ("comeback-7", "red_card-7", "unlucky-7")
EN_CHANNELS = [i for i, k in enumerate(KEYS) if k.startswith("en/")]
GAP_S = 3.0
ANSWER_DELAY_S = 0.2  # the recorded insert's analyst answer came from the cache 0.2 s after the goal
AFTER_GOAL_S = 30.0
SPANS = ("insert", "windows", "matches")
# metric -> (kind, insert, windows, matches). kind: min | max | range. A range holds for all three spans.
GATES: dict[str, tuple[str, object, object, object]] = {
    "segments_per_min": ("min", 16, 16, 12),
    "words_per_min": ("min", 75, 75, 60),
    "coverage": ("min", 0.75, 0.70, 0.55),
    "gaps_over_3s": ("max", 0.12, 0.12, 0.20),
    "short_share": ("range", 0.40, 0.70, None),
    "long_share": ("range", 0.05, 0.20, None),
    "named_share": ("range", 0.30, 0.55, None),
    "names_per_100": ("range", 6.0, 14.0, None),
    "after_goal": ("min", None, 0.0, 0.0),
    "skip_share": ("max", 0.35, 0.35, 0.35),
}
LABEL = {
    "segments_per_min": "Segments per minute", "words_per_min": "Words per minute (en channels)", "coverage": "Speech coverage",
    "gaps_over_3s": "Gaps over 3 s", "short_share": "Segments of 5 words or fewer", "long_share": "Segments of 12 words or more",
    "named_share": "Segments naming a player", "names_per_100": "Names per 100 words",
    "after_goal": "Words per minute 30 s after a goal vs the span", "skip_share": "Captions skipped by the voice (skeleton and analyst lines)",
}
PROFILE = {"segments_per_min": 22, "words_per_min": 131, "coverage": 0.90, "gaps_over_3s": 0.025, "short_share": 0.56, "long_share": 0.10,
           "named_share": 0.38, "names_per_100": 9.3, "after_goal": 0.19, "skip_share": None}


@dataclass
class Seg:
    ch: int
    m: int
    s: float
    e: float
    text: str
    kind: str


async def _no_call(prompt: str) -> str:
    raise RuntimeError("the density report makes no model calls")


class _StandIn(Runner):
    """A run whose analyst answers like the recorded insert's cached answer: after 0.2 s, as the analyst's own line, written from the
    longest template wording. No model, no call: it shows what the layers do when the analyst's line does arrive (the template
    fallback of the default run is perishable after 4 s, so a long goal call can make it skip)."""

    async def _write(self, m, snapshot, recent):
        lines = {k: render_variants(m, *k.split("/")) for k in KEYS}
        lines = {k: [*v, v[-1]] for k, v in lines.items()}
        return Published(m.id, lines, {k: "analyst" for k in KEYS}, [], ANSWER_DELAY_S, cached=True)


def run_span(bundle: MatchBundle, start: float, until: float | None, fast: bool = True, stand_in: bool = False) -> list[dict]:
    """The messages of a live run at 1x, unpaced, from `start` to `until` (None: the whole match). 0 model calls."""
    # a private cache directory: the newsroom discards the cached answer of a prompt whose call failed, and this call always fails.
    # Pointed at the real cache it would delete the recorded insert's answer, so the real cache is never touched.
    with tempfile.TemporaryDirectory() as tmp:
        live = LiveConfig(_no_call, CallBudget(100_000), cache_dir=Path(tmp), fresh=True)
        # patterns=False: the report measures the dense layers as reviewed in phase 3; the co-commentator's pattern set-up (commentary/patterns.py,
        # 2026-10-26) adds analyst lines to quiet spells and is not part of these gates
        runner = (_StandIn if stand_in else Runner)(bundle, "live", 1.0, paced=False, live=live, start=start, until=until, fast=fast, patterns=False,
                                                         rejoin=False)  # the measured windows stay as they were
        return asyncio.run(runner.collect())


def segments(msgs: list[dict]) -> tuple[list[Seg], dict[tuple[int, int], dict], dict[tuple[int, int], dict]]:
    """The spoken segments per channel, plus the last `say` and `voice` message of every line.

    A live `say` with s < e was voiced at once; otherwise the `voice` message carries the slot; a `skip` was never spoken, a `cut`
    ended at its `e`. A recorded (non-live) `say` is the slot itself, a cut one ends where it was cut."""
    say: dict[tuple[int, int], dict] = {}
    voice: dict[tuple[int, int], dict] = {}
    for msg in msgs:
        if msg["k"] == "say":
            say[(msg["ch"], msg["m"])] = msg
        elif msg["k"] == "voice":
            voice[(msg["ch"], msg["m"])] = msg
    out: list[Seg] = []
    for key, sm in say.items():
        vm = voice.get(key)
        if vm is not None:
            if vm.get("skip"):
                continue
            s, e = vm["s"], vm["e"]
        elif sm["e"] > sm["s"]:
            s, e = sm["s"], sm["e"]
        else:
            continue
        out.append(Seg(key[0], key[1], s, e, sm["text"], sm["kind"]))
    return sorted(out, key=lambda x: (x.ch, x.s)), say, voice


def _words(text: str) -> int:
    return len(text.split())


class Names:
    def __init__(self, bundle: MatchBundle):
        sur = sorted({surname(p.name).lower() for t in bundle.meta.teams.values() for p in t.players}, key=len, reverse=True)
        self.rx = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(x) for x in sur) + r")(?:s|es)?(?!\w)", re.I)

    def count(self, text: str) -> int:
        return len(self.rx.findall(text))


def channel_metrics(segs: list[Seg], say: dict, voice: dict, ch: int, lo: float, hi: float, names: Names) -> dict:
    """The ten metrics of one channel over the match stretch [lo, hi] (viewer seconds at 1x)."""
    mine = [x for x in segs if x.ch == ch and lo <= x.s < hi]
    minutes = (hi - lo) / 60
    words = [_words(x.text) for x in mine]
    spoken = sum(max(0.0, min(x.e, hi) - x.s) for x in mine)
    gaps = [b.s - a.e for a, b in zip(mine, mine[1:])]
    named = [names.count(x.text) for x in mine]
    total_words = sum(words)
    # words per minute in the AFTER_GOAL_S after each goal call, against the whole stretch
    goal_w = goal_min = 0.0
    for key, sm in say.items():
        if key[0] != ch or sm["kind"] != "shot_goal" or not lo <= sm["s"] < hi:
            continue
        g_hi = min(sm["s"] + AFTER_GOAL_S, hi)
        goal_w += sum(w for x, w in zip(mine, words) if sm["s"] <= x.s < g_hi)
        goal_min += (g_hi - sm["s"]) / 60
    wpm = total_words / minutes
    captions = [sm for key, sm in say.items() if key[0] == ch and lo <= sm["t"] < hi and layer_of(sm["m"]) == "skeleton"]
    skipped = [sm for sm in captions if voice.get((ch, sm["m"]), {}).get("skip")]
    return {
        "segments": len(mine), "segments_per_min": len(mine) / minutes, "words_per_min": wpm,
        "coverage": spoken / (hi - lo), "gaps_over_3s": (sum(g > GAP_S for g in gaps) / len(gaps)) if gaps else None,
        "short_share": (sum(w <= 5 for w in words) / len(words)) if words else None,
        "long_share": (sum(w >= 12 for w in words) / len(words)) if words else None,
        "named_share": (sum(n > 0 for n in named) / len(named)) if named else None,
        "names_per_100": (100 * sum(named) / total_words) if total_words else None,
        "after_goal": (goal_w / goal_min / wpm - 1) if goal_min and wpm else None,
        "skip_share": (len(skipped) / len(captions)) if captions else None,
        "captions": len(captions), "skipped": len(skipped),
    }


def measure(bundle: MatchBundle, lo: float, hi: float, msgs: list[dict]) -> dict[int, dict]:
    segs, say, voice = segments(msgs)
    names = Names(bundle)
    return {ch: channel_metrics(segs, say, voice, ch, lo, hi, names) for ch in range(len(KEYS))}


def _pool(rows: list[dict], metric: str, channels: list[int]) -> float | None:
    vals = [r[ch][metric] for r in rows for ch in channels if r[ch][metric] is not None]
    return statistics.median(vals) if vals else None


def holds(metric: str, value: float | None, span: str) -> bool | None:
    kind, a, b, c = GATES[metric]
    if value is None:
        return None
    if kind == "range":
        return a <= value <= b
    limit = {"insert": a, "windows": b, "matches": c}[span]
    if limit is None:
        return None
    if metric == "after_goal":
        return value > limit
    return value >= limit if kind == "min" else value <= limit


def summarise(per_unit: list[dict[int, dict]], span: str) -> dict:
    """One row per metric: the value that is gated (insert: the worst channel; windows and matches: the median of the
    per-unit median over channels), the worst single channel, and whether the gate holds."""
    out = {}
    for metric in GATES:
        channels = EN_CHANNELS if metric == "words_per_min" else list(range(len(KEYS)))
        kind = GATES[metric][0]
        per_unit_value = [_pool([u], metric, channels) for u in per_unit]
        per_unit_value = [v for v in per_unit_value if v is not None]
        every = [u[ch][metric] for u in per_unit for ch in channels if u[ch][metric] is not None]
        if span == "insert":  # every channel must pass: the gated value is the worst one (for a range, the one furthest out)
            mid = statistics.median(every) if every else None
            if kind == "min":
                worst = min(every, default=None)
            elif kind == "max":
                worst = max(every, default=None)
            else:
                lo, hi = GATES[metric][1], GATES[metric][2]
                worst = max(every, key=lambda v: max(lo - v, v - hi, 0.0), default=None)
            gated = worst
        else:
            gated = statistics.median(per_unit_value) if per_unit_value else None
            worst = (min(every) if kind == "min" else max(every)) if every and kind != "range" else (
                max(every, key=lambda v: max(GATES[metric][1] - v, v - GATES[metric][2], 0.0)) if every else None)
        out[metric] = {"gated": gated, "worst_channel": worst, "median_channel": statistics.median(every) if every else None,
                       "holds": holds(metric, gated, span)}
    return out


# ---------- the three spans ----------
def windows_of(lib: Library) -> list[tuple[str, dict]]:
    rng = random.Random("density:guided-arcs")
    arcs = sorted(ARCS)
    out = []
    for seed in GUIDED_SEEDS:
        match_id = f"{rng.choice(arcs)}-{seed}"
        out.append((match_id, pick_window(lib.bundle(match_id))))
    return out


def measure_insert(lib: Library, fast: bool = True, stand_in: bool = False) -> dict[int, dict]:
    d = demo_insert(lib)
    b = lib.bundle(d["match"])
    return measure(b, d["start"], d["until"], run_span(b, d["start"], d["until"], fast, stand_in))


def measure_recorded_insert(path: Path | None = None) -> dict[int, dict]:
    """The same metrics on the insert as it is recorded in ui/public/insert/replay.json (the 'before' column)."""
    doc = orjson.loads((path or ROOT / "ui" / "public" / "insert" / "replay.json").read_bytes())
    lo, hi = doc["demo"]["start"], doc["demo"]["until"]
    lib = Library()
    return measure(lib.bundle(doc["demo"]["match"]), lo, hi, doc["messages"])


def measure_windows(lib: Library, fast: bool = True) -> list[dict[int, dict]]:
    out = []
    for match_id, win in windows_of(lib):
        b = lib.bundle(match_id)
        out.append(measure(b, win["start"], win["until"], run_span(b, win["start"], win["until"], fast)))
    return out


def measure_matches(lib: Library, fast: bool = True, stand_in: bool = False) -> list[dict[int, dict]]:
    out = []
    for match_id in FULL_MATCHES:
        b = lib.bundle(match_id)
        out.append(measure(b, 0.0, b.duration, run_span(b, 0.0, None, fast, stand_in)))
    return out


def report(lib: Library | None = None, fast: bool = True) -> dict:
    lib = lib or Library()
    ins, wins, mats = measure_insert(lib, fast), measure_windows(lib, fast), measure_matches(lib, fast)
    return {
        "version": 1, "model_calls": 0, "elevenlabs_credits": 0, "fast": fast, "speed": 1.0,
        "channels": list(KEYS), "profile": PROFILE,
        "windows": [{"match": m, **w} for m, w in windows_of(lib)], "matches": list(FULL_MATCHES),
        "summary": {"insert": summarise([ins], "insert"), "windows": summarise(wins, "windows"), "matches": summarise(mats, "matches")},
        "insert": ins, "per_window": wins, "per_match": mats,
        "recorded_insert": summarise([measure_recorded_insert()], "insert"),
        "insert_stand_in": summarise([measure_insert(lib, fast, stand_in=True)], "insert"),
        "matches_stand_in": summarise(measure_matches(lib, fast, stand_in=True), "matches"),
    }


DRY_RUN = """## The density dry run (start of phase 3, measured once, not regenerated)

Before any wording was written: one placeholder per kind ("Name.", "Name, forward.", a nine-word sentence for the context kinds), through the real
director, on the insert and the 20 guided windows, 0 calls (the script is not part of the repo; the numbers below are what it printed).

| Metric (worst channel on the insert, median of the windows) | Gate | Rules as written (7.1, 7.2) | Rules as built |
| --- | --- | --- | --- |
| Segments per minute, insert | >= 16 | 17.1 | 22.9 |
| Segments per minute, windows | >= 16 | 13.8 | 20.1 |
| Speech coverage, insert | >= 75% | 46% | 78% |
| Speech coverage, windows | >= 70% | 52% | 67% |
| Words per minute (en), insert | >= 75 | 48.6 | 105.7 |
| Words per minute (en), windows | >= 75 | 51.6 | 83.8 |

Coverage missed its gate by more than a quarter (insert 46 against 75, windows 52 against 70), so the rules changed before the strings were written.
Read with care: one-word placeholders cannot fill a voice, so the first column mostly says that the rules left time unused. The changes, each
found by looking at where the silence sat:

1. A pass fragment stays worth saying while the ball is in the air (its `t_arr` is visible at the kick): ttl and voice wait grow to the flight, at most 4 s.
   Before, the switch of the insert was dropped by the voice wait because the interception fragment at the same instant was still speaking.
2. Every pass kick gets a fragment (`pass_kind`), not only the special types, and a first-time pass names itself; skeleton pressure events become `press_on`
   and carries from 6 m on become `carry`. The skeleton gives 12 events in a typical guided window, so the receipts alone were too few candidates.
3. Context lines have more to say: the score and the clock about once a minute (COMMENTATOR.md: game state is 1.0 segments per minute), the match so far
   (shots, corners, fouls, the ball), more facts per player (assists, clean sheets, apps, captain, age, left foot, tallest), a fact may come back after 20
   minutes. After the hour, where the guided windows sit, slots kept finding nothing to say. (The first version also asked every topic at every slot, so
   facts were marked as said without being spoken; a topic is now asked only when it is its turn.)
4. Context caps: one line per 12 viewer seconds in play (was 40) and per 7 in a dead ball (was 10), still at most 3 per dead-ball window; the dead-ball slots
   come every 5 s from the stoppage so the cap, not the slot grid, decides. A receiver who still holds the ball 4.5 s after the receipt opens a second slot
   that takes the long wording. In play the shortest wording, in a dead ball the longest.
5. Name rationing is stricter than 7.1: while one team keeps the ball every third fragment names a player (was every second), because the skeleton's own
   lines name theirs on top.
6. Fast and context lines are both captioned when the voice takes them (7.1 had that for fast only), so a context line that never gets the voice is not a skip.
"""

REVIEW_FIXES = """## Phase 3 review fixes, round 3 (measured once, with the numbers of this report as the "after")

The review of round 2 found that the volume layer had been moved, not removed. Name-less receipt and zone fragments were 34 to 38% of all segments, pitch-zone readouts
alone 23 to 33% ("Under control." 231 times, "In the final third." 215, "Dead centre, in the final third." and its mirror image about 110 times each), they sounded like a
position readout, and the counters and the game state came back word for word. What changed, and what it did to the gates (round 2 build, then this build; insert is the worst
channel, windows and matches the median):

| Gate | Round 2 | This build |
| --- | --- | --- |
| Insert: segments per minute (16) / speech coverage (75%) / captions skipped (35%) | 17.1 / 69% (NO) / 50% (NO) | 20.0 / 79% / 0% |
| Insert: segments of 5 words or fewer (40 to 70%) / naming a player (30 to 55%) / names per 100 words (6 to 14) | 50% / 50% / 9.4 | 71% (NO) / 71% (NO) / 15.8 (NO) |
| Insert: segments of 12 words or more (5 to 20%) | 0% (NO) | 0% (NO) |
| Windows: segments per minute (16) | 14.4 (NO) | 16.5 |
| Windows: segments of 12 words or more (5 to 20%) | 10% | 15% |
| Windows: naming a player (30 to 55%) / names per 100 words (6 to 14) | 40% / 10.2 | 81% (NO) / 20.8 (NO) |
| Matches: segments per minute (12) / coverage (55%) / captions skipped (35%) | 15.5 / 65% / 25% | 18.5 / 81% / 22% |
| Matches: segments of 12 words or more (5 to 20%) | 1% (NO) | 6% |
| Matches: segments of 5 words or fewer (40 to 70%) / naming a player (30 to 55%) / names per 100 words (6 to 14) | 66% / 38% / 12.1 | 85% (NO) / 83% (NO) / 26.4 (NO) |

1. The volume is names and verbs. A routine short pass is a name chain on every kick ("Lindqvist finds Lemaire.", "Lindqvist, under pressure, finds Lemaire.", "Okafor drives it to Cole.";
   four to six wordings in rotation, so no shape is more than 7% of a channel), a receipt says who has the ball and how he took it ("Rasmussen chests it down.", "Tavares, from Rasmussen."), and
   a pass with a type always names its target ("Long ball for Tavares.", "Rasmussen goes long for Tavares."; a clearance has none). The zone ("in the final third", "out on the left") is said on a
   rare turn (at most once per `PLACE_EVERY_S`, never the zone just said, one order only: 4% of the receipts carry it and it is two wordings among nine). The name-less wordings are
   left for a ball worth a word: a chested ball, a header, a switch, a cross, a clearance, a carry, an interception (`NAMED_EVERY = 2`: never two in a row). A receipt waits `TOUCH_SETTLE_S` = 0.5 s
   and is void if the receiver plays on first, and it is not called at all when the kick already named him with his type: the insert says "Long ball for Tavares." and "To Fontaine.", never
   "Tavares." in between.
2. The goal build-up of the insert (comeback-135, 4381 to 4402 s), en/expert: "Ibsen cuts it out. Switched. Rasmussen chests it down. Long ball for Tavares. To Fontaine. GOAL! ..." (de/beginner and
   fr/expert name the same four). The tally lands at 4402.7 s, 0.7 s after the end of the window: the voice has the goal call and the analysis to get through (`GOAL_QUIET_S` = 9 s).
3. The game state comes back when the score has moved or five match minutes have passed (never within a minute, not before the tenth minute unless a goal moved the score), takes turns between
   wordings and says "in added time" instead of a minute that stands still.
4. Counters never come back word for word: a pass streak is news only when it is longer than the last one of that side (ten, fifteen, twenty, at most four lines in a match), a stat only
   when the value has moved (`STAT_STEP`) and at most `STAT_MAX` times per team and fact, a news item once in a match, the wording takes turns.
5. The builder is as slow as the director: dead-ball slots are `CONTEXT_DEAD_S` + `SLOT_SLACK_S` apart, no more than `CONTEXT_PER_WINDOW` lines are built for a window, and an in-play slot waits
   `CONTEXT_PLAY_S`; a built line is no longer dropped by the voice and a fact is no longer lost with it. After a goal its move comes first, then its tally. All six post-goal lines of the three
   full matches are voiced on all six channels (before, 2 of 5 tallies were lost).
6. No wording opens with "Worth noting:", "Worth a mention:", "Good to know:", "Bemerkenswert:", "Auffällig:", "À noter :" or their like; the second wording of a context kind exists only where
   the facts hold a longer sentence.
7. Wordings: no "auf" twice in a German line, a clearance has no target, "Lemaire, dead centre." became "Lemaire, in the middle.", "X gets tight on the ball" became "X gets tight."
8. Longer connected sentences: the move before a goal ("After a move through Quinlan, Abara and Becker-Lyle, Lemaire finishes it off to make it nil-one."), the move before a chance (saved, off
   target, blocked, post), the move that ended in a stoppage, the scorer's tally with its assist, the state with the shots of both sides, and a match fact against the other side's ("Tamsworth have not
   had a shot for nineteen minutes, and Marlow have had five in that time."). A dead ball takes the long sentence of two or three facts of one player. The match facts wait for the dead ball.
9. Windows reach 16.5 segments per minute: the fragments keep their wording rota and the receipts wait a little longer for the voice (ttl 2.5 s, wait 1.6 s), a name chain has priority 27 (below a foul
   or a tackle call, so the skipped captions stay at 22%). The template stand-in of the goal analysis is no longer perishable behind the goal call (`STANDIN_BEHIND_GOAL_S`): it is spoken on all
   six channels of the insert (before: skipped on de/beginner and en/beginner after a 5.2 s call).

Not met, and why:

- Naming a player, names per 100 words, segments of 5 words or fewer (windows, matches, insert). They held in round 2 because a third of the segments were name-less position readouts of five words.
  A stream of names and verbs puts a name in more than 80% of the segments: about 13 name chains and receipts a minute, 3 to 4 words each. The name-less sentences a template can say
  truthfully (counters, notes, restarts, carries: about 3 a minute) are not enough to carry 45% of the segments. This is a conflict between the review (no position readout) and the gates; the gates are
  not changed here. The model's analyst lines, which are not in this measurement, are the intended source of the missing colour.
- Segments of 12 words or more on the insert (0% on the worst channel). Seven segments in 21 s: the build-up is five fragments of two to five words, the goal call, and the analysis template, which has
  12 words or more on en, de/expert and fr/expert but 9 on de/beginner and 10 on fr/beginner (the stand-in uses the same templates). The context layer builds no line inside the window: the tally
  is 0.7 s late and nothing is left to say about a player who holds the ball for 3.6 s. A model line is 15 words or more.

## Phase 3 review fixes, round 4 (measured once; the gates that held in round 3 still hold)

The review of round 3 found names said twice, a lost move, repeated facts and a few zeros. What changed:

1. Each name once per hop. A routine pass used to say both names ("Lindqvist finds Lemaire.") and its receipt the receiver again ("Inside to Lemaire.", 166 to 295 receipts per match and
   channel, and "Wrenfield, from Lemaire." with both names twice, 24 to 39). Now the kick names the kicker ("Lindqvist plays it on.", "Ulrich, under pressure, plays it on.") and the
   receipt names the receiver ("Inside to Lemaire."), without the kicker. A pass with a type that named its target still skips a plain receipt, and a receipt worth a word does not
   repeat the direction or the kicker. The two short segments per hop are also what keeps the windows at their pace: with the receipt dropped and the kick naming both, windows fell to 14.1.
2. The second goal of a scorer has its move. The key of a news item (`fresh_news`) held no move and no score, so the move before his second goal was taken for the first one. It holds the
   players of the move and the score the goal made now; all 6 goals of the three matches get their move and then their tally (before: 5 of 6).
3. The same fact is not said twice in a row. A stat said for one side marks the other side's figure of it as said (the long sentence has both), a shot on target and a save are one
   fact, one of shape, press and phase per side in `TACTIC_GAP_S` (a change that has to wait is said later if it still holds), the tempo note at most twice per side with a second wording,
   and the scorer's season goals are not said again by his player note after the tally.
4. No zero as a contrast ("and Marlow have put in zero of their own"): a zero is left out and the short sentence stands; a stretch without a shot is only news when the other side shot meanwhile;
   the two shares of the ball add up to a hundred.

| Gate (round 3 build, then this build) | Round 3 | This build |
| --- | --- | --- |
| Windows: segments per minute (16) / coverage (70%) | 16.5 / 86% | 16.7 / 86% |
| Windows: naming a player (30 to 55%) / names per 100 words (6 to 14) | 81% (NO) / 20.8 (NO) | 80% (NO) / 17.2 (NO) |
| Matches: segments per minute (12) / coverage (55%) / captions skipped (35%) | 18.5 / 81% / 22% | 19.0 / 80% / 24% |
| Matches: naming a player (30 to 55%) / names per 100 words (6 to 14) | 83% (NO) / 26.4 (NO) | 84% (NO) / 19.0 (NO) |
| Insert (worst channel) | unchanged | unchanged |

## Phase 3 review fixes, round 5 (measured once; the gates that held in round 4 still hold)

The review of round 4 found that the double naming had moved, not gone, and that the context layer was a stats ticker. What changed, and what it did to the lines
(comeback-7, red_card-7 and unlucky-7, en/expert unless said otherwise):

1. A name is not said twice within `NAME_GAP_S` (6 s). "Inside to Wrenfield." and then "Wrenfield gets it away." named him twice (237 to 404 pairs of fast lines per match and channel). Now a routine
   kick whose kicker was named a moment ago (his receipt, a tackle, a duel of the skeleton) is not called: 76% of the routine kicks of comeback-7 follow such a naming, so a hop is one named
   segment, the receipt. A kick that shows something (closed down, hit hard and low) is called without his name ("Played on under pressure."), at most once per `SHOWN_GAP_S` (8 s), in six
   to eight wordings per language so no line is more than 20 to 23 times in a match. A typed pass whose kicker was just named says only its target ("Long ball for Tavares."), a carry goes
   name-less, a receipt does not name a kicker named a moment ago, and a turnover starts the rationing afresh (the winner of the ball is named). Same-name pairs of fast lines within 6 s
   (start to start, four channels, three matches): 13 to 23 per match and channel (before: 237 to 404). The insert reads "Ibsen cuts it out. To Rasmussen. Chested down. Long ball for
   Tavares. To Fontaine. GOAL!".
2. The kicker-only wordings: "gets it away" is gone (it reads as a clearance under pressure), more wordings take its place, and the most frequent kick line is 17 to 23 times in a match (before 28 to 38).
3. The context layer is not a ticker. Counter notes are 55% of the context lines (76 of 138 on comeback-7; before 125 of 184) and the context lines are 1.4 a minute (before 1.9). A stat or a minor
   news line comes at most every `MINOR_GAP_S` (90 s), whichever side and fact, so there are no three stat lines in 14 s; a stat at most `STAT_MAX` (3) times per team and fact and the facts that
   read as a ticker fewer (`STAT_MAX_BY`: throw-ins, goal kicks and the stretch without a shot once per side, long balls and fouls twice); `NEWS_MAX` caps the move that ended in a stoppage (before 9 to 13 a
   match, now 2 to 3), the player's fouls (7 to 11, now 4 to 5) and the corners; no match fact is said while the ball is in play (a short stat took the voice from the play and, in the insert, the interception call);
   a pass streak and the end of the same move are one fact (`streak_told`); the nth shot of the news line marks the shots stat as said; a player's pass count once per player; "no shot for N minutes" once per side.
4. A tactical idea is said once per side in a match (`TACTIC_IDEA`: sitting deep is the shape "protect", the press "passive" and the block "low"), so the phase note no longer comes back word for word
   every 8 minutes.
5. English plural agreement: "gone long once", "one shot" ("one times" is gone).
6. The long sentences the ticker had supplied now come from the colour: a player note of two or three facts says the club ("Holloway of Marlow has kept eight clean sheets this season and is
   left-footed."), the same player is offered every `PLAYER_GAP_S` (300 s), a one-fact note while the ball is in play at most every `PLAY_NOTE_GAP_S` (120 s, so it does not take the slot of the long
   sentence a longer hold has room for).

| Gate (round 4 build, then this build) | Round 4 | This build |
| --- | --- | --- |
| Windows: segments per minute (16) / coverage (70%) / words per minute (75) | 16.7 / 86% / 109.4 | 16.1 / 79% / 100.5 |
| Windows: naming a player (30 to 55%) / names per 100 words (6 to 14) | 80% (NO) / 17.2 (NO) | 71% (NO) / 15.9 (NO) |
| Matches: segments per minute (12) / coverage (55%) / words per minute (60) / skipped (35%) | 19.0 / 80% / 93.1 / 24% | 17.2 / 70% / 79.7 / 24% |
| Matches: segments of 12 words or more (5 to 20%) | 6% | 6% |
| Matches: 5 words or fewer (40 to 70%) / naming a player (30 to 55%) / names per 100 words (6 to 14) | 84% (NO) / 84% (NO) / 19.0 (NO) | 87% (NO) / 75% (NO) / 17.6 (NO) |
| Insert (worst channel): segments per minute (16) / coverage (75%) / words per minute (75) | 20.0 / 79% / 97.1 | 20.0 / 76% / 94.3 |
| Insert (worst channel): 5 words or fewer / naming a player / names per 100 words | 71% / 71% / 15.8 (all NO) | 71% / 71% / 16.7 (all NO) |

What this cost, and what is still open: fewer segments (one named segment per hop instead of two) means fewer words, so the windows' pace sits on the gate (16.1 against 16) and the insert's coverage is 76%
against 75. The share of segments of 5 words or fewer on the full matches went the wrong way (84% to 87%): the segments that were removed were three to four words, but so were the ones that remained
and the long colour lines are fewer. Naming a player and names per 100 words still fail on windows, matches and the insert: a stream of names and verbs puts a name in most segments, and a name-less sentence a template can say
without filler (a position readout, a bare "Plays it on.") is exactly what the reviews rejected. The insert has 0% of segments of 12 words or more (seven segments in 21 s, no context line fits before the goal) and
never says the assist inside its window (the tally lands after it).
"""

# ---------- output ----------
def _fmt(metric: str, v: float | None) -> str:
    if v is None:
        return "n/a"
    if metric in ("coverage", "gaps_over_3s", "short_share", "long_share", "named_share", "skip_share", "after_goal"):
        return f"{100 * v:.0f}%" if metric != "after_goal" else f"{100 * v:+.0f}%"
    return f"{v:.1f}"


def _gate(metric: str, span: str) -> str:
    kind, a, b, c = GATES[metric]
    if kind == "range":
        return f"{_fmt(metric, a).replace('%', '')} to {_fmt(metric, b)}" if metric in ("names_per_100",) else f"{_fmt(metric, a)} to {_fmt(metric, b)}"
    limit = {"insert": a, "windows": b, "matches": c}[span]
    if limit is None:
        return "not gated"
    sign = ">=" if kind == "min" else "<="
    if metric == "after_goal":
        return "> 0%"
    return f"{sign} {_fmt(metric, limit)}"


def render(res: dict) -> str:
    s = res["summary"]
    lines = ["# Density report", "",
             "Generated by `python -m matchvoice.evaluation.density` (0 model calls, 0 ElevenLabs credits, no key). Do not edit by hand.", "",
             "The real pipeline at 1x (unpaced live mode, the dense layers on, six channels) over the recorded insert, 20 guided windows "
             "(seeds 1001 to 1020) and the three demo matches. Analyst moments use their template fallback here, so the analyst share is a lower bound. "
             "A segment is one spoken line with its voice slot; words are whitespace-separated; a name is a player's surname in the text.", ""]
    for span, title in (("insert", "The insert (every channel must pass; the value shown is the worst channel)"),
                        ("windows", "Median of 20 guided windows (the median over channels of each window, then the median over windows)"),
                        ("matches", "Over the 3 full matches (the median over channels, then over matches)")):
        lines += [f"## {title}", "", "| Metric | Broadcast profile | Gate | Measured | Worst channel | Holds |", "| --- | --- | --- | --- | --- | --- |"]
        for metric in GATES:
            r = s[span][metric]
            prof = _fmt(metric, PROFILE[metric]) if PROFILE[metric] is not None else "n/a"
            ok = {True: "yes", False: "NO", None: "not gated"}[r["holds"]]
            lines.append(f"| {LABEL[metric]} | {prof} | {_gate(metric, span)} | {_fmt(metric, r['gated'])} | {_fmt(metric, r['worst_channel'])} | {ok} |")
        lines.append("")
    si = res["insert_stand_in"]
    lines += ["## The insert when the analyst's line arrives", "",
              "The default run above has no model, so the analysis falls back to its template, and a template stand-in is perishable after 4 s "
              "(Phase 8) plus the goal call it queues behind (round 3). The recorded insert had a real "
              "analyst line, cached, 0.2 s after the goal. Here a stand-in answers like that cached answer (the analyst's own line, written from the "
              "longest template wording, ready 0.2 s after the moment). No model, no call; it shows what the layers do when the line does arrive.", "",
              "| Metric | Gate | Measured (worst channel) | Holds |", "| --- | --- | --- | --- |"]
    for metric in GATES:
        r = si[metric]
        ok = {True: "yes", False: "NO", None: "not gated"}[r["holds"]]
        lines.append(f"| {LABEL[metric]} | {_gate(metric, 'insert')} | {_fmt(metric, r['worst_channel'])} | {ok} |")
    lines.append("")
    sm = res["matches_stand_in"]
    lines += ["## The 3 full matches when the analyst's line arrives", "",
              "The same stand-in over the whole matches (median over channels, then over matches). The template fallback of the default run is short "
              "and often skipped, so this is the closer stand-in for a run with the analyst, though its lines are still template wordings, not "
              "model lines (a model line is longer, so the share of long segments is understated here as well).", "",
              "| Metric | Gate | Measured | Worst channel | Holds |", "| --- | --- | --- | --- | --- |"]
    for metric in GATES:
        r = sm[metric]
        ok = {True: "yes", False: "NO", None: "not gated"}[r["holds"]]
        lines.append(f"| {LABEL[metric]} | {_gate(metric, 'matches')} | {_fmt(metric, r['gated'])} | {_fmt(metric, r['worst_channel'])} | {ok} |")
    lines.append("")
    rec = res["recorded_insert"]
    lines += ["## Before: the insert as it is recorded in `ui/public/insert/replay.json`", "",
              "| Metric | Median channel | Worst channel |", "| --- | --- | --- |"]
    for metric in GATES:
        lines.append(f"| {LABEL[metric]} | {_fmt(metric, rec[metric]['median_channel'])} | {_fmt(metric, rec[metric]['worst_channel'])} |")
    lines += ["", REVIEW_FIXES, DRY_RUN]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "eval" / "density.json")
    ap.add_argument("--report", type=Path, default=ROOT / "docs" / "DENSITY.md")
    ap.add_argument("--no-fast", action="store_true", help="measure the skeleton and analyst lines alone (the 'before' of the dense layers)")
    a = ap.parse_args()
    res = report(fast=not a.no_fast)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(orjson.dumps(res, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS))  # channel ids are integer keys
    a.report.write_text(render(res))
    print(f"{a.out}\n{a.report}")
    for span in SPANS:
        bad = [m for m, r in res["summary"][span].items() if r["holds"] is False]
        print(f"{span}: {'all gated metrics hold' if not bad else 'FAIL ' + ', '.join(bad)}")


if __name__ == "__main__":
    main()
