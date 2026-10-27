"""The public live server: the scene whitelist, sessions, per-session, per-IP and concurrency caps, the daily caps on model calls and
voice credits, the `row` stream, the Origin check, the world and fast switches per run, and a voice per person in all nine languages.
Zero network and no real call: fake models (with private answer caches) and FakeSynth stand in."""
from __future__ import annotations

import ast
import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from matchvoice.commentary.analyst import BudgetExceeded, CallBudget
from matchvoice.commentary.lang import ALL_KEYS, BOOTH, LANGS, who_of
from matchvoice.commentary.moments import Moment
from matchvoice.pipeline import scenes
from matchvoice.pipeline.library import Library
from matchvoice.pipeline.runner import ROWS_CATCH_UP_S, DailyCalls, LiveConfig, LiveUnavailable, Runner, _RunBudget
from matchvoice.server import app as app_module
from matchvoice.server.app import create_app
from matchvoice.server.public import PublicGate
from matchvoice.sim.micro.enrich import enrich
from matchvoice.tts import MODEL, GuardedTTS, TTSBudgetExceeded, TTSDailyExceeded
from matchvoice.tts.fake import FAKE_MP3, FakeSynth
from matchvoice.tts.voices import CAST, LANGUAGE_CODES, VOICES, voice_for
from test_pipeline import fake_llm
from test_server import ws_messages

ROOT = Path(__file__).resolve().parents[2]
LIB = Library()
WIN = scenes.SCENES["winner"]
TINY = scenes.Scene("tiny", "comeback-135", 5440.0, 5440.4, "A quiet stretch")  # no event inside: a run ends at once
TINY_Q = f"match={TINY.match}&mode=live&speed=1&start={TINY.start}&until={TINY.until}"
SECRET = b"test-secret-not-a-real-one"


class Clock:
    def __init__(self, at: datetime):
        self.at = at

    def __call__(self) -> datetime:
        return self.at


@pytest.fixture
def tiny(monkeypatch):
    monkeypatch.setitem(scenes.SCENES, "tiny", TINY)
    return TINY


def gate(**kw) -> PublicGate:
    return PublicGate(SECRET, **kw)


def public_app(tmp_path, g: PublicGate, tts=None, trusted_hops: int = 0, **live_kw) -> TestClient:
    cfg = LiveConfig(fake_llm(), CallBudget(30), "fake", tmp_path / "analyst", **live_kw)
    return TestClient(create_app(live=cfg, public=g, tts=tts, trusted_hops=trusted_hops))


def token_of(c: TestClient) -> str:
    return c.get("/api/session").json()["token"]


# ---------- the scene ----------
SEEDS = (0, 1, 3, 11)  # variants of the generated winner: edge, counter, cutback, overlap


def test_the_winner_scene_holds_build_up_goal_and_score_line():
    info = scenes.scene_info(LIB, "winner")
    assert info["match"] == "comeback-135" and info["start"] == 5415.0 and info["until"] == 5490.0 and info["goal_t"] is None
    assert info["goal_window"] == [5462.0, 5471.5] and info["start"] < info["goal_window"][0] < info["goal_window"][1] < info["until"]
    assert info["score"] == [1, 1] and info["clock"] == "88" and info["until"] - info["start"] <= 75 and info["title"]
    assert info["until"] - info["goal_window"][1] >= 18.5  # room for the call, the analysis and the score line
    assert scenes.find_scene("comeback-135", 5415.0, 5490.0) is WIN and scenes.find_scene("comeback-135", 5415.02, 5489.98) is WIN
    for args in (("comeback-7", 5415.0, 5490.0), ("comeback-135", 5431.0, 5490.0), ("comeback-135", 5415.0, None),
                 ("comeback-135", 5415.0, 5500.0), (None, 5415.0, 5490.0)):
        assert scenes.find_scene(*args) is None


GOAL_WORLD = {"es/expert": "¡GOOOL! ¡{n}! ¡Wexmoor por delante!", "it/beginner": "GOOOL! {n}! Wexmoor in vantaggio!",
              "pt/expert": "GOOOL! {n}! Wexmoor na frente!", "nl/beginner": "GOAL! {n}! Wexmoor op voorsprong!",
              "tr/expert": "GOOOL! {n}! Wexmoor öne geçti!", "ja/beginner": "ゴール！{ja}！ウェックスムーア、勝ち越し！"}
KATAKANA = {"Tavares": "タバレス", "Dacosta": "ダコスタ", "Fontaine": "フォンテーヌ", "Abara": "アバラ"}
PLAIN_WORLD = {"es/expert": "Sigue la jugada.", "it/beginner": "Si gioca.", "pt/expert": "Segue o jogo.", "nl/beginner": "Er wordt gespeeld.",
               "tr/expert": "Oyun sürüyor.", "ja/beginner": "プレー続行。"}


def world_fake(prompts: list[str] | None = None):
    async def call(prompt: str) -> str:
        if prompts is not None:
            prompts.append(prompt)
        kind = re.search(r"Moment kind (\w+)", prompt).group(1)
        if kind != "shot_goal":
            return json.dumps(PLAIN_WORLD, ensure_ascii=False)
        n = re.search(r'"player": "([^"]+)"', prompt).group(1)  # the scorer of this run's goal
        return json.dumps({k: v.format(n=n, ja=KATAKANA.get(n, n)) for k, v in GOAL_WORLD.items()}, ensure_ascii=False)
    return call


def scorer_of(bundle) -> str:
    goal = next(e for e in bundle.events if e.t >= WIN.start and e.type.value == "shot" and e.outcome == "goal")
    return next(p.name for t in bundle.meta.teams.values() for p in t.players if p.id == goal.player).split()[-1]


