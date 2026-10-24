# MCP server

The match tools as a Model Context Protocol server, so any MCP client can ask about a match, its commentary and its facts.
It runs over stdio, reads `data/` and the fact engine, and needs no API key: commentary comes from the recorded analyst
lines and the templates. All matches are fictional.

```
source .venv/bin/activate
python -m matchvoice.mcp_server
```

## Claude Desktop

Add this to `claude_desktop_config.json` (Settings, Developer, Edit Config), with the absolute path of your checkout:

```json
{
  "mcpServers": {
    "match-voice": {
      "command": "/absolute/path/to/match-voice/.venv/bin/python",
      "args": ["-m", "matchvoice.mcp_server"]
    }
  }
}
```

Claude Code: `claude mcp add match-voice -- /absolute/path/to/match-voice/.venv/bin/python -m matchvoice.mcp_server`.
Times are match seconds since kick-off, half-time break excluded, as in `docs/PROTOCOL.md`.

## Tools

| Tool | Arguments | Returns |
| --- | --- | --- |
| `list_matches` | none | id, title, arc, teams, final score, duration, replay flag |
| `match_summary` | `match`, `t?` | score, team statistics, win probability and momentum at `t` (full time by default) |
| `key_moments` | `match`, `min_importance?` | facts that moved the match, in time order, with the event ids that prove them. Goals and red cards are always included |
| `commentary_at` | `match`, `t`, `lang`, `style`, `speed?` | the line on air at `t` for that channel, or the last one with the silence since; `src` tells whether the analyst or a template wrote it. `speed` defaults to 1, real time |
| `win_probability_curve` | `match`, `step_s?` | rows of `[t, home, draw, away]`, at least `step_s` apart (default 60, minimum 30) |
| `player_stats` | `match`, `player`, `t?` | passes, shots, xG, goals, tackles, top speed and more; `player` is an id like `H9`, a full name or a surname |
| `verify_sentence` | `match`, `t`, `text`, `lang?` | `ok` and the violations from the pipeline's own verifier (scoreline, numbers, players, language) |

`lang` is `en`, `de` or `fr`; `style` is `beginner` or `expert`. Bad input comes back as a tool error with a message that names the valid values.

## Try it

Ask the client: "Who scored in comeback-7, and is 'Lemaire makes it 1-0' a true sentence at 13:20?"
It should call `key_moments`, then `verify_sentence`, which rejects the sentence because scores are always home-away (the real score is 0-1).

`verify_sentence` allows the scoreline and statistics at `t`, the team names, and the players, shot xG values and minutes of
the last 60 match seconds. A sentence naming anyone else is flagged, even if that player exists. It checks facts, not judgement:
"they dominate" passes if the numbers in it are right.

Tests: `python -m pytest -q backend/tests/test_mcp.py` starts the server as a subprocess and talks to it with the official
stdio client (`tools/list`, then `tools/call`).
