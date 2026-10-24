import json

import pytest
from starlette.testclient import TestClient

from matchvoice.commentary.analyst import CallBudget
from matchvoice.pipeline.runner import LiveConfig, LiveUnavailable
from matchvoice.server.app import create_app
from test_pipeline import IDS, fake_llm

QUERY = "match=comeback-7&mode=replay&speed=30&paced=false"


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(ui_dist=None)) as c:
        yield c


def ws_messages(client: TestClient, query: str) -> list[dict]:
    out = []
    with client.websocket_connect(f"/ws?{query}") as ws:
        while True:
            msg = ws.receive_json()
            out.append(msg)
            if msg["k"] in ("end", "error"):
                return out


def test_match_list_and_meta(client):
    rows = client.get("/api/matches").json()
    assert [r["id"] for r in rows if r["replay"]] == IDS and all(len(r["final"]) == 2 for r in rows)
    one = client.get("/api/matches/comeback-7").json()
    assert one["hello"]["k"] == "hello" and len(one["hello"]["channels"]) == 6 and one["final"] == [2, 1]
    assert client.get("/api/matches/nope").status_code == 404
    assert client.get("/api/matches/..%2F..%2Fetc").status_code == 404


def test_health_reports_live_state(client):
    body = client.get("/api/health").json()
    assert body["replay"] is True and body["live"]["available"] is False and body["live"]["reason"]
    assert set(body["live"]) == {"available", "code", "reason", "calls_left", "fresh", "runs_left", "runs_per_day", "max_seconds"}


def test_websocket_replay_streams_frames_say_and_log(client):
    msgs = ws_messages(client, QUERY)
    kinds = [m["k"] for m in msgs]
    assert kinds[0] == "hello" and kinds[-1] == "end" and {"f", "say", "log"} <= set(kinds)


def test_websocket_stream_equals_the_static_export(client):
    stream = ws_messages(client, QUERY)
    export = client.get("/api/matches/comeback-7/replay.json?speed=30").json()
    assert export["hello"] == stream[0] and export["messages"] == stream[1:] and export["speed"] == 30


def test_replay_json_is_cached_gzipped_and_checks_its_input(client):
    r = client.get("/api/matches/unlucky-7/replay.json", headers={"accept-encoding": "gzip"})
    assert r.status_code == 200 and r.headers["content-encoding"] == "gzip"
    assert client.get("/api/matches/unlucky-7/replay.json?speed=0").status_code == 400
    assert client.get("/api/matches/nope/replay.json").status_code == 404


@pytest.mark.parametrize("query,code", [("match=nope&mode=replay", "not_found"),
                                        ("match=comeback-7&speed=100000", "bad_request"),
                                        ("match=comeback-7&mode=live", "no_budget"),
                                        ("match=comeback-7&mode=foo", "bad_request"),
                                        ("match=comeback-7&speed=abc", "bad_request"),
                                        ("mode=replay", "bad_request")])
def test_websocket_errors_are_messages_then_a_close(client, query, code):
    with client.websocket_connect(f"/ws?{query}") as ws:
        msg = ws.receive_json()
        assert msg["k"] == "error" and msg["code"] == code and msg["message"]


def test_live_over_websocket_with_a_budgeted_fake_model(tmp_path):
    cfg = LiveConfig(fake_llm(), CallBudget(30), "fake", tmp_path)
    with TestClient(create_app(live=cfg)) as c:
        assert c.get("/api/health").json()["live"]["available"] is True
        msgs = ws_messages(c, "match=comeback-7&mode=live&speed=60&paced=false")
        assert msgs[0]["mode"] == "live" and msgs[-1]["calls"] == cfg.budget.used > 0
        assert any(m["k"] == "say" and m["src"] == "analyst" for m in msgs)


def test_live_refusal_has_a_reason():
    err = LiveUnavailable("no_key", "live mode needs an Anthropic API key, none is configured")
    with TestClient(create_app(live_error=err)) as c:
        assert c.get("/api/health").json()["live"]["reason"] == str(err)
        msgs = ws_messages(c, "match=comeback-7&mode=live")
        assert msgs == [{"k": "error", "code": "no_key", "message": str(err)}]
        r = c.get("/sse?match=comeback-7&mode=live")
        assert r.status_code == 409 and r.json()["detail"]["code"] == "no_key"


def test_sse_fallback_carries_the_same_messages(client):
    events = []
    with client.stream("GET", f"/sse?{QUERY}") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        name = None
        for line in r.iter_lines():
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                events.append((name, json.loads(line.split(":", 1)[1])))
    assert events[0][0] == "hello" and events[-1][0] == "end"
    assert [m for _, m in events] == ws_messages(client, QUERY)


def test_serves_the_built_ui_when_present(tmp_path):
    (tmp_path / "index.html").write_text("<title>ui</title>")
    with TestClient(create_app(ui_dist=tmp_path)) as c:
        assert "<title>ui</title>" in c.get("/").text and c.get("/api/matches").status_code == 200
    with TestClient(create_app(ui_dist=tmp_path / "missing")) as c:
        assert c.get("/").json()["ui"].startswith("not built")


@pytest.mark.parametrize("query", ["match=comeback-7&mode=foo", "match=comeback-7&speed=abc", "speed=30"])
def test_sse_errors_use_the_protocol_shape(client, query):
    r = client.get(f"/sse?{query}")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_request"


def test_spent_budget_is_reported_and_refuses_new_live_runs(tmp_path):
    cfg = LiveConfig(fake_llm(), CallBudget(2, used=2), "fake", tmp_path)
    with TestClient(create_app(live=cfg)) as c:
        live = c.get("/api/health").json()["live"]
        assert live["available"] is False and live["code"] == "no_budget" and live["calls_left"] == 0
        assert c.get("/sse?match=comeback-7&mode=live").status_code == 409


def test_start_is_validated_and_only_for_live():
    with TestClient(create_app(ui_dist=None)) as c:
        for q in ("match=comeback-7&mode=replay&start=100", "match=comeback-7&mode=live&start=abc", "match=comeback-7&mode=live&start=-5"):
            assert ws_messages(c, q)[0]["code"] == "bad_request"