@pytest.mark.parametrize("seed", SEEDS)
def test_every_channel_captions_the_goal_call_the_analysis_and_the_score_line_in_the_winner_window(tmp_path, seed):
    live = LiveConfig(fake_llm(), CallBudget(60), "fake", tmp_path, world_call=world_fake())
    b = LIB.scene_bundle(WIN, seed)
    msgs = asyncio.run(Runner(b, "live", 1.0, False, live, WIN.start, None, WIN.until, fast=True,
                              world=True, rows=True).collect())
    says = [m for m in msgs if m["k"] == "say"]
    for kind in ("shot_goal", "goal_analysis", "score_line"):
        assert {m["ch"] for m in says if m["kind"] == kind} == set(range(12)), kind
    goal = {m["ch"]: m for m in says if m["kind"] == "shot_goal"}
    name = scorer_of(b)
    assert all(name in m["text"] or KATAKANA.get(name, "?") in m["text"] for m in goal.values()), (name, [m["text"] for m in goal.values()])
    assert all(m["who"] == BOOTH[ALL_KEYS[m["ch"]]].lead.name for m in goal.values())
    co = {m["ch"]: m["who"] for m in says if m["kind"] == "goal_analysis"}
    assert all(co[ch] == (BOOTH[ALL_KEYS[ch]].co or BOOTH[ALL_KEYS[ch]].lead).name for ch in co)
    score = [m for m in says if m["kind"] == "score_line"]
    assert all(m["t"] <= WIN.until for m in score)  # the score line is known inside the window


# ---------- rows ----------
def _run_rows(tmp_path, rows: bool, start=WIN.start, until=WIN.until, fast=True, seed=SEEDS[0]):
    live = LiveConfig(fake_llm(), CallBudget(60), "fake", tmp_path)
    return asyncio.run(Runner(LIB.scene_bundle(WIN, seed), "live", 1.0, False, live, start, None, until, fast=fast, rows=rows).collect())


@pytest.mark.parametrize("seed", SEEDS)
def test_rows_arrive_in_time_order_once_each_and_never_ahead_of_the_stream(tmp_path, seed):
    msgs = _run_rows(tmp_path, True, seed=seed)
    b = LIB.scene_bundle(WIN, seed)
    want = sorted((r for r in enrich(b.meta, b.events).rows if WIN.start - ROWS_CATCH_UP_S <= r["t"] <= WIN.until),
                  key=lambda r: (r["t"], r["eid"]))
    row_msgs = [m for m in msgs if m["k"] == "row"]
    got = [r for m in row_msgs for r in m["rows"]]
    assert got == want and len({r["eid"] for r in got}) == len(got)
    ts = [m["t"] for m in msgs[1:]]
    assert ts == sorted(ts)  # rows keep the stream's order
    for m in row_msgs:
        assert all(r["t"] <= m["t"] + 1e-9 for r in m["rows"])  # no lookahead: a row only once its time has come
        if m["t"] >= WIN.start:  # and not late: released at the first tick at or after it
            assert all(m["t"] - r["t"] < 0.25 for r in m["rows"])
    receipts = [(m["t"], r) for m in row_msgs for r in m["rows"] if r["type"] == "receipt" and r["t"] >= WIN.start]
    assert receipts and all(t >= r["t"] for t, r in receipts)  # a receipt at its arrival, not at the kick
    kicks = {r["eid"]: t for m in row_msgs for r in m["rows"] if r["type"] == "pass" for t in [m["t"]]}
    assert all(kicks[r["pass_eid"]] <= t for t, r in receipts if r["pass_eid"] in kicks)
    # the shape of ui/public/insert/micro.json rows (the page reads the same fields)
    micro = json.loads((ROOT / "ui/public/insert/micro.json").read_text())["rows"]
    by_type = {}
    for r in micro:
        by_type.setdefault(r["type"], set()).update(r)
    for r in got:
        assert {"eid", "i", "k", "t", "type", "team"} <= set(r)
        if r["type"] in by_type:
            assert set(r) <= by_type[r["type"]] | {"short", "implicit", "end_x", "end_y", "length", "assist_eid", "placement", "into_box",
                                                   "delivery", "target_zone", "contest_s", "player", "x", "y"}


@pytest.mark.parametrize("seed", SEEDS[:2])
def test_rows_fold_the_catch_up_without_changing_the_state_at_start(tmp_path, seed):
    def state(msgs):
        stats = [{}, {}]
        first = None
        for m in msgs:
            if m["k"] != "f":
                continue
            for side, d in enumerate(m.get("st", [{}, {}])):
                stats[side].update(d)
            if first is None and m["t"] >= WIN.start:
                first = m
            if m["t"] >= WIN.start:
                return [dict(s) for s in stats], first["s"], first["wp"]
    plain = _run_rows(tmp_path / "a", False, fast=False, seed=seed)
    folded = _run_rows(tmp_path / "b", True, fast=False, seed=seed)
    early = lambda msgs: [m for m in msgs if m["k"] == "f" and m["t"] < WIN.start]  # noqa: E731
    assert len(early(plain)) > 1000 and 1 <= len(early(folded)) <= 10
    assert all(m["t"] >= WIN.start - ROWS_CATCH_UP_S for m in early(folded)[:-1])
    assert state(plain) == state(folded)  # the first live frame sees the same stats, score and win chance
    assert not [m for m in plain if m["k"] == "row"]
    # the commentary does not depend on the rows switch
    say = lambda msgs: [(m["ch"], m["m"], m["text"]) for m in msgs if m["k"] == "say"]  # noqa: E731
    assert say(plain) == say(folded)


# ---------- daily calls ----------
def test_daily_calls_roll_at_midnight_utc_and_stop_both_booths():
    clock = Clock(datetime(2026, 10, 27, 23, 59, tzinfo=timezone.utc))
    daily = DailyCalls(2, clock)
    core, world = _RunBudget(CallBudget(10), daily), _RunBudget(CallBudget(10), daily)
    core.take()
    world.take()
    assert daily.left == 0
    with pytest.raises(BudgetExceeded):
        core.take()
    with pytest.raises(BudgetExceeded):
        world.take()
    assert core.used == 1 and world.used == 1 and core._shared.used == 1  # a refused call counts nowhere
    clock.at += timedelta(minutes=2)  # 00:01 UTC
    assert daily.left == 2
    core.take()
    assert daily.left == 1 and DailyCalls(0, clock).left is None


