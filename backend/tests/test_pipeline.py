import asyncio
import dataclasses
import json

import pytest

import matchvoice.config as config
from matchvoice.commentary.analyst import KEYS, PROMPT_VERSION, SYSTEM, CallBudget, build_prompt
from matchvoice.commentary.director import ChannelDirector, schedule
from matchvoice.commentary.moments import Moment, render_variants
from matchvoice.commentary.verifier import Verifier, allowed_for
from matchvoice.pipeline import protocol as proto
from matchvoice.pipeline.library import Library, MatchBundle
from matchvoice.pipeline.runner import LiveConfig, LiveUnavailable, ReplayMismatch, Runner
from test_commentary import build

LIB = Library()
IDS = LIB.recorded_ids()  # matches generated only for live runs have no recording
GOOD = {
    "en": "What a moment this is, and the crowd is on its feet for it.",
    "de": "Das ist ein starker Moment, und die Zuschauer sind auf den Beinen.",
    "fr": "C'est un grand moment pour le public, et il est sur ses pieds.",
}


def run(runner: Runner) -> list[dict]:
    return asyncio.run(runner.collect())


def fake_llm(delay: float = 0.0, fail: bool = False):
    async def call(prompt: str) -> str:
        await asyncio.sleep(delay)
        if fail:
            raise ConnectionError("model unreachable")
        return json.dumps({k: GOOD[k.split("/")[0]] for k in KEYS})
    return call


def live_cfg(tmp_path, max_calls=50, **kw) -> LiveConfig:
    return LiveConfig(fake_llm(**kw), CallBudget(max_calls), "fake", tmp_path)


def head(bundle: MatchBundle, until: float) -> MatchBundle:
    return dataclasses.replace(bundle, events=[e for e in bundle.events if e.t <= until])


@pytest.fixture(scope="module")
def replays():
    return {i: run(Runner(LIB.bundle(i), "replay", 30.0, paced=False)) for i in IDS}


# ---------- home-away fix ----------
def test_prompt_states_the_home_away_rule_and_names_the_score_that_way():
    meta, _, _, _, moments, snaps = build("comeback")
    m = next(x for x in moments if x.kind == "goal_analysis")
    prompt = build_prompt(m, snaps[m.id], meta)
    assert "home-away" in SYSTEM and PROMPT_VERSION != "v1"
    assert '"score": ' not in prompt and prompt.count('"score_home_away": "0-1"') == 2


def test_verifier_names_a_swapped_scoreline():
    meta, _, _, _, moments, snaps = build("comeback")
    m = next(x for x in moments if x.kind == "goal_analysis")  # 0-1, away team scored
    allowed = allowed_for(m, snaps[m.id], meta)
    ver = Verifier(meta)
    swapped = ver.check("Lemaire scores for Marlow Bay United and it is 1-0 in the 14th minute.", "en", allowed)
    assert [v.code for v in swapped.violations] == ["score_swapped"] and "0-1" in swapped.feedback()
    assert ver.check("Lemaire scores for Marlow Bay United and it is 0-1 in the 14th minute.", "en", allowed).ok


@pytest.mark.parametrize("match_id", IDS)
def test_recorded_analyst_lines_pass_the_verifier_with_home_away_scores(match_id):
    b = LIB.bundle(match_id)
    assert b.recorded, "no analyst recording"
    arc = b.meta.arc
    meta, _, _, _, moments, snaps = build(arc)
    by_id = {m.id: m for m in moments}
    ver = Verifier(meta)
    for pub in b.recorded:
        m = by_id[pub.moment_id]
        allowed = allowed_for(m, snaps[m.id], meta)
        assert set(pub.lines) == set(KEYS)
        for key, text in ((k, v[-1]) for k, v in pub.lines.items() if pub.sources[k] == "analyst"):
            verdict = ver.check(text, key.split("/")[0], allowed)
            assert verdict.ok, (match_id, m.kind, key, text, verdict.feedback())


# ---------- protocol ----------
@pytest.mark.parametrize("match_id", IDS)
def test_every_event_encodes_to_a_fixed_length_array(match_id):
    b = LIB.bundle(match_id)
    enc = proto.FrameEncoder(b.meta)
    for ev in b.events:
        row = proto.encode_event(ev, enc.player_index)
        assert len(row) == len(proto.EVENT_FIELDS) and row[0] == ev.i and all(isinstance(x, int) for x in row)


