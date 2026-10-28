"""Live captions are separate from the voice: a line is shown the moment it arrives, only the voice queues or skips."""
import asyncio

from starlette.testclient import TestClient

from matchvoice.commentary.analyst import KEYS, CallBudget, GuardedLLM
from matchvoice.commentary.director import ChannelDirector
from matchvoice.commentary.moments import Moment
from matchvoice.commentary.newsroom import Published
from matchvoice.pipeline import protocol as proto
from matchvoice.pipeline.runner import LIVE_PBP_TTL_S, LiveConfig, Runner
from matchvoice.server.app import create_app
from test_pipeline import LIB, fake_llm, head, live_cfg, run
from test_server import ws_messages


async def until(stream, t_stop: float) -> list[dict]:
    """Messages up to match time `t_stop`: what comes after is only the voice finishing its backlog."""
    out = []
    async for msg in stream:
        out.append(msg)
        if msg["t"] >= t_stop:
            break
    await stream.aclose()
    return out


def pbp(i: int, t: float, prio: int = 45, ttl: float = 8.0, kind: str = "corner") -> Moment:
    return Moment(i, t, "1", kind, "pbp", prio, ttl, {})


def director(speed: float = 1.0, wait: float = 3.0) -> ChannelDirector:
    return ChannelDirector(lambda m: ["A short one.", "A somewhat longer line of commentary."], "en", speed,
                           captions_first=True, voice_wait_s=wait)


def notes(d: ChannelDirector, kinds: tuple[str, ...] = ("caption", "start", "cut", "skip")):
    return [(k, sp.moment_id, round(sp.start, 2)) for k, sp in d.drain() if k in kinds]


# ---------- director ----------
def test_a_busy_voice_delays_the_speech_not_the_caption():
    d = director()
    d.push(pbp(0, 0.0, prio=60))  # speaks about 2.5 s
    d.push(pbp(1, 0.5))  # arrives while it speaks
    d.advance(1.0)
    got = notes(d)
    assert ("caption", 1, 0.5) in got and ("start", 1, 0.5) not in got
    d.advance(10.0)
    assert [(k, m) for k, m, _ in notes(d)] == [("start", 1)]  # spoken once the voice is free


def test_a_line_waiting_longer_than_the_limit_is_skipped_never_spoken():
    d = director(wait=1.0)
    d.push(pbp(0, 0.0, prio=60, ttl=30))
    d.push(pbp(1, 0.5, ttl=30))
    d.advance(20.0)
    got = notes(d)
    assert ("caption", 1, 0.5) in got and any(k == "skip" and m == 1 for k, m, _ in got)
    assert not any(k == "start" and m == 1 for k, m, _ in got)
    assert [s.moment_id for s in d.out] == [0]


def test_voice_never_starts_later_than_the_limit_after_the_caption():
    d = director(speed=10.0, wait=3.0)
    for i in range(40):
        d.push(pbp(i, i * 1.5, prio=30 + i % 30, ttl=60))
    d.advance(1e6)
    caption = {}
    for kind, sp in d.drain():
        if kind == "caption":
            caption[sp.moment_id] = sp.start
        if kind == "start":
            assert sp.start - caption[sp.moment_id] <= 3.0 * 10.0 + 1e-6
    assert d.dropped, "the backlog forced skips"


def test_urgent_moments_wait_for_the_voice_as_long_as_they_must():
    d = director(wait=0.5)
    d.push(pbp(0, 0.0, prio=95, ttl=30, kind="red"))
    d.push(pbp(1, 0.2, prio=100, ttl=30, kind="shot_goal"))  # cannot interrupt a 95
    d.advance(60.0)
    assert [s.moment_id for s in d.out] == [0, 1] and not [k for k, _ in d.drain() if k == "skip"]


def test_a_late_arrival_is_not_captioned_and_an_interrupt_cuts_the_voice():
    d = director()
    d.push(pbp(0, 0.0, prio=50, ttl=30))
    d.push(pbp(1, 1.0, prio=100, ttl=30, kind="shot_goal"))
    late = pbp(2, 0.0, ttl=2.0)
    late.ready_t = 5.0  # worth saying for 2 s, ready after 5
    d.push(late)
    d.advance(10.0)
    got = d.drain()
    cuts = [sp for k, sp in got if k == "cut"]
    assert [(sp.moment_id, sp.end) for sp in cuts] == [(0, 1.0)]
    assert [sp.moment_id for k, sp in got if k == "caption"] == [0, 1]  # nothing for the stale one
    assert [(x.moment_id, x.reason) for x in d.dropped] == [(2, "stale")]


