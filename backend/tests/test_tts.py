"""Spoken commentary: budget, cache, ledger, the line-only endpoint, the key. Zero network: a fake synthesiser stands in for ElevenLabs."""
import asyncio
import logging

import httpx
import pytest
from starlette.testclient import TestClient

from matchvoice.commentary.analyst import CallBudget
from matchvoice.pipeline.demo import demo_insert
from matchvoice.pipeline.library import Library
from matchvoice.pipeline.runner import LiveConfig, Runner
from matchvoice.server.app import create_app
from matchvoice.tts import CREDITS_PER_CHAR, MODEL, GuardedTTS, TTSBudgetExceeded, TTSError
from matchvoice.tts import client as tts_client
from matchvoice.tts.fake import FAKE_MP3, FakeSynth
from test_pipeline import fake_llm
from test_server import ws_messages

SENTINEL = "xi-SECRET-SENTINEL-0123456789"
LINE = "Okafor finds Becker-Lyle in the final third."  # 44 characters, 22 credits


def guarded(tmp_path, credits=300, synth=None) -> tuple[GuardedTTS, FakeSynth]:
    fake = synth or FakeSynth()
    return GuardedTTS(fake, credits, MODEL, tmp_path / "tts"), fake


def run(coro):
    return asyncio.run(coro)


def test_factor_lives_in_one_constant():
    assert CREDITS_PER_CHAR[MODEL] == 0.5


def test_a_line_is_billed_once_then_served_from_the_disk_cache(tmp_path):
    t, fake = guarded(tmp_path)
    audio, hit = run(t.speak(LINE, "en"))
    assert not hit and audio.startswith(FAKE_MP3) and t.spent == 22 and len(fake.calls) == 1
    audio2, hit2 = run(t.speak(LINE, "en"))
    assert hit2 and audio2 == audio and t.spent == 22 and len(fake.calls) == 1  # a cache hit costs nothing and calls nothing
    t2, fake2 = guarded(tmp_path)  # a new process sees the same cache and the same ledger
    assert run(t2.speak(LINE, "en"))[1] and t2.spent == 22 and not fake2.calls


def test_the_cache_key_includes_the_language(tmp_path):
    t, fake = guarded(tmp_path)
    run(t.speak(LINE, "en"))
    run(t.speak(LINE, "de"))
    assert len(fake.calls) == 2 and t.spent == 44


def test_over_budget_is_refused_before_any_request_and_never_spends_partially(tmp_path):
    t, fake = guarded(tmp_path, credits=30)
    run(t.speak(LINE, "en"))  # 22 of 30
    with pytest.raises(TTSBudgetExceeded):
        run(t.speak("A second line that needs about as much.", "en"))  # 20 credits, 8 left
    assert len(fake.calls) == 1 and t.spent == 22 and t.remaining == 8
    assert t.status()["available"] is True
    run(t.speak("Short.", "en"))  # 3 credits still fit
    assert t.spent == 25


def test_a_spent_budget_reports_unavailable_and_survives_a_restart(tmp_path):
    t, _ = guarded(tmp_path, credits=22)
    run(t.speak(LINE, "en"))
    assert t.status()["available"] is False and t.remaining == 0
    t2, fake2 = guarded(tmp_path, credits=22)  # the ledger is the memory, a restart does not refill it
    assert t2.remaining == 0
    with pytest.raises(TTSBudgetExceeded):
        run(t2.speak("Another line.", "en"))
    assert not fake2.calls


def test_a_failed_request_costs_nothing_and_is_not_cached(tmp_path):
    t, fake = guarded(tmp_path, synth=FakeSynth(fail=True))
    with pytest.raises(TTSError):
        run(t.speak(LINE, "en"))
    assert t.spent == 0 and t.remaining == 300 and not t.cached(LINE, "en") and len(fake.calls) == 1


def test_two_requests_for_the_same_new_line_pay_once(tmp_path):
    t, fake = guarded(tmp_path)

    async def both():
        return await asyncio.gather(t.speak(LINE, "en"), t.speak(LINE, "en"))
    a, b = run(both())
    assert a[0] == b[0] and len(fake.calls) == 1 and t.spent == 22


