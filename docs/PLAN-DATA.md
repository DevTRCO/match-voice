# Build plan: the rich synthetic data layer

Design: `docs/DATA-MODEL.md` (section numbers below refer to it). Today is 2026-10-21, submission closes 2026-10-27 23:59 PT.
Method as in `docs/PLAN.md`: Sonnet builds, Opus reviews, Sonnet fixes, Opus re-checks. Every phase ends with a hard gate. Nothing is committed or
pushed without the user. No model call and no ElevenLabs call before phase 7, and phase 7 only after the user approves the budget below.

Reviewed by Opus (adversarial pass, 2026-10-21). Changes against the first draft: the phases are reordered so the voice gets denser before movement
is built (the event-level enrichment and the fast layer need no tracking, DATA-MODEL 0 and 4.2); gates that were unreachable or meaningless were replaced
by measured ones; the cache table was corrected (live runs of the demo matches already miss the cache today); the runner is no longer edited by two
phases in parallel. The design-side fixes are listed in DATA-MODEL section 11.

## Model tiers

| Tier | Does | Never does |
| --- | --- | --- |
| Opus 5.5 | this design; the review at every gate (invariants, no-lookahead, determinism); the caster review of every new template in en/de/fr; the final whole-system review | write bulk code |
| Sonnet | builds phases 1 to 6 and 8, fixes review findings, writes tests and docs | spend model calls; change Decisions in CLAUDE.md |
| Haiku (`claude-haiku-5-5`, runtime only) | writes analyst lines through `GuardedLLM` in phase 7 and in live runs | build anything |

## Order and why

| Phase | Date | Needs tracking | Delivers |
| --- | --- | --- | --- |
| 0 decisions | 2026-10-21 | | the open decisions below |
| 1 player and team model | 2026-10-22 morning | no | profiles, roles, traits, tactics plan, postures |
| 2 event enrichment | 2026-10-22 afternoon | no | arrival retiming, receipts, gap repair, pass type and height, shot and set-piece fields |
| 3 fast and context layers | 2026-10-23 | no | the dense voice and the density report: the user's complaint, fixed first |
| 4 micro-simulation and tracking | 2026-10-23 evening to 2026-10-24 | is it | 22 players and ball xyz, pressure objects, runs, duels |
| 5 Interpret on tracking | 2026-10-25 morning | yes | runs in behind, line breaks, shape, press, overloads, `tactical_shift` facts |
| 6 protocol, board, MCP | 2026-10-25 | yes | `tk`, `f.x`, dots on the board, four MCP tools |
| 7 analyst v5 and recording | 2026-10-25 evening to 2026-10-26 | uses it if phase 4 passed | v5 prompt, 34 Haiku calls, the insert re-recorded |
| 8 evaluation, docs, video | 2026-10-26 to 2026-10-27 | | DENSITY.md, EVAL.md, README, PITCH, VIDEO, the video |

**Cut line.** If phase 4 has not passed its gate by the end of 2026-10-24, stop it: phases 5 and 6 shrink to the event-based insights (posture, PPDA, tempo,
counters, `fatigue_base`) and the MCP `player_profile` tool, the board stays as today, and phase 7 starts on 2026-10-25 with `shape` built from the tactics
plan only. Phases 1 to 3 and 7 still ship profiles, tactics, pass types and heights, receipts and the dense voice.

Runner edits are serialized: phase 3 owns `pipeline/runner.py` and `commentary/director.py` on 2026-10-23, phase 5 owns the Interpret wiring, phase 6 the `tk`
emission. No two Sonnet sessions edit the runner at the same time.

## Phase 0: decisions (user, 2026-10-21)

See "Open decisions for the user" at the end. Phases 1 to 3 need decisions 1, 3, 6 and 7; phase 4 needs 1; phase 6 needs 2; phase 7 needs 4 and 5.

## Phase 1: player and team model (Sonnet, 0.5 day, 2026-10-22)

Build: `sim/profile.py` (1.1 to 1.3), `sim/tactics.py` (2.1 to 2.3, postures compose with `ten_men`), optional fields on `schema.Player` and `TeamMeta`,
`python -m matchvoice.sim` writes them to `meta.json`.

