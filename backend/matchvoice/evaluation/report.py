"""Writes docs/EVAL.md from the results. Every number in the text is read from the results, none is typed."""
from __future__ import annotations

from ..commentary.analyst import KEYS

METRICS_HEAD = ["Lines", "Grounded", "Said by analyst", "Analyst voice by analyst",
                "Key moments voiced", "With analysis", "Speech share"]


def pct(x: float | None, digits: int = 0) -> str:
    return "n/a" if x is None else f"{100 * x:.{digits}f}%"


def sec(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f} s"


def table(head: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(" --- " for _ in head) + "|"]
    return "\n".join(out + ["| " + " | ".join(r) + " |" for r in rows])


def metric_row(name: str, g: dict) -> list[str]:
    return [name, str(g["lines"]), pct(g["grounding_rate"], 1), pct(g["said_by_analyst_share"], 1),
            pct(g["analyst_voice_by_analyst_share"]), pct(g["keymoment_spoken_coverage"]),
            pct(g["keymoment_analysis_coverage"]), pct(g["speech_share"], 1)]


def group_table(run: dict, group: str, label: str) -> str:
    return table([label] + METRICS_HEAD, [metric_row(name, g) for name, g in run[group].items()])


def moment_rows(run: dict) -> list[list[str]]:
    rows = []
    for mid, m in run["per_match"].items():
        for it in m["detection"]["items"]:
            ids = ", ".join(f"{x['kind']} at {x['t']:.0f} s" for x in it["moments"]) or "none in window"
            off = "" if it["nearest_offset_s"] is None else f"{it['nearest_offset_s']:+.0f} s"
            rows.append([mid, f"{it['t']:.0f} s", it["kind"].replace("_", " "), it["side"], f"{it['importance']:.2f}", ids,
                         off, f"{len(it['spoken'])} of {len(KEYS)}", f"{len(it['analysis_spoken'])} of {len(KEYS)}"])
    return rows


def _runs(res: dict) -> tuple[dict, dict]:
    return res["runs"]["%g" % res["primary_speed"]], res["runs"]["1"]


