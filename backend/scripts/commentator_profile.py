"""Profile how often a TV commentator says what, from the SoccerNet-Echoes transcripts (CC BY 4.0).

Reads the Arrow file (see docs/COMMENTATOR.md), counts topic hits per segment with small lexicons and writes
aggregate numbers only. No transcript text is stored or printed. The `_en` set is the Whisper translation to English,
so wording is the translator's; counts of topics are what carries over.
"""
from __future__ import annotations

import collections
import json
import re
import statistics as st
import sys
from pathlib import Path

import pyarrow as pa

TOPICS: dict[str, str] = {
    "ball_movement": r"\b(passes|pass|cross|crosses|long ball|switch|clears|clearance|throw-in|goal kick|plays it|finds|back to|forward)\b",
    "chance_shot": r"\b(shot|shoots|shoot|header|save|saves|goalkeeper|keeper|post|crossbar|wide|off target|chance)\b",
    "goal": r"\b(goal|scores|scored|equaliser|equalizer)\b",
    "off_ball_run": r"\b(runs|run|running|behind the defen[cs]e|in behind|space|spaces|overlap|between the lines|gets forward|advances|drops|tracking back|marking|marks)\b",
    "duel_dribble": r"\b(dribble|dribbles|takes on|one on one|beats|skips|turns|tackle|tackles|challenge|duel|wins the ball|recovers|steals|loses the ball|lost)\b",
    "set_piece": r"\b(corner|free kick|free-kick|penalty|throw-in)\b",
    "referee": r"\b(referee|foul|yellow|red card|offside|booking|booked|protest|protests)\b",
    "tactics": r"\b(press|pressing|shape|formation|high line|back four|back three|midfield|wing|wings|compact|positional|transition|counter|possession|lines|block)\b",
    "evaluation": r"\b(brilliant|great|wonderful|incredible|unbelievable|beautiful|superb|terrible|poor|mistake|error|danger|dangerous|well done|good|bad|excellent|magnificent)\b",
    "context_stats": r"\b(season|career|record|years|history|stats|first time|last time|points|table|league|since|already|only)\b",
    "game_state": r"\b(minutes|minute|half|time|score|lead|ahead|level|draw|behind|one-nil|nil)\b",
}
COMPILED = {k: re.compile(v) for k, v in TOPICS.items()}
NAME = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-zà-ÿ]{2,}\b")


def load(path: Path) -> dict[str, list[tuple[float, float, str]]]:
    t = pa.ipc.open_stream(open(path, "rb")).read_all().to_pydict()
    out: dict[str, list[tuple[float, float, str]]] = collections.defaultdict(list)
    for g, s, e, x in zip(t["game"], t["start_time"], t["end_time"], t["text"]):
        out[g].append((float(s), float(e), x))
    return out


def profile(halves: dict[str, list[tuple[float, float, str]]]) -> dict:
    hits = collections.Counter()
    segs = words = names = short = 0
    minutes = 0.0
    wpm: list[float] = []
    gaps: list[float] = []
    for rows in halves.values():
        rows.sort()
        dur = (rows[-1][1] - rows[0][0]) / 60
        minutes += dur
        w = sum(len(x.split()) for *_, x in rows)
        wpm.append(w / dur)
        for i, (s, e, x) in enumerate(rows):
            segs += 1
            n = len(x.split())
            words += n
            names += len(NAME.findall(x))
            short += n <= 5
            low = x.lower()
            for k, rx in COMPILED.items():
                hits[k] += bool(rx.search(low))
            if i:
                gaps.append(s - rows[i - 1][1])
    return {
        "halves": len(halves),
        "minutes": round(minutes),
        "segments_per_min": round(segs / minutes, 1),
        "words_per_min_median": round(st.median(wpm)),
        "words_per_min_p10_p90": [round(sorted(wpm)[len(wpm) // 10]), round(sorted(wpm)[-1 - len(wpm) // 10])],
        "words_per_segment": round(words / segs, 1),
        "name_mentions_per_100_words": round(100 * names / words, 1),
        "share_short_segments_le5_words": round(short / segs, 2),
        "share_gap_over_3s": round(sum(g > 3 for g in gaps) / len(gaps), 3),
        "topic_share_of_segments": {k: round(v / segs, 3) for k, v in hits.most_common()},
        "topic_per_min": {k: round(v / minutes, 1) for k, v in hits.most_common()},
    }


if __name__ == "__main__":
    src = Path(sys.argv[1])
    halves = load(src)
    epl = {g: r for g, r in halves.items() if g.startswith("england_epl")}
    res = {"all_leagues": profile(halves), "england_epl": profile(epl)}
    print(json.dumps(res, indent=2))