def test_frames_carry_stat_deltas_only():
    b = LIB.bundle("comeback-7")
    runner = Runner(b, "replay", 30.0, paced=False)
    frames = [m for m in run(runner) if m["k"] == "f"]
    assert set(frames[0]["st"][0]) == {str(i) for i in range(len(proto.STATS))}  # first frame sends everything
    assert any("st" not in f or len(f["st"][0]) < len(proto.STATS) for f in frames[1:])
    assert all(len(f["wp"]) == 3 and abs(sum(f["wp"]) - 1000) <= 2 for f in frames)


# ---------- replay stream ----------
@pytest.mark.parametrize("match_id", IDS)
def test_replay_stream_is_ordered_complete_and_speaks_every_goal(match_id, replays):
    msgs = replays[match_id]
    assert msgs[0]["k"] == "hello" and msgs[-1]["k"] == "end"
    assert {m["k"] for m in msgs} == {"hello", "f", "say", "log", "end"}
    ts = [m["t"] for m in msgs]
    assert ts == sorted(ts)
    assert sum(len(m["e"]) for m in msgs if m["k"] == "f") == len(LIB.bundle(match_id).events)
    for ch in range(len(KEYS)):
        said = [m for m in msgs if m["k"] == "say" and m["ch"] == ch]
        final = {}
        for m in said:  # a later message about the same moment is its cut correction
            final[m["m"]] = m
        lines = sorted(final.values(), key=lambda m: m["s"])
        assert all(a["e"] <= b["s"] + 1e-6 for a, b in zip(lines, lines[1:])), "lines overlap"
        assert sum(1 for m in lines if m["kind"] == "shot_goal") == sum(LIB.summary(match_id)["final"])
    assert msgs[-1]["score"] == LIB.summary(match_id)["final"]


def test_replay_uses_recorded_analyst_lines_and_logs_the_agent_steps(replays):
    for msgs in replays.values():
        assert any(m["k"] == "say" and m["src"] == "analyst" for m in msgs)
        steps = {m["step"] for m in msgs if m["k"] == "log"}
        assert {"queued", "analyst_wrote", "verified", "ready"} <= steps
        assert all(m["at"] <= m["t"] + 1e-6 for m in msgs if m["k"] == "log")