def test_no_calls_today_refuses_live_and_shows_in_health(tmp_path):
    daily = DailyCalls(1)
    daily.take()
    cfg = LiveConfig(fake_llm(), CallBudget(30), "fake", tmp_path, daily=daily)
    with TestClient(create_app(live=cfg)) as c:
        h = c.get("/api/health").json()
        assert h["live"]["available"] is False and h["live"]["code"] == "no_calls_today" and h["live"]["calls_left"] == 0
        assert h["today"]["calls_left"] == 0 and h["today"]["calls_per_day"] == 1
        with c.websocket_connect("/ws?match=comeback-7&mode=live&speed=60&paced=false&start=700&until=760") as ws:
            assert ws.receive_json()["code"] == "no_calls_today"
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 4029
        assert c.get("/sse?match=comeback-7&mode=live&start=700&until=760").status_code == 429


# ---------- the public server: whitelist and sessions ----------
def test_public_live_runs_only_the_whitelisted_scenes(tmp_path):
    with public_app(tmp_path, gate()) as c:
        tok = token_of(c)
        for q in (f"match=comeback-135&mode=live&speed=1&start=5000&until=5050&token={tok}",
                  f"match=comeback-7&mode=live&speed=1&start=5415&until=5490&token={tok}",
                  f"match=comeback-135&mode=live&speed=1&start=5431&until=5490&token={tok}",
                  f"match=comeback-135&mode=live&speed=1&start=5415&until=5480&token={tok}",
                  f"match=comeback-135&mode=live&speed=60&start=5415&until=5490&token={tok}",
                  f"match=comeback-135&mode=live&speed=1&paced=false&start=5415&until=5490&token={tok}",
                  f"match=comeback-135&mode=live&speed=1&start=5415&until=5490&analyst_from=5400&token={tok}",
                  f"match=comeback-135&mode=live&speed=1&start=5415&until=5490&seed=7&token={tok}",
                  f"match=comeback-135&mode=live&speed=1&start=5415&until=5490&seed=x&token={tok}"):
            msg = ws_messages(c, q)
            assert msg[0]["code"] == "bad_request", q
        assert c.get(f"/sse?match=comeback-135&mode=live&speed=1&start=5000&until=5050&token={tok}").status_code == 400
        replay = ws_messages(c, "match=comeback-7&mode=replay&speed=30&paced=false")  # replay is never limited
        assert replay[-1]["k"] == "end"


def test_public_live_needs_a_valid_session(tmp_path, tiny):
    g = gate(clock=Clock(datetime(2026, 10, 27, 12, tzinfo=timezone.utc)))
    with public_app(tmp_path, g) as c:
        good = g.issue()["token"]
        forged = good[:-1] + ("1" if good[-1] == "0" else "0")  # one character off (the old "+ '0'" was the real token 1 time in 16)
        for tok in ("", "&token=nope", "&token=a.b.c", "&token=" + forged):
            with c.websocket_connect(f"/ws?{TINY_Q}{tok}") as ws:
                assert ws.receive_json()["code"] == "session_required"
                with pytest.raises(WebSocketDisconnect) as closed:
                    ws.receive_json()
                assert closed.value.code == 4003
        s = c.get("/api/session").json()
        assert s["enforced"] and s["session_runs_left"] == 3 and s["token"].startswith(s["id"] + ".2026-10-27.")
        assert c.get(f"/api/session?token={s['token']}").json()["token"] == s["token"]  # a valid token comes back as it is
        msgs = ws_messages(c, f"{TINY_Q}&token={s['token']}")
        assert msgs[0]["k"] == "hello" and msgs[-1]["k"] == "end"
        g.clock.at += timedelta(days=2)  # a token lives on its day and the next
        assert g.verify(s["token"]) is None and c.get(f"/api/session?token={s['token']}").json()["token"] != s["token"]


def test_a_public_server_without_a_secret_refuses_live_but_replays(tmp_path, tiny):
    with public_app(tmp_path, PublicGate(None)) as c:
        r = c.get("/api/session")
        assert r.status_code == 503 and r.json()["detail"]["code"] == "no_session_secret"
        assert ws_messages(c, TINY_Q)[0]["code"] == "no_session_secret"
        h = c.get("/api/health").json()
        assert h["live"]["available"] is False and h["live"]["code"] == "no_session_secret" and h["public"]["sessions"] is False
        assert ws_messages(c, "match=comeback-7&mode=replay&speed=30&paced=false")[-1]["k"] == "end"


def test_a_server_that_is_not_public_needs_no_session():
    with TestClient(create_app()) as c:
        s = c.get("/api/session").json()
        assert s["token"] is None and s["enforced"] is False
        h = c.get("/api/health").json()
        assert h["public"]["on"] is False and set(h["today"]) >= {"runs_left", "calls_left", "voice_credits_left", "world"}


def test_session_limit(tmp_path, tiny):
    g = gate(session_runs=2)
    with public_app(tmp_path, g) as c:
        tok = token_of(c)
        for left in (1, 0):
            assert ws_messages(c, f"{TINY_Q}&token={tok}")[-1]["k"] == "end"
            assert c.get(f"/api/scene?token={tok}").json()["session_runs_left"] == left
        with c.websocket_connect(f"/ws?{TINY_Q}&token={tok}") as ws:
            assert ws.receive_json()["code"] == "session_limit"
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 4029
        assert ws_messages(c, f"{TINY_Q}&token={token_of(c)}")[-1]["k"] == "end"  # a new session starts again
        assert c.get(f"/sse?{TINY_Q}&token={tok}").status_code == 429


def test_ip_limit_per_utc_day(tmp_path, tiny):
    clock = Clock(datetime(2026, 10, 27, 23, 50, tzinfo=timezone.utc))
    g = gate(ip_runs=2, clock=clock)
    with public_app(tmp_path, g) as c:
        for _ in range(2):
            assert ws_messages(c, f"{TINY_Q}&token={token_of(c)}")[-1]["k"] == "end"  # a new session each time: the address still counts
        assert c.get("/api/scene").json()["ip_runs_left"] == 0
        assert ws_messages(c, f"{TINY_Q}&token={token_of(c)}")[0]["code"] == "ip_limit"
        clock.at += timedelta(minutes=15)
        assert ws_messages(c, f"{TINY_Q}&token={token_of(c)}")[-1]["k"] == "end"
    assert g.left(None, "203.0.113.9")["ip_runs_left"] == 2  # counted per address