Gate:
- SHA-256 of `events.jsonl` and `truth.json` for comeback-7, red_card-7, unlucky-7, red_card-11 identical before and after (`shasum -a 256 data/matches/*/events.jsonl data/matches/*/truth.json`).
- `Sim(arc, seed).run()` output unchanged for 50 seeds per arc (compare with the pre-change code).
- Posture shifts: exactly comeback 3, red_card 4, unlucky 2 for seeds 1..50 (test); red_card home is `ten_men + chase` after 61'.
- Every player has a role and at most 2 traits; one `set_piece_taker` and one captain per team; traits follow the rules (test per rule).
- 280 existing tests green.

## Phase 2: event enrichment without tracking (Sonnet, 0.5 day, 2026-10-22)

Build: `sim/micro/enrich.py` for every field DATA-MODEL 4.2 marks "known at kick" and 4.1 to 4.5 can fill from the skeleton, the profiles and the tactics
plan: arrival retiming and dwell filler (3.3), receipts, gap repair (implicit passes and carries, 3.4), `target`, `pass_type`, `height`, `body_part`,
`technique`, `first_time`, `t_arr`; shot `body_part`, `technique`, `first_time`, `assist_eid`, `placement`; set-piece and foul fields that need no positions;
`take_on` lost from tackles. Tracking-only fields (`pressure` object beyond the flag, cone, box counts, aerial duels) stay empty until phase 4.
Writes `enriched.jsonl` for the 4 demo matches plus comeback-135. These kick fields are final: phase 4 must conform to them, never rewrite them.

Gate:
- `eid = 16 * i + k` unique and increasing; regenerating a window gives the same eids; overflow count 0 (or listed).
- Every `t_arr` lies in `[t + T, t_next - 0.25]`; share of `first_time` passes per match reported (expected 15 to 30% after retiming; 0% before, measured).
- Pass mix inside the plausibility ranges of 4.2 (report table for 4 matches; the ranges are recollection, so a miss is reviewed, not auto-failed).
- Ball touches (pass, carry, shot, receipt) per minute >= 24 per match; touches in the insert window = 7 (1481, receipt, 1482, receipt, 23714, receipt, 1483).
- Every `under_pressure` skeleton event has `pressure.under == true`.
- The insert's goal has `assist_eid` 23714 (Tavares) and the build-up `interception, switch (1481, 53.6 m, 49.5 m across), long (1482), short (implicit 23714), shot`
  (or the review explains a different chain).
- No kick row carries an outcome field (test over all rows: `outcome`, `assist`, receipt data only on resolution rows).

## Phase 3: fast and context layers (Sonnet writes, Opus caster review, 1 day, 2026-10-23)

Build: `commentary/fast.py` (7.1, 7.2) on the phase 2 data, with the event-based context kinds (`player_note`, `counter_note`, `fatigue_note`, `tempo_note`)
and `shape_note` / `press_note` / `phase_note` from the tactics plan only (tracking versions come in phase 5); derived moment ids (0.2); templates for the 12 fast
kinds and 7 context kinds in en/de/fr x beginner/expert (2 to 3 wordings each, about 230 strings, name-less fragments included, 7.1); director settings per kind
(ttl, voice wait, one fast line per 1.2 viewer s, newer fragment replaces older, fast captions at voice start, context cap one per 40 s in play and one per 10 s
in a dead ball); `long_ball` and `pass_final_third` not pushed when the fast layer is on; shortest skeleton wording in play; the v5 continuity rule in
`Runner._said` (7.3: skeleton and analyst captions only, no skip removal); verifier claims lexicon (7.5); `evaluation/density.py`.

Start of the phase, before templates: a **density dry run** with one placeholder wording per kind ("Name." / "Name, forward.") through the real director, on the
insert and the 20 guided windows, 0 calls. If segments per minute or coverage miss the gate by more than a quarter, the rules change before 230 strings are
written.

Gate, the **density report** (`python -m matchvoice.evaluation.density`, writes `docs/DENSITY.md` and `data/eval/density.json`, 0 calls; analyst lines come from
the template fallback here, so the numbers are a lower bound for the analyst share):

