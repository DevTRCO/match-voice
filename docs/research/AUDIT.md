# Audit: what a richer synthetic data layer would touch

Research B. Read-only audit of the repo at the state of 2026-10-21 (280 tests green, no commit of the working tree). Every number below was
measured with code run for this audit (scripts in the session scratchpad, no model call, no ElevenLabs call, port 8000 untouched), or is marked as
quoted from another doc, or as my recollection and unverified.

## Summary

1. The generator is a single-threaded possession chain. It never models where the other 20 players are. The only per-player state it has is a
   formation anchor and three hidden attributes (`passing`, `finishing`, `pace`), and neither is exported. That is why there is nothing to say about
   shape, runs, pressing or roles.
2. The event stream is denser than the brief assumed: 20 to 22 events per minute, median gap 2.6 s between events, a pass, carry or shot every 3.3 s.
   The thinness is downstream. Only 8 to 10 percent of events become a commentary moment (about 2 moments per minute against 22 segments per minute in
   real broadcasts, `docs/COMMENTATOR.md`), and the event rows we already have carry fields that the protocol drops (pass difficulty, ball speed, pressure
   flag, body part, carry speed). So there are two separate gaps: a missing fast layer of moments, and missing data.
3. Least damage: a **sidecar tracking layer** computed after the events from `(meta, events, seed)` with its own random stream, delivered as a new
   protocol message kind and a new optional file. `events.jsonl`, `truth.json`, moment ids and the committed analyst cache stay byte-identical. The
   expensive traps are: touching the main RNG stream, inserting moments before the existing ones (ids shift), and adding any new spoken line to a live
   run (the analyst prompts include the last three lines each channel said, so every cached prompt changes).
4. The streaming budget is not the problem. 23 entities at 5 Hz are 138 bytes per message as delta JSON, about 5.5 kbit/s raw, against about 0.6 kbit/s
   for the whole current stream. The real costs are test and doc churn, the 4 remaining build calls, and keeping the browser drawing from one rAF loop.

---

## 1. How the generator works today

Files: `backend/matchvoice/sim/engine.py` (508 lines), `sim/arcs.py` (75), `sim/names.py`, `schema.py` (101).

**Seed and ids.** `Sim(arc, seed)` owns one `random.Random(seed)`. Match id is `<arc>-<seed>`. The same id gives the same events, so every cache
(analyst answers, TTS, replay export) is keyed off that determinism. The generator takes about 25 ms per match (measured, 20 seeds).

**Setup, all random from the one stream, in this order:** two club names and colours; per team a formation (4-4-2, 4-3-3, 4-2-3-1); 11 players each with
a given name and a surname (unique within the match), and gaussian `passing`, `finishing`, `pace`; team `attack`, `defense`, `press`, `finishing`,
`tempo` (arc skills override some); stoppage times `stop1` (60 to 180 s) and `stop2` (120 to 300 s). So any new `rng` draw anywhere before or inside
the match loop shifts every later number in the match.

