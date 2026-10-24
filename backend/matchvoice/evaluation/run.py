"""Runs the evaluation: three matches, six channels, unpaced replay, and aggregates the metrics."""
from __future__ import annotations

import orjson

from ..commentary.analyst import KEYS
from ..pipeline.library import Library
from . import metrics as mx

DEFAULT_SPEED = 30.0  # the speed of the shipped replay.json; speech durations scale with it
SPEEDS = (DEFAULT_SPEED, 1.0)  # the second run is real time, the only one where silence means something
INJECTED = ("score_swapped", "number_changed", "player_swapped")
GROUPS = {"channel": lambda k: k, "language": lambda k: k.split("/")[0], "style": lambda k: k.split("/")[1]}


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def evaluate_match(lib: Library, match_id: str, speed: float) -> dict:
    bundle = lib.bundle(match_id)
    run = mx.run_replay(bundle, speed)
    lines = mx.final_lines(run.msgs)
    truth = orjson.loads((lib.root / "matches" / match_id / "truth.json").read_bytes())
    ground, cov = mx.grounding(run, lines), mx.coverage(run, truth, lines)
    channels = {}
    for ch, key in enumerate(KEYS):
        channels[key] = {**ground[ch], **mx.speech(run, lines[ch]),
                         "covered_weight": sum(it["importance"] for it in cov["items"] if ch in it["spoken"]),
                         "analysis_weight": sum(it["importance"] for it in cov["items"] if ch in it["analysis_spoken"]),
                         "time_to_air_pbp_s": mx.time_to_air(run, {ch: lines[ch]}, "pbp"),
                         "time_to_air_analyst_s": mx.time_to_air(run, {ch: lines[ch]}, "analyst", "analyst"),
                         "time_to_air_analyst_voice_template_s": mx.time_to_air(run, {ch: lines[ch]}, "analyst", "template")}
    items = cov["items"]
    return {
        "title": bundle.meta.title, "arc": bundle.meta.arc, "events": len(bundle.events),
        "duration_s": round(bundle.duration, 1),
        "channels": channels,
        "detection": {"items": items, "total_weight": mx.weigh(items, bool)[1],
                      "detected_weight": mx.weigh(items, lambda i: i["detected"])[0],
                      "claimed_moments": cov["claimed"], "claimed_matching_truth": cov["claimed_matching"]},
        "latency": mx.latency(run),
    }


