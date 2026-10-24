import asyncio
import json
import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from matchvoice.commentary.analyst import KEYS
from matchvoice.mcp_server import tools

IDS = tools.library().recorded_ids()
TOOLS = {"list_matches", "match_summary", "key_moments", "commentary_at", "win_probability_curve", "player_stats",
         "verify_sentence"}


def test_list_matches_and_summary():
    rows = tools.list_matches()
    assert [r["id"] for r in rows if r["replay"]] == IDS
    full = tools.match_summary("comeback-7")
    assert full["at"]["score"]["text"] == "Tamsworth United 2-1 Marlow Bay United"
    mid = tools.match_summary("comeback-7", 1000)
    assert mid["at"]["score"]["away"] == 1 and mid["at"]["t"] <= 1000


def test_key_moments_are_ordered_facts_with_evidence():
    facts = tools.key_moments("comeback-7")
    assert [f["t"] for f in facts] == sorted(f["t"] for f in facts)
    goals = [f for f in facts if f["kind"] == "goal"]
    assert len(goals) == 3 and goals[0]["data"]["score"] == "0-1" and all(f["evidence"] for f in goals)
    assert all(f["importance"] >= 0.3 or f["kind"] == "goal" for f in facts)


@pytest.mark.parametrize("lang,style", [("en", "expert"), ("de", "beginner"), ("fr", "expert")])
def test_commentary_at_a_goal_speaks_in_the_channel_language(lang, style):
    out = tools.commentary_at("comeback-7", 792.0, lang, style)
    line = out["line"]
    assert line["kind"] == "shot_goal" and line["s"] <= 792.0 <= line["e"] + 6
    assert line["text"] and tools.verify_sentence("comeback-7", 792.0, line["text"], lang)["ok"]


def test_commentary_at_reports_silence_between_lines():
    lines = tools._lines("comeback-7", 1.0)[KEYS.index("en/expert")]
    a, b = next((a, b) for a, b in zip(lines, lines[1:]) if b["s"] - a["e"] > 20)
    t = (a["e"] + b["s"]) / 2
    out = tools.commentary_at("comeback-7", t, "en", "expert")
    assert out["speaking"] is False and out["silence_s"] > 10 and out["line"]["m"] == a["m"]


def test_win_probability_curve_is_a_distribution():
    curve = tools.win_probability_curve("red_card-7", 120.0)
    assert curve["columns"] == ["t", "home", "draw", "away"]
    assert all(abs(sum(r[1:]) - 1) < 0.01 for r in curve["rows"])
    assert all(b[0] - a[0] >= 30 for a, b in zip(curve["rows"][:-1], curve["rows"][1:-1]))  # the last row is the final whistle


def test_player_stats_resolve_by_id_name_and_surname():
    by_id = tools.player_stats("comeback-7", "A10")
    assert by_id["name"] == "Marek Lemaire" and by_id["goals"] == 1
    assert tools.player_stats("comeback-7", "lemaire")["id"] == "A10"
    assert tools.player_stats("comeback-7", "Marek Lemaire", 100)["goals"] == 0  # before the goal


def test_verify_sentence_flags_a_swapped_score_and_an_invented_number():
    bad = tools.verify_sentence("comeback-7", 795.0, "Lemaire scores and it is 1-0 now.", "en")
    assert not bad["ok"] and bad["violations"][0]["code"] == "score_swapped"
    assert tools.verify_sentence("comeback-7", 795.0, "Lemaire scores and it is 0-1 now.", "en")["ok"]
    wrong = tools.verify_sentence("comeback-7", 795.0, "Marlow Bay United have taken 31 shots already.", "en")
    assert any(v["code"] == "number_unsupported" for v in wrong["violations"])


@pytest.mark.parametrize("call", [
    lambda: tools.match_summary("nope"),
    lambda: tools.match_summary("comeback-7", 99999),
    lambda: tools.commentary_at("comeback-7", 10, "es", "expert"),
    lambda: tools.player_stats("comeback-7", "Nobody Here"),
    lambda: tools.verify_sentence("comeback-7", 10, "x", "xx"),
])
def test_bad_input_is_a_value_error(call):
    with pytest.raises(ValueError):
        call()


# ---------- over stdio, as a real client does it ----------
def test_stdio_server_lists_tools_and_answers_a_call_without_a_key():
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC")}
    env["MATCHVOICE_NO_DOTENV"] = "1"
    params = StdioServerParameters(command=sys.executable, args=["-m", "matchvoice.mcp_server"], env=env)

    async def go():
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            summary = await session.call_tool("match_summary", {"match": "unlucky-7"})
            line = await session.call_tool("commentary_at", {"match": "comeback-7", "t": 792, "lang": "fr", "style": "beginner"})
            bad = await session.call_tool("match_summary", {"match": "nope"})
            return listed, summary, line, bad

    listed, summary, line, bad = asyncio.run(asyncio.wait_for(go(), 60))
    assert {t.name for t in listed.tools} == TOOLS and all(t.description for t in listed.tools)
    assert not summary.isError and json.loads(summary.content[0].text)["id"] == "unlucky-7"
    assert json.loads(line.content[0].text)["line"]["kind"] == "shot_goal"
    assert bad.isError and "unknown match" in bad.content[0].text
