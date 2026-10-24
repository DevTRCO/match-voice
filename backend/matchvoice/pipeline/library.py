"""Finds the demo matches on disk and the analyst lines recorded for them."""
from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, fields
from pathlib import Path

import orjson

from ..commentary.newsroom import Published
from ..config import ROOT
from ..facts.__main__ import load
from ..facts.engine import analyse
from ..schema import Event, EventType, MatchMeta
from ..sim.arcs import ARCS
from ..sim.engine import Sim

PUBLISHED_FIELDS = {f.name for f in fields(Published)}
GENERATED_ID = re.compile(r"^(" + "|".join(ARCS) + r")-(\d{1,6})$")  # e.g. comeback-4242: simulated on request, nothing is written
GENERATED_KEPT = 24  # simulated matches kept in memory


@dataclass
class MatchBundle:
    meta: MatchMeta
    events: list[Event]
    recorded: list[Published] | None = None  # analyst output of precompute, None when never recorded
    recorded_kinds: dict[int, str] | None = None  # moment id -> kind, to catch a recording of another build
    recorded_times: dict[int, float] | None = None  # moment id -> match time, same purpose

    @property
    def duration(self) -> float:
        return self.events[-1].t


def load_recording(path: Path) -> tuple[list[Published], dict[int, str], dict[int, float]]:
    rows = orjson.loads(path.read_bytes())
    pubs = [Published(**{k: v for k, v in row.items() if k in PUBLISHED_FIELDS}) for row in rows]
    return (pubs, {row["moment_id"]: row["kind"] for row in rows if "kind" in row},
            {row["moment_id"]: row["t"] for row in rows if "t" in row})


class Library:
    def __init__(self, data_root: Path | None = None):
        self.root = data_root if data_root is not None else ROOT / "data"
        self._bundles: dict[str, MatchBundle] = {}
        self._summaries: dict[str, dict] = {}
        self._generated: OrderedDict[str, MatchBundle] = OrderedDict()

    @staticmethod
    def generated_id(match_id: str) -> tuple[str, int] | None:
        """(arc, seed) when the id has the form `<arc>-<seed>`, the shape the simulator names its matches."""
        m = GENERATED_ID.match(match_id)
        return (m.group(1), int(m.group(2))) if m else None

    def ids(self) -> list[str]:
        base = self.root / "matches"
        return sorted(p.name for p in base.iterdir() if (p / "meta.json").exists()) if base.exists() else []

    def recorded_ids(self) -> list[str]:
        """Matches with a recorded analyst run: the ones a replay, the static export and the evaluation can use."""
        base = self.root / "replays"
        return [i for i in self.ids() if (base / i / "analyst.json").exists()]

    def _generate(self, arc: str, seed: int) -> MatchBundle:
        """A fresh live match: the simulator takes about 0.02 s, so it is made on request and kept in memory.
        The same arc and seed always give the same match, so the answer caches are hit again."""
        key = f"{arc}-{seed}"
        if key not in self._generated:
            meta, events, _ = Sim(arc, seed).run()
            self._generated[key] = MatchBundle(meta, events)
            while len(self._generated) > GENERATED_KEPT:
                old, _ = self._generated.popitem(last=False)
                self._summaries.pop(old, None)
        self._generated.move_to_end(key)
        return self._generated[key]

    def bundle(self, match_id: str) -> MatchBundle:
        if match_id not in self.ids():  # a disk match, else a simulated one; never a path, so a request cannot walk the file system
            gen = self.generated_id(match_id)
            if gen is None:
                raise KeyError(match_id)
            return self._generate(*gen)
        if match_id not in self._bundles:
            meta, events = load(self.root / "matches" / match_id)
            rec = self.root / "replays" / match_id / "analyst.json"
            pubs, kinds, times = load_recording(rec) if rec.exists() else (None, None, None)
            self._bundles[match_id] = MatchBundle(meta, events, pubs, kinds, times)
        return self._bundles[match_id]

    @staticmethod
    def _highlights(b: MatchBundle) -> list[dict]:
        """Goals and red cards with their match time and clock, so a live start can be set near one."""
        out = []
        for ev in b.events:
            if ev.type == EventType.SHOT and ev.outcome == "goal":
                out.append({"kind": "goal", "t": round(ev.t, 1), "clock": ev.clock})
            elif ev.type == EventType.CARD and ev.card == "red":
                out.append({"kind": "red", "t": round(ev.t, 1), "clock": ev.clock})
        return out

    def summary(self, match_id: str) -> dict:
        if match_id not in self._summaries:
            b = self.bundle(match_id)
            eng = analyse(b.meta, b.events)
            self._summaries[match_id] = {
                "id": b.meta.id, "title": b.meta.title, "arc": b.meta.arc, "competition": b.meta.competition,
                "venue": b.meta.venue, "duration": round(b.duration, 1), "events": len(b.events),
                "final": [eng.score["H"], eng.score["A"]], "replay": b.recorded is not None,
                "highlights": self._highlights(b),
                "teams": [{"side": s, "name": b.meta.teams[s].name, "short": b.meta.teams[s].short,
                           "color": b.meta.teams[s].color} for s in ("H", "A")],
            }
        return self._summaries[match_id]