**What a step is.** `Sim.step()` handles one on-ball action by the current carrier, in attacking-normalised coordinates (x from own goal line to
the opponent's), converted to pitch metres at emit time. Order of decisions per step: pending set piece; scripted arc beat; foul (1 percent times `press`);
pressure flag and optional `pressure` event; shot if x > 68 with a distance based probability; else carry 20 percent, short pass 40, progressive pass 30,
long pass 10. A pass picks a target by random forward and lateral offsets, computes `length`, `difficulty`, success probability from length, passer skill,
pressure and team edge, and picks the receiver with `_nearest`. `_nearest` weights players by `exp(-d/11)` where each anchor has drifted 35 percent
towards the ball. That is the only place player positions exist, and it is implicit.

**Time.** Time advances inside the actions: pass duration is `length / ball speed (14 to 24 m/s)` plus a dwell of `uniform(1.6, 4.6) / (0.6 + tempo)`; carries
use distance over a speed of 2.5 to 9 m/s; fouls add 12 to 25 s; a goal adds 30 to 55 s and a kickoff; an out ball adds 6 to 14 s; a red card adds 40 to 70 s.
Two periods, `end_t = stop1 + 5400 + stop2`.

**Scripted versus random.**

| Scripted by the arc | Random |
| --- | --- |
| Every goal (count, side, minute): `Beat` in `arcs.py`; natural goals are forbidden, a saved shot is the best a natural shot can be | Everything else: passes, carries, shots that are not goals, pressure, tackles, interceptions, fouls, yellow cards, out of play, corners |
| The red card (who is random among DEF and MID, when is scripted) | Which player is on the ball (`_nearest`) |
| `Window` boosts: a side's edge is multiplied by `1 + boost` for minutes `start..end` (3 arcs, 1 or 2 windows each) | Formation, ratings, team skill (unless the arc sets it), stoppage times |
| Goal build-up: when a beat is due, the scheduled side gets 2 to 4 forced-success progressive passes and a forced goal shot (`_scripted_attack`); after 45 s without the ball for that side, `_steal` hands it over | xG per shot (geometry formula), shot speed, body part |

**How `truth.json` is made.** The sim appends `TruthItem`s as it goes: one `momentum_swing` per `Window` at construction (start, end, side, importance 0.6),
one `goal` per forced goal at the moment the shot is emitted (`t` of that shot), one `red_card` when the card is emitted. They are sorted by `t`
and written next to `meta.json` and `events.jsonl` by `python -m matchvoice.sim`. Truth is therefore a label written by the generator, and the evaluation
(`evaluation/metrics.py::coverage`) compares detected moments with it (goal and red card within 30 s, swing within the window minus 60 s lead).

**What the generator emits.** `Event` (pydantic, `extra="forbid"`) has 11 types: kickoff, pass, carry, shot, tackle, interception, pressure, foul, card,
possession_change, period_end. One acting player per event (`player`, optional `receiver`, `keeper`), a start position, an optional end position.
`MatchMeta` has per player only `id, name, number, pos, group`. The attributes, the formation anchors and the stamina-like fields (none exist) are not exported.

**Measured, three demo matches plus the insert match (`comeback-135`):**

| Match | Events | Per min | Passes | Passes per min | Pass accuracy | Pressure | Carries | Tackles | Interceptions | Shots |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| comeback-7 | 2,031 | 20.9 | 1,193 | 12.3 | 84.2% | 134 | 255 | 23 | 135 | 31 |
| red_card-7 | 2,132 | 22.0 | 1,221 | 12.6 | 83.1% | 153 | 276 | 28 | 151 | 22 |
| unlucky-7 | 2,162 | 22.3 | 1,279 | 13.2 | 85.8% | 156 | 259 | 36 | 135 | 32 |
| comeback-135 | 1,975 | 20.4 | 1,153 | 11.9 | 84.6% | 149 | 237 | 27 | 130 | 33 |

Durations are 97.0 minutes (5,822 s) because of stoppage time. Roughly 9 of 10 actions are passes or possession changes. There are no headers outside
corners, no crosses, no dribbles, no through balls, no clearances, no throw-in or goal-kick distinction beyond `set_piece`, no off-ball event of any kind
except `pressure`.

Conclusion for the brief: the generator has one ball, one actor per event and no off-ball world. Everything a commentator says about the other players has
no source.

---

## 2. Consumers of the event schema and what breaks

Legend for "change type": **F** = new optional field on `Event` or `Player`; **P** = new protocol message kind (for example `p` for positions) or new
event-row positions appended; **R** = anything that changes the main random stream or the events already generated; **M** = new commentary moments.

### 2.1 Producers and readers in the backend

| Consumer | File | Reads | Breaks on F | Breaks on P | Breaks on R | Breaks on M |
| --- | --- | --- | --- | --- | --- | --- |
| Loader | `facts/__main__.py::load`, `pipeline/library.py` | `events.jsonl` via `Event.model_validate`, `meta.json` | No: old files still validate (new fields default `None`). Writer uses `exclude_none`, so old matches stay byte-identical | No | Disk matches no longer equal a regeneration (they are equal today: checked for all four, events and truth) | No |
| Fact engine | `facts/engine.py` | type, team, player, x, y, end_x, outcome, xg, set_piece, length, speed, shot_speed, body_part, reason, keeper | No | No | Facts, win probability series, snapshots all change | Only if a new fact kind is added (additive) |
| Moment builder | `commentary/moments.py` | type, outcome, set_piece, length, receiver, x/y, card | No | No | Moments change, ids shift | **Ids are a running counter (`MomentBuilder._next`)**: inserting moments before existing ones renumbers every later one |
| Templates | `commentary/templates.py` | moment kind and params | No | No | Wording unchanged | New kinds need en/de/fr x beginner/expert x 2 to 3 wordings; a test checks placeholders, no digits, no dashes, verifier pass on 5 matches, length at most 130 |
| Verifier | `commentary/verifier.py::allowed_for` | numbers from moment params and snapshot stats only | No | No | No | Any number a new moment wants to say must be a moment param, or the verifier rejects the line |
| Analyst prompt | `commentary/analyst.py::build_prompt` | moment params, snapshot (possession, shots, xG, win probability), **last 3 lines per channel** | No | No | Every prompt changes | **Every analyst prompt after a new spoken line changes** (see 2.3) |
| Director | `commentary/director.py` | moments, priority, ttl | No | No | No | `min_priority=25` drops low priority moments; `interrupt_min=90`; the live same-template-slot rule; more fast-layer lines change who speaks and who is cut |
| Runner | `pipeline/runner.py` | events grouped per `dt`, facts, moments | No | A new message needs to be emitted from the tick loop; `_flush`, heartbeats and `trim_catch_up` assume only `f`, `say`, `voice`, `log`, `hb`, `end` | Yes | Yes (jobs, tasks, `_said`) |
| Protocol encoder | `pipeline/protocol.py` | event to a fixed 11-int row (`EVENT_FIELDS`) | Not unless exported | New `EVENT_FIELDS` entries are append-only safe for the UI (fixed indices up to 10); `test_pipeline.py:95` asserts `len(row) == len(EVENT_FIELDS)` so it follows the constant | Yes | No |
| Insights | `pipeline/insights.py` | facts only | No | No | Yes | No |
| Guided window | `pipeline/guided.py` | simulates a fresh `<arc>-<seed>`, scores windows by summed moment priority | No | No | Window choice changes (random per call anyway) | **Window scoring uses summed priority, so a dense low-priority layer changes which window wins** |
| Export | `pipeline/export.py`, `pipeline/demo.py` | `Runner.collect`, demo insert fixed to `comeback-135`, goal number 2 | No | New file or message needs a decision about whether the static replay carries it | Insert would move: goal 2 of seed 135 must still exist at the same time | Insert re-export raises on a cache miss (it passes `no_call`) |
| Server | `server/app.py` | `/ws`, `/sse`, `replay.json`, `/api/matches`, `/api/guided-live`, `/api/demo-insert` | No | `replay.json` is `orjson.dumps(build_replay(...))`, GZip middleware at 1000 bytes; WebSocket sends one text frame per message, no batching | Cache of replays is in memory only | No |
| MCP | `mcp_server/tools.py` | facts, snapshots, `Runner` replay `say`s | No | Reads only `say` messages, ignores the rest | `verify_sentence` allows players of the last 60 s; results change | `commentary_at` returns different lines |
| Evaluation | `evaluation/*.py` | messages, moments, `truth.json` | No | A new kind is ignored; `test_pipeline.py::test_replay_stream_is_ordered_complete...` asserts `{m["k"] ...} == {"hello","f","say","log","end"}`, which fails on a new kind | `docs/EVAL.md` and `data/eval/results.json` regenerate (no key, no calls) | Same, plus coverage and speech share move |
| Delivery / TTS | `commentary/delivery.py`, `tts/*` | moment priority, story tag; line text | No | No | No | TTS cache is keyed by model, voice, language, text: new lines are new credits (0.5 per character) |

### 2.2 UI consumers (`ui/src`)

| File | What it reads | Effect |
| --- | --- | --- |
| `protocol.ts` | `Msg = Frame | Say | Voice | Log | End | Heartbeat`; `EV` fixes indices 0 to 10 (`i,type,side,player,x,y,ex,ey,outcome,xg`, set piece is index 9 and unused by the UI) | A new message kind falls through `Sim.ingest`'s `if/else` chain and is ignored, so P is safe for the UI. Appended row positions are safe. Reordering existing positions is not |
| `sim.ts` | `ingest` per kind; `frame()` keeps a `recent` ring of 48 events (`RING`) and `events`/`eventsAt` maps keyed by event id; catch-up frames (`f.t < hello.start`) update state only | Tracking would need its own typed-array ring; do not push 23 rows per sample into `recent` |
| `pitch.ts` | One rAF loop. Ball and arrows are drawn from `recent` rows (`ex/ey`, comet trail). One name tag per acting player. | Ambient formation dots were left out on purpose in Phase 14 ("would read as tracking data"); adding positions is a reversal of that decision and needs a line in CLAUDE.md |
| `gamelog.ts` | `writeEvent`, `describeRow` over type, outcome, player, xg | Unknown fields are ignored |
| `derive.ts`, `components/Logs.tsx`, `Evidence.tsx` | Lanes from `log` messages by `m` (moment id); evidence box finds the event "through the frame time and the moment kind", shown only when exactly one event qualifies | **Moment ids are the join key** for lanes, evidence and `said` map (`"ch:m"`). A dense fast layer makes the "exactly one event qualifies" rule fire less often unless the new moments carry their own evidence ids |
| `player.ts`, `feed.ts` | WebSocket, `hello`, `start`/`until`, `analyst_from` carry on a speed change | Unaffected by new kinds |
| `speech.ts` | Voice queue: `say.s/e`, skip, stale, urgent | A denser caption stream raises the skip count. Rules `LIVE_VOICE_WAIT_S` (3 s caller, 6 s analyst) and stale cap 4 s will drop many lines if the layer is not tuned |
| Static assets | `ui/public/insert/replay.json` (13.5 KB, 6 frames, 9 events, 24 `say`, 59 `hb`), copies in `ui/dist` and `ui/dist-static` | A re-record is needed whenever wording, prompt or protocol shape changes. Re-record command: `python -m matchvoice.pipeline export-insert` |

### 2.3 Caches, recordings, truth and numbers: the concrete blast radius

| Artifact | Key | Survives if | Dies if |
| --- | --- | --- | --- |
| `data/matches/*/events.jsonl`, `meta.json` (4 matches: comeback-7, red_card-7, unlucky-7, red_card-11) | files | F only (fields default `None`) | R: a regeneration no longer equals the file (today it does) |
| `data/matches/*/truth.json` | files | Truth is written by the sim, independent of any sidecar | R: positions of goals change in time |
| `data/replays/*/analyst.json` (3 files, 144 lines) | `moment_id`, plus `kind` and `t` checked with 0.05 s tolerance in `Runner._prepass` | Existing moment ids, kinds and times unchanged | Any renumbering raises `ReplayMismatch` ("record the replay again"); a re-record costs real calls |
| `data/cache/analyst/*.json` (38 entries, 152 KB) | `sha256(PROMPT_VERSION | model | prompt)[:24]` | Same prompt text. The prompt is the moment kind and params, the match snapshot, **and the last 3 lines each channel showed**, plus `PROMPT_VERSION` | Any change in `SYSTEM`, `build_prompt`, snapshot content, or in the continuity lines (a new play-by-play line before an analyst moment). The bump rule is in CLAUDE.md "Known issues" |
| Recorded insert `replay.json` (`comeback-135`, 4381 to 4402 s, goal at 4393.7 s, 71') | the live run's captions and one cached goal answer | Nothing in the window changes | Any new line inside or just before the window changes the goal prompt's continuity block: `export-insert` raises (`no_call`), a real call is needed |
| `data/cache/tts/` | model, voice, language, text | Same text | New or reworded lines cost credits; the ledger counts a spend even if the audio was not heard (Phase 9 lesson) |
| `data/eval/results.json`, `docs/EVAL.md` | generated | Regenerate with `python -m matchvoice.evaluation` (0 calls) | Quoted numbers in `README.md`, `docs/PITCH.md`, `docs/VIDEO.md`, `CLAUDE.md` (818 lines, 100.0 percent grounding, 9.9 percent analyst, 93.8 percent coverage, 1,374 frames, 281 KB) go stale and have to be edited by hand |
| Four stray root files `f68f7086...json`, `4743971f...json`, `798faad9...json`, `9f2f29338...json` | analyst cache entries with `"model": "fake"` | not used | Debris from a test or probe run with a cache dir of `.`; not touched by this audit. Worth deleting before submission |

**Tests that encode today's data** (280 tests, 83 s): `test_sim.py` (final score per arc, monotonic time, ids `0..n-1`, coordinates in bounds, one truth item per
goal, same seed same match); `test_pipeline.py` (message kind set, events in frames equal event count, `len(row) == len(EVENT_FIELDS)`, deterministic replay equals
the earlier replay, `ReplayMismatch`, catch-up counts); `test_evaluation.py` (grounding 1.0, every goal found and spoken on all 6 channels, injected errors caught at
least 95 percent, **x30 speech share above 0.99 and x1 speech share between 0.05 and 0.4**: a denser fast layer will push x1 above 0.4, which is the goal, so the upper bound must move);
`test_live_captions.py` (caption latency, skip rules, TTL, slot avoidance); `test_caster.py` (every template wording at most 130 characters, no digits, passes the
verifier on 5 matches); `test_mcp.py` (hard-coded player A10 Lemaire, goal at 792 s, silence over 10 s); `test_guided.py`; `test_server.py`.

---

## 3. Where a tracking layer plugs in with the least damage

### 3.1 Options

| Option | Idea | Pro | Contra |
| --- | --- | --- | --- |
| **A. Sidecar tracker (recommended)** | New `sim/tracking.py`: `track(meta, events, seed) -> frames`, a pure function of the existing events with its **own** `random.Random(f"{seed}:track")` (a string seed is stable across runs, `hash()` is not). Ball path from event `x,y` to `end_x,end_y`; players from formation anchors, ball-side shift, press and line-height by phase, the actor placed at the event position. Written to an optional `tracking` sidecar, streamed as a new message kind | Events, truth, ids, caches, recordings, eval of the existing moments stay byte-identical. Can be generated lazily for a window (`start..until`), so `/api/guided-live` stays at about 30 ms. Fully deterministic per `<arc>-<seed>`. Old matches without a sidecar keep working | The tracks are consistent with events only if invariants are enforced and tested; no new on-ball events (headers, crosses, dribbles) come from it by itself |
| **B. Enrich the sim in place** | Add pass type, height, receiver run, press count to the emitted events, drawing from `self.rng` | Richest causal consistency | Every draw shifts the main stream: all events, facts, moment ids, prompts, recordings, truth times, the insert and all cached analyst answers change at once. Highest damage, deadline 2026-10-27 |
| **C. Enrich with a second stream (hybrid, recommended on top of A)** | Add optional fields to `Event` (`pass_type`, `pass_height`, `run_in_behind`, `duel`, `line_broken`, `players_pressing`), computed in a post-pass over the finished events and the tracking, with the derived `random.Random` | Gives the commentator the data it asked for (type and height of the pass, runs in behind, pressing, duels) without touching existing fields | `Event` is `extra="forbid"` so the model must grow; the loader accepts old files; protocol rows need appended positions; the downstream templates and verifier need entries |
| D. Agent-based sim rewrite | 22 moving agents, events emerge | Most realistic | Rewrites the engine; arcs and truth would have to be re-fitted; weeks, not days. Not recommended |

### 3.2 Why A and C together are the least damaging plan

* The main RNG stream is untouched (see section 1: any extra draw before or inside the loop shifts everything). The existing `_nearest` already encodes a
  drift of anchors 35 percent towards the ball. The tracker should reuse exactly that rule as its base shape, so the receiver chosen by the sim is
  among the nearest tracked players at the pass end time. That is the first consistency invariant to test.
* `exclude_none=True` on write means that adding optional fields leaves any match file without them unchanged. Old `events.jsonl` still validates.
* Players need exported attributes and roles for the commentator ("quick winger", "holding midfielder"). `SimPlayer` already has `passing`, `finishing`,
  `pace`, `pos`, anchors. Export them in `meta.json` as optional `Player` fields (the `Player` model has no `extra="forbid"`, so old files load). New
  fields that need randomness (age, foot, height) must use a derived stream, not `_make_team`'s `rng`.
* The protocol change is purely additive: `hello` gets a `tracking` descriptor; a new message kind carries positions (`"k": "p"`); `eventFields` grows
  at the end. v1 clients ignore what they do not know (the UI does, MCP does, evaluation does), so the contract version can stay 1 with an additive
  note in `docs/PROTOCOL.md`. Two tests need a deliberate update (message kind set, row length constant).
* Moment ids: the fast layer must **not** take ids from `MomentBuilder._next` in the middle of the existing sequence. Give new moments their own counter
  (for example a second builder, or an offset such as `1_000_000 + n`), keep them out of `data/replays/*/analyst.json`, and mark them `voice="pbp"` so `MODEL_KINDS`
  and `_is_model_moment` never see them. Otherwise `ReplayMismatch` fires for all three recordings.
* Live mode honesty (no lookahead): the sidecar is generated offline like the events, so the tracker may know the future when it is generated. The consumers
  must not. Rule for the runner: emit `p` frames only for `t <= current frame time`, and a moment computed from tracking may only read samples up to the event
  it explains. Add a test next to the existing no-lookahead tests: shuffling samples after `t` must not change a line.
* Catch-up and `start`: positions are state, like the score. Catch-up frames before `hello.start` should send one position keyframe at `start`, not the whole past
  (same idea as `CATCH_UP_KEPT = 3` in `export.py`).
* Lazy generation: stateless noise (hash of seed, player, frame index through the string-seeded RNG or a counter-based generator) lets the tracker produce a
  60 s window without simulating from kickoff, with a 10 s warm-up for smoothing. A minimal kernel of 640k player updates (a full match at 5 Hz) ran in
  0.09 s here, a 60 s window in about 1 ms; a realistic kernel with roles, lines and pressing will be several times heavier and still far below the
  25 ms the sim takes.

### 3.3 Consistency invariants to enforce before anything is streamed

1. At event time `t`, the ball position equals `(x, y)` and at `t + pass duration` equals `(end_x, end_y)`; the actor stands within 1.5 m of the ball at the start.
2. Player speed never above 9 m/s (a carry is at most `9.0 m/s` in the sim), ball speed within the event's `ball_speed`.
3. A completed pass's `receiver` is within the three nearest team-mates of the end point at the end time.
4. Offsides, line height and compactness are derived, never drawn independently of the shape (so "high line" and the picture agree).
5. A red card removes the player from the tracking and the team shape changes accordingly (`SimPlayer.off`, `strength() = 0.9 ** reds`).
6. Pitch bounds, the half-time side swap (home attacks right in period 1 and left in period 2), and the goalkeeper stays near the goal line.
7. Same `<arc>-<seed>` gives byte-identical tracking, in any order of requests.

### 3.4 What this unlocks, and what it does not

Per `docs/COMMENTATOR.md`, real commentary volume comes from a thin identity layer (about 22 short segments per minute); tactics are 1.0 percent of segments
and off-ball runs 0.6 percent of segments in the measured sample (lexicon counts, lower bounds, machine translated). So the richer data does two different jobs:
a **cheap constant fast layer** (who has it, where it goes, pass type and height, who is closing down), which fixes the line rate and the silence; and a
**differentiator on key moments** (shape, runs in behind, pressing traps), which fixes the content. The audit finding below makes the first job smaller than it looks.

Measured on the three demo matches, moments versus events:

| Match | Moments | Per min | Events that produce a moment | Moment gap median / mean / p90 |
| --- | --- | --- | --- | --- |
| comeback-7 | 193 | 2.0 | 179 of 2,031 (8.8%) | 23.6 s / 30.3 s / 69.7 s |
| red_card-7 | 183 | 1.9 | 170 of 2,132 (8.0%) | 24.9 s / 32.0 s / 70.6 s |
| unlucky-7 | 221 | 2.3 | 209 of 2,162 (9.7%) | 21.6 s / 26.5 s / 58.3 s |

Moment kinds in comeback-7: `pass_final_third` 56, `long_ball` 37, `tackle_won` 23, `foul` 18, `shot_off` 14, `shot_saved` 13, `shot_milestone` 7, `corner` 6, `shot_goal` 3,
`goal_analysis` 3, `momentum` 3, plus singles. Not one moment is built from a plain pass between two defenders, a carry, a pressure event, an interception or a
possession change, which is 90 percent of the stream. The eval run in real time (x1) has 3,548 `say`s over 18 channel-matches of 97 minutes, about 2.0 per
channel per minute, and a speech share of 16.6 percent with a longest silence of 174 viewer seconds (`data/eval/results.json`). The brief quotes 11 lines per minute and
53 percent coverage; I could not reproduce those from the eval harness, so they presumably count a different window or channel set. Either way the gap is large, and most of it sits in the 90 percent of events that no moment uses, which exist before any tracking does.

The insert window specifically: `comeback-135`, 4381 to 4402 s, holds 5 events (2 passes, 1 interception, 1 possession change, 1 shot). The whole match
averages 7.3 events per 21 s window (median 8; 3 to 5 windows of 277 have zero events), so the insert is a quiet stretch. For a demo window, the dead time is
real: 19 to 25 percent of match time sits in gaps longer than 10 s (set pieces after fouls, 30 to 55 s after every goal, out-of-play balls), and tracking
frames can fill exactly that dead time with believable motion.

---

## 4. Real numbers

All from `Sim(arc, seed).run()` and the pipeline in this checkout.

**Events per minute** (97.0 minute matches): comeback-7 20.9, red_card-7 22.0, unlucky-7 22.3, comeback-135 20.4.

**Passes per minute** (both teams): 12.3, 12.6, 13.2, 11.9. Touches (pass, carry, shot) per minute: 15.2, 15.7, 16.2, 14.7. My recollection, not measured here, is
that real Premier League matches have clearly more passes in total (several hundred per team), so pass volume is probably 30 to 50 percent below real
football. Treat as unverified; it matters for the "ball touch every 2 to 3 s" claim.

**Gap between consecutive events (s):**

| Match | Mean | Median | p90 | Max | Gaps over 10 s | Gaps over 30 s | Share of match time in gaps over 10 s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| comeback-7 | 2.87 | 2.6 | 4.7 | 54.4 | 84 | 4 | 24.6% |
| red_card-7 | 2.73 | 2.5 | 4.5 | 66.5 | 77 | 3 | 22.4% |
| unlucky-7 | 2.69 | 2.5 | 4.6 | 38.1 | 72 | 1 | 19.5% |
| comeback-135 | 2.95 | 2.7 | 4.9 | 53.0 | 80 | 3 | 23.5% |

Gap between ball-touch events only (pass, carry, shot): mean 3.7 to 4.1 s, median 3.2 to 3.5 s.

**Events per 21 s window** (277 windows per match): mean 7.1 to 7.8, median 7 to 8, empty windows 3 to 5 per match. The insert window itself has 5.

**Size of a full match.**

| Artifact | Bytes | Gzipped |
| --- | --- | --- |
| `events.jsonl` comeback-7 (2,031 events, about 185 bytes each) | 376,681 | 49,795 |
| `events.jsonl` red_card-7 / unlucky-7 | 392,352 / 402,211 | 51,510 / 52,438 |
| `meta.json` | about 3.8 KB | |
| Protocol stream, comeback-7, replay x30 (1,752 messages: 1,374 frames, 320 say, 56 log) | 275,232 | 51,145 |
| Protocol stream, comeback-7, replay x1 (2,667 messages: 1,481 frames, 1,152 say, 32 log) | 439,182 | 69,265 |
| Protocol stream, unlucky-7, x30 / x1 | 286,489 / 480,609 | 53,234 / 74,073 |
| Frames only, comeback-7 x30 (average 151 bytes per frame) | 206,960 | 34,905 |
| `ui/public/insert/replay.json` (recorded insert) | 13,560 | |
| `data/replays/comeback-7/analyst.json` | 21,436 | |
| `data/cache/analyst` (38 entries) | 152 KB total | |

Current wire rate of a full live match at 1x: 439 KB over 5,822 s is about 75 bytes per second (0.6 kbit/s). Frames are sent per event group, with
`hb` heartbeats (about 30 bytes every 0.25 s) in quiet stretches.

**Server cost:** `Sim.run` 25 ms per match; `analyse` (fact engine over a match) 6 ms; `guided_live` (simulate, moments, window pick) 32 ms; test suite 83 s.

**Input fields the events already carry but nothing uses** (comeback-7 counts): `difficulty` 1,193, `ball_speed` 1,193, `under_pressure` 386, `speed` (carry, km/h) 255, `body_part`
31, `shot_speed` 31, `reason` 233. Only `length`, `receiver`, `speed` (the sprint fact), `shot_speed`, `body_part` and `reason` reach the fact engine or moments, and the wire protocol
carries 11 of the 22 event fields (it drops `receiver`, `length`, `difficulty`, `ball_speed`, `speed`, `shot_speed`, `body_part`, `keeper`, `under_pressure`, `reason`, `score`).
That is data for "a pressured long ball", "a driven shot", "a sprint down the right" that costs nothing to expose.

---

## 5. Performance and bandwidth budget: 22 players plus ball at a few Hz

Setup: 23 entities, x and y in integer decimetres (same unit as the event rows, `SCALE = 10`), full match of 5,822 s. The test data is a random walk, which is
worse for compression than real movement, so these are upper bounds for the deltas. Encoder timing is orjson on a flat int list.

| Rate | Format | Bytes per message | Raw rate | Per-message deflate | Full match raw | Full match gzipped as one file |
| --- | --- | --- | --- | --- | --- | --- |
| 2 Hz | JSON absolute | 203 | 3.3 kbit/s | 2.2 kbit/s | 2.4 MB | 0.9 MB |
| 2 Hz | JSON delta vs previous | 149 | 2.4 kbit/s | 1.6 kbit/s | 1.7 MB | 0.5 MB |
| 2 Hz | binary int8 delta | 50 | 0.8 kbit/s | 1.0 kbit/s | 0.6 MB | 0.4 MB |
| 5 Hz | JSON absolute | 206 | 8.2 kbit/s | 5.5 kbit/s | 6.0 MB | 2.0 MB |
| 5 Hz | **JSON delta** | 138 | 5.5 kbit/s | 3.7 kbit/s | 4.0 MB | 1.0 MB |
| 5 Hz | binary int16 absolute | 96 | 3.8 kbit/s | 4.3 kbit/s | 2.8 MB | 1.9 MB |
| 5 Hz | binary int8 delta | 50 | 2.0 kbit/s | 2.1 kbit/s | 1.5 MB | 0.8 MB |
| 10 Hz | JSON delta | 135 | 10.8 kbit/s | 6.6 kbit/s | 7.9 MB | 1.6 MB |
| 10 Hz | binary int8 delta | 50 | 4.0 kbit/s | 3.7 kbit/s | 2.9 MB | 1.3 MB |
| 25 Hz | JSON delta | 129 | 25.8 kbit/s | 13.3 kbit/s | 18.8 MB | 2.7 MB |

Reading:

* **Bandwidth is irrelevant for a viewer.** The worst row, 25 Hz JSON, is 26 kbit/s. 5 Hz JSON delta is 5.5 kbit/s, about nine times today's whole stream and well under
  any mobile link. Per-message deflate barely helps at 140 bytes (30 to 35 percent), so it is not a reason to choose binary.
* **Recommended: 5 Hz, JSON delta, integer decimetres, one message per tick.** Human readable like the rest of protocol v1, no new codec in the UI. 4 Hz is enough if the client
  interpolates (players move at most 9 m/s, which is 2.25 m between samples at 4 Hz; the ball is the exception and should ride on the event rows' `end_x/end_y` plus duration
  rather than on samples). Do not go to binary unless a measured problem appears: the saving is a factor of 2 to 3 on a number that is already tiny.
* **The frame cadence is not a free choice.** The runner sets `dt = max(0.2 if live else 0.5, speed / 20)` match seconds per frame, so a replay at x30 emits about 20 frames per wall second, each
  covering 1.5 match seconds. A tracking message "at 5 Hz of match time" would be 150 per wall second at x30. Tracking must be **sampled per frame at the stream's own `dt`** (one keyframe per
  frame, the client interpolates), not at a fixed match-time rate, or the speed control floods the socket. At 1x live, `dt = 0.2 s` equals 5 Hz exactly.