def weaknesses(res: dict) -> list[str]:
    fast, real = _runs(res)
    o, r = fast["overall"], real["overall"]
    items = [(mid, it) for mid, m in fast["per_match"].items() for it in m["detection"]["items"]]
    missed = [(mid, it) for mid, it in items if not it["detected"]]
    unexplained = [(mid, it) for mid, it in items if it["detected"] and not it["analysis_spoken"]]
    out = [
        f"Most spoken lines are templates. The analyst wrote {pct(o['said_by_analyst_share'], 1)} of all spoken lines at "
        f"x{fast['speed']:g} and {pct(r['said_by_analyst_share'], 1)} in real time. Even among analyst-voice lines, only "
        f"{pct(o['analyst_voice_by_analyst_share'])} (x{fast['speed']:g}) and {pct(r['analyst_voice_by_analyst_share'])} (real time) carry "
        "the model's text, because the director often picks a shorter template wording to fit the time left. The newsroom published "
        f"{pct(o['published_by_analyst_share'])} of the lines it was asked for as analyst-written"
        + ("; the loss happens at scheduling, not in the newsroom." if o["published_by_analyst_share"] == 1 else "."),
    ]
    if missed:
        where = "; ".join(
            f"{it['kind'].replace('_', ' ')} {it['side']} in {mid} ({it['t']:.0f} to {it['end']:.0f} s)" if it.get("end") is not None
            else f"{it['kind'].replace('_', ' ')} {it['side']} in {mid} at {it['t']:.0f} s" for mid, it in missed)
        offsets = ", ".join("none" if it["nearest_offset_s"] is None else "%.0f s" % abs(it["nearest_offset_s"]) for _, it in missed)
        out.append(
            f"Some truth moments are not found. {len(missed)} of {len(items)} ({pct(1 - o['keymoment_detection_coverage'], 1)} "
            f"importance-weighted) have no same-side moment of the matching kind in their window: {where}. "
            f"The nearest one is {offsets} outside it (a swing counts inside its stretch, plus a lead of "
            f"{fast['tolerance_s']['momentum_swing']:.0f} s). Of {o['claimed_moments']} goal, red card and momentum moments the pipeline produced, {o['claimed_moments_matching_truth']} "
            "match a truth moment; the rest are momentum phases the simulator did not label, which are not necessarily wrong.")
    if unexplained:
        kinds = sorted({it["kind"].replace("_", " ") for _, it in unexplained})
        out.append("Some detected moments get no analysis: " + ", ".join(
            f"{it['kind'].replace('_', ' ')} in {mid}" for mid, it in unexplained)
            + f". On every channel the analyst voice never spoke for these kinds ({', '.join(kinds)}).")
    out += [
        f"Analysis arrives late. The analyst's lines are ready a median {sec(o['ready_delay_viewer_s']['median'])} "
        f"(p95 {sec(o['ready_delay_viewer_s']['p95'])}) after the moment. Lines the analyst wrote start a median {sec(o['time_to_air_analyst_viewer_s']['median'])} "
        f"(p95 {sec(o['time_to_air_analyst_viewer_s']['p95'])}) of viewer time after the event at x{fast['speed']:g}, "
        f"template lines in the analyst voice a median {sec(o['time_to_air_analyst_voice_template_viewer_s']['median'])}, "
        f"and play-by-play {sec(o['time_to_air_pbp_viewer_s']['median'])}. These are the model latencies recorded when the replays were made, "
        "not measured in this run.",
        f"Silence only exists in real time. At x{fast['speed']:g} a line's speaking time is multiplied by the speed, so every channel "
        f"speaks {pct(o['speech_share'])} of the match. In real time the channels speak {pct(r['speech_share'], 1)} of the match, "
        f"with a longest silence of {sec(r['longest_silence_viewer_s'])} and about {r['long_silences_per_match_channel']:.0f} gaps over 20 s per channel and match. "
        "Speaking times are estimates from text length, not measured audio.",
        f"Grounding is a narrow check. The verifier tests numbers, scorelines, player names, language and length. It cannot tell "
        f"whether a claim such as 'dominating' or 'against the run of play' is fair. The {pct(o['grounding_rate'], 1)} grounding rate is an "
        f"independent check on template lines ({pct(o['grounding_rate_template_lines'], 1)} of {o['lines'] - o['lines_by_analyst']}), "
        f"which the pipeline never verifies, and a self-check on analyst lines ({pct(o['grounding_rate_analyst_lines'], 1)} of "
        f"{o['lines_by_analyst']}), which the newsroom already filtered with the same verifier. "
        "The injected-error test above is the better signal: "
        + ", ".join(f"{k.replace('_', ' ')} {pct(v['catch_rate'], 1)} of {v['applicable']}" for k, v in o["injected_errors"].items())
        + " caught."
        + (" Missed: " + "; ".join(f"{x['error'].replace('_', ' ')} '{x['text']}' ({x['channel']}, {x['match']})" for x in o["injected_misses"])
           + ". The verifier does not see a surname with a suffix attached, such as a German genitive; the fix belongs in the verifier, not in this harness."
           if o["injected_misses"] else ""),
        "Small sample. Three synthetic matches, one seed each, and the truth file comes from the same simulator that produced the events, "
        "so coverage measures agreement with a simulator label, not with a human editor. German and French wording has not been read by native speakers.",
    ]
    return out


