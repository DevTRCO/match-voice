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
- UI: one calm dark screen, no scrolling, no modals. One use case: the demo insert (Phase 10). No match picker, speed, scrubber, stats or log views.
- Overlay format must be high performance (compact updates, canvas rendering, no per-event React re-render).
- Prefer open source over custom code.
- Fictional clubs and players only. No real logos, marks or music in the video.
- ElevenLabs voice is OPTIONAL. The key (`ELEVENLABS_API_KEY`, via `matchvoice.config`) lives server side only; the browser can
  only request lines the server published in a live run. Model `eleven_flash_v2_5` only. The browser SpeechSynthesis voice is the
  always-available fallback (no key, over budget, error, static build) and the UI says which voice is in use.

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
  sim/                 synthetic match generator, story arcs (comeback, red_card, unlucky); profile.py (player attributes, roles, traits, season), tactics.py (base plan, shapes, posture schedule), both written to meta.json
  sim/micro/           event enrichment without tracking (enrich.py: arrival retiming, receipts, gap repair, pass and shot fields; report.py: gate numbers); python -m matchvoice.sim.micro writes data/matches/<id>/enriched.jsonl
  facts/               fact engine: live stats, momentum, win probability, key moments
  commentary/
    templates.py       fast path wording, en/de/fr x beginner/expert, written as a commentator (Phase 11)
    delivery.py        energy_of (calm|rising|peak), ElevenLabs VOICE_SETTINGS per energy, shape_for_tts (pure text shaping); docs/VOICES.md lists voice candidates
    moments.py         things worth saying, detected from events and facts
    verifier.py        deterministic fact check (numbers, scorelines, players, language, length)
    director.py        speech scheduling under a time budget, interruptions, silence; live form (captions_first) captions at arrival, only the voice queues
    analyst.py         slow path prompt, guarded model call, cache, budget
    newsroom.py        Agent Framework workflow: Analyst <-> Verifier loop -> Publisher, template fallback
    fast.py            the fast and context layers (DATA-MODEL 7.1, 7.2): build_layers(meta, events, enriched rows) -> moments with derived ids; the director applies their rules (ChannelDirector(dense=True)); Runner(fast=True) switches them on (off by default)
    precompute.py      run the newsroom over a match and store the replay
  pipeline/
    runner.py          one runner, modes live and replay, paced by wall clock or unpaced, one director per channel
    protocol.py        encoder for the overlay messages (docs/PROTOCOL.md is the contract)
    library.py         finds matches and recorded analyst lines on disk
    export.py          static replay.json export; CLI: python -m matchvoice.pipeline play | export
    guided.py          GET /api/guided-live: random arc + seed, the window (40 s before a goal to 14 s after) with the most action (simulation and fact engine only)
    insights.py        insight logs (agent facts, step insight): win probability swing, pressure phase, shot milestone, live only, no lookahead
  server/              FastAPI app: /api/matches, /ws, /sse, replay.json, serves ui/dist if built
  tts/                 optional ElevenLabs voice: client.py (httpx), guarded.py (GuardedTTS: budget, disk cache, ledger), voices.py (model, credit factor, language to voice table), fake.py
  mcp_server/          MCP server (official mcp SDK, FastMCP, stdio): tools.py plain functions, server.py registration
  evaluation/          harness: metrics.py, run.py (aggregation), report.py (docs/EVAL.md); python -m matchvoice.evaluation; density.py (docs/DENSITY.md, data/eval/density.json); python -m matchvoice.evaluation.density