* **Static replay and insert.** A full-match tracking file at 5 Hz JSON delta is 4.0 MB raw, 1.0 MB gzipped (upper bound); the static build ships only the insert, whose 21 s at 5 Hz would add about
  105 messages and 15 KB to a 13.5 KB file. Both far inside the hosting limits, but a full-match sidecar should not enter `ui/dist` by default.
* **Server memory.** `Library` keeps up to 24 generated matches (`GENERATED_KEPT`). A full match at 5 Hz as int16 is 29,110 frames x 46 values x 2 bytes = 2.7 MB; 24 of them are 65 MB. Generate tracking
  lazily per requested window instead of per match, and do not cache it with the bundle.
* **CPU.** orjson encoding of a 46-int message is about 1 microsecond; at 20 messages per wall second this is noise. `JSON.parse` of the same message in Node took 0.76 microseconds
  (29,110 messages in 22 ms). The cost to watch is Python-side generation, not encoding. `send_text` is one await per message, so keep tracking out of the per-event group loop: one tracking
  message per frame, appended to the same `_out` list that already carries `f`, so ordering by `t` is preserved (the test sorts all messages by `t`).
* **Browser.** Positions go into a preallocated `Float32Array` ring (about 4 s) and are interpolated inside the existing single rAF loop; nothing new may call `notify` or set React state per sample,
  as the Phase 14 rule says (60 fps measured, median 16.7 ms, no frame over 20 ms). Drawing 23 circles and 22 name tags is far below the cost of the existing striped turf. The risk is visual (it reads as
  tracking data, which was removed on purpose), not computational.