def test_replay_directors_are_unchanged():
    d = ChannelDirector(lambda m: ["Corner."], "en", 1.0)
    d.push(pbp(0, 0.0))
    d.advance(10.0)
    assert [k for k, _ in d.drain()] == ["start"]


# ---------- runner ----------
def test_live_template_captions_do_not_wait_for_the_voice(tmp_path):
    cfg = live_cfg(tmp_path, delay=0.2)

    async def collect() -> list[dict]:
        return await until(Runner(head(LIB.bundle("comeback-7"), 2400.0), "live", 300.0, paced=True,
                                  live=cfg, start=1500.0).stream(), 3600.0)

    msgs = asyncio.run(collect())
    says = [m for m in msgs if m["k"] == "say" and m["voice"] == "pbp"]
    voices = [m for m in msgs if m["k"] == "voice"]
    assert says and max(m["lat"] for m in says) < 0.35  # event to caption, whatever the voice is doing
    assert any(m.get("skip") for m in voices) and any(not m.get("skip") and not m.get("cut") for m in voices)
    captions = {(m["ch"], m["m"]): m for m in says}
    for v in voices:
        if v.get("skip") or v.get("cut") or (v["ch"], v["m"]) not in captions:
            continue
        assert v["w"] - captions[(v["ch"], v["m"])]["w"] <= 3.0 + 0.5  # the voice stays within its limit of the caption
    assert all(m["s"] == m["e"] or m["e"] > m["s"] for m in says)


def test_an_analyst_caption_appears_when_the_line_is_ready_not_when_the_voice_is_free(tmp_path):
    cfg = live_cfg(tmp_path, delay=0.6)

    async def collect() -> list[dict]:
        return await until(Runner(head(LIB.bundle("comeback-7"), 900.0), "live", 400.0, paced=True,
                                  live=cfg, start=760.0).stream(), 1500.0)

    msgs = asyncio.run(collect())
    ready = {m["m"]: m["w"] for m in msgs if m["k"] == "log" and m["step"] == "ready"}
    caps = [m for m in msgs if m["k"] == "say" and m["voice"] == "analyst" and m["m"] in ready]
    assert caps and all(0.0 <= c["w"] - ready[c["m"]] < 0.3 for c in caps)


def test_template_stand_ins_for_the_analyst_go_stale_like_play_by_play(tmp_path):
    r = Runner(LIB.bundle("comeback-7"), "live", 10.0, paced=False, live=live_cfg(tmp_path))
    m = Moment(5, 100.0, "2", "momentum", "analyst", 55, 40.0, {})
    lines = {k: ["t1", "t2"] for k in KEYS}
    r.pubs[5] = Published(5, lines, {k: ("analyst" if k == "en/expert" else "template") for k in KEYS}, [], 0.0)
    r._push(m)
    ttl = {k: d._arrivals[0].ttl for k, d in zip(KEYS, r._dirs)}
    assert ttl["en/expert"] == 40.0 and all(v == LIVE_PBP_TTL_S for k, v in ttl.items() if k != "en/expert")
    assert m.ttl == 40.0
    milestone = Moment(6, 100.0, "2", "shot_milestone", "analyst", 35, 20.0, {})
    asyncio.run(r._on_moment(milestone, None, 100.0))  # type: ignore[arg-type]
    assert milestone.ttl == LIVE_PBP_TTL_S


def test_unpaced_live_and_replay_keep_their_message_kinds(tmp_path):
    live = run(Runner(head(LIB.bundle("comeback-7"), 1500.0), "live", 10.0, paced=False, live=live_cfg(tmp_path)))
    assert {"hello", "f", "say", "voice", "log", "end"} >= {m["k"] for m in live}
    assert live[-1]["says"] == sum(1 for m in live if m["k"] == "say")
    assert not any(m["k"] == "say" and m["cut"] for m in live)


def test_voice_message_shape():
    assert proto.voice(1.234, 2, 7, 1.0, 4.0, w=0.5, lat=0.25) == {"k": "voice", "t": 1.23, "ch": 2, "m": 7, "s": 1.0, "e": 4.0,
                                                                     "w": 0.5, "lat": 0.25}
    assert proto.voice(1.0, 0, 1, 1.0, 1.0, skip=True)["skip"] == 1 and proto.voice(1.0, 0, 1, 0.0, 1.0, cut=True)["cut"] == 1


