"""MCP server over stdio: the match tools of tools.py for any MCP client (Claude Desktop, Claude Code, ...)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import tools

mcp = FastMCP(
    "match-voice",
    instructions=("Synthetic football matches with a fact engine and multilingual commentary (en, de, fr; beginner, expert). "
                  "Times are match seconds since kick-off, half-time excluded. Start with list_matches. All data is fictional."),
)

for fn in (tools.list_matches, tools.match_summary, tools.key_moments, tools.commentary_at,
           tools.win_probability_curve, tools.player_stats, tools.verify_sentence):
    mcp.tool()(fn)