* **Live mode.** The tick loop in `Runner.stream` already waits on the wall clock per frame; adding one message per frame does not change pacing. Heartbeats can be dropped from a stream that
  sends tracking every frame, because tracking keeps the client clock moving (`_flush` sends `hb` only when the tick produced nothing).

---

## Decisions this audit puts to the user

1. **Plug-in point.** A only (sidecar tracking), or A plus C (sidecar plus optional enriched event fields: pass type, height, run in behind, pressing, duel)? B and D are not advised before 2026-10-27.
2. **Fast-layer lines.** Adding spoken lines before the goal in the demo insert changes the goal analysis prompt (continuity block), which costs one real Haiku call to re-record the insert (4 of 40 build calls left,
   live budget 12). Do you approve one call, or should the insert window be kept frozen and the richer layer shown only in the guided live run?
3. **Reversal of a Phase 14 decision.** The pitch has no ambient player dots on purpose. Showing the 22 players is a UI decision that needs an explicit yes.
4. **Doc and test churn.** `test_pipeline.py` (kind set), `test_evaluation.py` (x1 speech share upper bound 0.4), `test_caster.py` (new templates) and the quoted numbers in README, PITCH, VIDEO, CLAUDE.md
   and EVAL.md change by design. Expect a regenerate-and-edit pass with no model calls.
5. **Pass volume.** Our 12 passes per minute for both teams is probably low for football; raising it changes the main RNG stream (rule R) and so is the one change that must not be done silently.