def test_concurrency_cap_and_release(tmp_path, tiny):
    g = gate(concurrent=1)
    with public_app(tmp_path, g) as c:
        held = g.claim("someone", "198.51.100.1")  # a run playing elsewhere
        assert c.get("/api/health").json()["public"]["busy"] is True
        assert ws_messages(c, f"{TINY_Q}&token={token_of(c)}")[0]["code"] == "busy"
        held()
        held()  # idempotent
        assert g.active == 0
        assert ws_messages(c, f"{TINY_Q}&token={token_of(c)}")[-1]["k"] == "end"
        assert g.active == 0  # released when the stream ended


def test_scene_endpoint(tmp_path):
    with public_app(tmp_path, gate()) as c:
        tok = token_of(c)
        body = c.get(f"/api/scene?token={tok}").json()
        assert {k: body[k] for k in ("id", "match", "start", "until", "goal_t", "goal_window", "score", "clock")} == {
            "id": "winner", "match": "comeback-135", "start": 5415.0, "until": 5490.0, "goal_t": None, "goal_window": [5462.0, 5471.5],
            "score": [1, 1], "clock": "88"}
        assert body["session"] is True and body["session_runs_left"] == 3 and body["ip_runs_left"] == 10 and body["title"]
        assert body["today"]["calls_left"] == 30 and c.get("/api/scene?id=nope").status_code == 404
        assert body["attack"] == {"H": 0.0, "A": 105.0}  # second half: the home side attacks x = 0


# ---------- a new play per run ----------
SCENE_Q = "match=comeback-135&mode=live&speed=1&paced=false&start=5415&until=5490&rows=1&world=0"


def _first(c: TestClient, q: str) -> dict:
    with c.websocket_connect(f"/ws?{q}") as ws:
        return ws.receive_json()


def test_every_run_of_the_scene_plays_a_new_variant(tmp_path, monkeypatch):
    seeds = iter([11, 12, 11])
    monkeypatch.setattr(app_module.secrets, "randbelow", lambda n: next(seeds))
    cfg = LiveConfig(fake_llm(), CallBudget(80), "fake", tmp_path)
    with TestClient(create_app(live=cfg)) as c:
        a, b = ws_messages(c, SCENE_Q), ws_messages(c, SCENE_Q)
        assert a[0]["scene_seed"] == 11 and b[0]["scene_seed"] == 12
        rows = lambda msgs: [(r["eid"], r["type"], r.get("player"), r.get("x")) for m in msgs if m["k"] == "row" for r in m["rows"]  # noqa: E731
                             if r["t"] > 5409]
        assert rows(a) and rows(a) != rows(b)
        assert any(m["k"] == "log" and m["agent"] == "facts" and m["step"] == "scene" for m in a)
        assert a[-1]["score"] == [2, 1] and b[-1]["score"] == [2, 1]
        assert rows(ws_messages(c, SCENE_Q)) == rows(a)  # the same seed again: the same play
        fixed = [ws_messages(c, SCENE_Q + "&seed=7") for _ in range(2)]
        assert fixed[0][0]["scene_seed"] == 7 and rows(fixed[0]) == rows(fixed[1])
        for bad in ("&seed=-1", "&seed=1234567", "&seed=abc"):
            assert ws_messages(c, SCENE_Q + bad)[0]["code"] == "bad_request", bad
        other = ws_messages(c, "match=comeback-135&mode=live&speed=1&paced=false&start=5460&until=5490&rows=1&world=0")
        assert "scene_seed" not in other[0]  # any other window plays the plain match
        assert ws_messages(c, "match=comeback-135&mode=live&speed=1&paced=false&start=5460&until=5490&seed=3")[0]["code"] == "bad_request"


def test_a_public_run_of_the_scene_gets_a_seed_of_its_own(tmp_path, monkeypatch):
    seeds = iter([21, 22])
    monkeypatch.setattr(app_module.secrets, "randbelow", lambda n: next(seeds))
    with public_app(tmp_path, gate()) as c:
        q = f"match=comeback-135&mode=live&speed=1&start=5415&until=5490&fast=1&rows=1&token={token_of(c)}"
        assert _first(c, q)["scene_seed"] == 21 and _first(c, q)["scene_seed"] == 22
        assert ws_messages(c, q + "&seed=21")[0]["code"] == "bad_request"


def test_two_variants_keep_their_own_continuity(tmp_path):
    live = LiveConfig(fake_llm(), CallBudget(80), "fake", tmp_path)
    for seed in SEEDS[:2]:
        asyncio.run(Runner(LIB.scene_bundle(WIN, seed), "live", 1.0, False, live, WIN.start, None, WIN.until, fast=True).collect())
    variants = {k[1] for k in live.recent_memo}
    assert variants == {str(s) for s in SEEDS[:2]}


# ---------- world and fast per run ----------
def test_fast_and_world_are_switched_per_run(tmp_path):
    prompts: list[str] = []
    cfg = LiveConfig(fake_llm(), CallBudget(80), "fake", tmp_path, world_call=world_fake(prompts))
    q = "match=comeback-135&mode=live&speed=1&paced=false&start=5460&until=5490"
    with TestClient(create_app(live=cfg)) as c:
        assert c.get("/api/health").json()["today"]["world"] is True
        on = ws_messages(c, q + "&fast=1&world=1")
        assert len(on[0]["channels"]) == 12 and prompts
        kinds = {m["kind"] for m in on if m["k"] == "say"}
        assert {"touch", "shot_goal", "goal_analysis", "score_line"} <= kinds  # the fast layer speaks
        assert any(m["k"] == "row" for m in on) and {m["ch"] for m in on if m["k"] == "say"} == set(range(12))
        n = len(prompts)
        off = ws_messages(c, q + "&world=0")
        assert len(off[0]["channels"]) == 6 and len(prompts) == n  # no world call for a run that did not ask for it
        assert not any(m["k"] == "row" for m in off) and "touch" not in {m["kind"] for m in off if m["k"] == "say"}
        rows_only = ws_messages(c, q + "&world=0&rows=1")
        assert any(m["k"] == "row" for m in rows_only) and "touch" not in {m["kind"] for m in rows_only if m["k"] == "say"}
        assert len(ws_messages(c, q)[0]["channels"]) == 12  # no switch: the server's default, as before
        for bad in ("&fast=2", "&world=yes"):
            assert ws_messages(c, q + bad)[0]["code"] == "bad_request"
        assert ws_messages(c, "match=comeback-7&mode=replay&paced=false&fast=1")[0]["code"] == "bad_request"
    with TestClient(create_app(live=LiveConfig(fake_llm(), CallBudget(30), "fake", tmp_path / "b"))) as c:
        assert c.get("/api/health").json()["today"]["world"] is False
        msgs = ws_messages(c, q + "&world=1")
        assert msgs[0]["code"] == "no_world"