def render(res: dict) -> str:
    fast, real = _runs(res)
    o, ro = fast["overall"], real["overall"]
    sp = f"x{fast['speed']:g}"
    lat = table(["Match", "Moments", "Ready delay, median", "p95", "Max", "Model latency, median"],
                [[mid, str(m["latency"]["ready_delay_viewer_s"]["n"]), sec(m["latency"]["ready_delay_viewer_s"]["median"]),
                  sec(m["latency"]["ready_delay_viewer_s"]["p95"]), sec(m["latency"]["ready_delay_viewer_s"]["max"]),
                  sec(m["latency"]["model_latency_s"]["median"])] for mid, m in fast["per_match"].items()])
    real_rows = [[name, pct(g["speech_share"], 1), pct(g["silence_share"], 1), sec(g["longest_silence_viewer_s"]),
                  f"{g['long_silences_per_match_channel']:.1f}", sec(g["time_to_air_pbp_viewer_s"]["median"]),
                  sec(g["time_to_air_analyst_viewer_s"]["median"]), sec(g["time_to_air_analyst_voice_template_viewer_s"]["median"]),
                  pct(g["said_by_analyst_share"], 1)]
                 for name, g in real["by_channel"].items()]
    realt = table(["Channel", "Speech share", "Silence", "Longest silence", "Gaps over 20 s per match", "Play-by-play to air",
                   "Analysis to air", "Analyst-voice templates to air", "Said by analyst"], real_rows)
    inj = table(["Injected error", "Lines it applied to", "Caught"],
                [[k.replace("_", " "), str(v["applicable"]), pct(v["catch_rate"], 1)] for k, v in o["injected_errors"].items()])
    parts = [
        "# Evaluation",
        "Generated by `python -m matchvoice.evaluation`. Do not edit by hand; the machine-readable numbers are in `data/eval/results.json`. "
        "No model call and no key is used: the pipeline runs in replay mode, unpaced, on the recorded analyst lines.",
        "## What is measured",
        f"- Setup: {len(fast['matches'])} synthetic matches ({', '.join(fast['matches'])}), {len(KEYS)} channels (en, de, fr by beginner, expert), "
        f"{fast['overall']['lines']} spoken lines at {sp}. A second run in real time (x1) shows silence and latency as a viewer lives them.",
        "- **Grounding rate**: share of spoken lines that the deterministic verifier accepts when it checks the final text again with the facts "
        "of its moment. Reported with the share of lines written by the analyst, as opposed to a template (including a shorter template wording "
        "the director chose to fit the time).",
        "- **Injected errors**: each spoken line is also corrupted (scoreline swapped, a number changed, a player named who is not part of the moment) "
        "and the verifier is asked again. This tests the verifier, not the commentary.",
        f"- **Key-moment coverage**: the importance-weighted share of `truth.json` moments the pipeline found (a moment of the matching kind "
        f"and side within {fast['tolerance_s']['goal']:.0f} s for goals and red cards; for a momentum swing, anywhere in its stretch "
        f"from the start to the end the simulator wrote, with {fast['tolerance_s']['momentum_swing']:.0f} s of lead), and the share a channel actually voiced.",
        "- **Latency**: the analyst's ready delay, from the detector queueing a moment to the publisher releasing its lines, in viewer seconds "
        "(match seconds divided by speed), and the time from the event to the start of the line.",
        "- **Speech time and silence**: share of match time a channel is speaking, and the gaps between lines.",
        f"## Results at {sp}",
        table(["Metric", "Value"], [
            ["Spoken lines", str(o["lines"])],
            ["Grounding rate", f"{pct(o['grounding_rate'], 1)} ({o['grounding_failures']} failing lines)"],
            ["Lines written by the analyst", pct(o["said_by_analyst_share"], 1)],
            ["Analyst-voice lines written by the analyst", f"{pct(o['analyst_voice_by_analyst_share'])} of {o['analyst_voice_lines']}"],
            ["Lines the newsroom published that the analyst wrote", pct(o["published_by_analyst_share"])],
            ["Key-moment coverage, found", pct(o["keymoment_detection_coverage"], 1)],
            ["Key-moment coverage, voiced", pct(o["keymoment_spoken_coverage"], 1)],
            ["Key-moment coverage, voiced with analysis", pct(o["keymoment_analysis_coverage"], 1)],
            ["Analyst ready delay, median / p95 / max", f"{sec(o['ready_delay_viewer_s']['median'])} / {sec(o['ready_delay_viewer_s']['p95'])} / {sec(o['ready_delay_viewer_s']['max'])}"],
            ["Play-by-play to air, median / p95", f"{sec(o['time_to_air_pbp_viewer_s']['median'])} / {sec(o['time_to_air_pbp_viewer_s']['p95'])}"],
            ["Analysis to air (written by the analyst), median / p95", f"{sec(o['time_to_air_analyst_viewer_s']['median'])} / {sec(o['time_to_air_analyst_viewer_s']['p95'])}"],
            ["Analyst-voice templates to air, median / p95", f"{sec(o['time_to_air_analyst_voice_template_viewer_s']['median'])} / {sec(o['time_to_air_analyst_voice_template_viewer_s']['p95'])}"],
            ["Grounding rate, template lines / analyst lines", f"{pct(o['grounding_rate_template_lines'], 1)} / {pct(o['grounding_rate_analyst_lines'], 1)}"],
            ["Speech share", pct(o["speech_share"], 1)],
        ]),
        "### Per language", group_table(fast, "by_language", "Language"),
        "### Per style", group_table(fast, "by_style", "Style"),
        "### Per channel", group_table(fast, "by_channel", "Channel"),
        "Key-moment coverage does not differ between channels by design: every channel gets the same moments, only the wording and the director's choices differ.",
        "### Verifier on injected errors", inj,
        "### Key moments against truth", table(
            ["Match", "Truth time", "Kind", "Side", "Importance", "Moments found in window", "Nearest same-side offset",
             "Voiced", "With analysis"], moment_rows(fast)),
        "### Latency per match", lat,
        "## Real time (x1)",
        f"Speech share {pct(ro['speech_share'], 1)}, silence {pct(ro['silence_share'], 1)}, grounding {pct(ro['grounding_rate'], 1)} over {ro['lines']} lines, "
        f"analyst ready delay median {sec(ro['ready_delay_viewer_s']['median'])}.",
        realt,
        "## Weaknesses",
        "\n".join(f"{i}. {w}" for i, w in enumerate(weaknesses(res), 1)),
        "",
    ]
    return "\n\n".join(parts)