ui/                    Vite + React + TypeScript single-screen UI (src/sim.ts store, pitch.ts canvas, player.ts guided flow, feed.ts, speech.ts, caption.ts, gamelog.ts event wording, derive.ts agent rows, lanes and evidence); ui/public/insert/replay.json is the recorded demo insert
docs/PROTOCOL.md       overlay protocol v1, the single contract for UI and MCP
docs/MCP.md            MCP tools and the Claude Desktop config snippet
docs/ARCHITECTURE.md, PITCH.md, VIDEO.md, img/   submission material (diagram, form text, video script, screenshots, GIF)
docs/EVAL.md           generated evaluation report (data/eval/results.json is the machine output)
docs/DENSITY.md        generated density report against the broadcast profile (data/eval/density.json), with the phase 3 dry run
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
python -m matchvoice.server --port 8000                     # replay only, no key needed
python -m matchvoice.server --port 8000 --live-calls 12     # live needs a key and this budget; cached answers are reused and marked
python -m matchvoice.server --port 8000 --live-calls 12 --live-max-seconds 75 --live-runs-per-day 150   # the two live limits and their defaults; 0 turns one off
python -m matchvoice.server --port 8000 --live-calls 12 --live-fresh   # no cache reads: every analyst line is a real call (use for the demo video)
python -m matchvoice.pipeline play --match comeback-7 --speed 60 --channel de/expert
python -m matchvoice.pipeline export --out ui/public/replays --speed 30
python -m matchvoice.server --port 8000 --live-calls 3 --tts-credits 300   # ElevenLabs voice if ELEVENLABS_API_KEY is set; --no-tts forces the browser voice
python -m matchvoice.mcp_server                             # MCP over stdio, no key needed
python -m matchvoice.evaluation                             # rewrites data/eval/results.json and docs/EVAL.md, no key, no calls
python -m matchvoice.evaluation.density                     # rewrites data/eval/density.json and docs/DENSITY.md, no key, no calls, about 5 s
MATCHVOICE_NO_DOTENV=1 python -m matchvoice.server          # ignore .env, proves replay needs no key
```

## Status
Done: generator with ground truth, fact engine, templates, moments, verifier, director, newsroom workflow
with retry and fallback.

Phase 1 done (see docs/PLAN.md): pipeline runner (live and replay, paced and unpaced, 6 channels, timestamped
agent log), overlay protocol v1 in docs/PROTOCOL.md, FastAPI server (WebSocket, SSE, replay.json, UI hosting).
Analyst replays re-recorded for all three arcs with `PROMPT_VERSION` v2 (home-away fix): 23 model calls,
144 lines recorded, all by the analyst, no rejections or fallbacks. In a speed-30 replay the director often picks a shorter
template variant to fit, so only 25 of 81 (comeback), 33 of 78 (red_card) and 31 of 74 (unlucky) analyst-voice says carry the model's text. 23 of the 40 build calls are spent, 17 are left. Live mode refuses to
start without a key or without a positive call budget (`--live-calls`, default 0).

Director changes made for the runner: `ChannelDirector` (stepwise, `schedule()` is a wrapper with identical
output), time-to-live is in viewer seconds (times speed), and analysis no longer waits for all play-by-play,
it competes by priority. Without that no analyst line survived at speed 10 or more.

Phase 3 done: MCP server (7 tools, stdio, works without a key, docs/MCP.md) and evaluation harness (replay pipeline,
unpaced, 3 matches x 6 channels at x30 plus a real-time x1 run; no model calls). Real numbers in docs/EVAL.md: 966 lines at x30,
verifier accepts 100% (and catches 99.7 to 100% of injected errors; the one miss is a German genitive, 'Abaras Tor', a verifier gap), the analyst wrote only 9% of spoken lines (41% of analyst-voice
lines), 93.8% of truth moments found (11 of 12; the one miss is comeback-7's home swing, 52 to 90 min, whose nearest momentum moment is 435 s before it), red cards get no
analysis, real-time speech share 14.5%. Still 23 of the 40 build calls spent. `key_moments` always includes goals because the opening
goal of comeback-7 has fact importance 0.284, under the 0.3 threshold.

Phase 2 done: `ui/` (Vite 7, React 19, TypeScript, uPlot, lucide-react, fontsource Barlow Condensed and Schibsted Grotesk).
One screen, no page scroll at 1920x1080, 1440x900 and 1280x720 (checked: scrollHeight equals innerHeight). Replay
plays `replay.json` (server endpoint with `?speed=N`, or the static `replays/<id>/replay.json` written by the export
CLI into `ui/public/replays`); live uses the WebSocket. `?ws=1` plays a replay over the WebSocket instead. The page
auto-detects the server through `/api/health`, otherwise it runs from the static files (speed fixed, Live disabled).
Hot path: `Sim` folds messages into plain fields and arrays, the canvas pitch, the uPlot chart and the DOM hud
(clock, score, momentum, captions, stats) are written from one rAF loop; React only re-renders on rare topics
(match loaded, moments found, transport, agent log). Voice is SpeechSynthesis, captions always show, a cut line stops speech.
Modals (native `<dialog>`): stats and roster, player facts (click a name on the pitch), key moment in all six voices
(rail info button or click on the caption), agent log, how it works. URL params for tooling: `match`, `lang`, `style`,
`speed`, `at` (match seconds), `autoplay`, `mute`, `static`, `ws`. Screenshots in `docs/img/`.
See the Phase 7 entry below for live mode, which is now the UI default.

Phase 4 done: `Dockerfile` (node stage builds the UI, python stage runs the server as a non-root user, no secrets,
replay by default; live only with `ANTHROPIC_API_KEY` plus `MATCHVOICE_LIVE_CALLS`), `.dockerignore`, `docs/DEPLOY.md`
(Static Web Apps for the static build, Container Apps for the server; nothing deployed). `npm run build:static` writes
`ui/dist-static` (mode `static` forces the static backend, replays for all three matches, `staticwebapp.config.json`).
Server CLI now reads `MATCHVOICE_HOST`, `PORT`, `MATCHVOICE_LIVE_CALLS`. Gate passed: docker build and run (no key, live off),
static build served by `python -m http.server` with no backend plays a match in Chrome. No model calls spent.

Phase 5 done: README rewritten (commands checked, architecture table, evidence table, honest limitations), `docs/ARCHITECTURE.md`
(Mermaid plus `docs/img/architecture.svg`, drawn by hand), `docs/PITCH.md` (five criteria, every number from code or EVAL.md),
`docs/VIDEO.md` (8 shots, 1:52 timeline, 243 words of narration), `docs/img/demo.gif` (5 frames of the real UI via
claude-in-chrome screenshots; the gif_creator download landed in ~/Downloads, which the shell cannot read, so the frames were
assembled with Pillow), plus `de-expert.jpg` and `agent-log.jpg`. Gate passed in a temp copy without .venv/.env/node_modules:
`pip install -e ".[dev]"`, 167 tests green, replay (CLI, `/api/health`, `/api/matches`, `replay.json`, UI 200) and
`python -m matchvoice.evaluation` reproduce docs/EVAL.md (966 lines, 100.0%, 9.2%, 93.8%). The gate found a real bug: a fresh
install pulled mcp 2.x, which removed `mcp.server.fastmcp`; `pyproject.toml` now pins `mcp>=1.30,<2`. Also fixed stale numbers
in docs/SETUP-MAC.md (167 tests) and docs/PROTOCOL.md (54 KB gzipped). No model calls spent (23 of 40 used in total).
Still open: recording the video itself (the optional TTS voice is done, see Phase 9).

Phase 6 review done (Opus, 2026-10-20): 167 tests green, UI build and build:static clean (1.5 MB), replay server
(health, matches, replay.json, WebSocket, SSE) with `MATCHVOICE_NO_DOTENV=1`, static replay.json equals the server's,
evaluation reproduces docs/EVAL.md byte for byte, MCP stdio smoke (7 tools, verify_sentence, commentary_at), UI in Chrome
without scroll or console errors. No `sk-ant` and no em dashes outside .env, .venv, node_modules and the cache.
Decisions checked: en/de/fr, beginner/expert, Agent Framework newsroom with `agent-framework-anthropic`, one runner for
live and replay, one screen with modals, canvas pitch from one rAF loop, fictional names. Doc numbers match the code
(1,374 frames, 347 says, 56 logs, 281 KB, 54 KB gzipped; VIDEO.md shot 5 output). No model calls spent (23 of 40).

Phase 7 done (real-time rework, 2026-10-20). What is real-time and what is not:
- REAL-TIME (`mode=live`, the UI default): the runner feeds events at match pace on the server's monotonic clock (1x, 5x, 10x,
  30x, optional `start` minute with catch-up frames), the fast path (templates) speaks at once, the analyst newsroom runs
  while play continues, wordings are chosen without foresight, no recorded line is read. Messages carry `w` (wall seconds)
  and `lat` (event to caption); the log carries real step times; `hb` heartbeats keep the clock moving. Live template lines older than
  4 viewer seconds are dropped (see Phase 8). Needs key plus `--live-calls N`. A live match cannot be scrubbed.
- RECORDED RUN (`mode=replay`, and the whole static build): analyst lines written earlier, played back tape-delayed. The UI labels it
  "Recorded run", gives the reason when live was wanted but unavailable, and disables it for matches without a recording.
- Speed bug root cause: the browser pauses `requestAnimationFrame` in a hidden tab (verified: `visibilityState` hidden, 0 frames in 2 s)
  and the old client clock only moved inside rAF, clamped to 0.25 s per frame. Now the replay clock follows the wall clock, a 500 ms
  timer drives it in hidden tabs, and a live stream applies messages as they arrive. The server pacing was always correct.
- Also fixed: win chart filled from catch-up and live frames, key-moment rail shows a timeline ruler until the first moment,
  clock shows match time plus speed, caption hidden until kick-off, voice never outlives its slot (timer cut) and skips stale lines.
- `Library.recorded_ids()`: matches generated only for live (`red_card-11`) have no recording and stay out of tests, export and evaluation.
- Gate (Chrome, new tab, unseen match red_card-11, `--live-calls 12`, live 10x from kick-off): clock advanced 10.0015 match s per wall s
  (wall-measured 100 to 500 s). 9 model calls (8 moments, 1 verifier retry on moment 114, then accepted), model latency 3.8 to 7.2 s
  (median 6.1 s). Event to caption, 6 channels: goals, red card and full time 2 to 3 ms; template lines overall median 1.2 s, p90 3.6 s
  (the rest is director queueing behind a speaking line, 28% under 100 ms); analyst lines 6.0 to 18.3 s (median 10.4 s = model call plus
  waiting for the voice). 19 stale lines shown but not spoken. 32 of 40 build calls spent (9 new), 8 left on the budget of 12 live.
  Screenshots at start, goal (55'), 72' and full time were taken in the session.

Phase 8 done (live latency, voice, continuity, 2026-10-20). Behaviour changes, all live only (a recording and the replay export
are unchanged, the export parity test still passes):
- Caption and speech are separate. The live director (`ChannelDirector(captions_first=True)`) captions a moment the instant it
  arrives and fixes its wording then (no lookahead). Only the voice queues: it starts a captioned line at most 3 viewer seconds after
  its caption (6 for analyst-voice lines), else the line is skipped (shown, not spoken). Priority 90 and up is exempt, interrupts
  work as before. Protocol: live `say` is the caption (`s == e` while the voice is busy), the new `voice` message carries start,
  cut (`cut`) and skip (`skip`). The 4 s staleness cap now covers every template line (also `shot_milestone` and template stand-ins for
  a failed analyst line), which are dropped without a caption when late. `says` in `end` counts captions in live.
- Measured with the fake model at 5 s (`fake2.py` and `measure.py` in the session scratchpad, comeback-7 from kick-off to 50', 10x,
  six channels, WebSocket client). Before: event to caption median 1.44 s, p90 3.82 s, max 15.16 s (template lines median 1.42 s,
  p90 3.71 s, max 13.93 s; analyst-voice lines median 7.75 s). After: all captions median 0.002 s, p90 0.003 s, max 5.06 s (the
  max is an analyst line: 5.007 s model call, 0.043 s newsroom, 0.000 s waiting for the voice slot; before, the voice wait was 8.2 s
  on top). Template lines max 0.005 s. Voice behind caption: play-by-play max 3.02 s (limit 3), analyst max 3.91 s (limit 6);
  588 captions, 335 spoken, 253 skipped. The model call itself is untouched.
- Speed change in a running live match (`Player.changeLiveSpeed`): the stream restarts just after the newest frame (`start` = newest
  frame time + 0.1) with `analyst_from` = the oldest analyst moment still being written. The client keeps the log (deduplicated),
  the latency samples, the skip counter and the lines shown, and swaps in the new state in one go (catch-up frames are held).
  `GuardedLLM` shares calls under way across runs (`LiveConfig.inflight`) and a call survives a closed stream, so the pending moment is
  not paid twice. Proof in Chrome with the fake model (10x to 30x at 2760 s): 18 log lines before and after, score, moments and latency samples
  kept, clock continued 2760 -> 2786 s, 3 fake calls in total, the pending moment 91 was queued once and ready once.
  Carried moments have no `lat` (the event happened in the old stream).
- SpeechSynthesis, verified in a visible Chrome tab (hidden tabs report `visibilityState` hidden, `osascript` activation of Chrome was
  needed): 199 voices, `start` events 5 to 17 ms after `speak`, `cancel()` while speaking ends the line with `interrupted`, goals interrupt,
  no speech errors. Of 19 captions on en/expert, 11 were spoken (4 at once, 7 queued, longest wait 2.88 s) and 8 were skipped; the
  client counter matched the server's skip messages. The caption's level meter now follows the real `onstart`/`onend` (not the plan)
  and shows a flat dim meter for a skipped line, in the same place, no layout change.
- `ui/public/replays` regenerated from recorded data (has `highlights`), `npm run build` and `build:static` clean, static build served
  by `python -m http.server` with no backend: match list, switching match, play all work, no console errors. `window.__player` exists only
  on the Vite dev server, `__plot` is gone.
- 186 tests green (14 new in `test_live_captions.py`). No model calls spent (32 of 40 build calls used, 8 left).

Phase 9 done (ElevenLabs voice, fresh matches, demo insert, 2026-10-20):
- `tts/`: `GuardedTTS` (hard credit budget counted from `data/cache/tts/ledger.jsonl`, so a restart does not refill it; refuses before any
  request, never a partial spend; disk cache keyed by model|voice|lang|text; one bill for concurrent requests of a line; no retries),
  `ElevenLabsClient` (plain endpoint, `mp3_44100_64`), `FakeSynth` for tests. Voice: Daniel (British, "Steady Broadcaster"), id in
  `tts/voices.py`; de and fr map to the same multilingual voice and are not exercised. Credit factor verified: 41 characters
  cost 21 credits (API header `character-cost` 21, subscription counter +21, which shows up about a minute late), so 0.5 per character.
- Server: `/api/health` has `tts`, `/api/tts?run&ch&m` synthesises only lines a live run published (`hello.run`, 16 runs remembered), `/api/demo-insert`,
  `until` query parameter, any `<arc>-<seed>` is simulated on request (`Library._generate`, in memory). Details in docs/PROTOCOL.md.
- UI: `speech.ts` has two engines behind one queue (same skip, stale, urgent and cut rules): an `<audio id="voice-audio">` per line
  fetched when the voice starts the line, rate up to 1.25 to fit the slot, the real `ended` ends the slot; any failure falls back to
  SpeechSynthesis for the rest of the slot. Footer label "ElevenLabs n / 300 credits" or "Browser voice". Setup overlay: "New match" (arc, seed) and
  "Demo insert, 30 s"; the seed is shown on the board. `?demo=1` and `?match=<arc>-<seed>` work. A shared audio element got stuck
  (`stalled`, never played); one element per line fixed it.
- Demo insert: `comeback-135`, start 4379 s, until 4402 s (goal 4393.7 s, 71'). One model moment in the window (the goal analysis), two spoken lines before
  the goal, the second is cut off by it, the analyst reaction is captioned 0.2 s after the goal when cached and about 5 to 6 s after it live.
- Real proof (Chrome, 1x, fresh seed, `--live-calls 3`): subscription 85,970 -> 86,131 (+161) equals the ledger and the on-page meter (4 lines, 28+29+42+62 credits;
  total with the 21 credit probe 182 of the 300 cap, 118 left). 2 Haiku calls (34 of 40 build calls used, 6 left) (goal analysis plus one verifier retry of the three beginner lines), 1 of 3 left on that server.
  The first run's audio never played (shared element bug, found by logging `loadedmetadata`/`playing`), so the lines were paid but not heard; after the fix the same insert was replayed:
  `playing` at currentTime 0, `ended` at 3.81 s of a 3.81 s mp3, 0 credits (ledger unchanged, all `X-Voice-Cached: 1`), 0 model calls (log `lookup`).
  Goal interrupt of live audio proven with cached lines in the Vite dev page (urgent line replaced a playing one at 1.5 s, `stopSpeaking` removed the element); in the real insert
  the line before the goal ended 0.05 s before it, so nothing was left to cut. 404 on a bad run falls back to the browser voice (checked).
- Open: the chrome tab was `hidden` (AppleScript saw 0 windows, activation did nothing), audio still played; the replayed second run is the only one with audible-state evidence. Run-to-run the spoken set can differ when the analyst arrives instantly (cache), so a replay may need a new line.

Phase 10 done (minimal UI, 2026-10-20): the user found the UI a bug monster and too full. `ui/` was rebuilt as one calm screen for the one use
case, the demo insert (comeback-135, goal at 71'): top bar with wordmark, language (EN DE FR) and style (Beginner Expert); scoreboard, canvas pitch,
ONE large caption line (small dot and label: Template or Analyst), ONE agent line ("Analyst wrote it in 5.9 s, verifier checked every number, published",
worded from the real log messages, `agent.ts`), one "Play the moment" button that becomes "Replay the moment", footer with the honest voice label and mute.
Deleted: match picker, live/recorded toggle, speed, start minute, scrubber, rail, chart, stats, latency and credit readouts, all modals, the three
`ui/public/replays`, uPlot and lucide-react, the old screenshots. The protocol and the server are unchanged; the client only trims.
Caption rule (`caption.ts`): a line that is being voiced is not pushed off screen by a newer line that has not started speaking (a cached analyst answer
lands 0.2 s after the goal call); goals and red cards cut in. Source: a server with a live budget streams the insert over the WebSocket ("Live run");
otherwise (static build, no key, budget spent, WebSocket failure) the page plays `ui/public/insert/replay.json`, a paced live run of the insert saved
as streamed, through the same handlers ("Recorded insert", browser voice). Re-record it with `python -m matchvoice.pipeline export-insert` (answer cache
only, the model call raises, 0 calls) whenever the commentary changes. Server-side additions (pipeline only, no commentary files): `capture_insert` and
`trim_catch_up` in `pipeline/export.py`, the `export-insert` CLI, one test. Switching language or style mid-run no longer re-speaks the current line
(that would have bought a second ElevenLabs line). Gate: build and build:static clean, 245 tests green, Chrome (new tab, cached insert, 0 credits, 0 model
calls): scrollHeight equals innerHeight at 1920x1080, 1430x769 and 1280x720 (iframe check), no console errors, DE/FR/Beginner switches change the caption,
static build loads and says "Recorded insert". Screenshots: docs/img/ui-start.jpg, ui-goal.jpg, ui-end.jpg. docs/PITCH.md and docs/VIDEO.md still describe
the old UI (modals, speed, match picker) and need a pass before the video.

Phase 11 done (caster persona, text first, 2026-10-20). The user: "es klingt null nach einem richtigen Caster". There is no docs/CLAUDE.md; this file is the project notes.
- `PROMPT_VERSION` v3. `SYSTEM` is a named two-person booth (Ewan Marsh, play-by-play caller; Nadia Rowe, colour analyst, who owns the model's lines), a per-language
  voice guide (en British broadcast, de German TV commentator, fr French broadcast pace), number discipline (at most ONE number per line, a score counts as it,
  beginner lines none except the score), energy (calm / rising / peak, from `delivery.energy_of`: priority, plus a story tag or a big chance lifts one level),
  length 60 to 110 characters (hard cap 150, unchanged), 3 good examples and 5 bad ones. The bad ones are real v2 lines from `data/replays/comeback-7/analyst.json`
  (a test checks they still exist there). Every verifier rule is kept (digits, numbers from facts, home-away, surnames, MAX_CHARS).
  `build_prompt(..., recent=)` adds energy, an angle per moment kind, and a Continuity block: the last 3 lines each wanted channel showed or spoke.
- Continuity: `Runner._said` (per channel, filled from caption/start notes, a skipped line is taken out again) feeds `Runner._recent_for(m)`, which fixes the lines per
  (match, moment) in `LiveConfig.recent_memo`. That keeps the prompt identical for a restarted stream or a second run, so the cache and the call under way still match.
  `write_moment(..., recent)` hands them to every attempt, retries included. `precompute` stands in with the lines published so far.
- Templates: all 21 kinds rewritten in en/de/fr x beginner/expert, 2 to 3 wordings each, short to long (sorted at import). No metres, no stat lists, at most one number
  (tests: placeholders, no digits in text, no dashes, no gendered pronouns, all wordings pass the verifier on 5 matches, rendered length at most 130). New `men_en` param.
- Delivery, nothing exercised: `shape_for_tts` (scorelines to "one-all", "eins zu eins", "un à un"; decimals, percent, ordinals, xG, km/h; dashes and colons to pauses),
  `VOICE_SETTINGS` (stability / similarity / style / speed per energy; style is left out for Flash), `GuardedTTS(delivery=True)` / `--tts-delivery` / `MATCHVOICE_TTS_DELIVERY=1`
  send the shaped text and the settings and bill the text actually sent; off by default, so text, cache keys and costs are what they were. `Runner.energies` and the
  `/api/tts` endpoint pass the energy through. Voice shortlist, free previews and a recommendation per language in docs/VOICES.md. The default voice is unchanged.
- Evidence on the demo insert goal (comeback-135, 71', moment 163), same moment, six lines: v2 averaged 128 characters and 27 numbers (4 to 5 per line); v3 averages
  78 characters and 3 numbers (only the 36 percent in the expert lines), all six accepted first time, no retry. 1 real Haiku call by this task. A second v3 call (an earlier
  state of this prompt) was spent at 23:41 by a live run on the server at port 8000 that picked up the work in progress: 35 of 40 build calls used, 5 left.
- The existing demo lines are stale: re-run `python -m matchvoice.pipeline export-insert` (answer cache only, 0 calls) to refresh `ui/public/insert/replay.json`.
  `docs/EVAL.md` regenerated (818 lines at x30, 100.0% grounding, analyst 9.9%); the quoted numbers in README, PITCH and VIDEO were updated to match.
- `test_live_captions` now runs at 300x (was 600x): the shorter lines no longer overrun the voice at 600x, which is the intended effect. 245 tests green.
- Open: nobody has listened to a v3 line. Next spend decision: ElevenLabs preview of Charlie and Daniel (free), then one paid take per energy level.

Phase 12 done (caster fixes after the Opus review, 2026-10-21): xG is out of all play-by-play (goal, saved, post, off) and out of the de/fr analysis fallbacks; the longest expert goal
wording is a real call with the score ('GOAL! Fontaine buries it, and it's 1-1!'). The director keeps the order of `variants_of` (templates short to long, the model line last) instead of
sorting by length, so an accepted analyst line wins whatever its length and a template only takes over when it does not fit. Model jobs now start after the tick that captions the same event
group (`Runner._start_jobs`), so the goal call is part of the analyst's continuity (3 lines in the block). `PROMPT_VERSION` v4: the colour analyst never opens with a reaction, the good example is
a go-ahead at 2-1 with 58 percent (no longer the demo goal). Bank rewrites per the review (Notizbuch, Das Spiel hat sich bewegt, share-of-threat variants, buts attendus, rate le gros coup and more).
Demo insert re-recorded with 1 real Haiku call (36 of 40 build calls used, 4 left), all six lines accepted first time; ElevenLabs credits spent: 0. Not done: v4 was judged on the goal moment only, a
second moment kind (momentum or big_save) needs the user's go-ahead for 1 or 2 calls.

Phase 13 done (UI review fixes, 2026-10-21): start screen shows 0-1 and 70' from `demo_insert` (`score`, `clock`) plus one line "Wexmoor Athletic trail 0-1. 70th minute."; the insert starts 12 s
before the goal (`LEAD_S`), first spoken line 1.7 s after Play; `ChannelDirector` in `captions_first` also avoids the same template slot for consecutive moments of one kind. docs/VIDEO.md,
PITCH.md and the README limitations rewritten for the one-insert UI. Insert re-exported (0 calls, cache hit): no `skip` for m163 on any channel, analyst line in all six channels (15.8 to 18.0 s of a 21 s insert).
No ElevenLabs credits, no model calls by this task. 250 tests green.

Phase 14 done (board polish and review fixes, 2026-10-21): the user wants the heard commentary as the USP and the board as one polish pass, so nothing was added (no panels, chips or controls).
`ui/src/pitch.ts` redrawn as broadcast graphics: striped turf with floodlight falloff and vignette, glowing line work, nets; ball with soft shadow and a comet trail; passes as arcs that draw on and fade, shots as a straight
line with an arrowhead that lingers; one name tag per acting player that fades; fouls and tackles as quiet rings; cards as a small flag; goal moment = light pulse and net ripple on the goal mouth, a 5 percent push-in toward it,
scoreboard digit flip, and a standing "Goal 71'" ring so the end state still points at the goal (the Replay button now sits on the bottom edge of the pitch in that state). Team colours are lifted toward white on the turf,
the UI accent moved from amber to ice (`--signal`) so it no longer fights Tamsworth's amber or Wexmoor's purple. Scoreboard is names with a team bar, tabular digits, a dash and a clock pill. Start screen keeps the real
state of the insert (0-1, 70', not 0-0: that is where the insert starts) plus one line with the ordinal and the length ("21 seconds of commentary"). One rAF loop, no per-event React render; `hooks.ts` schedules the next
frame before running the callbacks so one throwing frame cannot stop the loop. `prefers-reduced-motion`: no push-in, ripple, comet, wave or glide, only fades. The ambient formation dots were left out on purpose (would read as tracking data).
Review fixes: `ChannelDirector(has_model_line=...)` so the live slot-avoid rule never filters the model line (Runner passes it per channel; two regression tests in `test_live_captions.py`), correct English ordinal (`ordinal()` in Stage.tsx, none for added time),
dead code removed (`ui/src/format.ts`, the `silent` paths in `Sim`), PITCH.md level paragraph corrected, README screenshots retaken (docs/img: ui-start, ui-mid, ui-goal, ui-end). Insert re-exported (cache only, 0 calls): text unchanged.
Gate: 252 tests green, build and build:static clean, static build served with no backend plays the insert ("Recorded insert", no console errors), no scroll at 1430x769, 1920x1080, 1280x720 (also with reduced motion), 60 fps
(median 16.7 ms, max 16.8 ms in the goal window, no frame over 20 ms) measured with requestAnimationFrame timing. The user's Chrome never reported a visible tab (rAF 0 frames, `visibilityState` hidden, `osascript` saw 0 windows),
so screenshots and the fps check came from a separate headless Chrome with its own profile (driver in the session scratchpad). No ElevenLabs credits, no model calls. Not heard by anyone yet: the voice choice is still open, docs/VIDEO.md and PITCH.md get their rewrite after it.

Guided live backend (no UI yet): `GET /api/guided-live` returns `{match, arc, seed, start, until, window_s, goal_t, fresh, runs_left}` for a random arc and seed (SystemRandom), a window from 40 s before the goal to 14 s after it (the pitch is silent about 50 s after a goal) with the most
moment priority (`pipeline/guided.py`, simulation only). Hard limits in `LiveLimits` (runner.py), enforced server side: `--live-max-seconds` (default 75, `until - start`; a live run without `until` is refused with `bad_request`) and
`--live-runs-per-day` (default 150, UTC day, in memory so a restart resets it, counted under a lock when the stream is accepted and after every other check, refusal code `no_runs_today`, SSE 429); `/api/health` `live` gained
`runs_left`, `runs_per_day`, `max_seconds`; the call budget stays the last guard. Insight logs (`pipeline/insights.py`, agent `facts`, step `insight`, live only): `wp_swing` (10+ points), `momentum`, `shots`, rate limited to 3 per minute,
no model, no lookahead. Documented in docs/PROTOCOL.md. Insert re-exported from the cache (0 calls): the 24 `say` texts are identical, one `wp_swing` insight (goal, 67% to 22%) was added. 26 new tests in `test_guided.py`.

Guided run UI done (2026-10-21, user approved the mockup; no model calls, no ElevenLabs credits, no commit): `ui/` is now a guided run. The user explicitly asked for log views, so the
"no modals, no log views" line in Decisions is superseded for the two full logs only (native `<dialog>`, Esc and close button, focus trap, focus returns to the icon button); the page itself never scrolls.
- Flow (`player.ts`): a step rail on top, Step 1 Recorded (always `ui/public/insert/replay.json`, also with a server), Step 2 Live (`GET /api/guided-live`, new random match, `until`, 1x, browser voice only, ElevenLabs is
  not used by the UI any more, the server endpoint stays). The settings card (language, style) sits on the pitch before Step 1; after it: "Go live" plus "Replay recorded". Lengths come from the data (insert `until - start`,
  `guided.window_s`). Live blocked (static build, `no_key`, `no_budget`, `no_runs_today` from `/api/health`, or a refused run: WS `error` then close 4001, `bad_request`) shows one honest line, hides the Go live button, keeps Recorded
  working; health is re-read after every live run (`runs_left`). The old Live/Recorded toggle, footer and the one agent line are gone (`agent.ts` deleted, the "why this line" box replaces it).
- No scrolling: html and body are fixed, the pitch is sized by container query units (`.pitchslot`), caption and evidence sizes follow `min(vw, vh)`. Right column: Game log (`gamelog.ts` writes events from the frames and
  `hello.players`: minute, player, what happened, goal score, plus the `facts` insight logs) and Agent log (every other agent with `+w` seconds since run start, durations from `latency_s`/`wall_s`, `lat`, verified minus
  analyst_wrote). Panels show only the newest rows that fit (overflow hidden, `scrollTop = scrollHeight`, top fade); the full log is in the modal. Below 900 px the logs collapse to two icon buttons in the top bar.
- Lanes (`derive.ts`, documented in `Lanes` in `components/Logs.tsx`): Detector dots (`queued`, template captions), Analyst bars [analyst_wrote.w minus its latency, analyst_wrote.w] plus an open bar while a call is pending,
  Verifier [analyst_wrote, verified/rejected], Publisher [verified, ready], Voice = the server's speech slot of each spoken line (skipped, dropped or muted lines have none). A lamp is lit while the playhead is inside an interval
  (+0.25 s so a 2 ms verifier pass is seen). The axis is the run's window and grows only when a voice slot runs past it (the end of the recorded run: 21 s to 24 s).
- "Why this line": template line = the event row found through the frame time and the moment kind (shown only when exactly one event qualifies, surname breaks ties), analyst line = the moment's log steps (cache or live
  latency, rejected number and retry, verified, ready) plus insight logs with the same event ids. Clicking a log row selects the same evidence (related rows light up), a new caption takes the selection back.
- Checked (headless Chrome, own profile, fake model server on another port, real server without key, static build, no spend): `scrollHeight == innerHeight` and no overflowing element at 1430x769, 1920x1080, 1280x720,
  1024x640 in ready, recorded playing, recorded over, live playing, live over; also 900x500, 700x900, 390x844; live unavailable (static, `no_budget`, runs used up), live refused after the page booted (`no_runs_today`), error
  (missing replay.json); modal opens, Tab stays inside, Esc closes and focus returns; 60 fps (median 16.7 ms, max 16.8, no frame over 20 ms) through a recorded and a live run; no console errors. Screenshots in docs/img
  (ui-start, ui-mid, ui-goal, ui-end) are the real recorded insert. Not checked: real model output in Step 2 (fake canned lines only), audible voice, the user's own Chrome, SSE in the UI (WebSocket only).
- Stale docs left for the user: docs/VIDEO.md (shots 1 to 4 and 8 name the old "Play the moment" only flow, the agent line and the "Recorded insert" footer; line 51 refers to the footer), docs/ARCHITECTURE.md calls the UI "single-screen" (still true).

Review fixes after the guided run UI (2026-10-21, no model calls, no ElevenLabs credits, no commit): `analyst_from` may reach back at most `--live-max-seconds` before `start` (`LiveLimits.check_carry`, `bad_request`), so a fresh
`<arc>-<seed>` id cannot start model calls for the whole match before start under the run cap; the caption block is `3.6 fs + 30px` tall (three lines, gap and source row; `4.8 fs` on a phone) so nothing is clipped; below 640 px the
evidence box hides its title and keeps two columns of three, no overlap. Checked headless at 1430x769, 1920x1080, 1280x720, 1024x640, 390x844 with the longest recorded fr line injected. 279 tests green, insert unchanged (no re-export needed).

Guided run length fix (2026-10-21, no model calls, no ElevenLabs credits, no commit): a live run with `until` now keeps ticking idle frames and heartbeats up to `until` after its last event (`Runner.stream`), so a quiet stretch
before the kickoff no longer ends the run early while the countdown still shows seconds left; the over status prints the real run length (`player.elapsed()`), not `guided.window_s`. New test in `test_pipeline.py`; 280 tests green,
build and build:static clean, insert re-exported from the cache (0 calls; wall-time fields differ). Not re-checked in the headless browser.

Light design pass on the guided run UI (2026-10-21, design only, no behaviour change except the two fixes below; no model calls, no ElevenLabs credits, no commit): the visual identity changed from dark/ice to LIGHT and GREEN. Decisions are untouched
(the "one calm dark screen" line there is superseded visually only: it is now one calm light screen). Tokens in `ui/src/styles.css`: warm paper `#faf9f5`, panels `#fffefc`, ink `#1f1d1a`, hairlines `#1f1d1a17`, ONE accent `--signal` `#12803f`; no ice blue left.
One grotesk only: Schibsted Grotesk 800 with tight tracking for score digits, caption, brand, team names and panel titles, 400 to 600 for UI text; Barlow Condensed is removed (import, dependency and font files gone from the bundle). Airy: rounder cards (logs are one rounded card),
paddings scale with `clamp()`. Lanes are monochrome: grey bars, only the active bar and lamp are green (`data-act` set from the frame loop in `Lanes`), lamps are plain dots with no glow or box-shadow, agent names in log rows are grey and only Analyst is green. Pitch (`pitch.ts`):
lighter turf with soft stripes, white lines, ball with a dark outline, dark "Goal" pill with white text, white name tags with dark text, team colours deepened 22 percent (`tune`; amber cannot reach 3:1 on the turf, so markers carry a white ring plus a thin dark ring, trail and off-ball marks a white halo; checked with a contrast script). Still one rAF loop, no arcs.
Space: board, caption (two lines plus the source row, `data-long` sentences over 96 characters are set smaller to keep three lines inside) and the evidence box (height computed from its own font and padding) were tightened, so the pitch is about 60 percent larger at 1430x769; the start screen sentence moved from the pitch to the caption slot, the run status and the live note moved to one foot line under the evidence.
Fixes: (1) log panels cut a row at the top: `fit()` in `components/Logs.tsx` measures the rows and hides whole rows from the top until the list fits (also on resize and when the font arrives), no mask, no clipping. (2) live note: `Player.checkLive()` asks the server the same way at boot and again when the recorded run ends (health, then the next window), the Go live button waits for the answer (`checking`) and never shows while live is blocked, and one `noteOf()` words a refusal wherever it was found.
Checked in headless Chrome (own profile, fake backend on another port, no-key server, static build, dist without replay.json): `scrollHeight == innerHeight` and no overflowing element at 1430x769, 1920x1080, 1280x720, 1024x640 in ready, recorded playing, recorded over, live playing, live over, live unavailable (no budget, static), error and both log modals; whole rows only; no console errors; the note text is identical at start and end for no budget and static, and after another visitor used the last run the end of the recorded run shows the refusal and no button. `npm run build`, `build:static` and `tsc` clean. docs/img/ui-*.jpg retaken. Not checked: the user's own Chrome, audible voice, real model output in Step 2.