def test_public_world_is_off_unless_asked_for(tmp_path, tiny):
    with public_app(tmp_path, gate(), world_call=world_fake()) as c:
        assert len(ws_messages(c, f"{TINY_Q}&token={token_of(c)}")[0]["channels"]) == 6
        assert len(ws_messages(c, f"{TINY_Q}&world=1&token={token_of(c)}")[0]["channels"]) == 12
    with public_app(tmp_path / "b", gate()) as c:
        assert ws_messages(c, f"{TINY_Q}&world=1&token={token_of(c)}")[0]["code"] == "no_world"


def test_fresh_makes_every_run_pay_its_own_calls(tmp_path):
    q = "match=comeback-135&mode=live&speed=60&paced=false&start=5460&until=5490&fast=1&world=1"
    for fresh, second in ((True, lambda n: n > 0), (False, lambda n: n == 0)):
        prompts: list[str] = []
        cfg = LiveConfig(fake_llm(), CallBudget(80), "fake", tmp_path / str(fresh), fresh=fresh, world_call=world_fake(prompts))
        with TestClient(create_app(live=cfg)) as c:
            first = ws_messages(c, q)[-1]["calls"]
            again = ws_messages(c, q)[-1]["calls"]
        assert first > 1 and second(again), (fresh, first, again)


def test_the_world_booth_skips_what_would_be_too_old_and_calls_the_goal_first(tmp_path):
    live = LiveConfig(fake_llm(), CallBudget(10), "fake", tmp_path, world_call=world_fake(), world_skip_late=True)
    r = Runner(LIB.bundle(WIN.match), "live", 1.0, True, live, WIN.start, None, WIN.until, fast=True, world=True)
    mk = lambda i, t, prio, ttl, kind: Moment(id=i, t=t, clock="89", kind=kind, voice="pbp", priority=prio, ttl=ttl, params={})  # noqa: E731
    r._moments = {1: mk(1, 5460.0, 26, 3.0, "touch"), 2: mk(2, 5459.0, 100, 20.0, "shot_goal"), 3: mk(3, 5463.0, 26, 3.0, "touch")}
    r._wq, r._wlat = [1, 2, 3], 3.0
    assert r._world_next(5462.0) == 2  # 1 is too old by the time a 3 s call returns (5465 > 5463); the goal goes first
    assert r._wq == [3] and r._world_next(5462.0) == 3 and r._world_next(5462.0) is None
    logs = [m for m in r._out if m["k"] == "log"]
    assert [(m["step"], m["m"], m["d"]["world"]) for m in logs] == [("too_late", 1, True)]


# ---------- voices ----------
def test_a_voice_for_every_person_and_language():
    tree = ast.parse((ROOT / "backend/scripts/bake_story_audio.py").read_text(encoding="utf-8"))
    baked = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "CAST")
    assert {who: v.id for who, v in CAST.items()} == baked  # the live cast is the recorded one
    langs = {k.split("/")[0] for k in ALL_KEYS}
    assert len(langs) == 9 and langs <= set(VOICES) and langs <= set(LANGUAGE_CODES)
    for key in ALL_KEYS:
        lang = key.split("/")[0]
        for role in ("pbp", "analyst"):
            who = who_of(key, role)
            assert voice_for(lang, who) is CAST[who]
    assert voice_for("en").id == "onwK4e9ZLuTAKqWW03F9" == voice_for("de").id == voice_for("fr").id  # unchanged without a speaker
    assert voice_for("ja") is CAST["Yuki Tanaka"] and voice_for("es", "Nobody") is CAST["Lucía Romero"]
    with pytest.raises(KeyError):
        voice_for("xx")
    assert set(LANGS) <= set(VOICES)


def _tts(tmp_path, credits=1000, daily=None, clock=None, synth=None):
    fake = synth or FakeSynth()
    kw = {"clock": clock} if clock else {}
    return GuardedTTS(fake, credits, MODEL, tmp_path / "tts", daily_credits=daily, **kw), fake


def test_world_lines_are_voiced_by_their_commentator_and_never_500(tmp_path):
    t, fake = _tts(tmp_path)
    cfg = LiveConfig(fake_llm(), CallBudget(80), "fake", tmp_path / "analyst", world_call=world_fake())
    with TestClient(create_app(live=cfg, tts=t)) as c:
        msgs = ws_messages(c, "match=comeback-135&mode=live&speed=60&paced=false&start=5460&until=5490&fast=1&world=1")
        run = msgs[0]["run"]
        for ch in (1, 6, 11):
            say = next(m for m in msgs if m["k"] == "say" and m["ch"] == ch and m["kind"] == "shot_goal")
            r = c.get(f"/api/tts?run={run}&ch={ch}&m={say['m']}")
            assert r.status_code == 200 and r.headers["x-voice-name"] == {1: "Charlie", 6: "Sarah", 11: "Jessica"}[ch]
            assert fake.calls[-1][1] == CAST[say["who"]].id and fake.calls[-1][2] == ALL_KEYS[ch].split("/")[0]
        co = next(m for m in msgs if m["k"] == "say" and m["ch"] == 2 and m["kind"] == "goal_analysis")
        assert c.get(f"/api/tts?run={run}&ch=2&m={co['m']}").headers["x-voice-name"] == "Anna"  # Kim Berger, the de co-commentator