| Metric (x1, per channel) | Profile | Gate on the insert | Gate on the median of 20 guided windows | Gate over the 3 full matches |
| --- | --- | --- | --- | --- |
| Segments per minute | 22 | >= 16 | >= 16 | >= 12 |
| Words per minute (en channels only, 7.6) | 131 | >= 75 | >= 75 | >= 60 |
| Speech coverage | about 90% | >= 75% (today 76 to 81%, it must not fall) | >= 70% | >= 55% |
| Gaps over 3 s | 2.5% | <= 12% | <= 12% | <= 20% |
| Segments of 5 words or fewer | 56% | 40 to 70% | 40 to 70% | 40 to 70% |
| Segments of 12 words or more | 10% | 5 to 20% | 5 to 20% | 5 to 20% |
| Segments naming a player | 38% | 30 to 55% | 30 to 55% | 30 to 55% |
| Names per 100 words | 9.3 | 6 to 14 | 6 to 14 | 6 to 14 |
| Words per minute 30 s after a goal vs match | +19% | not gated (the insert has 8 s after the goal) | > 0% | > 0% |
| Captions skipped by the voice (skeleton and analyst lines) | n/a | <= 35% | <= 35% | <= 35% |

All six channels must pass on the insert; on the windows and full matches the gate is the median over channels and the worst channel is listed.
Also: verifier accepts 100% of template renderings on 5 matches (the existing caster test, extended to the new kinds), no digits, no dashes, no gendered pronouns,
de and fr fragments within 7 words; `pipeline/guided.py` window choice unchanged for 50 seeds (it must score skeleton moments only).

Fast and context wording may still change after this phase: with the v5 continuity rule it does not enter any analyst prompt, so it costs no call.

## Phase 4: micro-simulation and tracking (Sonnet builds, Opus reviews, 1.5 days, 2026-10-23 evening to 2026-10-24)

Build: `sim/micro/segments.py`, `kinematics.py`, `ball.py`, `plan.py` (appointments, planned runs including decoys), the tracking fields of 4.1 to 4.5, numpy
declared in `pyproject.toml` (the `Runner` opt-in flag comes with phase 6, which owns the runner then), a dev-only PNG dump (three frames of the insert, Pillow as in Phase 5) for the visual review.

First step, before the kernel is tuned: measure step cost on comeback-135 at 10 Hz. If a full match is over 3 s, drop the internal rate to 5 Hz (the wire is
5 Hz anyway) and record that in DATA-MODEL 3.1.

Gate (all measured, reported in the phase note):
- Invariants of AUDIT 3.3 as tests, with `t_arr` for the pass end: ball at `(x, y)` at event time and at `(end_x, end_y)` at `t_arr`; actor within 1.0 m;
  player speed p99 <= 9.0 m/s and max <= 9.8 m/s outside counted violations; keeper inside x 0..20 of its own goal (attacking frame); a sent-off player has no
  position after the card; half-time side swap.