Data layer phase 1 done (player and team model, 2026-10-21, docs/PLAN-DATA.md; no model calls, no ElevenLabs credits, no commit): `sim/profile.py` and `sim/tactics.py` add optional fields to `schema.Player`
(`attrs`, `foot`, `weak_foot`, `height_cm`, `age`, `top_speed`, `work_rate`, `role`, `traits`, `season`, `captain`) and `schema.TeamMeta` (`tactics`, `postures`); `python -m matchvoice.sim` writes them to `meta.json` (None values left out).
Profiles draw from their own streams (`"{seed}:profile:{id}"`, `"{seed}:tactics:{side}"`) and the posture schedule is a pure function of the finished events, so the skeleton did not move: SHA-256 of `events.jsonl` and `truth.json` of
the four demo matches identical before and after, and a digest of events, truth and the old meta fields identical for 50 seeds x 3 arcs (150 of 150, a one-off script against the pre-change code); the four demo hashes are a test (`test_profile.py`). Posture shifts for seeds 1..50: comeback 3, red_card 4, unlucky 2
(50 of 50 each); red_card home is `ten_men + chase` (3-3-3 in possession) from the 61' checkpoint. 3,300 players: all have a role and at most 2 traits; 300 of 300 teams have exactly one set piece taker and one captain.
`effective_plan` and `plan_at` give the plan in force at any match second (ten_men first, posture on top). 412 tests green (132 new in `test_profile.py` and `test_tactics.py`, 280 before). Nothing reads the new fields yet; protocol, prompts and cache keys are unchanged.
Phase 1 review fix 2 (2026-10-21, no model calls, no commit): the first fix (`t = max(effective, previous t)`) pulled A's goal-triggered `base` off its own restart in 2 of 150 runs (red_card 18, 22), against DATA-MODEL 2.3.
Reverted: every shift in `posture_schedule` is dated by the 2.3 rule alone (first restart within 180 s, else first possession change at or after 180 s), so `t` can be out of order within a side. `plan_at` now picks the latest
TRIGGER among shifts in effect, so a later trigger still wins. New `superseded(shifts)` flags a shift that a later trigger overtook; it was never in force (5 of 50 red_card matches: seeds 9, 18, 22, 35, 39, always A's `protect`, never the last shift). Counts unchanged
(comeback 3, red_card 4, unlucky 2, 50 of 50). Open for the plan owner: phase 7 must decide whether a superseded `protect` still becomes a `tactical_shift` moment (it is in the 4-shift count and the 13-call budget, but the team never plays it); `superseded()` is the hook.
Data layer phase 2 done (event enrichment without tracking, 2026-10-21, docs/PLAN-DATA.md; no model calls, no ElevenLabs credits, no commit): `sim/micro/enrich.py` reads the skeleton, the profiles and the tactics plan and writes `enriched.jsonl`
for comeback-7, red_card-7, unlucky-7, red_card-11 and comeback-135 (that one without a meta.json, so `Library.ids()` ignores it; 539 to 596 KB each, not the 250 KB estimated). `eid = 16 * i + k`; annotation rows (k=0) for pass, carry, shot, foul and interception,
sub-events for `receipt`, implicit `pass` and `carry` (gap repair) and `take_on` lost (a tackle that follows a carry). Stream `"{seed}:micro:{16 * i_of_restart}"` per segment, so a window equals the full run. Arrival is retimed inside `[t + T, t_next - 0.25]`,
first-time actions are steered with 15 to 25 percent chance (a header from a cross or corner always, if the physics allow). Skeleton files untouched: the four hashes are identical, and 150 of 150 digests (events, truth, meta, 50 seeds x 3 arcs) are identical with and without an
`enrich` call. 498 tests green (82 new in `test_enrich.py`). Measured (`python -m matchvoice.sim.micro --report`): touches per minute 24.8 to 27.5 (skeleton alone 14.7 to 16.2), insert window 7 touches, 0 arrivals outside the bounds, 0 `under_pressure` events without `pressure.under`, 0 kick rows with an outcome field,
0 overflow, 0 unrepaired jumps in the five matches (19 of about 300 gap repairs over 150 other matches, all long jumps the skeleton leaves under 4 s: listed in `Stats.unrepaired`, no row). NOT met: first-time passes are 0.5 to 1.0 percent of passes (expected 15 to 30): the skeleton leaves a median 2.75 s between arrival and the next action and
the 3.3 caps allow 0.55 s of slow-down (upper bound if every feasible pass were steered: 4 to 5 percent). Pass mix misses the 4.2 ranges (through 55 to 85 per team, long 1 to 2 percent, back 1 to 3 percent): reviewed, not fixed, see the phase note. The insert's implicit pass 23714 is `through` (1.5 m past A's planned line at 78.5 m), not `short`.
Phase 2 review fix (2026-10-21, no model calls, no commit): (1) receipts no longer carry `hold_s` (it was the time to the next skeleton event, a lookahead against DATA-MODEL 0.1 and 4.1); tests now forbid it on receipts. (2) `through` now needs the end 10 m past the opponent's planned line and `L >= 40` (DATA-MODEL 4.2 updated):
through balls per team 3 to 8 on the five matches (median 5 over 150 matches, 18 of 300 team-matches above 8, max 11), so the 4.2 range holds on the demo matches; the insert's implicit pass 23714 is `short`, the chain is interception, switch, long, short, shot as the gate asks. The five `enriched.jsonl` files are regenerated (skeleton hashes identical), 499 tests green.
(3) Still open, a decision for the plan owner: first-time passes stay at 0.5 to 1.0 percent (0.76 percent over 150 matches: 1,377 of 182,169) because the 3.3 caps (ground floor 8 m/s) leave no room for 15 to 30; options are to correct the expected range to about 1 percent, raise P_FIRST to 1.0 for feasible passes (4 to 5 percent), or lower the ground floor to 5 m/s (14 to 19 percent, slow visible rolls). Code unchanged for this point.
Superseded in the entry above: the insert pass 23714 is `short`, not `through`, and the through count is 3 to 8 per team, not 55 to 85.
Phase 2 review fix 2 (2026-10-21, no model calls, no commit): (1) `cross` needs `L >= 15` (`CROSS_MIN_LEN_M`, DATA-MODEL 4.2): before, 17 to 33 crosses per match were under 12 m (a 0.8 m tap became a lofted inswinger). Now 5 to 21 crosses per team on the five matches (max 21), over 150 matches median 12, 10 of 300 team-matches above the range of 25, 70 of 300 below 8 (few wide balls in the skeleton); shortest cross 15.0 m. The insert chain is unchanged (interception, switch, long, short 23714, shot with `assist_eid` 23714, 7 touches). (2) Receipts no longer read the next action: `facing` is drawn from the direction of the incoming pass, `pressure.under` is `null` until the micro-sim sets it in phase 4 (the skeleton has no receiver flag; 4.1 updated). Tests: the lookahead test is replaced by a perturbation test (next action changed, receipt identical), a facing-versus-loss test and a no-value test. (3) First-time gate NOT met and not decided by me: 0.67 percent of passes on the five matches (0.57 to 0.87), 1,229 of 182,169 (0.67 percent) over 150 matches. Measured options on the five matches: `P_FIRST` 1.0 gives 3.9 percent, plus ground floor 6 m/s 9.9, 5 m/s 14.3, 4 m/s 21.4, 3 m/s 30.3 (a 15 m pass rolling at 4 m/s takes 3.8 s, not credible), so only the range correction (option a) is realistic. The old test that asserted 0.2 to 6 percent as correct is now a labelled ceiling guard, and the 15 to 30 gate is a strict xfail. The five `enriched.jsonl` files are regenerated (skeleton hashes identical).
Data layer phase 3 built (fast and context layers, 2026-10-21, docs/PLAN-DATA.md; no model calls, no ElevenLabs credits, no commit; the Opus caster review of the strings is still to do): `commentary/fast.py` turns the skeleton, the enriched rows and the tactics plan into
moments (fast: `touch`, `pass_kind`, `carry`, `duel`, `restart`, `setpiece_setup`, `press_on` fire now; `take_on`, `block`, `in_behind`, `line_break`, `duel_1v1` have words and wait for tracking; context: `player_note`, `counter_note`, `fatigue_note`, `tempo_note`, `shape_note`,
`press_note`, `phase_note`) with ids derived from data (`1_000_000 + 8 * eid + slot`, `3_000_000 + 8 * fi + slot`), stamped with their time of knowledge (a kick at the kick, a receipt at its arrival, a carry at its end). `ChannelDirector(dense=True)` adds the pace rules (a newer fragment replaces an
older one, 1.2 s between fast starts, context caps, shortest wording in play, fast and context captioned when voiced). `Runner(fast=True)` switches the layers on, replaces `long_ball` and `pass_final_third`, applies the v5 continuity rule (only skeleton and analyst captions, no skip removal); it is
off by default, so every recording, cache key and earlier test is as it was, and it stays off until phase 6 updates the protocol doc and the tests that must change. `evaluation/density.py` is the density report (`python -m matchvoice.evaluation.density`, 0 calls). The dry run (first, with one placeholder per kind) missed the
coverage gate by more than a quarter, so the rules changed before the strings were written: the changes and the numbers are in docs/DENSITY.md and DATA-MODEL 7.7. 339 template strings (213 fast, 126 context) in en, de and fr x beginner and expert, plus 309 entries in the word tables (`WORDS`: directions, pass types, clauses).
Measured gates (x1, six channels): over the 3 full matches every gated metric holds (segments per minute 15.7 against 12, coverage 76% against 55%, words per minute 91 against 60, short segments 62% inside 40 to 70, long 5.2% inside 5 to 20, names per 100 words 10.7, skipped captions 33% against 35).
NOT met: guided windows, segments per minute 14.9 against 16 (everything else on the windows holds: coverage 84%, words per minute 113, after a goal +35%); the insert on its worst channel, short segments 33% (gate 40), segments naming a player 67% (gate 55) and skipped captions 50% (gate 35). The skips are the template fallback of the analysis line, which is
perishable after 4 s and cannot start behind a 5 s beginner goal call; with a stand-in that answers like the recorded insert (0.2 s, no call) skips are 0%, coverage 90%, segments per minute 17.1, but short segments stay 33% and long segments 0%: six segments in 21 s make every share a coin flip. The "before" column (the recorded insert, 4 lines) reproduces the plan: 11.4 segments per minute, 76 to 81% coverage.
Unchanged, checked against the numbers taken before the build: SHA-256 of events, truth, meta and enriched files of all five matches, of `data/eval/results.json`, `docs/EVAL.md`, `ui/public/insert/replay.json` and the three `analyst.json` recordings; the moment ids, kinds, times and priorities of the five matches; the guided window of 50 seeds x 3 arcs; the replay stream of the
three recorded matches at x30 (message hashes); a paced capture of the insert reproduces all 32 `say` and `voice` messages of the recording with 0 calls. 585 tests green (82 new in `test_fast.py` and `test_density.py`), 1 strict xfail as before. The fast layer at x30 replay would push skeleton lines out (the voice time is multiplied by 30): the shipped replay stays on the default until phase 6.
Incident, fixed: `AnalystExecutor` discards the cached answer of a prompt whose call failed, also in fresh mode. My first measurement run used a call that always raises against the real cache directory and deleted the recorded insert's answer (`3e1eb87834e94b078cfc9c9e.json`). Rebuilt from the six accepted lines in `ui/public/insert/replay.json` (latency 6.7 s from its log), checked: a capture of the insert reads it and reproduces the recording with 0 calls. The density report and its tests now use a private cache directory.
Next in docs/PLAN-DATA.md: the Opus caster review of the new strings and rules, then phase 4 (micro-simulation and tracking).
Phase 3 review fixes (2026-10-21, Sonnet, no model calls, no ElevenLabs credits, no commit; details in DATA-MODEL 7.7): name-less pass fragments now say only what the kick shows (type, lane, direction), never a verdict or the outcome; `touch` wordings say how the ball arrived ("Forward to X"), not what the receiver does next; `press_on` says "high" only for a presser 60 m or more up the pitch (`facet` high or low); the verifier has the claims lexicon of 7.5 (`CLAIMS`, `TRAIT_WORDS`, `claims_of`; codes `claim_unsupported`, `trait_unsupported`); the meta leads of the context wordings are gone (two wordings per kind); a saved shot or the post no longer opens a dead ball and the conceding side gets no player note after a goal; two German context wordings corrected. 14 new tests, 599 green, 1 strict xfail. Density gates, measured x1: full matches 15.7 segments per minute (12), coverage 75% (55), 85.9 words per minute (60), short 63%, named 44%, skipped 29% all hold; NOT met and not claimed: long segments over the full matches 1% (gate 5 to 20; the old 5.2% was the dead-ball leads), words per minute after a goal over the full matches -25% (gate > 0%), the insert's short 33%, long 0%, named 67% and skipped 50% (the insert's short, named and skipped were already failing), guided windows 14.9 segments per minute (as before). Insert segments per minute 17.1, coverage 75%, 117 words per minute hold.