def test_no_voice_is_a_clear_fallback_not_a_500(tmp_path, monkeypatch):
    t, fake = _tts(tmp_path)
    with TestClient(create_app(live=LiveConfig(fake_llm(), CallBudget(30), "fake", tmp_path / "a"), tts=t)) as c:
        msgs = ws_messages(c, "match=comeback-7&mode=live&speed=60&paced=false&start=700&until=760")
        say = next(m for m in msgs if m["k"] == "say")
        def none(lang, who=None):
            raise KeyError(lang)
        monkeypatch.setattr(app_module, "voice_for", none)
        r = c.get(f"/api/tts?run={msgs[0]['run']}&ch={say['ch']}&m={say['m']}")
        assert r.status_code == 409 and r.json()["detail"] == {"code": "no_voice", "message": r.json()["detail"]["message"], "fallback": "browser"}
        assert r.headers["x-voice-fallback"] == "browser" and not fake.calls


# ---------- voice credits per day and per session ----------
def test_tts_daily_credits_count_todays_ledger_rows_only(tmp_path):
    now = datetime(2026, 10, 27, 0, 30, tzinfo=timezone.utc).timestamp()
    t, fake = _tts(tmp_path, credits=1000, daily=40, clock=lambda: now)
    t.ledger.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"at": now - 3600, "credits": 500}, {"at": now - 60, "credits": 10}]  # yesterday 23:30, today 00:29
    t.ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert t.spent == 510 and t.spent_today == 10 and t.remaining_today == 30 and t.remaining == 30
    assert t.status()["credits_today_left"] == 30 and t.status()["credits_per_day"] == 40
    asyncio.run(t.speak("Short line, fourteen.", "en"))  # 21 chars, 11 credits
    assert t.spent_today == 21 and t.remaining == 19
    with pytest.raises(TTSDailyExceeded) as err:
        asyncio.run(t.speak("A longer line that needs more than what is left today.", "en"))
    assert err.value.code == "tts_daily_limit" and len(fake.calls) == 1
    t2, _ = _tts(tmp_path, credits=515, daily=40, clock=lambda: now)  # the lifetime cap still holds under the daily one
    assert t2.remaining == 0
    with pytest.raises(TTSBudgetExceeded):
        asyncio.run(t2.speak("Another.", "en"))
    later, _ = _tts(tmp_path, credits=1000, daily=40, clock=lambda: now + 86400)  # the next UTC day starts fresh
    assert later.remaining_today == 40


def test_voice_out_answers_with_the_browser_fallback(tmp_path, tiny):
    t, fake = _tts(tmp_path, credits=1000, daily=1)
    with TestClient(create_app(live=LiveConfig(fake_llm(), CallBudget(30), "fake", tmp_path / "a"), tts=t)) as c:
        msgs = ws_messages(c, "match=comeback-7&mode=live&speed=60&paced=false&start=700&until=760")
        say = next(m for m in msgs if m["k"] == "say")
        r = c.get(f"/api/tts?run={msgs[0]['run']}&ch={say['ch']}&m={say['m']}")
        assert r.status_code == 402 and r.json()["detail"]["code"] == "tts_daily_limit" and r.json()["detail"]["fallback"] == "browser"
        assert r.headers["x-voice-fallback"] == "browser" and not fake.calls
        assert c.get("/api/health").json()["today"]["voice_credits_left"] == 1


def test_public_voice_needs_the_runs_session_and_has_a_session_credit_cap(tmp_path):
    t, fake = _tts(tmp_path)
    g = gate(session_credits=20)
    with public_app(tmp_path, g, tts=t) as c:
        tok, other = token_of(c), token_of(c)
        # a run of this session (a paced 60 s scene is too slow for a test: make one unpaced and register it the way make_runner does)
        sid = g.verify(tok)
        r = Runner(LIB.bundle(WIN.match), "live", 60.0, False, LiveConfig(fake_llm(), CallBudget(5), "fake", tmp_path / "b"),
                   5460.0, None, 5490.0)
        msgs = asyncio.run(r.collect())
        say = [m for m in msgs if m["k"] == "say" and m["ch"] == 1]
        # reach into the app's run registry the way make_runner does
        state = _registry(c)
        state["runs"][r.run_id], state["speakers"][r.run_id], state["energies"][r.run_id] = r.lines, r.speakers, r.energies
        g.own(r.run_id, sid)
        url = lambda s, token: f"/api/tts?run={r.run_id}&ch={s['ch']}&m={s['m']}&token={token}"  # noqa: E731
        assert c.get(url(say[0], "")).status_code == 401
        assert c.get(url(say[0], other)).status_code == 404  # another session cannot voice this run
        spent = 0
        for s in say:
            res = c.get(url(s, tok))
            if res.status_code == 402:
                assert res.json()["detail"]["code"] == "tts_session_limit" and res.json()["detail"]["fallback"] == "browser"
                break
            assert res.status_code == 200
            spent += t.cost(s["text"])
        else:
            pytest.fail("the session credit cap never answered")
        assert spent <= 20 and g.left(sid, None)["session_credits_left"] == 20 - spent
        assert t.spent == spent  # nothing was billed for the refused line


def _registry(c: TestClient) -> dict:
    """The run registry inside create_app (closure cells of the voice endpoint)."""
    route = next(r for r in c.app.routes if getattr(r, "path", "") == "/api/tts")
    fn = route.endpoint
    cells = dict(zip(fn.__code__.co_freevars, (x.cell_contents for x in fn.__closure__)))
    return {k: cells[k] for k in ("runs", "speakers", "energies")}


