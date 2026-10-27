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
- Languages (the user approved 9 languages on 2026-10-26): core en, de, fr at both levels (instant templates for play-by-play, the analyst writes the analysis),
  plus six world channels, one level each: es/expert, it/beginner, pt/expert, nl/beginner, tr/expert, ja/beginner (channel ids 6..11, after the core 0..5; solo booths;
  EVERY line by the model, play-by-play included, one call per moment, the same verifier). Styles: beginner, expert only.
- Agents run on the **Microsoft Agent Framework** (hero technology). Claude is the model behind it
  (`agent-framework-anthropic`). Do not switch to the Claude Agent SDK.
- Two prototypes from ONE pipeline: a **live** run with a visible log, and a **static replay** of a recorded
  run that needs no API key (public demo must work without a key).
- UI: one calm dark screen, no scrolling, no modals. One use case: the demo insert (Phase 10). No match picker, speed, scrubber, stats or log views.
- Overlay format must be high performance (compact updates, canvas rendering, no per-event React re-render).
- Prefer open source over custom code.
- Fictional clubs and players only. No real logos, marks or music in the video.
- Booth per channel (user, 2026-10-25), one source in `commentary/lang.py` `BOOTH`: leads Owen Carter (en/b), Charlie Hale (en/x), Felix Brandt (de/b),
  Jonas Weber (de/x), Théo Laurent (fr/b), Hugo Martin (fr/x); co-commentators Daniel Price (en), Kim Berger (de, a woman), Sacha Morel (fr, a man), unisex first names.
  World solo booths (user, 2026-10-26): Lucía Romero (es/x, woman), Giulia Conti (it/b, woman), Rafael Souza (pt/x, man), Sanne de Vries (nl/b, woman), Emre Aydın (tr/x, man),
  Yuki Tanaka (ja/b, woman); the lead says every line. `BOOTH` and `hello.channels` carry name, gender, lang, level. Ewan Marsh and Nadia Rowe (Phase 11) are gone. Players may get gendered pronouns only when the squad's gender is known (`TeamMeta.gender`; the Synthetic League is men).
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
    patterns.py        pattern detector (no lookahead): a habit of one side found in a quiet spell (pattern_insight, the co's set-up) and the goal that breaks it (pay-off)
    verifier.py        deterministic fact check (numbers, scorelines, players, language, length)
    director.py        speech scheduling under a time budget, interruptions, silence; live form (captions_first) captions at arrival, only the voice queues
    analyst.py         slow path prompt, guarded model call, cache, budget
    world.py           the world booth (es, it, pt, nl, tr, ja): its own system prompt (WORLD_PROMPT_VERSION), facts and room per moment; every world line is the model's
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
docs/ARCHITECTURE.md, SUBMISSION.md, VIDEO.md, img/   submission material (diagram, form text, video script, screenshots, GIF); PITCH.md was deleted 2026-10-27, SUBMISSION.md replaces it
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
Open (fixed 2026-10-25, next line): the goal analysis in the story insert was a template fallback; only en/expert has baked audio.
Story insert analyst line (2026-10-25, Mac): `export-story-insert --max-calls 2` made 1 real Haiku call for m163 (4.1 s, all six lines accepted first time, no retry; cache file `534b2f054c32475976221dcd.json`), then a cache-only re-export (0 calls) is what ships in `ui/public/insert/story.json`: the live-timed run voiced the analysis in only 3 of 6 channels (the expert lines expired behind the goal call), the cached one in all six at the old times. `mock3.html` LINES updated to the new text. 0 ElevenLabs credits. STALE: `ui/public/insert/story-audio/1-163.mp3` still speaks the old template line ("That goal lifts Wexmoor Athletic's chance of a win to 36 percent."); re-bake that one file before the video.
UI direction agreed with the user, NOT built yet: `ui/public/mock3.html` (served at /mock3.html, uses the insert's real data and audio) is the target:
a "Choose your commentator" picker (flags, language and level filters, search, inactive languages marked Soon), a stream-style player (DAZN/Prime score bug,
LIVE badge, subtitles, win probability as a data graphic, commentator name plate), and "How does it know?" with three columns (What arrives, What it understands,
What you hear). mock.html and mock2.html are earlier steps. Remove the mocks from ui/public before submission.
Open decisions for the user: generated faces (gpt-image-2.5-flare, about 13 calls; needs an OPENAI_API_KEY in .env, added by the user), and whether the
commentators need female or native de/fr voices before the faces are made.

Submission drafts and hosting prep (2026-10-25, no commit, nothing published, 0 calls, 0 credits): docs/VIDEO.md (8 shots, 1:45, game-first flow, shots marked NEEDS UI, a claims table),
docs/PITCH.md (five criteria, short) and README.md (quick start static / server / live, honest limitations) rewritten for the game-first UI. `.github/workflows/pages.yml` builds `build:static` and deploys
`ui/dist-static` to GitHub Pages on push to main (needs Pages enabled; private repo needs a paid plan, see docs/DEPLOY.md). `ui/vite.config.ts` drops `mock*.html` from the static build only. Checked: static build
under `/match-voice/` and at `/` in headless Chrome, no console errors, no failed requests, insert plays. Before the video: re-bake `story-audio/1-163.mp3`; `proof.json` still comes from `replay.json` (old insert lines).

Insert script encoded (2026-10-25, Mac; docs/INSERT-SCRIPT.md section 8 plus the user's four decisions; no commit, 0 ElevenLabs credits): the pipeline itself now speaks the script.
- `PROMPT_VERSION` v5 (the stopped run's unfinished v5 was reviewed and replaced): SYSTEM names the booth per channel, a goal co line is HOW first (one picture from the move's real facts) then ONE idiom,
  no score and no number in it (the score is the lead's), no percentage, probability, xG or count anywhere, room per channel in seconds, words and characters (`ROOM_S`, `room_of`), good examples
  in that shape, the three mood lines of the old insert on the bad list, beginner plain words vs expert technique words, "switch" (Verlagerung, transversale) allowed when a move step has `pass_type` switch
  (verifier: `claims_of` reads `move`, the de/fr switch patterns include Verlagerung and transversale). `MomentBuilder(engine, rows)` gives a goal analysis the move from the enriched rows (pass type, height, foot,
  first time, touch, technique, pressure, distance band, `move_seconds`), the chain is every player of the move; without rows (non-fast runs) the skeleton steps as dicts.
  `claude_llm` max_tokens 2048 -> 16000: Haiku 5.5 thinks by default and thinking counts toward max_tokens (two empty answers, then 3,947 output tokens for one answer, 16.4 s; live latency is now well over the old 4 to 6 s).
- Templates: goal call = shout, scorer, meaning (`goal_facet`: equaliser, opener, go_ahead, more, back) or the hit for a strike from outside the box, no score; `player_full` for the English full name. New
  kind `score_line` (runner `score_line_for`, id 900000 + analysis id, priority 60, voice wait 20 s): pushed when the goal analysis completes, so it is voiced after the co line, with the time left true to the clock
  (`time_left`: "twenty minutes or so", "knapp zwanzig Minuten", "une vingtaine de minutes"; none under five minutes). German writes scores 1:1 in templates; `shape_for_tts` says "eins zu eins" and French
  level scores "un partout" (`delivery.score_said`). Ticker words out (Abgefangen von, Brustannahme, Lang geschlagen, Intercepté par, Vers); per-type pass calls `WORDS["pass_call"]` / `pass_call_plain`
  for switch, long and first time, always used for a named typed pass and allowed to run 1.3 s past the arrival (`director.CALL_SLACK_S`); story notes are the lead's (`fast.LEAD_CONTEXT`, voice pbp);
  `_tidy` for clauses that carry their own end. Pronoun placeholders ({he}, {er}, {il}) render only with `squad` in the params (two kinds use them: big_chance_analysis). `GOAL_QUIET_S` 9 -> 15 s so the
  post-goal context comes after call, co line and score.
- Protocol: optional `who` on `say` (lead or co of the channel), documented as additive in docs/PROTOCOL.md, plus the `score_line` kind.
- Story insert: about 33 s (part 1 4238 to 4246, part 2 4382 to 4407; `STORY_LEAD_S` 1, `GOAL_LEAD_S` 11, `GOAL_TAIL_S` 13). 4 real Haiku calls of the 6 allowed: 2 empty answers (max_tokens), then 1 answer plus 1 verifier
  retry (fr/beginner said "frappe de loin", a trait claim). `ui/public/insert/story.json` re-exported from the cache (0 calls): all six channels voice story, build-up, call, co line (analyst), score line;
  every template line equals the script. Weak co lines: en/expert ends "Level" with no stop, de/expert "und wieder gleich" is a thin idiom, fr/expert "Tout est relancé." sits next to the lead's "Le match est relancé".
- 717 tests green, 1 xfail. Replay hashes re-measured (the replays now carry the score line and `who`). docs/EVAL.md and docs/DENSITY.md were not regenerated.
- STALE baked audio: every file in `ui/public/insert/story-audio/` that speaks a changed line: `1-3339167` (story), `1-1189316` (unchanged text, keep), `1-1189569`, `1-1189576`, `1-1189713`, `1-162`, `1-163`; `1-1189697`
  is unchanged text; there is no file for the new score line (`1-900163`), and channels 0 and 2 to 5 have no story audio at all. `1-152` to `1-155`, `1-1184328`, `1-1188808`, `1-1188936`, `1-1189061`, `1-3352221` are not in the insert any more.
  `ui/public/insert/audio/` belongs to the old `replay.json` insert. The story note is now the lead's voice (was the co-commentator's). mock3/mock4 still show Daniel Price in every booth.

Producer fixes to the story insert (2026-10-25, Mac; no commit, 0 ElevenLabs credits, 2 real Haiku calls of 3 allowed: 1 answer plus 1 verifier retry, fr/beginner "frappe de loin"):
- `PROMPT_VERSION` v6: the lead's line right after the co line (the score line) is in the prompt (`AFTER` keys in `recent`, `Runner._recent_for`), the co idiom must not repeat the call's meaning or the next line's idiom, no phrase twice in a line, a line ends on a stop; the v5 lines are on the bad list; good examples without "chez eux" / "Hinten den Ball geholt". Capitalised pronoun helpers never reach the prompt.
- Director: `BREATH_S` (0.7 s call -> co line, 0.4 s co line -> score line), and the score line waits while the co line is queued. Publisher: `finish_line` adds a final "." to an accepted line. `hype_for_tts`: only the first shout word is stretched ("BUUUT! But de Fontaine !").
- Templates: expert first-time call is the name alone ("Fontaine!", the goal cut it mid-name); de/b "Rüber zu X...", "Lang nach vorne auf X!"; fr/b "Ibsen récupère.", shorter fr story notes; shorter beginner score lines; fast fragments carry `squad`, `touch_bare_plain_pron` ("Il contrôle de la poitrine."). `GOAL_QUIET_S` 17, `GOAL_TAIL_S` 15.5 (part 2 to 4410), `demo.length` from the wall (37 s). UI browser voice says German "1:1" as "eins zu eins" (`speech.ts spokenForm`).
- At x30 replay the breaths (21 and 12 match s) drop some score lines (comeback-7 18 of 21, red_card-7 7 of 12, unlucky-7 3 of 6); replay hashes re-measured. 723 tests green, 1 xfail.
- STALE story audio, channel 1: 1-3339167, 1-1189569, 1-1189576, 1-1189713, 1-162, 1-163; missing 1-900163; channels 0 and 2 to 5 have none.

Analyst latency fix (2026-10-25, Mac; no commit, 0 ElevenLabs credits, 1 real Haiku call of 2 allowed): `claude_llm` uses `ANALYST_OPTIONS` = `max_tokens` 2048 and `thinking: {type: "disabled"}` (allowed on Haiku 5.5 at its default effort medium; passed through by agent-framework-anthropic). `GuardedLLM._fetch` never caches an empty answer: one retry taken from the same `CallBudget`, a second empty answer raises `EmptyAnswer` (template fallback). `PROMPT_VERSION` stays v6, so the cached insert answers stay valid; story insert not re-exported. Measured on a fresh prompt (red_card-11 goal, moment 114, `use_cache=False`, private cache dir): 2.14 s for the call (was 16.4 s with thinking), all six lines accepted first time, no retry. Seen in that answer: de/beginner and fr/beginner say "drei Pässe" / "trois passes", a count the v5 prompt forbids and the verifier lets through. 727 tests green (4 new in `test_empty_answer.py`), 1 xfail.

Insight set-up and pay-off (2026-10-26, Mac; docs/INSIGHT-SETUP.md option A; no commit, 0 ElevenLabs credits, 4 real Haiku calls of 6 allowed):
- `commentary/patterns.py` `PatternFeed`: fed every event in order, no lookahead (a test throws the later events away and gets the same set-ups). Habit `short_after_win`: a side has won the ball in its own half `MIN_WINS` (8) times this half,
  every first pass after it went short and no open-play ball went 30 m or more across. It fires in a quiet spell (a dead ball: a shot that is not a goal, a foul, a card, a ball out; no event for `QUIET_S` 5 s), once per side and half,
  one per spell (a named ball winner first), as moment `pattern_insight` (co voice, priority 50, id 800000 + 4 x (half - 1) + side). `broken_by(side)` at a goal: the possession began with an own-half ball win whose first pass went across.
  The habit was common in the sim (switches are rare); after the fact check (below) it fires once on four of the five demo matches; on comeback-135 for Wexmoor at 65', in the insert (a live run that joins at 4233) at 68'.
- Runner (live and `fast` only, `patterns=False` opts out; replays, recordings, guided live and the density report are unchanged): the detector is fed before the moment builder, asked on idle frames, its set-up goes through the newsroom like any model moment.
  `booth` (a dict, shared by the parts of the story insert) keeps the set-ups said with each channel's caption; a goal analysis of that side and half that breaks the habit gets `pays_off` facts and the set-up lines (`SETUP` keys in `recent`);
  a goal that does not break it gets the lines with "did NOT come that way: do not refer back". `say.ins` (evidence: zone, dots, arrows, players, counts, event ids) and log steps `detector/pattern` and `detector/payoff`, documented in docs/PROTOCOL.md.
- `PROMPT_VERSION` v7: pattern and pay-off sections, a good set-up example, `ANGLE_PAYOFF` (callback first, `first time`/`direkt` only for first_time steps), +1 s room for a pay-off, beginner style says no counts and the good examples lost "two passes".
  Verifier: habit claims (`habit_winner`, `habit_short`, `habit_never_across`) only with a pattern in the facts; the newsroom checks every model line with `spelled=True` (numbers two to twenty as words must be in the facts) and `style`
  (beginner: a count like "three passes", "drei Pässe", "trois passes", "elfmal" is `count_in_beginner`). Templates and tools call `check` without them, unchanged. `pattern_insight` templates (no count) are the fallback.
- Story insert re-exported (`export-story-insert`, then cache-only from a copy of the answer cache): part 1 is 4233 to 4249 (set-up at 4234.5, then the lead's story, cut before the corner at 4249.6), part 2 unchanged; 45 s as heard.
  Calls: run 1 (3 calls: set-up, goal, one fr/beginner retry for "frappe de loin"); the de/expert pay-off said "Ibsen direkt quer" (the pass was not first time) and three channels had no callback, so `ANGLE_PAYOFF` was sharpened (user prompt only) and run 2 made 1 call for the goal.
  Set-up (all six accepted first time): en/b "Ibsen keeps winning it back, and then it's always short. Nothing across, not once." en/x "Ibsen keeps winning it, and the first pass is always short. Nothing across."
  de/b "Ibsen holt sich die Bälle immer wieder, aber dann geht es nur kurz. Nie rüber." de/x "Ibsen holt den Ball, und dann immer kurz. Nie rüber." fr/b "Ibsen récupère le ballon, et derrière c'est toujours court. Jamais une longue transversale." fr/x "Ibsen récupère, et derrière, toujours court. Jamais de transversale."
  Pay-off: en/b "There it is. Ibsen wins it back, and this time it goes straight across, long to Rasmussen." en/x "There it is. Ibsen wins it, and this time it goes across, lofted to Rasmussen." de/b "Genau das. Ibsen holt den Ball, und diesmal geht er sofort quer rüber."
  de/x "Genau das. Ibsen holt den Ball, und diesmal rüber, quer auf Rasmussen." fr/b "Voilà ! Ibsen récupère, et cette fois la longue balle passe de l'autre côté." fr/x "Voilà ! Ibsen récupère, et cette fois, la transversale passe de l'autre côté."
  All six channels voice set-up, story, build-up, call, pay-off, score. `BREATH_S` gained set-up -> story 0.3 s (fr/beginner's story only starts inside its 3 s voice wait with that). Not read by a native de or fr speaker.
- UI `ui/public/mock4.html`: an insight card under the score bug ("PATTERN SPOTTED · 11 balls won in own half since half-time, none played across"; at the pay-off "CALLED IT 2:44 AGO · Ibsen wins it, this time the first ball goes across",
  match seconds between the two lines as the channel spoke them; a short text when the picture is small), the own half, the 11 ball wins and their 11 first passes on the board with Ibsen ringed; at the pay-off the switch arrow, the band it landed in,
  the short passes once more faintly, Ibsen and Rasmussen ringed. How mode lane 2: "Pattern found from 11 ball wins since half-time" and "Goal breaks the pattern from 68'". Timing note now reads the goal analysis only.
  Baked audio is not played for lines with `ins` or for 163 and 900163 (it would speak other words than the subtitle). Checked headless (own Chrome, ui/public on port 8773): no overlap of the card with bug, top right, win graphic, subtitles or name plate, card above the pitch,
  no page scroll at 1430x769 and 1920x1080 (also How mode), no console errors; screenshots in the session scratchpad `insight/`. `npm run build` clean; the built app loads the new story.json without errors.
- 742 tests green (15 new in `test_patterns.py`), 1 xfail.
- Fact check (2026-10-26, 0 calls, 0 credits): every claim of the six set-ups is true from events before 4234.5 (11 own-half wins since half-time, all 11 first passes under 26 m and short/back, 0 of 184 passes 30 m or more across, Ibsen 5 of the 11 and 13 ball wins in the match, team high), and the goal matches (i1479 own half, first pass i1481 switch, lofted, 49.5 m across, same second, to Rasmussen).
  Two detector defects fixed: (1) "short" was never checked, only "not across": 11 of the 15 set-ups on the five matches had a clearance, long or through first pass (38 to 51 m). Now every first pass must be under `SHORT_M` (30 m). (2) A free kick after the win no longer leaves the win open, so a pass 23 to 31 s later is not its "first pass" (comeback-135 i984, unlucky-7 i361).
  Set-ups now: comeback-135 H 2nd half (65' in a full run, 68' in the insert, unchanged), comeback-7 A 56', red_card-7 H 59', red_card-11 H 67', unlucky-7 none; all recomputed true from raw events (pinned in `test_patterns.py`). The shipped `story.json` evidence equals the new detector output, no re-export needed. 750 tests green, 1 xfail.
  Open: the verifier does not check whose number it is ("Ibsen keeps winning it, eleven times" passes; 11 is the team's, Ibsen has 5); `broken_by` has no time limit between the win and the goal.
- STALE audio: no file for the set-up (800004) on any channel; `story-audio/1-163.mp3` speaks an old line (now skipped by mock4); still none for 900163; the earlier stale list (1-3339167, 1-1189569, 1-1189576, 1-1189713, 1-162) is unchanged. `docs/DENSITY.md` excludes the set-up (`patterns=False`).

German and French set-up and pay-off fix, and six world channels (2026-10-26, Mac; no commit, 0 ElevenLabs credits, 13 real Haiku calls of the 16 allowed):
- Task 1, `PROMPT_VERSION` v8 (2 calls, set-up and goal, all 12 lines accepted first time): the habit as a habit ("Ibsen holt die Bälle"), German switch "rüber" / "Verlagerung" / "auf die andere Seite" and never "quer"
  (a square ball), a real callback "Genau das meinte ich.", fr/beginner "Jamais de l'autre côté.", fr/expert "transversale" said once; the v7 lines are on the bad list, a pay-off good example. Now in the insert:
  de/b set-up "Ibsen holt die Bälle immer wieder, aber dann geht es immer nur kurz." pay-off "Genau das meinte ich! Ibsen holt den Ball, und diesmal geht's sofort auf die andere Seite.";
  de/x "Ibsen holt die Bälle, und dann immer kurz. Nie rüber." / "Genau das meinte ich. Ibsen holt ihn, und diesmal sofort rüber."; fr/b "Ibsen récupère le ballon, mais après, toujours court.
  Jamais de l'autre côté." / "Voilà ! Ibsen récupère, et cette fois, ça part de l'autre côté !"; fr/x "Ibsen récupère, et derrière, toujours court. Jamais de transversale." / "Voilà ! Ibsen récupère, et cette fois,
  transversale tout de suite." The answers follow the new good examples almost word for word. The core prompt is frozen at v8 since (the world booth has its own), so these answers stay cached.
- Task 2, world channels: `lang.py` (`Booth`, `Person`, `CORE_KEYS`, `WORLD_KEYS`, `ALL_KEYS`, CPS estimates for the new languages), `commentary/world.py` (WORLD_SYSTEM: six solo booths, register and shout per language,
  score 1-1 / 1対1, katakana names, no percentages, xG or traits, good examples from the Harbour fixture; `world_facts` gives raw facts, never English template text; room per kind and level), the newsroom runs
  the same Analyst -> Verifier -> Publisher workflow for the world keys (no template fallback: a line that fails twice is not said, log step `dropped`), `Runner(world=...)` adds directors 6..11:
  a moment the English booth (ch 0 or 1) captions is queued, one call per moment writes all six lines, calls run one after another (deterministic continuity: each prompt sees the lines the booth wrote
  before, so a cached re-run builds identical prompts). `LiveConfig.world_call` / `world_budget`, server `--world-calls N` (off by default, own budget so world calls never starve the core analysis).
  `GuardedLLM(version=)`, `claude_llm(instructions=)`. Replays and recordings without the world booth keep six channels.
- Verifier for es/it/pt/nl/tr/ja: stop words (and Turkish/Spanish letters), a world channel is checked against all nine languages and is wrong only by a clear margin (es, it and pt share function words),
  Japanese by script (kana); number words two to twenty per language (Japanese kanji numerals only with a counter, 十分な is not ten), count nouns, the whole claims and traits lexicon in six more languages,
  scores with 対, sentence split on 。！？. Names: Latin names in Japanese are matched without word boundaries ("Ibsenが"); decision: Japanese may write players in katakana as Japanese TV does, and a
  katakana word is mapped to the roster by its consonant skeleton (r/l, b/v merged, one edit allowed from four consonants), so イブセン is Ibsen and ペトロフ outside the moment is `player_unsupported`; no football
  loanword maps to a player on the five demo matches (test). Also new for every model line: no em dash and no middle dot ("·", "・"), code `punctuation`; and `comeback_win` (a comeback record counts points,
  draws included, so "won", "virou", 逆転勝ち are wrong; scoped to the comebacks story). Delivery: "uno a uno", "um a um", "één-één", "bir bir", 1対1.
- Story insert re-exported with all 12 channels (paid run, then cache only, 0 calls; 46 s as heard, was 45): 10 world calls (one per moment, all 60 lines accepted first time), then 1 retry call for the story note
  after `comeback_win` was added (es "ha ganado tres veces", pt "virou três jogos", ja "3度逆転勝ち" overstated the record). World continuity is what the booth wrote first, before the check, so that retry changed no
  later prompt. Every channel voices all 10 moments, 0 skips; the world first-time fragments are cut by the goal call. `WORLD_CONTEXT_WAIT_S` 6 s: a solo booth's story waits for its own set-up (it/b and nl/b
  dropped the story before). Measured latency (the paid run, paced 1x, real calls): calls 1.1 to 2.6 s (median 1.3), world captions 1.2 to 4.4 s behind the English booth, event to caption median 2.6 s, max 5.7 s.
- World lines in the insert (set-up, story, interception, switch, chest, long ball, first time, goal, pay-off, score):
  es/x Lucía Romero: "Wexmoor recupera en campo propio y luego siempre en corto. Ni un balón cruzado desde el descanso." "Tercera vez esta temporada que el Wexmoor suma puntos tras ir por detrás." "Intercepta Ibsen."
  "Ibsen cambia a Rasmussen." "Rasmussen, de pecho." "Rasmussen, largo a Tavares." "Tavares, de primeras." "¡GOOOL! ¡Fontaine! ¡Empata el Wexmoor!" "¡Lo que les decía! Ibsen la recupera y esta vez, cambio de
  orientación al instante para Rasmussen." "Uno a uno, y quedan unos veinte minutos."
  it/b Giulia Conti: "Il Wexmoor recupera palla nella sua metà campo, ma poi passa sempre corto. Dal riposo nessun pallone dall'altra parte." "Il Wexmoor ha già rimontato tre volte quest'anno, dopo essere stato sotto."
  "Ibsen intercetta." "Ibsen, dall'altra parte." "Di petto, Rasmussen." "Lungo per Tavares, a sinistra." "Tavares, di prima." "GOOOL! Fontaine! Pareggio del Wexmoor!" "L'avevo detto! Ibsen recupera palla e
  stavolta subito dall'altra parte, a Rasmussen." "1-1, e mancano una ventina di minuti."
  pt/x Rafael Souza: "O Wexmoor rouba no seu campo e sempre passa curto. Nenhuma inversão desde o intervalo." "Terceira vez na temporada que o Wexmoor soma pontos depois de ficar atrás." "Ibsen rouba."
  "Ibsen inverte para Rasmussen." "No peito, Rasmussen." "Lançamento longo para Tavares." "Tavares, de primeira." "GOOOL! Fontaine! Empata o Wexmoor!" "Não falei? Ibsen rouba e, dessa vez, inversão na hora
  para Rasmussen." "Um a um, e faltam uns vinte minutos."
  nl/b Sanne de Vries: "Wexmoor wint de bal op eigen helft, maar speelt daarna altijd kort. Sinds de rust nooit naar de andere kant." "Wexmoor heeft dit seizoen al drie keer een achterstand omgebogen."
  "Ibsen onderschept." "Ibsen speelt naar de andere kant." "Op de borst, Rasmussen." "Lang naar Tavares, links." "Tavares, direct door." "GOAL! Fontaine! Wexmoor maakt gelijk!" "Zie je, dat zei ik! Ibsen wint de
  bal en nu meteen naar de andere kant, naar Rasmussen." "1-1, en nog zo'n twintig minuten te gaan."
  tr/x Emre Aydın: "Wexmoor kendi yarısında topu kapıyor, hep kısa pas. Devreden beri çapraz top yok." "Wexmoor bu sezon üç kez geriden gelip puan aldı." "Ibsen kesti." "Ibsen'den Rasmussen'e çapraz."
  "Göğsünde, Rasmussen." "Tavares'e uzun top." "Tavares'e, tek vuruş." "GOOOL! Fontaine! Wexmoor eşitledi!" "Söylemiştim! İbsen topu kaptı, bu kez hemen Rasmussen'e çapraz pas." "Bir bir, yaklaşık yirmi dakika var."
  ja/b Yuki Tanaka: "ウェクスモアは自陣で奪っても、いつも短いパス。後半、反対側へのボールは一度もありません。" "今季、ウェクスモアは3度、負けていた試合から勝ち点を拾っています。" "イブセンがカット。" "イブセンから反対側へ。"
  "ラスムッセン、胸で。" "左のタバレスへ長いパス。" "タバレスへ、ワンタッチ。" "ゴール！フォンテーヌ！同点！" "言った通りです！イブセンが奪って、今度はすぐ反対側のラスムッセンへ！" "1対1。残りはおよそ20分です。"
- Weak, for a native read (nobody has read or heard these): es "Ibsen cambia a Rasmussen." is no broadcast Spanish for a switch; it "rimontato" and nl "een achterstand omgebogen" lean towards a win (the verifier lets them
  through); tr writes "İbsen" once (Turkish capital I); the world set-ups name the team, not Ibsen; it/b and nl/b set-ups run about 9 s (room 6.5); speech times use estimated CPS, no voice measured; no ElevenLabs
  voice for the new languages (`tts/voices.py` has en/de/fr only). `ui/public/mock4.html`: one fix so a solo booth is read from `hello.channels` (`solo`, `lead` object), nothing else changed. Checked headless (own Chrome, ui/public on port 8779): mock4 plays every new channel with its name plate, the "Soon" row is gone,
  no console errors, no page scroll at 1430x769 and 390x844. The user's rule (no "·", no em dash in user-facing text): the separators in `ui/src/components` Proof, Voices and Stage
  became commas and the empty trace placeholder in `styles.css` says "none"; `npm run build` clean. `ui/public/mock.html` and `mock2.html` still have 13 each (old mocks, not in the static build).
- 769 tests green (19 new in `test_world.py`), 1 xfail. The replay hashes in `test_fast.py` were re-pinned: with the new `hello.channels` fields taken out the three streams hash to the old digests.

Story insert voice baked, all 12 channels (2026-10-26, Mac; no commit, 0 Anthropic calls, 5,075 ElevenLabs credits = sum of `character-cost`, cap 11,000; subscription 12,795 of 33,800 before): `backend/scripts/bake_story_audio.py`
(dry run by default, `--go`, `--channel`, `--limit`, `--max-credits`, 2 requests at a time) voices every `say` of `story.json` with `eleven_v4` (1.0 credit a character, measured), cast per speaker (`who`), `language_code` per channel,
delivery as in the v4 audition: goal call `[shouting]` with stability 0.25 and style 0.8, pay-off and lines ending "!" `[excited]`, the rest untagged. 120 files `ui/public/insert/story-audio/<ch>-<m>.mp3` (3.3 MB) plus `manifest.json`
(per file a hash of voice, model, settings and sent text, and the caption): an up-to-date file is skipped, a stale one re-made, a file no line needs deleted (the 9 old ch-1 files went). New solo voices (premade, GET /v2/voices):
Lucía Romero Sarah, Giulia Conti Matilda, Rafael Souza Eric, Sanne de Vries Lily, Emre Aydın Brian, Yuki Tanaka Jessica. `delivery.py` TAG_MODELS and STYLE_MODELS include `eleven_v4`; `bake_insert_audio.py` is the goal insert only now.
`mock4.html` reads the manifest and plays `<channel id>-<m>.mp3` only when the manifest caption equals the subtitle (no more en/expert-only list, `ins` lines play too). Checked headless (own Chrome, ui/public on 8791): en/expert, es/expert, ja/beginner
fetch all 10 files (200), 7 to 9 end; the others are cut by the next line as designed (first-time fragment by the goal call) or run past their slot (ja set-up 7.3 s, es and ja switch 2.2 to 2.3 s). Nobody has listened yet. 770 tests green, 1 xfail.

Seek in mock4 (2026-10-26, the user asked; supersedes "no scrubber" in Decisions for the demo page): the progress bar is clickable and draggable, ArrowLeft/ArrowRight jump 5 s. `seek(w)` restarts at w, restores the score and the line on air (its baked file starts at the offset, the browser voice stays quiet mid-line), the insight card and montage resume at the right age, cuts ahead of w still play, a paused seek stays paused. Checked headless: back to 4 s (montage 6 / 11, card, 0-1), to 38 s (1-1, pay-off), no console errors.

Live "New run" on the public demo (2026-10-27 night, founder approved "planen + machen"; plan docs/live/PLAN.md, reports docs/live/UNDERSTAND.md; no commit, no push):
server `matchvoice.server.public` (scene whitelist `pipeline/scenes.py`, winner = comeback-135 5431 to 5490, HMAC session tokens, 3 runs a session, 10 an IP a UTC day,
3 at once, 150 runs / 600 calls / 3,000 voice credits a day (900 a session, 1,500 an address since the review fixes), in memory, reset on restart; `row` stream message; `/api/session`, `/api/scene`, `/api/tts` with Flash voices per person;
Origin allowlist; IP = rightmost X-Forwarded-For, `MATCHVOICE_TRUSTED_HOPS=1`). Deployed on Azure Container Apps `encara-live` (env `encara-env`, centralus, 1 replica)
at https://encara-live.agreeablemeadow-1641ec5a.centralus.azurecontainerapps.io, image `encaramv630916.azurecr.io/match-voice:20261027-1603` (run cues, deployed 2026-10-27 16:10; before 20261027-1251, 20261027-0109); ACR Tasks are not allowed on this
subscription, so build locally with `docker buildx --platform linux/amd64 --push`. Turkish "İki" crashed the verifier's number words (KeyError), fixed in `verifier.py` with a test.
Page: `mock4.html` live branch (`LIVE_API` constant, `?api=` override), runs open in How mode 3 s behind the generator, lane 1 rows, lane 2 model calls with real times, voice per line from
`/api/tts`, browser voice fallback; dev launcher `docs/live/devserver.py` (fake model and voice). Four-lens review, all majors fixed. SWA redeployed. End to end against the deployed
server: en/expert at 1430x769 (18 ElevenLabs lines, analyst line sent back once and rewritten) and ja at 390x844, no console errors; forged X-Forwarded-For does not move the IP count.
Spend for all live testing: about 23 Haiku calls, 329 ElevenLabs credits. Open: a ja (world) viewer hears nothing until the goal (world booth skips the fast build-up); the
founder may want New run to default to a core channel. 804 tests green, 1 xfail.
New run in the top bar and live-only motion (2026-10-27, page only, backend unchanged, no commit): `#topnew` next to How (hidden while a run streams and on the end screen, which has its own New run and count);
a refusal clicked during a replay of a new run jumps that replay to its end screen. When the board shows live data (`D.isLive`) only: passes under 5 m are drawn as a carry by the player on the ball,
receivers start a run up to DELAY-1 (2 s) before the kick (`preRuns`), break and pass-and-go runs after a ball win, a 10 m/s speed cap, the close-up to the ball with a 3 m dead-zone shape ball (`sbTrack`)
and less wander, after the goal everyone stops where the goal found them (`goalSpots`, the board run up to the goal once off screen), the scorer and a few teammates celebrate, then each walks back into
their own half. The recorded run is byte-identical (all players, 30 fps).
Generated live scene (2026-10-27, founder: "massively optimise only the LIVE mode"; no commit, no push, 0 model calls, 0 ElevenLabs credits): the plain
match's live window stuck the ball at the corner flag (19 of 26 on-ball points of 5431 to 5490 within 2.1 m of a line, a 0 m pass) and every New run streamed
the same rows. Now every New run plays a new phase (`sim/scene.py` `ScenePlan`, hooked into `Sim.step` at Tamsworth's goal kick at 5408.6; `Library.scene_bundle`
with an LRU of 8; `bundle()`, the recorded insert, EVAL and replays are untouched and pinned by `tests/test_scene_guard.py`): the keeper takes the goal kick
7 to 9 s later, Tamsworth build up under Wexmoor's press, Wexmoor win it (interception in midfield, or a pressed ball back cut out near the box),
then one of five finishes (through ball, switch and cross with a header, cutback, one-two at the edge, full back's cross) and the 2-1 in
5462 to 5471.5 (89'). Scene window 5415 to 5490 (75 s, the run cap; it was 5431 and would have been refused at 84 s). Receivers are picked where the page
draws them (`sim/sceneshape.py` ports `FORM` and `shapeOf`; a test parses mock4's `FORM`), passes 6 to 50 m with length-based flight, no ball on a line,
presses after the ball arrived (else enrich squeezes), no tackles. `secrets` seed per run, `hello.scene_seed`, a `facts`/`scene` log, `seed=` only on a
server that is not public (`docs/live/devserver.py --not-public` plus `&seed=N` on the page); `recent_memo` is keyed by variant; `/api/scene` has
`goal_t` null and `goal_window`. Fakes name the run's scorer (katakana for ja). mock4 (live only): carries are drawn (the page ignored carry rows), `?seed=`
is passed through. 839 tests green (35 new), 1 xfail. Measured over 5 seeds in headless Chrome (devserver, fake model): 0 of 31 to 45 on-ball points per
scene on a line, pass median 10 to 15 m, top speed 10 m/s, ball to holder 0.93 m median, receiver to pass end at the kick median 5.7 to 7.7 m; 4 public
runs (en, ja, en, ja at 390x844): goal call on all channels with the right scorer, 2-1, end screen, no console errors; the recorded run's positions are
identical at 30 fps. The backend changed: the Container Apps image must be rebuilt and redeployed (and SWA for mock4).
Scene review fixes (2026-10-27, after a three-lens review; no commit, no push, 0 model calls, 0 ElevenLabs credits): scene (`sim/scene.py`): no counter-press
(`COUNTER_PRESS_P = 0`, one turnover per play), the ball winner by zone and role (midfield regains go to the central and wide midfielders, high
regains to the strikers), the presser by role and flank (no centre back presses high), Tamsworth press Wexmoor's attack (about 30% of its passes
under pressure, a full back closes the winger as he sets off before a cross), the counter is a run in behind by a striker who did not win the
ball (pass end 7 to 20 m beyond his spot, met first time, a 7 to 8.5 m/s carry), cross targets 4.5 to 11 m out with no clamp, cutback runner and
shooter and the edge finisher rotate (Tavares 30%, Dacosta 36%, Fontaine 26%, Abara 8% over 1,000 seeds; 964 distinct goal spots), Tamsworth's
build-up plays one ball back and goes across before back (a back-and-forth swung the whole board), most finishes
under pressure, `validate()` refuses a pass to oneself; enrich: a goal kick under 24 m is played on the ground (no plain-match goal kick is that
short; all five matches' enriched rows checked identical). Booth (`fast.py`, only with `scene_at`, which the runner sets for a generated scene):
no context line from Wexmoor's ball win to the goal, a carry is play from its first stride, one carry line per 8 s in the attack, a receipt is
not called within 0.3 s of the shot and a header waits 1.2 s, a cut-out short pass is not "played on", cross, cutback and through ball outrank a
touch (priority 38, wait 1.5 s): over 16 fake-booth runs every final ball was called and no context line fell in the attack. Server: the scene is
simulated only after the session, IP and concurrency checks; voice caps 900 a session, 1,500 an address (global 3,000 a day unchanged). Page
(live only): the side without the ball defends its box (back four 6 to 13 m out and narrow, nearest defender 2.4 to 3.4 m from the scorer at the
shot), the keeper takes his goal kick (0.93 m from the ball), a run with under 250 credits left starts in the browser voice, lane 1 says metres
instead of "Short", headers once, "met first time", carry and press rows name the player, "1 commentator", phone rows wrap. A forged-token test
was flaky 1 time in 16 (it appended "0" to a real token), fixed. 849 tests green, 1 xfail. The backend changed again: rebuild and redeploy the image.

Live picture 1 s behind instead of 3 (2026-10-27, founder: "das ist aber nicht realtime"; no commit, 0 model calls, 0 ElevenLabs credits): the 3 s
buffer existed for the board's runs before a kick (up to 2 s). The runner now sends `run` cues (`proto.runs`, `RUN_LEAD_S` 2.5) with rows on: per targeted
pass the runner, passer, pass type, pressure, spot and times, before the kick; the booth never reads them (same lines with rows off, `test_run_cues.py`).
mock4: `DELAY` 1, `RUN_LEAD` 2, cues become receiver and keeper anchors, pre-kick runs (`FLH`) and pressure until the pass row arrives, and name the restart
at the start. Measured with a live-arrival emulator (8 seeds, 115 passes, board rebuilt every 0.25 s from what the server had sent): without cues at 1 s,
26 receivers more than 2 m off the ball at arrival (16 m worst); with cues at 1 s, 4 (as at 3 s), positions differ from the full-knowledge board by more
than 1 m in 0.1% of player frames (the opening second only). Devserver runs en 1430x769 and ja 390x844: run starts 1.1 s after the click, 2-1, no errors.
852 tests green, 1 xfail. Deployed (image 20261027-1603, revision encara-live--0000005, SWA): a real en run started 2.0 s after the click (session, scene, socket, 1 s buffer), 2-1, no errors, 21 ElevenLabs lines, /api/tts median about 0.48 s, 19 of 21 under 1 s, max 1.06 s.

Booth memory, offside, live voice energy (2026-10-27 evening, founder: "the commentators lack the brain of earlier facts", "watch out for offside",
"the voices are not hyped enough"; 0 model calls, 0 ElevenLabs credits in the build):
- Memory: `FactEngine.so_far` gives every live core and world prompt a "match so far" block (minute, score, every goal with minute, scorer and the score
  it made, how it got here, red cards, late). The model only had the score after the goal and "it was level" before. `PROMPT_VERSION` v9,
  `WORLD_PROMPT_VERSION` w3. Verifier: earlier scorers and minutes count as facts only in goal calls, analyses, score lines and the scene line; a goal
  minute must go with its scorer (`history_mismatch`); opener and goalless phrases after earlier goals are rejected. New scene-setting line
  `match_state` (id 850000) after the first call of a mid-match live run ("Eighty-eight minutes gone, one-all, and Wexmoor have fought back from a goal
  down."), world copy from its own call, dropped when stale. Recordings opt out (`rejoin=False`). Tests in `test_match_memory.py`.
- Offside: the page's live motion holds every player off the ball behind the drawn offside line until his pass is played (`onside(out,w)` in
  `positions()`); `sim/scene.py` only picks pass ends an onside runner can reach. 40 seeds: receivers offside at the kick 43 -> 0, other attackers
  214 -> 0, goal moves 39 of 80 -> 0; runs in behind kept (32), receiver accuracy and speed cap unchanged, recorded run byte-identical.
- Voice (live only, the recorded run is unchanged): `MATCHVOICE_TTS_DELIVERY=1` on the container app (shaped text, per-energy Flash settings, peak
  lines hyped: "GOOOAL!"); `Runner._scene_energy`: in a generated scene, late and level, every play-by-play call is at least rising, the final ball
  (cross, cut-back, through) and shots are peak. Page (live only): the crowd bed rises from 0.09 to about 0.21 as the attacking side nears goal,
  goal roar 0.75 with the bed at 0.3 for 8 s.

Next, in order:
6. Record the video from docs/VIDEO.md.

## Known issues
- A measurement or test that runs the newsroom with a model call that raises must use a private `cache_dir`: `AnalystExecutor` discards the cached answer of a failing prompt (`GuardedLLM.discard`), also with `fresh=True`, and that deletes real recorded answers from `data/cache/analyst`.
- Bump `PROMPT_VERSION` in `analyst.py` whenever `SYSTEM` or `build_prompt` change; the cache key ignores the system prompt. The same for `WORLD_PROMPT_VERSION` in `world.py` (`WORLD_SYSTEM`, `build_world_prompt`).
- World continuity is the lines the world booth wrote first, before the verifier, so later prompts stay stable when a rule changes; a rejected line can therefore appear in the next prompts' continuity block.
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