Phase 3 review fixes, round 2 (2026-10-21, Sonnet, no model calls, no ElevenLabs credits, no commit; DATA-MODEL 7.8, docs/DENSITY.md): (1) season notes add what the player has done in the match (the review saw "six" for Fontaine 223 s after his goal; the goal is now news in the dead ball after it, `tally`); (2) `lane` is the flank a kick leaves from ("Switched from the right."), a pass has no `dir` phrase, no wording says a thing twice;
(3) a routine short pass is only a name chain on a turn that may name a player (`pass_kind` 53% -> 23% of the segments, pass fragments that name nobody 5 to 6%, "Played short ..." 0); a receipt says where the receiver stands ("In the final third, left side."); `NAMED_EVERY = 4`; fast fragments take turns (`ChannelDirector._turn`) and a kick fragment ends with the flight of the ball; (4) tempo notes are about the side that has the ball (55% of the passes), with hysteresis, worded "in no hurry on the ball"; (5) a fact about a player is said once in the match, never twice in a row of one kind (every spoken `player_note` is distinct now, was 42 to 44 of 115 to 124), plus a live "passes completed so far" fact;
(6) goals: the first context slot comes 9 s after the goal, with the move that led to it and the scorer's tally; quiet stretches (4, 10, 16 s) offer a slot; (7) press wording (de "läuft früh an" / "geht eng drauf"). Measured x1 (`python -m matchvoice.evaluation.density`, byte-identical in 3 hash seeds): full matches hold every gate but the 12-word share (1%; after-goal words per minute -25% -> +16%); windows hold every gate but segments per minute (14.4 against 16, 14.9 before); the stand-in insert holds every gate but the 12-word share; the default insert falls to 69% coverage on en/beginner (was 75%) and keeps 0% long and 50% skipped captions. NOT met and not claimed: the 12-word share (a fast fragment is capped at 6 words, context lines are one fact each, reaching 5% needs model lines or tracking content: plan-owner decision), windows segments per minute, the default insert's coverage. Tests: 116 in `test_fast.py` (17 new), `test_density.py` guards which gates hold.

