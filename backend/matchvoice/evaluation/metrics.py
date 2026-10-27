"""Evaluation metrics over one replay run of one match. Pure functions of the overlay messages (docs/PROTOCOL.md).

Every number is computed from what a viewer would have received, except grounding, which asks the
deterministic verifier again about each spoken line with the facts of its moment, and coverage, which
compares the moments the pipeline found with the ground truth the simulator wrote (truth.json).
"""
from __future__ import annotations

import asyncio
import re
import statistics
from dataclasses import dataclass

import orjson

from ..commentary.analyst import KEYS
from ..commentary.moments import Moment, MomentBuilder
from ..commentary.verifier import NUM_RE, SCORE_RE, Allowed, Verifier, allowed_for
from ..facts.engine import FactEngine
from ..pipeline.library import MatchBundle
from ..pipeline.runner import Runner, score_line_for

# truth kind -> moment kinds that voice it, and the tolerance in match seconds between truth time and moment time.
# A goal or a red card is one event. A momentum swing is a stretch of play (truth t to truth end): a same-side
# momentum moment anywhere inside it counts, with a small lead because the detector may call it just before.
TRUTH_KINDS = {"goal": ("shot_goal", "goal_analysis"), "red_card": ("red",), "momentum_swing": ("momentum",)}
TOLERANCE_S = {"goal": 30.0, "red_card": 30.0, "momentum_swing": 60.0}  # momentum: lead before the swing starts
LONG_SILENCE_S = 20.0  # viewer seconds without a word on a channel before the gap is counted


@dataclass
class Run:
    bundle: MatchBundle
    speed: float
    msgs: list[dict]
    pubs: dict  # moment id -> Published, as the runner used them
    moments: dict[int, Moment]
    snapshots: dict[int, dict]


def run_replay(bundle: MatchBundle, speed: float) -> Run:
    runner = Runner(bundle, "replay", speed, paced=False)
    msgs = asyncio.run(runner.collect())
    eng = FactEngine(bundle.meta)
    mb = MomentBuilder(eng)
    moments, snaps = {}, {}
    for ev in bundle.events:
        for m in mb.feed(ev, eng.ingest(ev)):
            moments[m.id], snaps[m.id] = m, eng.snapshot()
            if m.kind == "goal_analysis":  # the lead's score line after it is made by the runner
                line = score_line_for(m, bundle.meta, bundle.duration)
                moments[line.id], snaps[line.id] = line, snaps[m.id]
    return Run(bundle, speed, msgs, runner.pubs, moments, snaps)


def final_lines(msgs: list[dict]) -> dict[int, list[dict]]:
    """Per channel the lines as they ended up: a later message about the same (channel, moment) is a cut."""
    final: dict[tuple[int, int], dict] = {}
    for msg in msgs:
        if msg["k"] == "say":
            final[(msg["ch"], msg["m"])] = msg
    return {ch: sorted((v for (c, _), v in final.items() if c == ch), key=lambda m: m["s"]) for ch in range(len(KEYS))}


def quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    return round(v[min(len(v) - 1, int(q * len(v)))], 2)


def summary(values: list[float]) -> dict:
    return {"n": len(values), "median": round(statistics.median(values), 2) if values else None,
            "p95": quantile(values, 0.95), "max": round(max(values), 2) if values else None}


# ---------- grounding ----------
def _like(found: str, surname: str) -> str:
    """The surname in the casing of the text it replaces: Becker-Lyle, becker-lyle or BECKER-LYLE."""
    if found.isupper():
        return surname.upper()
    return "-".join(p.capitalize() for p in surname.split("-")) if found[:1].isupper() else surname