- Appointment violations < 1.5% per match (measured floor before any build: 0.2 to 0.6%), reported per kind, 0 inside the insert window 4381 to 4402.
- Realism: off-shape distance per player p50 and p90 reported; share of completed passes whose receiver is more than 12 m from the end at kick time and not on a
  planned run, reported (target under 25%; the skeleton's own geometry puts the median receiver anchor 20 m away, DATA-MODEL 3.2).
- Served share of planned `in_behind` runs between 30 and 60% per match (decoys keep "in behind!" from foretelling the pass).
- Determinism: same bytes for the insert window generated alone and cut out of a full-match run; same bytes in two processes; same SHA-256 for the insert window on
  the dev Mac and in the Docker image.
- Cost: full match < 3 s, a 75 s window with its lead-in < 300 ms (dev Mac, `time python -m matchvoice.sim.micro --match comeback-135 --from 4381 --until 4402`).
- Test suite time does not grow by more than 20 s (tracking is opt-in).
- Opus looks at the three PNGs: back lines straight-ish, block shifts toward the ball, Ibsen's 53.6 m switch visibly lofted, Tavares arrives where 1482 lands,
  no player standing still for the 4.2 s Rasmussen holds the ball.

## Phase 5: Interpret on tracking (Sonnet, 0.5 day, 2026-10-25 morning)

Build: `interpret/` (5.1 to 5.14), wired into `Runner.stream` after `FactEngine.ingest` and once per frame, catch-up from `start - LOOKBACK_S`; the existing
`FactEngine`, `MomentBuilder` and `InsightFeed` stay untouched. The tracking versions of `shape_note`, `press_note`, `phase_note` and the fast kinds `in_behind`,
`line_break`, `press_on`, `duel_1v1` switch on. `precompute` gains the same feed (micro-sim plus Interpret from kick-off), because it builds the v5 facts block.

Gate:
- No-lookahead test of section 5 (perturb or delete everything after `now`, tracking generated once) for every insight kind on the three demo matches.
- Start-independence test of section 5 on the insert and five other windows.
- Every insight has non-empty `ev` or `fr`.
- Precision and recall of `run_in_behind` and `line_break` against `micro_truth.jsonl` >= 0.8.
- Existing moment ids of the three demo matches unchanged (compare `[(m.id, m.kind, m.t)]` with the pre-change run): `ReplayMismatch` must not fire for `data/replays/*`.
- Runner cost per live frame < 2 ms for Interpret (measured at 1x over the insert).
- The density report of phase 3 re-run: no metric falls below its gate.

## Phase 6: protocol, board, MCP (Sonnet, 1 day, 2026-10-25; needs decision 2)

Build: `tk` and `f.x` in `pipeline/protocol.py` and `docs/PROTOCOL.md` (8.1), the runner emits one `tk` per frame and one keyframe at `start` when tracking is on;
`ui/src/tracking.ts` and the board (8.2); the four MCP tools (8.3) and `docs/MCP.md`.

Gate:
- A v1 client without `tk` support plays the new stream (old `ui/public/insert/replay.json` and a new one both play in the current UI build, no console errors).
- Bandwidth measured on a 1x live run of the insert: under 16 kbit/s (estimate about 10, DATA-MODEL 8.1).
- 60 fps (median 16.7 ms, no frame over 20 ms) through the insert, headless Chrome with its own profile as in Phase 14; no scroll at 1430x769, 1920x1080, 1280x720, 390x844.
- MCP stdio smoke: 11 tools listed, `tracking_at` and `team_shape` on comeback-135 at 4389.6 s return 22 positions and a line height.
- `test_pipeline.py` kind set, `test_evaluation.py` speech share bound and `test_live_captions.py` caption timing for fast kinds updated on purpose, nothing else loosened.

## Phase 7: analyst v5 and re-recording (Haiku, 0.5 day, 2026-10-25 evening to 2026-10-26; needs decisions 4 and 5)

Build (Sonnet, before any call): `PROMPT_VERSION` v5, `build_prompt` with `shape`, `build_up`, `people` (7.3), the `tactical_shift` kind with templates and fallbacks,
`MODEL_KINDS` extended, `precompute` emits shifts (id `2_000_000 + eid`), the facts block checked under 250 extra tokens on the 34 prompts (count with a tokenizer
estimate, 0 calls). A dry run of every phase 7 prompt with a stub model (records the prompt, raises, writes nothing) prints the 34 prompts and confirms the count
before the first real call.

Order of calls, every call through `GuardedLLM` with a hard `CallBudget`:

| Step | What | Haiku calls (first attempts) |
| --- | --- | --- |
| 7a | smoke: the first 2 analyst moments of comeback-7 in precompute order (a momentum moment and the 14' goal), read by Opus and the user | 2 (counted in 7b: the prompts are identical, so 7b reads them from the cache) |
| 7b | `precompute` comeback-7: 8 existing moments + 3 shifts | 11 |
| 7c | `precompute` red_card-7: 9 existing + 4 shifts | 13 |
| 7d | `precompute` unlucky-7: 7 existing + 2 shifts | 9 |
| 7e | `export-insert` comeback-135: the 71' goal analysis (no shift falls inside 4381 to 4402) | 1 |
| | **Total** | **34** |

Where the numbers come from: existing model moments per recording are counted from `data/replays/*/analyst.json` (8, 9, 7; checked); they do not change because
the skeleton, the fact engine and the moment builder do not change. Shifts per arc are fixed by the beats (DATA-MODEL 2.3, checked against `arcs.py`). Verifier
retries cost one call each; the recordings themselves have 0 retries, the live and insert runs since had 2 in about 14 calls (Phase 7 and Phase 9 notes in CLAUDE.md). **Approval asked: a budget of 40
Haiku calls (34 expected, up to 6 retries).** If the smoke leads to a prompt change, the 2 smoke calls are lost and the total is 36 (cap stays 40). ElevenLabs: 0
credits (the UI uses the browser voice).

Separate, for the video only: each live take of a guided window with `--live-fresh` costs 1 call (its goal analysis) or 2 when a posture shift falls into the window
(rare: the shift takes effect at the kick-off 30 to 55 s after the goal, the window ends 14 s after it). Two takes: at most 4 calls under `--live-calls 4`.

Gate: `docs/EVAL.md` regenerated (0 calls): grounding 100% of accepted lines, every goal found and spoken on all 6 channels, truth coverage not below 93.8%; all
34 moments published, fallbacks listed by moment; the insert re-exported with `export-insert` (cache only after 7e) and the density gate of phase 3 re-run on it.

## Phase 8: evaluation, docs, video (Sonnet, Opus final review, 2026-10-26 to 2026-10-27)

Build: `docs/DENSITY.md` final, `docs/EVAL.md`, `docs/PROTOCOL.md`, `docs/MCP.md`, README (data layer section, honest limits), `docs/PITCH.md` (data innovation
category), `docs/VIDEO.md` (below), CLAUDE.md status and Decisions (Phase 14 reversal recorded, the stale "demo matches run live for free" line corrected), with
the user's go-ahead for the CLAUDE.md edits.

Gate: full test suite green; fresh-clone path from Phase 5 (temp copy, `pip install -e ".[dev]"`, pytest, replay with `MATCHVOICE_NO_DOTENV=1`, static build plays the insert);
every number in README, PITCH and VIDEO found in `docs/EVAL.md` or `docs/DENSITY.md`; no em dashes; fictional names only. The video itself is recorded on
2026-10-27 at the latest; the voice choice (open since Phase 11) and the native read of de and fr fragments must be settled before that.

## Effect on caches and recordings

| Artifact | Effect | Cost |
| --- | --- | --- |
| `data/matches/*/events.jsonl`, `truth.json` | unchanged (gate in phase 1) | 0 |
| `data/matches/*/meta.json` | new optional fields | 0 |
| `data/matches/*/enriched.jsonl`, `micro_truth.jsonl` | new | 0 |
| `data/cache/analyst` (38 entries) | all miss after v5 (prompt version, facts block and continuity rule change); old entries stay on disk, unused | phase 7 |
| `data/replays/*/analyst.json` | ids of existing moments still match after phases 1 to 6, so replay keeps working until phase 7 rewrites them with v5 and the shifts | 33 calls in phase 7 |
| `ui/public/insert/replay.json` | changes in phase 3 (dense lines, new continuity) and phase 6 (`tk`, `f.x`). The goal prompt changes with v5 and with the continuity rule, so the file cannot be re-exported from the cache before 7e; until then the old file stays as it is | 1 call in 7e |
| Rule for the insert | with the v5 continuity rule only skeleton and analyst captions enter the goal prompt, so later fast or context wording changes cost nothing. A change to a skeleton wording or a goal-call wording in the 12 s before the goal still costs 1 call | |
| `data/cache/tts` | untouched; new lines would cost credits only if ElevenLabs were used, which the UI does not | 0 |
| `data/eval/results.json`, `docs/EVAL.md` | regenerate (speech share and line counts rise by design; `long_ball` and `pass_final_third` leave the spoken set when the fast layer is on) | 0 |
| Live runs on the three demo matches | they miss the cache today and will after phase 7: `precompute` builds continuity from published analyst lines, a live run from director captions. Measured with a stub model (0 spend): 8 of 8 comeback-7 and 9 of 9 red_card-7 prompts uncached at v4. Only the insert and runs that repeat an earlier live run hit the cache | a fresh live run of a demo match costs about 8 calls |

## Risks

| Risk | Effect | Mitigation |
| --- | --- | --- |
| Movement looks robotic or wrong next to the events | the board undermines trust, the reverse of the goal | role offsets, jitter, appointments, dwell filler; the Opus PNG review in phase 4; the board shows dots only after the gate passes; cut line on 2026-10-24 |
| Skeleton events that a body cannot follow | violations, teleports | gap repair, arrival retiming and appointment planning; measured floor 0.2 to 0.6% before any build; gate 1.5%; the insert must have none |
| Receivers chosen far from the ball by `_nearest` | players leave the shape early and visibly | measured (median 20 m); realism measures gated in phase 4; if it looks wrong the planner may start the receiver's move at the previous event, never change the skeleton |
| The voice cannot keep up with the fragments | many skips, the voice sounds clipped | fragments replace each other instead of queueing and are captioned only when voiced, ttl 1.5 to 2.5 s, one fast line per 1.2 s; the density dry run at the start of phase 3 |
| Too many names | sounds like a roll call | name rationing (7.1); names per 100 words gated |
| Tactics in tracking but not in event statistics (DATA-MODEL 2.3) | a "pressing high" line while PPDA says passive | the analyst gets the posture label; the press insight needs tracking and events to agree for `intense` |
| de and fr fragments sound translated | weak in the video's language switch | Opus caster review; keep fragments to names plus one verb; native read before the video (open since Phase 11) |
| Time: 6 days, 8 phases plus the video | late features, no video | reordered so the voice is dense by 2026-10-23; cut line for tracking on 2026-10-24; cut list in this order if still late: `overload`, `tempo_note`, `duel_1v1`, MCP `possession_chain`, the shape line on the board |
| Prompt grows | latency and cost per call up slightly | facts block capped at about 250 tokens, checked on the stub dry run; latency checked on the smoke calls |
| Cross-platform float differences | determinism breaks on another machine | kernel limited to correctly rounded operations, fixed summation order, output in decimetres; checked on the dev Mac and in Docker only |
| Retries above 6 | budget runs out mid-recording | `CallBudget` stops at 40; precompute writes nothing partial; the user decides on more |
| Season numbers read as real stats | credibility | everything is labelled synthetic; decision 5 lets the user drop them |

## What a 2 minute video can show

Only numbers measured by phase 8 go into the voice-over; the figures below in brackets are targets, to be replaced by the measured ones. If the tracking cut line
is used, shot 1 shows the dense captions over the existing board instead, and shot 3 shows the event evidence only.

| Time | Shot | What it proves |
| --- | --- | --- |
| 0:00 to 0:12 | The board before and after: today 2 dots and a ball, now 22 players shifting as a block, the ball rising on Ibsen's 54 m switch (shadow and height) | the data layer exists and moves |
| 0:12 to 0:42 | The insert at 1x, captions on: "Ibsen cuts it out. Rasmussen. Long for Tavares. Tavares, inside to Fontaine... GOAL!" then Nadia on the build-up | density: a line every few seconds, names and ball movement (target 16+ lines per minute against 11 today) |
| 0:42 to 1:02 | "Why this line" on the lay-off and the line break: the insight, its event ids and frame range, the arrow on the board | every sentence still traces to data, now including tracking |
| 1:02 to 1:20 | The same goal in en/expert, de/beginner, fr/expert | personalisation unchanged |
| 1:20 to 1:38 | The density report next to the broadcast profile: segments per minute, coverage, short fragments, names per 100 words, before and after | measurable closeness to real commentary (726 broadcast halves) |
| 1:38 to 1:55 | Claude Desktop over MCP: "Who is tiring for Wexmoor?" answered by `player_profile`, "How high is Tamsworth's line?" by `team_shape` | the data is an API, not only a picture |
| 1:55 to 2:00 | One line: synthetic, deterministic per seed, fictional clubs, no real data | rules met |

## Open decisions for the user

Each with the options and the reviewer's recommendation. Nothing in phases 1 to 3 starts before 1, 3, 6 and 7 are answered.

1. **Architecture A** (skeleton frozen, micro-sim fitted to it). Pro: events, truth, ids, recordings and the insert stay put. Contra: movement is fitted to
   events, not the cause of them; receivers are often far from the ball (median 20 m) and the planner must hide that. Alternative B (agent rewrite) does not
   fit the deadline. Recommendation: A.
2. **Board shows 22 players, ball height and one shape line** (reverses Phase 14). Pro: the data is visible, the video's first shot. Contra: if the movement
   looks wrong it costs trust; Phase 14 left dots out on purpose. Recommendation: yes, but only after the phase 4 gate and the Opus PNG review, with the cut line.
3. **The voice talks most of the time** (target 75 to 90% coverage, 16+ segments per minute, mostly short fragments). Pro: sounds like a broadcast. Contra:
   busier, more lines to review in three languages, the browser voice may sound choppy on fragments. Recommendation: yes; judge it by ear on the insert after phase 3.
4. **Haiku budget of 40 calls** for phase 7 (34 expected), plus at most 4 for two fresh video takes. The 40 build calls of the first budget are 36 spent.
   Recommendation: approve 40 plus 4.
5. **Synthetic season numbers spoken as context** ("sixth of the season"). Pro: the context topic is about one segment a minute in real commentary. Contra: a judge
   may read them as real stats. Alternative: match-internal context only. Recommendation: keep, labelled synthetic in README and PITCH.
6. **Fast fragments are captioned only when voiced.** Pro: captions match what is heard, the skip share stays honest, fewer messages. Contra: departs from the
   Phase 8 rule "every line is captioned the instant it arrives" for fragments; a muted viewer sees fewer touches. Alternative: caption every fragment at arrival
   and accept a skip share above 40% (the skip gate would then count skeleton and analyst lines only, as it does now). Recommendation: caption when voiced.
7. **Phase order: dense voice first, movement second.** Pro: the measured complaint is fixed by 2026-10-23 with no tracking risk; tracking can be cut without
   losing it. Contra: the fast layer is tuned twice (event-only, then with runs and pressing); kick-time fields cannot use tracking (pass height is drawn by length,
   not by defenders in the lane). Recommendation: this order.
8. **The fast layer replaces the skeleton pass calls `long_ball` and `pass_final_third`.** Pro: no double call, and no wording that says the pass arrives before it
   does (today "and Rasmussen gets onto it" is captioned 2.7 s early, a lookahead the live rule forbids). Contra: two kinds that are in today's recordings, EVAL
   numbers and screenshots leave the spoken set. Recommendation: replace.
9. **Determinism scope.** Same bytes per `<arc>-<seed>` are checked on the dev Mac and in the Docker image only, not claimed for any machine (CPython `random.gauss`
   and the skeleton's `math.exp` use the platform libm). Recommendation: accept, and word the pitch as "deterministic per seed on the shipped image".
10. **Live runs of the demo matches are not free.** Measured today: none of their prompts are cached (continuity differs between `precompute` and live). Options:
    (a) accept and correct the CLAUDE.md line in phase 8; (b) make `precompute` run the live runner unpaced so its prompts equal a live run from kick-off (a live run
    from another start would still miss). Recommendation: (a); only the insert and fresh guided windows matter for the demo.
11. **The video depends on two open items from earlier phases**: the voice (Phase 11) and a native read of the de and fr bank, now with about 230 more strings.
    Recommendation: decide the voice by 2026-10-25 and limit the native read to the strings in the insert and in the two guided takes.

## Decisions taken by the user (2026-10-21)

Approved: architecture A (skeleton frozen, micro-simulation on top), the board shows all 22 players with ball height and a shape line (only after the phase 4 gate
and the Opus PNG review), the voice talks most of the time, the phase order (dense voice first, tracking second). Haiku budget: the user lifted the limit
("unlimited, Haiku costs almost nothing"); the `CallBudget` guard stays in the code as a safety net and is set per run (400 for phase 7 and video takes),
never removed. ElevenLabs stays out of the live runs. The remaining decisions (5 to 11) are taken as the reviewer recommended, listed above, and stay open
for the user to veto: season numbers kept and labelled synthetic, fast fragments captioned only when voiced, the fast layer replaces `long_ball` and
`pass_final_third`, determinism claimed per seed on the shipped image only, live runs of the demo matches not free, decide the voice by 2026-10-25.