def pool(per_match: dict[str, dict], keys: list[str]) -> dict:
    """Sum the counts of the given channels over all matches and derive the rates."""
    rows = [(m, per_match[m]["channels"][k]) for m in per_match for k in keys]
    tot = lambda f: sum(f(m, r) for m, r in rows)  # noqa: E731
    weight = tot(lambda m, r: per_match[m]["detection"]["total_weight"])
    dur = tot(lambda m, r: r["duration_match_s"])
    pbp = [x for _, r in rows for x in r["time_to_air_pbp_s"]]
    ana = [x for _, r in rows for x in r["time_to_air_analyst_s"]]
    tpl = [x for _, r in rows for x in r["time_to_air_analyst_voice_template_s"]]
    return {
        "lines": tot(lambda m, r: r["said"]),
        "grounding_rate": _rate(tot(lambda m, r: r["grounded"]), tot(lambda m, r: r["said"])),
        "grounding_rate_analyst_lines": _rate(tot(lambda m, r: r["grounded_from_analyst"]), tot(lambda m, r: r["from_analyst"])),
        "grounding_rate_template_lines": _rate(tot(lambda m, r: r["grounded"] - r["grounded_from_analyst"]),
                                               tot(lambda m, r: r["said"] - r["from_analyst"])),
        "grounding_failures": tot(lambda m, r: len(r["failures"])),
        "injected_errors": {k: {"applicable": a, "caught": c, "catch_rate": _rate(c, a)}
                            for k in INJECTED for a, c in [(tot(lambda m, r: r["injected"].get(k, {}).get("applicable", 0)),
                                                            tot(lambda m, r: r["injected"].get(k, {}).get("caught", 0)))]},
        "injected_misses": [{**x, "match": m} for m, r in rows for x in r["missed_injections"]],
        "lines_by_analyst": tot(lambda m, r: r["from_analyst"]),
        "said_by_analyst_share": _rate(tot(lambda m, r: r["from_analyst"]), tot(lambda m, r: r["said"])),
        "analyst_voice_lines": tot(lambda m, r: r["analyst_voice"]),
        "analyst_voice_by_analyst_share": _rate(tot(lambda m, r: r["analyst_voice_from_analyst"]),
                                                tot(lambda m, r: r["analyst_voice"])),
        "published_by_analyst_share": _rate(tot(lambda m, r: r["published_by_analyst"]), tot(lambda m, r: r["published"])),
        "keymoment_spoken_coverage": _rate(tot(lambda m, r: r["covered_weight"]), weight),
        "keymoment_analysis_coverage": _rate(tot(lambda m, r: r["analysis_weight"]), weight),
        "speech_share": _rate(tot(lambda m, r: r["spoken_match_s"]), dur),
        "silence_share": _rate(dur - tot(lambda m, r: r["spoken_match_s"]), dur),
        "longest_silence_viewer_s": max(r["longest_silence_viewer_s"] for _, r in rows),
        "long_silences_per_match_channel": round(tot(lambda m, r: r["long_silences"]) / len(rows), 2),
        "time_to_air_pbp_viewer_s": mx.summary(pbp),
        "time_to_air_analyst_viewer_s": mx.summary(ana),
        "time_to_air_analyst_voice_template_viewer_s": mx.summary(tpl),
    }


def evaluate(lib: Library | None = None, speed: float = DEFAULT_SPEED, match_ids: list[str] | None = None) -> dict:
    lib = lib or Library()
    ids = match_ids or lib.recorded_ids()
    per_match = {i: evaluate_match(lib, i, speed) for i in ids}
    groups = {}
    for name, of in GROUPS.items():
        buckets: dict[str, list[str]] = {}
        for k in KEYS:
            buckets.setdefault(of(k), []).append(k)
        groups[name] = {b: pool(per_match, ks) for b, ks in buckets.items()}
    det = [per_match[i]["detection"] for i in ids]
    total = sum(d["total_weight"] for d in det)
    claimed = sum(d["claimed_moments"] for d in det)
    overall = {
        **pool(per_match, list(KEYS)),
        "keymoment_detection_coverage": _rate(sum(d["detected_weight"] for d in det), total),
        "claimed_moments": claimed,
        "claimed_moments_matching_truth": sum(d["claimed_matching_truth"] for d in det),
        "ready_delay_viewer_s": mx.summary([x for i in ids for x in per_match[i]["latency"]["samples"]["ready_viewer_s"]]),
        "model_latency_s": mx.summary([x for i in ids for x in per_match[i]["latency"]["samples"]["model_s"]]),
    }
    for m in per_match.values():  # raw samples were only needed for pooling
        m["latency"].pop("samples")
        for c in m["channels"].values():
            for k in ("time_to_air_pbp_s", "time_to_air_analyst_s", "time_to_air_analyst_voice_template_s"):
                c[k] = mx.summary(c[k])
    return {"speed": speed, "matches": ids, "channels": list(KEYS),
            "tolerance_s": mx.TOLERANCE_S,
            "overall": overall, **{f"by_{n}": g for n, g in groups.items()}, "per_match": per_match}



def evaluate_all(lib: Library | None = None, speeds: tuple[float, ...] = SPEEDS, match_ids: list[str] | None = None) -> dict:
    lib = lib or Library()
    return {"version": 1, "primary_speed": speeds[0], "model_calls": 0,
            "runs": {f"{s:g}": evaluate(lib, s, match_ids) for s in speeds}}