# ---------- origins ----------
def test_origin_allow_list_for_websocket_and_cors(tmp_path):
    ok, evil = "https://demo.example", "https://evil.example"
    with TestClient(create_app(allowed_origins=[ok])) as c:
        q = "/ws?match=comeback-7&mode=replay&speed=30&paced=false"
        with c.websocket_connect(q, headers={"origin": ok}) as ws:
            assert ws.receive_json()["k"] == "hello"
        for headers in ({"origin": evil}, {}):
            with pytest.raises(WebSocketDisconnect) as refused:
                with c.websocket_connect(q, headers=headers) as ws:
                    ws.receive_json()
            assert refused.value.code == 4003
        r = c.get("/api/health", headers={"origin": ok})
        assert r.headers["access-control-allow-origin"] == ok and "X-Voice-Name" in r.headers["access-control-expose-headers"]
        assert "access-control-allow-origin" not in c.get("/api/health", headers={"origin": evil}).headers
        assert c.get("/sse?match=comeback-7&mode=replay&speed=30&paced=false", headers={"origin": evil}).status_code == 403
    with TestClient(create_app()) as c:  # unset: open, as before (local development)
        assert c.get("/api/health", headers={"origin": evil}).headers["access-control-allow-origin"] == "*"
        with c.websocket_connect("/ws?match=comeback-7&mode=replay&speed=30&paced=false", headers={"origin": evil}) as ws:
            assert ws.receive_json()["k"] == "hello"


def test_live_unavailable_codes_have_close_codes():
    for code in ("session_limit", "ip_limit", "busy", "no_calls_today", "session_required", "no_world", "no_session_secret"):
        assert code in app_module.WS_CODES
    assert LiveUnavailable("busy", "x").code == "busy"


# ---------- review fixes (2026-10-27) ----------
def _ws_with(c: TestClient, query: str, headers: dict) -> list[dict]:
    out = []
    with c.websocket_connect(f"/ws?{query}", headers=headers) as ws:
        while True:
            out.append(ws.receive_json())
            if out[-1]["k"] in ("end", "error"):
                return out


def test_client_ip_trusts_only_the_rightmost_forwarded_entries():
    from starlette.requests import Request as Req
    def req(*xff):
        return Req({"type": "http", "client": ("10.0.0.7", 5000), "headers": [(b"x-forwarded-for", v.encode()) for v in xff]})
    assert app_module.client_ip(req("6.6.6.6, 20.50.1.1"), 0) == "10.0.0.7"  # no proxy trusted: the socket peer
    assert app_module.client_ip(req("6.6.6.6, 20.50.1.1"), 1) == "20.50.1.1"  # the entry the ingress appended
    assert app_module.client_ip(req("6.6.6.6", "20.50.1.1"), 1) == "20.50.1.1"  # two header lines read as one list
    assert app_module.client_ip(req("6.6.6.6, 7.7.7.7, 20.50.1.1"), 2) == "7.7.7.7"
    assert app_module.client_ip(req(), 1) == "10.0.0.7" and app_module.client_ip(req("20.50.1.1"), 2) == "10.0.0.7"


def test_a_forged_forwarded_entry_does_not_dodge_the_ip_cap(tmp_path, tiny):
    g = gate(ip_runs=1)
    with public_app(tmp_path, g, trusted_hops=1) as c:
        real = "20.50.1.1"  # what Envoy appends: the peer it saw
        assert _ws_with(c, f"{TINY_Q}&token={token_of(c)}", {"x-forwarded-for": real})[-1]["k"] == "end"
        for forged in ("1.1.1.1", "2.2.2.2", "not-an-ip"):
            msgs = _ws_with(c, f"{TINY_Q}&token={token_of(c)}", {"x-forwarded-for": f"{forged}, {real}"})
            assert msgs[0]["code"] == "ip_limit", forged
            r = c.get(f"/sse?{TINY_Q}&token={token_of(c)}", headers={"x-forwarded-for": f"{forged}, {real}"})
            assert r.status_code == 429 and r.json()["detail"]["code"] == "ip_limit"
        assert c.get("/api/scene", headers={"x-forwarded-for": f"9.9.9.9, {real}"}).json()["ip_runs_left"] == 0
        assert c.get("/api/session", headers={"x-forwarded-for": f"9.9.9.9, {real}"}).json()["ip_runs_left"] == 0
        other = _ws_with(c, f"{TINY_Q}&token={token_of(c)}", {"x-forwarded-for": f"{real}, 20.50.1.2"})
        assert other[-1]["k"] == "end"  # another visitor (another appended address) still runs
    with public_app(tmp_path / "b", gate(ip_runs=1)) as c:  # no trusted hop: the header is ignored, the peer counts
        assert _ws_with(c, f"{TINY_Q}&token={token_of(c)}", {"x-forwarded-for": "1.1.1.1"})[-1]["k"] == "end"
        assert _ws_with(c, f"{TINY_Q}&token={token_of(c)}", {"x-forwarded-for": "2.2.2.2"})[0]["code"] == "ip_limit"


def _own_run(c: TestClient, g: PublicGate, tok: str, tmp_path) -> tuple[Runner, list[dict]]:
    """A finished unpaced core run registered for this session the way make_runner does (a paced scene is too slow for a test)."""
    r = Runner(LIB.bundle(WIN.match), "live", 60.0, False, LiveConfig(fake_llm(), CallBudget(5), "fake", tmp_path), 5460.0, None, 5490.0)
    msgs = asyncio.run(r.collect())
    state = _registry(c)
    state["runs"][r.run_id], state["speakers"][r.run_id], state["energies"][r.run_id] = r.lines, r.speakers, r.energies
    g.own(r.run_id, g.verify(tok))
    return r, [m for m in msgs if m["k"] == "say"]


