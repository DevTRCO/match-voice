# Build plan: from tested core to final prototype

Deadline: submission closes 2026-10-27 23:59 PT. Today is 2026-10-20.
Method: Sonnet builds, Opus reviews, Sonnet fixes, Opus re-checks. Every phase ends with a hard gate.

## Phase 1: Pipeline runner, overlay protocol, FastAPI server
Closes "Next 1" in CLAUDE.md.
- Fix the known issue first: tell the analyst that scores are always home-away, bump `PROMPT_VERSION`.
- `backend/matchvoice/pipeline/`: one runner, two modes.
  - `live`: events -> facts -> moments -> analyst/verifier newsroom (real model calls, guarded) -> director, with a timestamped log.
  - `replay`: same pipeline, analyst lines read from `data/replays/<match>/analyst.json`, no key needed.
- Overlay protocol: compact JSON frames (arrays, numeric codes), same stream for live and replay. Documented in `docs/PROTOCOL.md`.
- FastAPI: match list, meta, WebSocket stream (speed control), SSE fallback, static replay export (`replay.json`) so the public demo works with no server and no key, static file hosting of the built UI.
- Re-record analyst replays for all three arcs. Hard cap: 40 Haiku calls in total, always through `GuardedLLM`.
- Gate: pytest green, WebSocket smoke test, replay needs no key, live mode refuses to start without key and without budget.

## Phase 2: Single-screen UI (parallel with Phase 3)
- Vite + React + TypeScript, dark, Netflix-like, one screen, no scrolling, details in modals.
- Canvas pitch (no React re-render per event), uPlot win-probability chart, language and style switch, live agent log, key-moment rail.
- Voice: browser SpeechSynthesis per language (free, no key). Captions always shown.
- Runs against the server stream and against the static `replay.json`.
- Gate: `npm run build` clean, visual QA in Chrome at 1440x900 and 1920x1080 with screenshots, nothing scrolls, no console errors.

## Phase 3: MCP server and evaluation harness (parallel with Phase 2)
- MCP server (official `mcp` SDK) exposing match tools: list matches, get facts, key moments, commentary at time t in lang/style, verify a sentence.
- Evaluation harness over `truth.json`: grounding rate (verifier pass rate), key-moment coverage, latency, fallback rate, per language and style. Writes `docs/EVAL.md` and a JSON.
- Gate: tests green, harness runs on all three matches without a key.

## Phase 4: Deploy artefacts
- Dockerfile, `azure.md` with the free-tier steps for Azure Container Apps or Static Web Apps, GitHub Actions optional. Nothing is deployed or pushed without the user's go-ahead.
- Static replay build target (`npm run build:static`) that bundles `replay.json`.

## Phase 5: Submission material
- README polish, architecture diagram (Mermaid plus SVG), pitch text against the five judging criteria,
  demo video script under 2 minutes with shot list, screen recording GIF of the real UI.
- Final whole-system Opus review against the rules in CLAUDE.md (no key leaks, no em dashes, fictional data only, no real marks).
- Gate: fresh clone path works (`pip install`, `pytest`, run replay), claims in README match the code.

## Rules for every agent
- English only. No em dashes or filler in user-facing text. Fictional clubs and players only.
- Never print, log or read `.env`; use `matchvoice.config`.
- Model calls only through `GuardedLLM`. Total budget for the whole build: 40 calls.
- Do not commit, push or publish. Keep decisions in CLAUDE.md "Decisions" intact.
- Match the style of the surrounding code. Update CLAUDE.md status at the end of each phase.