# ---------- a restarted stream does not pay twice ----------
def test_a_call_under_way_is_shared_and_survives_its_caller(tmp_path):
    calls = []

    async def slow(prompt: str) -> str:
        calls.append(prompt)
        await asyncio.sleep(0.2)
        return '{"en/expert": "x"}'

    async def go() -> None:
        shared: dict = {}
        budget = CallBudget(5)
        a = GuardedLLM(slow, budget, "fake", tmp_path, inflight=shared)
        b = GuardedLLM(slow, budget, "fake", tmp_path, inflight=shared)
        first = asyncio.create_task(a("same prompt"))
        await asyncio.sleep(0.05)
        first.cancel()  # the stream that asked went away
        assert await b("same prompt") == '{"en/expert": "x"}'
        assert len(calls) == 1 and budget.used == 1
        assert await GuardedLLM(slow, budget, "fake", tmp_path)("same prompt") and len(calls) == 1  # now it is cached
        assert not shared

    asyncio.run(go())


def test_a_restart_picks_up_the_moments_still_being_written_without_a_second_call(tmp_path):
    calls = []

    async def slow(prompt: str) -> str:
        calls.append(prompt)
        await asyncio.sleep(0.5)
        return await fake_llm()(prompt)

    cfg = LiveConfig(slow, CallBudget(50), "fake", tmp_path)
    bundle = head(LIB.bundle("comeback-7"), 900.0)

    async def go() -> tuple[list[dict], list[dict]]:
        first, second = Runner(bundle, "live", 400.0, paced=True, live=cfg), None
        out1, out2 = [], []
        stream = first.stream()
        async for msg in stream:
            out1.append(msg)
            if msg["k"] == "log" and msg["step"] == "writing":
                break
        await stream.aclose()  # the viewer changed the speed: the stream goes away with a call under way
        pending = {m["m"] for m in out1 if m["k"] == "log" and m["step"] == "queued"} - {
            m["m"] for m in out1 if m["k"] == "log" and m["step"] == "ready"}
        at = max(m["t"] for m in out1) + 0.1  # a client resumes just after the newest frame, so no event repeats
        second = Runner(bundle, "live", 300.0, paced=True, live=cfg, start=at, analyst_from=0.0)
        out2 = await until(second.stream(), 1500.0)
        assert pending
        return out1, out2

    out1, out2 = asyncio.run(go())
    queued = {m["m"] for m in out1 if m["k"] == "log" and m["step"] == "queued"}
    again = {m["m"] for m in out2 if m["k"] == "log" and m["step"] in ("writing", "lookup")}
    assert queued & again, "the new stream asks for the moment the old one was writing"
    assert not any(m["k"] == "log" and m["step"] == "queued" and m["m"] in queued for m in out2)  # no second 'queued' line
    assert len(calls) == len(set(calls)), "no prompt was sent to the model twice"
    carried = [m for m in out2 if m["k"] == "say" and m["m"] in queued]
    assert carried and all("lat" not in m for m in carried)  # the event happened in the old stream, no latency to claim
    early = [m for m in out2 if m["k"] == "say" and m["voice"] == "pbp" and m["s"] < out2[0]["start"]]
    assert not early, early[:3]


def test_analyst_from_is_validated():
    with TestClient(create_app(ui_dist=None)) as c:
        for q in ("match=comeback-7&mode=live&start=100&analyst_from=200", "match=comeback-7&mode=live&start=100&analyst_from=x",
                  "match=comeback-7&mode=live&analyst_from=-1"):
            assert ws_messages(c, q)[0]["code"] in ("bad_request", "no_budget")
        assert ws_messages(c, "match=comeback-7&mode=replay&analyst_from=0")[0]["code"] == "bad_request"


def test_slot_avoidance_never_filters_the_model_line():
    """Two goal_analysis moments in a row, each with templates plus a model line last: the model line is never dropped for its slot."""
    lines = {0: ["t one", "t two", "t three", "model line zero"], 1: ["t one", "t two", "t three", "model line one"]}
    d = ChannelDirector(lambda m: lines[m.id], "en", 1.0, captions_first=True, has_model_line=lambda m: True)
    for i, t in enumerate((0.0, 200.0)):
        d.push(Moment(i, t, "1", "goal_analysis", "analyst", 60, 300, {}))
    d.advance(1000.0)
    caps = [sp.text for k, sp in d.drain() if k == "caption"]
    assert caps == ["model line zero", "model line one"]


def test_slot_avoidance_still_applies_to_templates():
    d = ChannelDirector(lambda m: ["t one", "t two", "t three"], "en", 1.0, captions_first=True)
    for i, t in enumerate((0.0, 200.0)):
        d.push(Moment(i, t, "1", "corner", "pbp", 60, 300, {}))
    d.advance(1000.0)
    caps = [sp.text for k, sp in d.drain() if k == "caption"]
    assert len(caps) == 2 and caps[0] != caps[1]