def mutations(text: str, allowed: Allowed, ver: Verifier) -> dict[str, str]:
    """Wrong versions of a line, one per error class the verifier claims to catch, where the line allows it."""
    out = {}
    score = SCORE_RE.search(text)
    if score and score.group(1) != score.group(2):
        out["score_swapped"] = f"{text[:score.start()]}{score.group(2)}-{score.group(1)}{text[score.end():]}"
    spans = [m.span() for m in SCORE_RE.finditer(text)]
    num = next((m for m in NUM_RE.finditer(text) if not any(a <= m.start() < b for a, b in spans)), None)
    if num:
        value = float(num.group(0).replace(",", "."))
        wrong = next((value + d for d in (37, 41, 43, 47) if not any(abs(value + d - a) < 0.01 for a in allowed.numbers)))
        out["number_changed"] = f"{text[:num.start()]}{wrong:g}{text[num.end():]}"
    low = text.lower()
    named = next((sur for sur in ver.players if f" {sur}" in f" {low}" and sur in allowed.names), None)
    other = next((sur for sur in sorted(ver.players) if sur not in allowed.names and sur not in low), None)
    if named and other:
        # case-insensitive, so hyphenated surnames are replaced too, and a suffix stays (a German genitive); a no-op is not a test
        wrong = re.sub(rf"(?<!\w){re.escape(named)}", lambda m: _like(m.group(0), other), text, flags=re.IGNORECASE)
        if wrong != text:
            out["player_swapped"] = wrong
    return out


def grounding(run: Run, lines: dict[int, list[dict]]) -> dict[int, dict]:
    """Per channel: lines said, lines passing the verifier, by whom they were written, and the failures."""
    ver = Verifier(run.bundle.meta)
    out = {}
    for ch, said in lines.items():
        key = KEYS[ch]
        lang = key.split("/")[0]
        c = {"said": len(said), "grounded": 0, "from_analyst": 0, "analyst_voice": 0, "analyst_voice_from_analyst": 0,
             "grounded_from_analyst": 0, "failures": [], "injected": {},
             "missed_injections": []}
        for line in said:
            m = run.moments[line["m"]]
            allowed = allowed_for(m, run.snapshots[m.id], run.bundle.meta)
            verdict = ver.check(line["text"], lang, allowed)
            for kind, wrong in mutations(line["text"], allowed, ver).items():
                slot = c["injected"].setdefault(kind, {"applicable": 0, "caught": 0})
                slot["applicable"] += 1
                caught = not ver.check(wrong, lang, allowed).ok
                slot["caught"] += caught
                if not caught:
                    c["missed_injections"].append({"error": kind, "channel": key, "m": m.id, "text": wrong})
            c["grounded"] += verdict.ok
            c["grounded_from_analyst"] += verdict.ok and line["src"] == "analyst"
            c["from_analyst"] += line["src"] == "analyst"
            if line["voice"] == "analyst":
                c["analyst_voice"] += 1
                c["analyst_voice_from_analyst"] += line["src"] == "analyst"
            if not verdict.ok:
                c["failures"].append({"m": m.id, "kind": line["kind"], "src": line["src"], "text": line["text"],
                                      "why": verdict.feedback()})
        # what the newsroom published, before the director chose among the wordings
        mine = [p for p in run.pubs.values() if key in p.sources]
        c["published"] = len(mine)
        c["published_by_analyst"] = sum(p.sources[key] == "analyst" for p in mine)
        out[ch] = c
    return out


# ---------- key-moment coverage ----------
def _side_of(run: Run, m: Moment) -> str | None:
    team = m.params.get("team")
    return next((s for s, t in run.bundle.meta.teams.items() if t.name == team), None)