@pytest.mark.parametrize("text", ["", "   ", "x" * 221])
def test_empty_and_overlong_text_is_refused(tmp_path, text):
    t, fake = guarded(tmp_path)
    with pytest.raises(TTSError):
        run(t.speak(text, "en"))
    assert not fake.calls


# ---------- the key ----------
def test_the_client_never_puts_the_key_in_an_error(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers.get("xi-api-key")
        return httpx.Response(401, json={"detail": f"bad key {SENTINEL}"})  # even an upstream body that echoes it is not repeated
    real = httpx.AsyncClient
    monkeypatch.setattr(tts_client.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    c = tts_client.ElevenLabsClient(SENTINEL)
    with pytest.raises(tts_client.UpstreamError) as err:
        run(c.synth(LINE, "voice", "en"))
    assert seen["key"] == SENTINEL and SENTINEL not in str(err.value) and "401" in str(err.value)


def test_the_client_parses_the_mp3_and_the_reported_cost(monkeypatch):
    real = httpx.AsyncClient
    handler = lambda request: httpx.Response(200, content=b"ID3mp3", headers={"character-cost": "22"})  # noqa: E731
    monkeypatch.setattr(tts_client.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    assert run(tts_client.ElevenLabsClient(SENTINEL).synth(LINE, "voice", "en")) == (b"ID3mp3", 22.0)


# ---------- the server ----------
def live_app(tmp_path, tts):
    cfg = LiveConfig(fake_llm(), CallBudget(30), "fake", tmp_path / "analyst")
    return create_app(live=cfg, tts=tts)


def a_line(msgs):
    say = next(m for m in msgs if m["k"] == "say" and m["ch"] == 1 and m["src"] == "template")
    return msgs[0]["run"], say


def test_health_reports_the_voice_without_a_key(tmp_path):
    t, _ = guarded(tmp_path)
    with TestClient(live_app(tmp_path, t)) as c:
        v = c.get("/api/health").json()["tts"]
        assert v["available"] is True and v["voice"] == "ElevenLabs" and v["credits_left"] == 300 and v["credits_max"] == 300
        assert SENTINEL not in c.get("/api/health").text
    with TestClient(create_app()) as c:  # no key: the browser voice
        v = c.get("/api/health").json()["tts"]
        assert v["available"] is False and v["reason"] and v["credits_left"] is None
        assert c.get("/api/tts?run=x&ch=1&m=1").status_code == 503


def test_only_lines_the_server_published_can_be_synthesised(tmp_path):
    t, fake = guarded(tmp_path)
    with TestClient(live_app(tmp_path, t)) as c:
        msgs = ws_messages(c, "match=comeback-7&mode=live&speed=60&paced=false&start=700&until=900")
        run_id, say = a_line(msgs)
        ok = c.get(f"/api/tts?run={run_id}&ch={say['ch']}&m={say['m']}")
        assert ok.status_code == 200 and ok.headers["content-type"] == "audio/mpeg"
        assert ok.content == FAKE_MP3 + say["text"].encode() and ok.headers["x-voice-cached"] == "0"
        again = c.get(f"/api/tts?run={run_id}&ch={say['ch']}&m={say['m']}")
        assert again.headers["x-voice-cached"] == "1" and len(fake.calls) == 1
        spent = t.spent
        for q in ("run=nope&ch=1&m=1", f"run={run_id}&ch=1&m=999999", f"run={run_id}&ch=x&m=1", f"run={run_id}", "",
                  f"run={run_id}&ch={say['ch']}&m={say['m']}&text=Say%20anything%20at%20all"):
            r = c.get(f"/api/tts?{q}")
            if "text=" in q:  # an extra parameter is ignored: the text is still the published one
                assert r.content == FAKE_MP3 + say["text"].encode()
            else:
                assert r.status_code == 404 and r.json()["detail"]["code"] == "unknown_line"
        assert len(fake.calls) == 1 and t.spent == spent
        assert [x[0] for x in fake.calls] == [say["text"]]


def test_a_replay_run_has_no_voice_lines(tmp_path):
    t, fake = guarded(tmp_path)
    with TestClient(live_app(tmp_path, t)) as c:
        msgs = ws_messages(c, "match=comeback-7&mode=replay&speed=30&paced=false")
        assert "run" not in msgs[0] and "until" not in msgs[0]
        assert c.get("/api/tts?run=anything&ch=1&m=1").status_code == 404 and not fake.calls


def test_over_budget_over_http_is_402_and_health_flips_to_the_browser_voice(tmp_path):
    t, fake = guarded(tmp_path, credits=10)
    with TestClient(live_app(tmp_path, t)) as c:
        msgs = ws_messages(c, "match=comeback-7&mode=live&speed=60&paced=false&start=700&until=900")
        run_id, say = a_line(msgs)
        r = c.get(f"/api/tts?run={run_id}&ch={say['ch']}&m={say['m']}")
        assert r.status_code == 402 and r.json()["detail"]["code"] == "tts_over_budget" and not fake.calls
        h = c.get("/api/health").json()["tts"]
        assert h["available"] is True and h["credits_left"] == 10  # nothing was spent, the client falls back for this line


def test_an_upstream_failure_is_502_without_the_key_in_body_or_logs(tmp_path, caplog):
    t, _ = guarded(tmp_path, synth=FakeSynth(fail=True))
    caplog.set_level(logging.DEBUG)
    with TestClient(live_app(tmp_path, t)) as c:
        msgs = ws_messages(c, "match=comeback-7&mode=live&speed=60&paced=false&start=700&until=900")
        run_id, say = a_line(msgs)
        r = c.get(f"/api/tts?run={run_id}&ch={say['ch']}&m={say['m']}")
        assert r.status_code == 502 and SENTINEL not in r.text and r.json()["detail"]["code"] == "tts_unavailable"
        assert t.spent == 0 and c.get("/api/health").json()["tts"]["credits_left"] == 300
    assert SENTINEL not in caplog.text
    assert not any(SENTINEL in p.read_text(errors="ignore") for p in (tmp_path / "tts").iterdir())


# ---------- fresh matches and the demo insert ----------
def test_a_fresh_match_is_simulated_on_request_and_is_repeatable():
    lib = Library()
    a, b = lib.bundle("red_card-4242"), Library().bundle("red_card-4242")
    assert a.meta.id == "red_card-4242" and [e.t for e in a.events] == [e.t for e in b.events] and a.recorded is None
    assert lib.bundle("comeback-7").meta.id == "comeback-7"  # a match on disk wins
    for bad in ("nope-1", "comeback-", "comeback-1234567", "../comeback-7", "comeback-7/../x"):
        with pytest.raises(KeyError):
            lib.bundle(bad)


def test_a_fresh_match_streams_over_the_server(tmp_path):
    with TestClient(live_app(tmp_path, None)) as c:
        assert c.get("/api/matches/unlucky-31337").json()["arc"] == "unlucky"
        assert c.get("/api/matches/unlucky-31337").json()["hello"]["match"]["id"] == "unlucky-31337"
        assert c.get("/api/matches/unlucky-").status_code == 404


def test_until_ends_a_live_insert_and_is_validated(tmp_path):
    with TestClient(live_app(tmp_path, None)) as c:
        msgs = ws_messages(c, "match=comeback-7&mode=live&speed=60&paced=false&start=700&until=800")
        assert msgs[0]["until"] == 800.0 and msgs[-1]["k"] == "end" and max(m["t"] for m in msgs if m["k"] == "f") <= 800
        for q in ("until=abc", "until=600&start=700", "until=800&mode=replay", "until=999999"):
            q = q if "mode=" in q else q + "&mode=live"
            m = ws_messages(c, f"match=comeback-7&speed=60&paced=false&{q}" + ("" if "start=" in q else "&start=700"))
            assert m[0]["k"] == "error" and m[0]["code"] == "bad_request"


def test_the_demo_insert_has_one_model_moment_and_a_goal_inside_the_window(tmp_path):
    lib = Library()
    d = demo_insert(lib)
    assert d["start"] < d["goal_t"] < d["until"] and d["until"] - d["start"] <= 30
    cfg = LiveConfig(fake_llm(), CallBudget(3), "fake", tmp_path)
    r = Runner(lib.bundle(d["match"]), "live", 1.0, paced=False, live=cfg, start=d["start"], until=d["until"])
    msgs = asyncio.run(r.collect())
    assert msgs[-1]["calls"] == 1  # the goal analysis is the only call in the window
    assert any(m["k"] == "voice" and m.get("cut") for m in msgs)  # the goal interrupts the line that is talking
