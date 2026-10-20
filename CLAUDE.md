# match-voice: working notes for Claude Code

Entry for the Microsoft x Premier League "Inside the Game: Developer Hackathon".
Submission closes **2026-10-27 23:59 PT**, judging until 2026-11-10. All data is synthetic.

## Goal
Every fan gets their own commentator: real-time football commentary generated from synthetic
match events, in several languages and styles, with every sentence checked against facts.

Pipeline required by the rules: Ingest -> Interpret -> Explain -> Render -> Personalize.
Judging (20% each): technology, agentic design, real-world impact, UX and presentation, category fit.
A project can win one Grand Prize and one Category Prize. Demo video must be under 2 minutes.
Judges may not run the project, so video and description must carry everything.

## Decisions already made (do not reopen without asking)
- Languages: en, de, fr only. Styles: beginner, expert only.
- Agents run on the **Microsoft Agent Framework** (hero technology). Claude is the model behind it
  (`agent-framework-anthropic`). Do not switch to the Claude Agent SDK.
- Two prototypes from ONE pipeline: a **live** run with a visible log, and a **static replay** of a recorded
  run that needs no API key (public demo must work without a key).
- UI: Netflix-like, dark, **one screen, no scrolling**, details open as modals.
- Overlay format must be high performance (compact updates, canvas rendering, no per-event React re-render).
- Prefer open source over custom code.
- Fictional clubs and players only. No real logos, marks or music in the video.

## Working rules
- **All communication in English.**
- Model calls cost money. Say how many calls you expect and get a go-ahead before any batch.
  Always run through `GuardedLLM` (disk cache plus hard `CallBudget`). Never print or log the key.
- The key lives in the git-ignored `.env` (`ANTHROPIC_API_KEY_2`, then `ANTHROPIC_API_KEY`, then `ANTHROPIC_KEY`).
  `.env` is never committed. Do not read it, load it through `matchvoice.config`.
- Do not push, publish or make the repo public without asking.
- No em dashes or AI-sounding filler in user-facing text.

## Layout
```
backend/matchvoice/
  schema.py            event and match schema (pydantic)
  sim/                 synthetic match generator, story arcs (comeback, red_card, unlucky)
  facts/               fact engine: live stats, momentum, win probability, key moments
  commentary/
    templates.py       fast path wording, en/de/fr x beginner/expert
    moments.py         things worth saying, detected from events and facts
    verifier.py        deterministic fact check (numbers, scorelines, players, language, length)
    director.py        speech scheduling under a time budget, interruptions, silence
    analyst.py         slow path prompt, guarded model call, cache, budget
    newsroom.py        Agent Framework workflow: Analyst <-> Verifier loop -> Publisher, template fallback
    precompute.py      run the newsroom over a match and store the replay
backend/tests/         pytest suite
data/matches/          generated demo matches (events.jsonl, meta.json, truth.json)
data/replays/          recorded analyst output for replay mode
```

## Commands
```
python -m pytest -q
python -m matchvoice.sim --arc comeback --seed 7
python -m matchvoice.facts data/matches/comeback-7
python -m matchvoice.commentary.precompute --arc comeback --seed 7 --max-calls 10   # costs money
```

## Status
Done: generator with ground truth, fact engine, templates, moments, verifier, director, newsroom workflow
with retry and fallback, first real run (8 moments, 48 lines, 9 calls, stored in data/replays/comeback-7).

Next, in order:
1. Pipeline runner (live with timestamped log, replay from the recording), overlay format, FastAPI server.
2. Netflix-style single-screen UI (canvas pitch, uPlot win-probability chart, modals).
3. MCP server exposing the match tools, evaluation harness (grounding rate, key-moment coverage, latency).
4. Optional Azure deploy (free tiers), TTS voice.
5. README polish, architecture diagram, pitch text, demo video.

## Known issues
- Tell the model scores are always home-away (it once wrote 1-0 for a 0-1 match). Needs `PROMPT_VERSION` bump
  and a re-run of the analyst pass.
- Bump `PROMPT_VERSION` in `analyst.py` whenever `SYSTEM` or `build_prompt` change; the cache key ignores the system prompt.
- xG is slightly high for point-blank shots. German templates need a native read-through, French has not been checked by a native speaker.
- Real-time speaking time is about 15% with templates alone; more variety from the analyst is expected.