def test_replay_is_deterministic_and_needs_no_key(monkeypatch, replays):
    for name in ("ANTHROPIC_API_KEY_2", "ANTHROPIC_API_KEY", "ANTHROPIC_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "_ENV", {})
    assert config.anthropic_api_key() is None
    assert run(Runner(LIB.bundle("comeback-7"), "replay", 30.0, paced=False)) == replays["comeback-7"]


def test_replay_without_a_recording_falls_back_to_templates():
    b = dataclasses.replace(LIB.bundle("comeback-7"), recorded=None)
    msgs = run(Runner(b, "replay", 10.0, paced=False))
    assert not any(m["k"] == "say" and m["src"] == "analyst" for m in msgs) and msgs[-1]["k"] == "end"


def test_replay_of_another_build_is_refused():
    b = LIB.bundle("comeback-7")
    wrong = dataclasses.replace(b, recorded_kinds={p.moment_id: "corner" for p in b.recorded})
    with pytest.raises(ReplayMismatch):
        run(Runner(wrong, "replay", 30.0, paced=False))


def test_speed_changes_the_schedule_not_the_frames_content():
    b = LIB.bundle("comeback-7")
    slow, fast = (run(Runner(b, "replay", s, paced=False)) for s in (10.0, 60.0))
    count = lambda ms: sum(len(m["e"]) for m in ms if m["k"] == "f")
    assert count(slow) == count(fast) == len(b.events)
    assert sum(m["k"] == "say" for m in slow) > sum(m["k"] == "say" for m in fast)


def test_paced_run_waits_for_the_wall_clock():
    import time

    async def first_frames_after(until: float, runner: Runner) -> tuple[float, float]:
        t0 = time.monotonic()
        stream = runner.stream()
        async for msg in stream:
            if msg["k"] == "f" and msg["t"] >= until:
                break
        await stream.aclose()
        return time.monotonic() - t0, msg["t"]

    b = head(LIB.bundle("comeback-7"), 400.0)
    fast, _ = asyncio.run(first_frames_after(200.0, Runner(b, "replay", 200.0, paced=False)))
    slow, t = asyncio.run(first_frames_after(200.0, Runner(b, "replay", 200.0, paced=True)))
    assert fast < 0.5 and 0.9 * t / 200.0 <= slow < t / 200.0 + 1.0  # about one second for 200 match seconds at 200x


# ---------- live mode ----------
def test_live_refuses_without_key_and_without_budget(monkeypatch):
    for name in ("ANTHROPIC_API_KEY_2", "ANTHROPIC_API_KEY", "ANTHROPIC_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "_ENV", {})
    with pytest.raises(LiveUnavailable) as no_key:
        LiveConfig.from_env(5)
    assert no_key.value.code == "no_key"
    with pytest.raises(LiveUnavailable) as no_budget:
        LiveConfig.from_env(0)
    assert no_budget.value.code == "no_budget"
    b = LIB.bundle("comeback-7")
    with pytest.raises(LiveUnavailable):
        Runner(b, "live")
    with pytest.raises(LiveUnavailable):
        Runner(b, "live", live=LiveConfig(fake_llm(), CallBudget(0), "fake"))


def test_live_unpaced_runs_the_newsroom_and_speaks_its_lines(tmp_path):
    cfg = live_cfg(tmp_path)
    msgs = run(Runner(head(LIB.bundle("comeback-7"), 1500.0), "live", 10.0, paced=False, live=cfg))
    assert msgs[0]["mode"] == "live" and msgs[-1]["k"] == "end" and msgs[-1]["calls"] == cfg.budget.used > 0
    assert any(m["k"] == "say" and m["src"] == "analyst" for m in msgs)
    assert {"queued", "analyst_wrote", "verified", "ready"} <= {m["step"] for m in msgs if m["k"] == "log"}
    assert [m["t"] for m in msgs] == sorted(m["t"] for m in msgs)


def test_live_with_until_runs_to_the_end_of_its_window_even_when_it_goes_quiet(tmp_path):
    b = LIB.bundle("comeback-7")
    start = 200.0
    until = start + 60.0
    last_ev = max(e.t for e in b.events if start <= e.t <= until)
    r = Runner(b, "live", 10.0, start=start, until=until, paced=False, live=live_cfg(tmp_path))
    end = run(r)[-1]
    assert end["k"] == "end" and end["t"] >= until - r.dt - 1e-6 and end["t"] >= last_ev


def test_live_paced_collects_the_newsroom_while_the_match_streams(tmp_path):
    cfg = live_cfg(tmp_path, delay=0.3)

    async def until_first_ready() -> list[dict]:
        out = []
        stream = Runner(head(LIB.bundle("comeback-7"), 400.0), "live", 200.0, paced=True, live=cfg).stream()
        async for msg in stream:
            out.append(msg)
            if msg["k"] == "log" and msg["step"] == "ready":
                break
        await stream.aclose()
        return out

    msgs = asyncio.run(until_first_ready())
    i_queued = next(i for i, m in enumerate(msgs) if m["k"] == "log" and m["step"] == "queued")
    i_ready = len(msgs) - 1
    assert any(m["k"] == "f" for m in msgs[i_queued:i_ready]), "the match must keep streaming while the analyst writes"
    assert cfg.budget.used >= 1


def test_live_survives_model_errors_and_an_empty_budget(tmp_path):
    b = head(LIB.bundle("comeback-7"), 1500.0)
    broken = run(Runner(b, "live", 10.0, paced=False, live=live_cfg(tmp_path, fail=True)))
    assert broken[-1]["k"] == "end" and any(m["k"] == "log" and m["step"] == "analyst_error" for m in broken)
    capped_cfg = live_cfg(tmp_path / "other", max_calls=1)
    capped = run(Runner(b, "live", 10.0, paced=False, live=capped_cfg))
    assert capped[-1]["k"] == "end" and capped_cfg.budget.used == 1
    assert any(m["k"] == "log" and m["step"] == "analyst_unavailable" for m in capped)


# ---------- director ----------
def test_stepwise_director_matches_the_batch_schedule():
    _, _, _, _, moments, _ = build("comeback")
    f = lambda m: render_variants(m, "en", "expert")
    batch = schedule(moments, f, "en", 10.0)
    d = ChannelDirector(f, "en", 10.0)
    for m in moments:
        d.push(m)
    t = 0.0
    while not d.idle:
        t += 7.0
        d.advance(t)
    assert [vars(x) for x in d.close()[0]] == [vars(x) for x in batch[0]]


def test_analysis_stays_worth_saying_at_high_speed():
    pbp = Moment(0, 0.0, "1", "corner", "pbp", 45, 8, {})
    late = Moment(1, 0.0, "1", "goal_analysis", "analyst", 70, 40, {}, ready_t=6.0 * 30)
    spoken, _ = schedule([pbp, late], lambda m: ["Corner."] if m is pbp else ["Context for the goal."], "en", 30.0)
    assert [s.kind for s in spoken] == ["corner", "goal_analysis"]


@pytest.mark.parametrize("arc", ["comeback", "red_card", "unlucky"])
@pytest.mark.parametrize("speed", [1.0, 10.0, 60.0])
@pytest.mark.parametrize("key", KEYS)
def test_stepwise_director_matches_the_batch_schedule_everywhere(arc, speed, key):
    _, _, _, _, moments, _ = build(arc)
    lang, style = key.split("/")
    f = lambda m: render_variants(m, lang, style)
    d = ChannelDirector(f, lang, speed)
    for m in moments:
        d.push(m)
    t = 0.0
    while not d.idle:
        t += max(0.5, speed / 20.0)
        d.advance(t)
    assert [vars(x) for x in d.close()[0]] == [vars(x) for x in schedule(moments, f, lang, speed)[0]]


@pytest.mark.parametrize("match_id", IDS)
def test_lines_start_within_one_frame_of_their_start_time(match_id):
    r = Runner(LIB.bundle(match_id), "replay", 5.0, paced=False)
    msgs = run(r)
    late = [m["t"] - m["s"] for m in msgs if m["k"] == "say" and not m["cut"]]
    assert late and max(late) <= r.dt + 1e-6


def test_end_calls_counts_this_run_only(tmp_path):
    cfg = live_cfg(tmp_path)
    b = head(LIB.bundle("comeback-7"), 1500.0)
    first = run(Runner(b, "live", 10.0, paced=False, live=cfg))[-1]["calls"]
    cfg.cache_dir = tmp_path / "second"  # no cache hits, the second run pays for its own calls
    second = run(Runner(b, "live", 10.0, paced=False, live=cfg))[-1]["calls"]
    assert 0 < first == second and cfg.budget.used == first + second


def test_replay_notes_model_moments_without_a_recording_and_checks_times():
    b = dataclasses.replace(LIB.bundle("comeback-7"), recorded=None)
    msgs = run(Runner(b, "replay", 10.0, paced=False))
    queued = {m["m"] for m in msgs if m["k"] == "log" and m["step"] == "queued"}
    ready = {m["m"] for m in msgs if m["k"] == "log" and m["step"] == "ready"}
    assert queued and queued == ready
    real = LIB.bundle("comeback-7")
    moved = dataclasses.replace(real, recorded_times={i: t + 1.0 for i, t in real.recorded_times.items()})
    with pytest.raises(ReplayMismatch):
        run(Runner(moved, "replay", 10.0, paced=False))


# ---------- live: start minute, wall-clock data, no recordings ----------
def test_live_start_catches_up_without_commentary_and_ignores_recordings(tmp_path):
    cfg = live_cfg(tmp_path)
    b = LIB.bundle("comeback-7")  # has a recording, which live must not read
    msgs = run(Runner(head(b, 1500.0), "live", 10.0, paced=False, live=cfg, start=700.0))
    assert msgs[0]["start"] == 700.0
    catch_up = [m for m in msgs if m["k"] == "f" and m["t"] < 700.0]
    assert catch_up and sum(len(m["e"]) for m in msgs if m["k"] == "f") == len(head(b, 1500.0).events)
    assert all(m["s"] >= 700.0 for m in msgs if m["k"] == "say"), "nothing is said about the part skipped"
    analyst = {m["text"] for m in msgs if m["k"] == "say" and m["src"] == "analyst"}
    assert cfg.budget.used > 0 and analyst <= set(GOOD.values())  # the model was called, no recorded text appears


def test_paced_live_stamps_wall_time_latency_and_heartbeats(tmp_path):
    cfg = live_cfg(tmp_path, delay=0.2)

    async def collect() -> list[dict]:
        out = []
        stream = Runner(head(LIB.bundle("comeback-7"), 900.0), "live", 100.0, paced=True, live=cfg, start=760.0).stream()
        async for msg in stream:
            out.append(msg)
        return out

    msgs = asyncio.run(collect())
    says = [m for m in msgs if m["k"] == "say" and not m["cut"]]
    assert says and all("lat" in m and "w" in m for m in says)
    pbp = next(m for m in says if m["src"] == "template" and m["kind"] == "shot_goal")
    assert pbp["lat"] < 0.5  # the fast path does not wait for a model
    logs = [m for m in msgs if m["k"] == "log" and m["step"] in ("queued", "analyst_wrote", "ready")]
    assert logs and all("w" in m for m in logs)
    wrote = next(m for m in logs if m["step"] == "analyst_wrote")
    queued = next(m for m in logs if m["step"] == "queued")
    assert wrote["w"] - queued["w"] >= 0.15  # the model delay shows in the log timestamps
    assert [m["t"] for m in msgs if m["k"] != "f" or m["t"] >= 760.0] == sorted(m["t"] for m in msgs if m["k"] != "f" or m["t"] >= 760.0)


def test_replay_has_no_wall_clock_fields_and_rejects_a_start():
    r = Runner(LIB.bundle("comeback-7"), "replay", 30.0, paced=False, start=500.0)
    assert r.start == 0.0  # a recording always plays from kick-off
    msgs = run(r)
    assert not any("lat" in m or "w" in m for m in msgs if m["k"] in ("say", "log"))
    with pytest.raises(ValueError):
        Runner(LIB.bundle("comeback-7"), "replay", 30.0, start=1e9)


def test_live_marks_cached_answers_and_fresh_mode_ignores_the_cache(tmp_path):
    def play(cfg: LiveConfig) -> list[dict]:
        return run(Runner(head(LIB.bundle("comeback-7"), 800.0), "live", 600.0, paced=True, live=cfg))

    first = live_cfg(tmp_path)
    msgs = play(first)
    calls = first.budget.used
    assert calls > 0 and not any(m.get("cached") for m in msgs if m["k"] == "say")
    assert "lookup" not in {m["step"] for m in msgs if m["k"] == "log"}

    again = live_cfg(tmp_path)  # same cache folder: every prompt is answered from disk
    msgs = play(again)
    steps = {m["step"] for m in msgs if m["k"] == "log"}
    assert again.budget.used == 0 and "lookup" in steps and "writing" not in steps
    assert any(m["k"] == "say" and m["src"] == "analyst" and m.get("cached") == 1 for m in msgs)
    wrote = next(m for m in msgs if m["k"] == "log" and m["step"] == "analyst_wrote")
    assert wrote["d"]["cached"] and "wall_s" in wrote["d"] and "cache hit" in wrote["msg"]

    fresh = live_cfg(tmp_path)
    fresh.fresh = True
    msgs = play(fresh)
    assert fresh.budget.used == calls and "lookup" not in {m["step"] for m in msgs if m["k"] == "log"}
    assert not any(m.get("cached") for m in msgs if m["k"] == "say")


def test_trim_catch_up_keeps_only_the_newest_catch_up_frames():
    from matchvoice.pipeline.export import trim_catch_up
    msgs = [{"k": "f", "t": float(t)} for t in range(10)] + [{"k": "say", "t": 3.0}, {"k": "f", "t": 12.0}, {"k": "log", "t": 5.0}]
    out = trim_catch_up(msgs, start=10.0, kept=2)
    assert [m["t"] for m in out if m["k"] == "f"] == [8.0, 9.0, 12.0]
    assert [m["k"] for m in out if m["k"] != "f"] == ["say", "log"]  # only frames are dropped