Phase 3 review fixes, round 3 (2026-10-21, Sonnet, no model calls, no ElevenLabs credits, no commit; DATA-MODEL 7.9, docs/DENSITY.md): the second review found the volume layer moved, not removed (name-less receipt and zone fragments 34 to 38% of the segments, "Under control." 231 times).
(1) The volume is names and verbs: every routine kick is a name chain ("X finds Y", "X, under pressure, finds Y"), a receipt says who has the ball and how he took it (control, chest, head), a pass with a type always names its target ("Long ball for Tavares"; a clearance has none), a zone is a rare wording in one order,
a name-less fragment is for a ball worth a word and never two in a row (`NAMED_EVERY = 2`); a receipt waits 0.5 s and is void if the receiver plays on, so the insert's goal chain is "Ibsen cuts it out. Switched. Rasmussen chests it down. Long ball for Tavares. To Fontaine. GOAL!" (de/beginner and fr/expert name the same four).
(2) The game state comes back when the score moved or five match minutes passed ("in added time" instead of a frozen minute), counters grow or stay quiet (streaks, stats, a news item once, caps per match), the builder follows the director (dead-ball slots `CONTEXT_DEAD_S` + 1 s apart, three per window; a goal's move, then its tally, all voiced), no meta leads, longer connected sentences
(the move before a goal or a chance, tally with assist, state with the shots, a stat against the other side, two or three facts of one player in a dead ball), the template stand-in of the goal analysis is not perishable behind the goal call (`STANDIN_BEHIND_GOAL_S`), the verifier reads a French sentence with two perfects as French.
Measured x1 (`python -m matchvoice.evaluation.density`, 0 calls): windows 16.5 segments per minute (was 14.4), long share windows 15% and matches 6% (was 10% and 1%), insert coverage 79% and 0% skipped captions (was 69% and 50%), full matches 18.5 segments per minute, coverage 81%, 22% skipped.
NOT met and not claimed: naming a player, names per 100 words and segments of 5 words or fewer (windows 81% and 20.8, matches 83% and 26.4 and 85%, insert 71%, 15.8 and 71%): they held in round 2 because a third of the segments were position readouts; names and verbs put a name in more than 80% of the segments and the name-less sentences a template can say are about 3 a minute (the model's analyst lines are the intended source);
the insert's 12-word share (0% on de/beginner and fr/beginner: the analysis template has 9 and 10 words, seven segments in 21 s), and the tally of the insert lands 0.7 s after its end. The test that failed once in the full suite (`test_guided::test_replay_streams_have_no_insights_and_insights_never_change_the_lines`) compared two live runs whose model-call latency is timed on the wall clock (`latency x speed` moves the analysis, 0.03 s apart under load); the clock of the call is pinned in the test now.
A re-run of `python -m matchvoice.evaluation` gives 876 lines at x30, the committed `data/eval/results.json` has 818: it was already stale before this round (the replay stream hashes are unchanged), and it was not regenerated.

Phase 3 review fixes, round 4 (2026-10-21, Sonnet, no model calls, no ElevenLabs credits, no commit; docs/DENSITY.md): (1) each name once per hop: a routine kick names the kicker ("Lindqvist plays it on."), its receipt the receiver ("Inside to Lemaire.") without the kicker, a typed pass that named its target skips a plain receipt; (2) the second goal of a scorer has its move (`fresh_news` key holds the chain and the score), 6 of 6 goals get move then tally; (3) no fact twice in a row (a stat marks the other side's figure and the save/shot-on-target twin as said, one shape/press/phase note per side per `TACTIC_GAP_S`, tempo at most `TEMPO_MAX` per side with a second wording, the tally covers the season note); (4) no zero as a contrast, two shares of the ball add up to 100; test tautology `or True` removed. Gates as in round 3 (windows 16.7 segments per minute, matches 19.0, insert unchanged); same NOT-met set.

Phase 3 review fixes, round 5 (2026-10-21, Sonnet, no model calls, no ElevenLabs credits, no commit; DATA-MODEL 7.10, docs/DENSITY.md): (1) a name is not said twice within `NAME_GAP_S` (6 s): a routine kick whose kicker was just named is not called
(or, when it shows something, called without him, at most every `SHOWN_GAP_S`), a typed pass says only its target, a carry goes name-less, a turnover resets the rationing; fast-line pairs naming one player within 6 s fell from 237 to 404 to 13 to 23 per match and channel;
the insert reads "Ibsen cuts it out. To Rasmussen. Chested down. Long ball for Tavares. To Fontaine. GOAL!"; (2) the context layer is not a ticker: counters 55% of the context lines (was 68%), 1.4 lines a minute (was 1.9), `MINOR_GAP_S` 90 s, `STAT_MAX` 3,
`STAT_MAX_BY`, `NEWS_MAX`, no match fact in play, one fact per streak, an idea (sit deep) once per side, the pass count once per player, "once" and "one shot" instead of "one times"; (3) player notes of several facts say the club so the long-sentence share holds.
Measured x1: windows 16.1 segments per minute (gate 16, thin), matches 17.2 segments per minute, 6% long, insert coverage 76% (gate 75, thin); every gate that held in round 4 still holds; same NOT-met set (naming a player, names per 100 words, short share; the insert has 0% long). 699 tests green, 1 strict xfail.

Baked voice for the recorded run (2026-10-22, the user asked for ElevenLabs instead of the browser voice in Step 1): `backend/scripts/bake_insert_audio.py` made one mp3 per spoken line of `ui/public/insert/replay.json` (24 files, 812 KB, `ui/public/insert/audio/<ch>-<m>.mp3`; 736 credits of 33,800, 0 model calls). Voices: Charlie (English play-by-play), Daniel (English colour, all of German and French), energy per line from `delivery.py` (goal peak, analyst calm, rest rising). `speech.ts` has a `baked` option: Step 1 plays the file with no server and no key, a failure falls back to the browser voice and never switches the live voice off; Step 2 (live) still uses the browser voice. Checked in headless Chrome on the static build: the four en/expert lines fetched (200), played and ended, no exceptions. Re-run the script (`--go`) whenever the insert's `say` texts change: files are keyed by channel and moment id only, a stale file would speak the old text. Not heard by a human yet; de and fr voices (Daniel) are borrowed and unchecked.

Demo rework (2026-10-24/25, Windows PC, handed back to the Mac): the UI got six voice cards, a verifier proof modal ("Try to break it", `pipeline/proof.py`),
a dark palette, a stadium crowd bed (`ui/src/crowd.ts`, `ui/public/audio`, from a freesound community recording, low-passed so the chants read as distant;
chants naming real clubs must not be audible in the video), hype shaping for eleven_v3 (`delivery.hype_for_tts`), a dossier of club and player stories for quiet
spells (`sim/dossier.py`, `story_note` in `fast.py`), and a 30 s two-part story insert (`ui/public/insert/story.json`: comeback story at 68', cut, build-up and the
71' equaliser; `export-story-insert`; en/expert baked in `ui/public/insert/story-audio`, 475 ElevenLabs credits). 704 tests green, 1 xfail.
Open: the goal analysis in the story insert is a template fallback (needs 1 Haiku call, not approved yet); only en/expert has baked audio.
UI direction agreed with the user, NOT built yet: `ui/public/mock3.html` (served at /mock3.html, uses the insert's real data and audio) is the target:
a "Choose your commentator" picker (flags, language and level filters, search, inactive languages marked Soon), a stream-style player (DAZN/Prime score bug,
LIVE badge, subtitles, win probability as a data graphic, commentator name plate), and "How does it know?" with three columns (What arrives, What it understands,
What you hear). mock.html and mock2.html are earlier steps. Remove the mocks from ui/public before submission.
Open decisions for the user: generated faces (gpt-image-2.5-flare, about 13 calls; needs an OPENAI_API_KEY in .env, added by the user), and whether the
commentators need female or native de/fr voices before the faces are made.

Next, in order:
6. Record the video from docs/VIDEO.md.

## Known issues
- A measurement or test that runs the newsroom with a model call that raises must use a private `cache_dir`: `AnalystExecutor` discards the cached answer of a failing prompt (`GuardedLLM.discard`), also with `fresh=True`, and that deletes real recorded answers from `data/cache/analyst`.
- Bump `PROMPT_VERSION` in `analyst.py` whenever `SYSTEM` or `build_prompt` change; the cache key ignores the system prompt.
- xG is slightly high for point-blank shots. German templates need a native read-through, French has not been checked by a native speaker. Phase 12 rewrote parts of the de/fr bank (calques removed); both need a native read before the video.
- Real-time speaking time is about 15% with templates alone; more variety from the analyst is expected.
- A replay export is scheduled for one speed (speech durations are speed times seconds). `replay.json?speed=N` makes
  another one; a static player must not change speed on its own. Live runs choose wordings without foresight, so
  they pick longer lines and get cut more than a replay.
- Live analyst captions lag the event by the model call (about 6 s); at 10x that is a minute of match time. The voice may skip a line that waited too long.
- A live run costs calls only for prompts not in `data/cache/analyst`; after precompute the three demo matches run live for free, but as cached answers (see the live honesty fix below), not fresh calls.
- Live honesty fix: live mode used to serve cached analyst text as if fresh. Now cache hits are marked (`cached` on `say`,
  `lookup` log step instead of `writing`, wall latency logged, "Cached" chip, excluded from the analyst latency median), and
  `--live-fresh` / `MATCHVOICE_LIVE_FRESH=1` skips the cache entirely. All three demo matches are fully cached, so only
  `--live-fresh` (or `red_card-11`/new prompts) makes real calls there. A fresh run costs about 8 calls per match.