def coverage(run: Run, truth: list[dict], lines: dict[int, list[dict]]) -> dict:
    """Importance-weighted share of truth moments found by the pipeline, and voiced on each channel."""
    voiced = {ch: {line["m"]: line for line in said} for ch, said in lines.items()}
    items = []
    for tr in truth:
        kinds, tol = TRUTH_KINDS[tr["kind"]], TOLERANCE_S[tr["kind"]]
        # the stretch of match seconds in which a moment counts as this truth
        lo, hi = (tr["t"] - tol, tr["end"]) if tr.get("end") is not None else (tr["t"] - tol, tr["t"] + tol)

        def gap(m: Moment) -> float:
            """Seconds outside the stretch: negative before it, positive after it, 0 inside."""
            return m.t - lo if m.t < lo else m.t - hi if m.t > hi else 0.0
        same = [m for m in run.moments.values() if m.kind in kinds and _side_of(run, m) == tr["side"]]
        found = [m for m in same if gap(m) == 0.0]
        swing = tr.get("end") is not None
        offset = (lambda m: gap(m)) if swing else (lambda m: m.t - tr["t"])  # a swing is measured from its stretch
        nearest = min(same, key=lambda m: abs(offset(m)), default=None)
        ids = {m.id for m in found}
        items.append({
            "t": tr["t"], "kind": tr["kind"], "side": tr["side"], "importance": tr["importance"],
            "end": tr.get("end"),
            "nearest_offset_s": round(offset(nearest), 1) if nearest else None,
            "detected": bool(found),
            "moments": [{"id": m.id, "kind": m.kind, "t": round(m.t, 1)} for m in found],
            "spoken": [ch for ch in range(len(KEYS)) if ids & voiced[ch].keys()],
            "analysis_spoken": [ch for ch in range(len(KEYS))
                                if any(voiced[ch][i]["voice"] == "analyst" for i in ids & voiced[ch].keys())]})
    # precision of the moments that claim to be a truth kind: how many match a truth moment
    claimed = [m for m in run.moments.values() if m.kind in {k for ks in TRUTH_KINDS.values() for k in ks}]
    hit = {mm["id"] for it in items for mm in it["moments"]}
    return {"items": items, "claimed": len(claimed), "claimed_matching": sum(m.id in hit for m in claimed)}


def weigh(items: list[dict], flag) -> tuple[float, float]:
    return sum(it["importance"] for it in items if flag(it)), sum(it["importance"] for it in items)


# ---------- latency ----------
def latency(run: Run) -> dict:
    """Analyst moment ready delay: from the detector queueing a moment to the publisher releasing its lines."""
    queued, ready, model = {}, {}, []
    for msg in run.msgs:
        if msg["k"] != "log":
            continue
        if msg["step"] == "queued":
            queued[msg["m"]] = msg["at"]
        elif msg["step"] == "ready":
            ready[msg["m"]] = msg["at"]
        elif msg["step"] == "analyst_wrote":
            model.append(msg["d"]["latency_s"])
    delay = [ready[m] - queued[m] for m in queued if m in ready]
    viewer = [d / run.speed for d in delay]
    return {"ready_delay_match_s": summary(delay), "ready_delay_viewer_s": summary(viewer),
            "model_latency_s": summary(model), "samples": {"ready_viewer_s": viewer, "model_s": model}}


def time_to_air(run: Run, lines: dict[int, list[dict]], voice: str, src: str | None = None) -> list[float]:
    """Viewer seconds from the event to the start of its line, over every channel. `src` keeps lines written by
    the analyst or by a template; without it a line counts whoever wrote it."""
    return [(line["s"] - run.moments[line["m"]].t) / run.speed
            for said in lines.values() for line in said if line["voice"] == voice and src in (None, line["src"])]


# ---------- speech time and silence ----------
def speech(run: Run, said: list[dict]) -> dict:
    """Spoken share of the match and the silences between lines. Lines on a channel never overlap."""
    end = run.bundle.duration
    spoken = sum(max(0.0, min(m["e"], end) - min(m["s"], end)) for m in said)
    edges = [0.0] + [x for m in said for x in (m["s"], m["e"])] + [end]
    gaps = [(b - a) / run.speed for a, b in zip(edges[::2], edges[1::2]) if b > a]
    return {"spoken_match_s": round(spoken, 1), "duration_match_s": round(end, 1),
            "longest_silence_viewer_s": round(max(gaps, default=0.0), 1),
            "long_silences": sum(g > LONG_SILENCE_S for g in gaps), "lines": len(said)}


def dumps(obj) -> bytes:
    return orjson.dumps(obj, option=orjson.OPT_INDENT_2)
