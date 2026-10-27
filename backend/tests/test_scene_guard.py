"""Guards for the live scene work: the full-match simulation, the disk matches and the recorded insert must not move.

The live "New run" forks the simulation at a dead ball (sim/scene.py). Everything else (data/matches, the recorded insert, EVAL,
replays) reads the plain `Sim(arc, seed).run()`, so its output is pinned here byte for byte."""
from __future__ import annotations

import hashlib
from pathlib import Path

import orjson
import pytest

from matchvoice.facts.__main__ import load
from matchvoice.sim.engine import Sim
from matchvoice.sim.micro.enrich import enrich

ROOT = Path(__file__).resolve().parents[2]

SIM_SHA = {  # sha256 of the orjson dump of events, meta and truth of Sim(arc, seed).run(), taken before the scene hook existed
    "comeback-135": "e3d939250d76bef1dd3faaa49c507a72ffa7a3487bb496c74380438b8d7b7bff",
    "comeback-7": "c36bd0a95750ad57d84bc5e013cc75f429abe9fdd3253f4f8d9111c5c34fbd19",
    "red_card-11": "8bbf006ca2cb71d563314da609027ab3c58bb1bd6421b621d742a200d4f5ab29",
    "red_card-7": "b0d4c4a4110211e586959a1c124e84a8fb6b04bf07ea150d03716b2b446c6000",
    "unlucky-7": "9827930812f1d543261c9f4d6100fc2fb32da4b00bc1c2e9e43bf674be641561",
}
INSERT_SHA = {
    "ui/public/insert/story.json": "2169b1a37087ff47ae579147b206402d42952838fccb5ac66c89224c07e596d0",
    "ui/public/insert/micro.json": "cba90afd275a8359ef3457d3c7348a55c606370e1cf1cd3e4812aaad8569778f",
}
AUDIO_SHA = "a0bf498a011dbf86e54c9ff129d3b1d12da217b3eff6a73c20974a05e5502b19"  # insert/audio and insert/story-audio, names and bytes


def _sim_sha(match_id: str) -> str:
    arc, seed = match_id.rsplit("-", 1)
    meta, events, truth = Sim(arc, int(seed)).run()
    return hashlib.sha256(orjson.dumps([e.model_dump(mode="json") for e in events]) + orjson.dumps(meta.model_dump(mode="json"))
                          + orjson.dumps([t.model_dump(mode="json") for t in truth])).hexdigest()


@pytest.mark.parametrize("match_id", sorted(SIM_SHA))
def test_the_full_match_simulation_is_unchanged(match_id):
    assert _sim_sha(match_id) == SIM_SHA[match_id]


@pytest.mark.parametrize("match_id", [m for m in sorted(SIM_SHA) if (ROOT / "data/matches" / m / "events.jsonl").exists()])
def test_disk_matches_are_the_simulation(match_id):
    arc, seed = match_id.rsplit("-", 1)
    _, events, _ = Sim(arc, int(seed)).run()
    assert load(ROOT / "data/matches" / match_id)[1] == events


def test_comeback_135_enriched_rows_on_disk_are_the_simulation():
    meta, events, _ = Sim("comeback", 135).run()
    disk = [orjson.loads(line) for line in (ROOT / "data/matches/comeback-135/enriched.jsonl").read_text().splitlines()]
    assert enrich(meta, events).rows == disk


def test_the_recorded_insert_is_unchanged():
    for path, sha in INSERT_SHA.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha, path
    h = hashlib.sha256()
    for d in ("ui/public/insert/audio", "ui/public/insert/story-audio"):
        for f in sorted((ROOT / d).iterdir()):
            h.update(f.name.encode())
            h.update(f.read_bytes())
    assert h.hexdigest() == AUDIO_SHA