def test_a_run_voices_only_its_watched_channel_and_one_switch(tmp_path):
    t, fake = _tts(tmp_path)
    g = gate(session_credits=0, ip_credits=0)
    with public_app(tmp_path, g, tts=t) as c:
        tok = token_of(c)
        r, says = _own_run(c, g, tok, tmp_path / "run")
        first = {ch: next(m for m in says if m["ch"] == ch) for ch in range(6)}
        url = lambda m: f"/api/tts?run={r.run_id}&ch={m['ch']}&m={m['m']}&token={tok}"  # noqa: E731
        assert c.get(url(first[1])).status_code == 200 and c.get(url(first[4])).status_code == 200  # watched, then one switch
        n = len(fake.calls)
        for ch in (0, 2, 3, 5):
            res = c.get(url(first[ch]))
            assert res.status_code == 409 and res.json()["detail"]["code"] == "tts_channel_limit", ch
            assert res.json()["detail"]["fallback"] == "browser" and res.headers["x-voice-fallback"] == "browser"
        assert len(fake.calls) == n  # nothing synthesised for the refused channels
        more = [m for m in says if m["ch"] == 1][1:3]
        assert more and all(c.get(url(m)).status_code == 200 for m in more)  # the bound channels keep working
        r2, says2 = _own_run(c, g, tok, tmp_path / "run2")  # every run binds its own channels
        m2 = next(m for m in says2 if m["ch"] == 3)
        assert c.get(f"/api/tts?run={r2.run_id}&ch=3&m={m2['m']}&token={tok}").status_code == 200


def test_voice_credits_are_capped_per_address_across_sessions(tmp_path):
    t, fake = _tts(tmp_path)
    g = gate(session_credits=0, ip_credits=30)
    with public_app(tmp_path, g, tts=t, trusted_hops=1) as c:
        xff = {"x-forwarded-for": "5.5.5.5, 20.50.1.1"}
        spent, refused = 0.0, None
        for i in range(6):  # a new session each time: the address's allowance does not refill
            tok = token_of(c)
            r, says = _own_run(c, g, tok, tmp_path / f"run{i}")
            for s in [m for m in says if m["ch"] == 1]:
                res = c.get(f"/api/tts?run={r.run_id}&ch=1&m={s['m']}&token={tok}", headers=xff)
                if res.status_code == 402:
                    refused = res.json()["detail"]
                    break
                assert res.status_code == 200
                if res.headers["x-voice-cached"] == "0":
                    spent += t.cost(s["text"])
            if refused:
                break
        assert refused and refused["code"] == "tts_ip_limit" and refused["fallback"] == "browser"
        assert spent <= 30 and g.left(None, "20.50.1.1")["ip_credits_left"] == pytest.approx(30 - spent)
        assert g.left(None, "20.50.1.2")["ip_credits_left"] == 30  # another address is untouched
        assert c.get("/api/session", headers=xff).json()["ip_credits_left"] == pytest.approx(30 - spent)


def test_a_run_that_crosses_midnight_keeps_its_voice(tmp_path, tiny):
    t, fake = _tts(tmp_path)
    clock = Clock(datetime(2026, 10, 27, 23, 59, 30, tzinfo=timezone.utc))
    g = gate(clock=clock)
    with public_app(tmp_path, g, tts=t) as c:
        tok = c.get("/api/session").json()["token"]  # issued on the 27th
        clock.at = datetime(2026, 10, 28, 23, 59, 30, tzinfo=timezone.utc)  # the token's last valid day: a run starts
        r, says = _own_run(c, g, tok, tmp_path / "run")
        line = next(m for m in says if m["ch"] == 1)
        clock.at += timedelta(minutes=1)  # 00:00:30 on the 29th, mid-run
        assert g.verify(tok) is None  # a new run, a session or a stream would need a new token
        res = c.get(f"/api/tts?run={r.run_id}&ch=1&m={line['m']}&token={tok}")
        assert res.status_code == 200 and res.headers["content-type"] == "audio/mpeg"
        forged = tok[:-1] + ("0" if tok[-1] != "0" else "1")
        assert c.get(f"/api/tts?run={r.run_id}&ch=1&m={line['m']}&token={forged}").status_code == 401  # the signature still counts
        assert ws_messages(c, f"{TINY_Q}&token={tok}")[0]["code"] == "session_required"


def test_sse_frees_the_slot_when_sending_fails_before_the_body_starts(tmp_path, tiny):
    g = gate()
    with public_app(tmp_path, g) as c:
        tok = token_of(c)
        app = c.app

    async def drive() -> None:
        query = f"{TINY_Q}&token={tok}".encode()
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
                 "path": "/sse", "raw_path": b"/sse", "root_path": "", "query_string": query, "headers": [(b"host", b"testserver")],
                 "client": ("198.51.100.4", 1234), "server": ("testserver", 80)}

        async def receive():
            await asyncio.sleep(3600)
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                raise OSError("the connection broke before the response started")
        with pytest.raises(BaseException):
            await app(scope, receive, send)
    asyncio.run(drive())
    assert g.active == 0  # the slot is free again, not held until a restart


def test_the_servers_own_page_may_open_a_stream_with_an_allow_list(tmp_path):
    with TestClient(create_app(allowed_origins=["https://page.example"]), base_url="https://api.example") as c:
        q = "ws://api.example/ws?match=comeback-7&mode=replay&speed=30&paced=false"  # Host: api.example, the server's own name
        with c.websocket_connect(q, headers={"origin": "https://api.example"}) as ws:
            assert ws.receive_json()["k"] == "hello"
        assert c.get("/sse?match=comeback-7&mode=replay&speed=30&paced=false", headers={"origin": "https://api.example"}).status_code == 200
        for evil in ("https://evil.example", "https://api.example.evil.example", "null"):
            with pytest.raises(WebSocketDisconnect) as refused:
                with c.websocket_connect(q, headers={"origin": evil}) as ws:
                    ws.receive_json()
            assert refused.value.code == 4003, evil


def test_a_refused_public_run_generates_no_scene(tmp_path, monkeypatch):
    """The scene is simulated only once every check has passed: a request the session, IP or concurrency caps refuse costs no Sim."""
    made = []
    orig = Library.scene_bundle
    monkeypatch.setattr(Library, "scene_bundle", lambda self, *a, **k: made.append(a) or orig(self, *a, **k))
    g = gate()
    def refuse(sid, ip):
        raise LiveUnavailable("session_limit", "this session has used its runs")
    monkeypatch.setattr(g, "check", refuse)
    with public_app(tmp_path, g) as c:
        q = f"match={WIN.match}&mode=live&speed=1&start={WIN.start}&until={WIN.until}&fast=1&token={token_of(c)}"
        with c.websocket_connect(f"/ws?{q}") as ws:
            assert ws.receive_json()["code"] == "session_limit"
    assert made == []
