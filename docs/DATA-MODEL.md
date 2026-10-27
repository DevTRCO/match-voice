# Data model: the rich synthetic match layer

Status: partly built. Roles, traits and tactics (sections 1 and 2) are in `backend/matchvoice/schema.py`, `backend/matchvoice/sim/profile.py` and `backend/matchvoice/sim/tactics.py`; the enriched event layer (section 4) is in `backend/matchvoice/sim/micro/enrich.py` and `data/matches/*/enriched.jsonl`; the tracking frames of section 3 are not built, the rest is design. Author: architect pass, 2026-10-21; adversarial review (Opus) the same day, its fixes are folded in and listed in
section 11 with the measurements behind them. Inputs: `docs/COMMENTATOR.md` (broadcast profile, 726 halves),
`docs/research/DATA-FEEDS.md` (field catalogue of public feed specs), `docs/research/AUDIT.md` (blast radius in this repo), and the code
(`sim/engine.py`, `commentary/moments.py`, `pipeline/protocol.py`, `pipeline/runner.py`, `commentary/analyst.py`). The build order, gates and budget
are in `docs/PLAN-DATA.md`.

## 0. The problem in numbers, and the shape of the answer

| Measure | Now | Broadcast profile (EPL sample, `docs/COMMENTATOR.md`) |
| --- | --- | --- |
| Lines per minute, one channel | 11.4 in the recorded insert (4 `say` on en/expert in 21 s); 2.0 over full matches at x1 (`data/eval/results.json`, quoted in AUDIT) | 22 segments |
| Speech coverage | 76 to 81% of the 21 s insert window by the server's voice slots (measured on `ui/public/insert/replay.json`, all 6 channels; the brief's 53% is not reproducible from the recording); 16.6% over full matches at x1 (AUDIT) | about 90% (fewer than 2.5% of gaps over 3 s) |
| Events in the insert window (21 s) | 5 (2 passes, 1 interception, 1 possession change, 1 shot) | a ball touch every 2 to 3 s |
| Events that become a moment | 8 to 10% (AUDIT 3.4) | n/a |
| What a player is | id, name, number, `pos`, `group` | role, attributes, traits, history |
| Where the other 21 players are | nowhere (the sim has one ball and one actor) | everywhere |

Reading the table: the insert is not short of speech time, it is short of segments. Its 4 lines are long (the first, "Ibsen launches it forward, and
Rasmussen gets onto it.", fills 4.6 s). The insert gap is rhythm (11 segments per minute against 22, no short fragments); the full-match gap is both rhythm
and silence (16.6% coverage, longest silence 174 s).

Two gaps, two jobs (COMMENTATOR.md findings 1 to 4):
1. **Volume.** A constant, cheap play-by-play layer of names and ball movement. Needs a touch-level stream (who has it, where it goes, how).
2. **Content.** Things worth saying between touches and on key moments: roles, shape, line height, pressing, runs in behind, duels, tempo,
   fatigue, context. Needs player profiles, team tactics, tracking of all 22 players and an Interpret stage that turns them into facts.

Job 1 needs no tracking: receipts, pass type and height, implicit passes and the fast layer are functions of the skeleton, the profiles and the tactics plan
(4.2). Job 2 needs tracking for shape, runs and pressing. The build order in `docs/PLAN-DATA.md` follows that split, so the measured complaint (sparse
voice) is fixed before the riskiest part (movement) starts.

### 0.1 Architecture: scripted skeleton, micro-simulation, interpretation

```
Sim (existing, untouched)        Micro (new)                               Interpret (new)          Explain / Render / Personalize
arc beats -> skeleton events  -> profiles + tactics plan                -> insights with evidence -> fast layer (templates, 0 calls)
   events.jsonl, truth.json      tracking 10 Hz (22 players + ball xyz)    (no lookahead)            context layer (templates, 0 calls)
                                 enriched events (eid = 16*i + k)                                     analyst layer (Haiku, guarded)
```

| Option | Idea | Pro | Contra | Verdict |
| --- | --- | --- | --- | --- |
| A. Skeleton plus micro-sim | Keep `Sim` and its random stream byte-identical. A second, deterministic stage reads the finished skeleton and fills in profiles, positions, ball height and event detail with its own random streams | Goals, red cards, `truth.json`, event ids, moment ids, the insert window (comeback-135, 4381 to 4402 s) all stay where they are. Each stage is testable alone | Positions must be fitted to events that were not generated from positions (needs appointments and gap repair, section 3.4). The skeleton's pass and press statistics do not react to tactics changes | **Chosen** |
| B. Agent-based rewrite | 22 agents, events emerge from movement | Most causal | Every event, truth time, recording and cache changes; arcs must be re-fitted; weeks of work, deadline 2026-10-27 | Rejected |

Rules every new stage obeys:
- **The main random stream is never touched.** No new draw in `Sim`. Every new random value comes from a named stream
  `random.Random(f"{seed}:{stream}:{key}")` (string seeds are hashed with SHA-512 by CPython, stable across runs and platforms).
- **Additive files and fields only.** `events.jsonl` and `truth.json` stay byte-identical (checked by SHA-256 in the gate). New data lives in new
  optional fields of `meta.json` and in new sidecars.
- **Generation may know the future, interpretation may not.** The micro-sim is offline and plans with the whole skeleton (a run starts before the pass it
  meets). Interpret, Explain and every consumer read only data with a time at or before the current frame.
- **Every field has a time of knowledge.** A value is published at the frame where a viewer could know it, not at the time of the row it describes. The
  skeleton breaks this today: a pass row carries its `outcome` and `receiver` at kick time, and the existing `long_ball` template "Ibsen launches it forward,
  and Rasmussen gets onto it." is captioned at the kick (4382.7 s), 2.7 s before Rasmussen has the ball. Rule from now on: kick-time fields (4.2, column
  "known at") go out with the kick; outcome fields (receiver, assist, take-on result) go out with the resolution row (receipt, interception, shot). The two
  skeleton pass calls that presuppose an outcome are replaced by the fast layer (7.1), their moment ids unchanged.
- **Prompt inputs are a pure function of (match id, moment).** Everything that enters an analyst prompt's facts block (`shape`, `build_up`, `people`)
  must not depend on where the stream started, its speed, or what the director voiced. Interpret state therefore has a bounded lookback
  (`LOOKBACK_S = 300`): the catch-up of a live run feeds Interpret from `start - 300` (tracking generated from the last restart before that), and no
  value that reaches a prompt may depend on older history or on emission rate limits. Continuity is restricted to skeleton and analyst captions (7.3); its one
  remaining dependence on the stream (the live same-slot rule can pick another wording for the first moment of a kind after `start`) is accepted, as today.

### 0.2 Coordinates, units, ids

| Thing | Convention |
| --- | --- |
| Pitch | 105 x 68 m (`PITCH_L`, `PITCH_W`). Absolute frame: x 0..105 left to right, y 0..68. Home attacks right in period 1, left in period 2 |
| Attacking frame | `ax`, `ay`: x 0 = own goal line, 105 = opponent goal line (as in `Sim`). All tactical numbers (line height, block depth) are in this frame |
| Height | `z` in metres above the turf, ball only |
| Time | `t` match seconds, half-time break excluded (as today) |
| Speed | m/s inside the data. km/h only when a line says it |
| Wire | integer decimetres (`SCALE = 10`), as in protocol v1 |
| Event id | skeleton `i` unchanged; enriched id `eid = 16 * i + k`, `k = 0` is the skeleton event itself, `k = 1..15` sub-events in the gap after event `i` |
| Frame id | `fi = round(10 * t)`: one tracking frame per 0.1 s, a pure function of time |
| Moment id | skeleton moments keep `MomentBuilder._next` (unchanged). New ids are derived from data, never from a counter: fast layer `1_000_000 + 8 * eid + slot` (slot 0..7 per kind, max about 1,281,600); `tactical_shift` `2_000_000 + eid` of the restart where it takes effect; context layer `3_000_000 + 8 * fi + slot` (max about 3,465,800) |

Why `eid = 16 * i + k`: ids stay integers, increase with time, and the id of a skeleton event never moves. Sub-events of the gap after `i` depend only on the
segment that contains it, so regenerating a window or the whole match gives the same ids. The gap repair (3.4) is estimated to need at most 5 sub-events per gap
(the goal build-up of the insert needs 3: receipt, implicit pass, receipt); nothing has been generated yet, so this is an estimate. 15 is the hard cap, overflow
drops the lowest-value sub-events (receipts last) and is counted in the gate. Order holds because the skeleton never emits the next event before a pass has
arrived (measured: arrival to next event at least 1.46 s, see 3.3).

Why derived moment ids: a counter (`1_000_000 + n`) restarts at 0 in a live stream that begins mid-match, so the same touch would get another id than in a
run from kick-off. `tactical_shift` moments are recorded in `data/replays/*/analyst.json` and looked up by id, so a counter id would make a live run and
its recording disagree, and the UI joins lanes, evidence and the `said` map on the id. A derived id is the same in every run.

---

## 1. Players: attributes, roles, traits, context

Stream `"{seed}:profile:{player_id}"`. Values that `Sim` already draws (`passing`, `finishing`, `pace`) are exported as they are, never redrawn.

### 1.1 `Player` fields (all optional, added to `schema.Player` and `meta.json`)

| Field | Type | Unit or range | Source |
| --- | --- | --- | --- |
| `attrs.pace` | int | 1..99 | `round(100 * SimPlayer.pace)` (existing, 0.30..0.95) |
| `attrs.passing` | int | 1..99 | `round(100 * SimPlayer.passing)` (existing) |
| `attrs.finishing` | int | 1..99 | `round(100 * SimPlayer.finishing)` (existing) |
| `attrs.acceleration` | int | 1..99 | `clamp(pace + gauss(0, 8))` |
| `attrs.dribbling` | int | 1..99 | gauss by group: GK 30, DEF 50, MID 62, FWD 68; sd 9 |
| `attrs.vision` | int | 1..99 | `clamp(passing + gauss(0, 7))`, MID +4 |
| `attrs.defending` | int | 1..99 | GK 20, DEF 72, MID 58, FWD 35; sd 8 |
| `attrs.aerial` | int | 1..99 | `clamp(40 + 1.6 * (height_cm - 175) + gauss(0, 8))` |
| `attrs.stamina` | int | 1..99 | gauss 70, sd 9; MID +5, GK -15 |
| `attrs.keeping` | int | 1..99 | GK only, gauss 72, sd 7 |
| `foot` | `"L" \| "R" \| "both"` | | R 0.72, L 0.22, both 0.06; a left-side slot (LB, LM, LW, left CB) moves 0.25 from R to L |
| `weak_foot` | int | 1..5 | 5 when `foot == "both"`, else 2..4 |
| `height_cm` | int | 165..198 | group means GK 190, CB 187, FB 178, MID 179, W 175, ST 183; sd 5 |
| `age` | int | 18..35 | |
| `top_speed` | float | m/s, 7.6..9.8 | `7.6 + 2.2 * (pace - 30) / 65` |
| `work_rate` | `"low" \| "medium" \| "high"` | | from stamina and role |
| `role` | enum, 1.2 | | rule on slot plus attributes, no draw |
| `traits` | list of enum, 1.3 | at most 2 | rule on attributes, no draw |
| `season` | object | | synthetic season so far: `apps` int, `goals` int, `assists` int, `clean_sheets` int (GK and DEF); drawn from role and attributes |
| `captain` | bool | | one per team: highest `age + stamina / 10` among DEF and MID |

The skeleton already uses `passing`, `finishing` and `pace` (pass success, shooter choice, carry speed), so the exported numbers agree with what the events show.
New attributes drive only the micro-sim (top speed, duel winners, take-on style, aerial duels) and the words. They never change a skeleton outcome.

### 1.2 Roles

`pos` stays the slot (`RB`, `CB`, `DM`, `LW`, ...). `role` is how the player plays it. First matching rule wins; the attribute thresholds use the 1..99 scale.

| Slot | Role | Rule | Movement effect in the micro-sim (in possession unless noted) |
| --- | --- | --- | --- |
| GK | `sweeper_keeper` | passing >= 60 | stands 4 m further off the line when the line is high |
| GK | `shot_stopper` | else | |
| CB | `ball_playing_cb` | passing >= 62 | steps into midfield with the ball (carries up to 15 m) |
| CB | `stopper` | defending >= 72 and aerial >= 65 | steps out to the striker on a ball into feet (out of possession) |
| CB | `cover_cb` | pace >= 65 | drops 2 m deeper than the line partner |
| CB | `centre_back` | else | |
| RB, LB | `inverted_fullback` | passing >= 62 and foot opposite to the flank | tucks into midfield (`ay` toward 34 by 14 m) |
| RB, LB | `attacking_fullback` | pace >= 60 and stamina >= 65 | overlaps when the winger on that side has the ball |
| RB, LB | `defensive_fullback` | else | stays in the back line |
| DM | `anchor` | defending >= 65 | screens 8 to 12 m in front of the centre backs |
| DM | `deep_playmaker` | else | drops between the centre backs in build-up |
| CM | `playmaker` | passing >= 68 | |
| CM | `ball_winner` | defending >= 66 | first presser in midfield |
| CM | `box_to_box` | stamina >= 70 | late runs into the box |
| CM | `central_midfielder` | else | |
| AM | `shadow_striker` | finishing >= 62 | runs beyond the striker |
| AM | `advanced_playmaker` | else | finds the space between the lines |
| RM, LM | `wide_midfielder` | | holds width |
| RW, LW | `inverted_winger` | foot opposite to the flank | starts wide, cuts inside on the ball |
| RW, LW | `winger` | else | stays wide, crosses |
| ST | `target_forward` | aerial >= 68 and height_cm >= 186 | pins the centre backs, wins headers |
| ST | `poacher` | finishing >= 65 | lives on the last line, runs in behind |
| ST | `pressing_forward` | stamina >= 70 and work_rate high | leads the press |
| ST | `complete_forward` | else | drops to link play |

### 1.3 Traits a commentator can cite

Rule based, at most 2 per player (largest margin over the threshold first). Each trait has a phrase per language and style in the template bank, never a number.

| Trait | Rule | Phrase (en expert, example) |
| --- | --- | --- |
| `rapid` | pace >= 80 | "real pace" |
| `quick_off_the_mark` | acceleration >= 80 | "quick off the mark" |
| `aerial_threat` | aerial >= 72 | "dominant in the air" |
| `long_range` | finishing >= 70 and group MID | "can strike it from distance" |
| `set_piece_taker` | exactly one per team: max of passing + vision | "the dead-ball specialist" |
| `press_resistant` | dribbling >= 72 and passing >= 65 | "so calm under pressure" |
| `engine` | stamina >= 82 | "never stops running" |
| `two_footed` | foot both or weak_foot 5 | "happy on either foot" |
| `tough_tackler` | defending >= 75 | "a tough tackler" |
| `visionary` | vision >= 78 | "sees the pass early" |
| `dribbler` | dribbling >= 78 | "loves to take a man on" |

Verifier rule (new): a line may attach a trait word to a player only if that player has the trait (lexicon per language, section 7.5).

### 1.4 Live player state (Interpret, per player, at time t)

| Field | Type | Meaning |
| --- | --- | --- |
| `touches` | int | skeleton plus sub-events where the player is the actor |
| `passes`, `passes_ok` | int | |
| `duels_won`, `duels_lost` | int | |
| `take_ons_won`, `take_ons_lost` | int | |
| `dist_spell_m` | float | metres covered since the stream started (tracking, live window only; depends on the stream start, so board and MCP only, never a prompt) |
| `sprints_spell` | int | runs above 7.0 m/s for at least 1 s in the window (same restriction) |
| `fatigue` | float 0..1 | section 5.10 |
| `since_touch_s` | float | seconds since the player last touched the ball |
| `on_since` | float | match second the player entered (0 for starters) |

---

## 2. Team tactics

Stream `"{seed}:tactics:{side}"`. The existing team skills (`attack`, `defense`, `press`, `finishing`, `tempo`, partly set by the arc) are exported and are the base.

### 2.1 `TeamMeta.tactics` (base plan, optional field)

| Field | Type | Unit or values | Rule |
| --- | --- | --- | --- |
| `formation` | str | existing `formation` (4-4-2, 4-3-3, 4-2-3-1) | unchanged |
| `shape_in` | str | e.g. `"2-3-5"` | table 2.2 from formation and full-back roles |
| `shape_out` | str | e.g. `"4-5-1"` | table 2.2 |
| `line_height` | float | m from own goal line, 26..50 | `30 + 25 * (press - 0.4)` plus `+4` for a `ball_playing_cb` pair, `-3` for a `cover_cb` |
| `block` | `"low" \| "mid" \| "high"` | | line_height < 32 low, 32..42 mid, > 42 high |
| `press.height` | `"high" \| "mid" \| "low"` | | from `block` |
| `press.intensity` | float 0..1 | | `press` (existing skill), arc may set it |
| `press.triggers` | list | `back_pass`, `pass_to_fullback`, `poor_touch`, `keeper_pass`, `receiver_facing_own_goal` | two or three, drawn |
| `build_up` | `"short" \| "mixed" \| "direct"` | | from mean passing of GK and DEF: >= 60 short, < 52 direct |
| `width` | float | m, team width in possession, 44..62 | from shape and wingers' roles |
| `tempo` | float 0..1 and class `"slow" \| "measured" \| "high"` | | existing `tempo` skill |
| `counter` | bool | | true when the team has 2 or more players with pace >= 75 among FWD and wide MID |
| `corner_delivery` | `"inswing" \| "outswing" \| "short"` | | from the set-piece taker's foot and the side the corner is taken from |

### 2.2 Shapes per phase

| Formation | `shape_in` (default) | `shape_in` with an inverted full-back | `shape_out` mid block | `shape_out` high press | `shape_out` low block |
| --- | --- | --- | --- | --- | --- |
| 4-3-3 | 2-3-5 (both full-backs high) | 3-2-5 | 4-5-1 | 4-3-3 | 4-5-1 deep |
| 4-4-2 | 4-2-4 | 3-3-4 | 4-4-2 | 4-4-2 (strikers split the centre backs) | 4-4-1-1 |
| 4-2-3-1 | 2-4-4 | 3-2-5 | 4-4-1-1 | 4-2-3-1 | 4-5-1 |

Each shape is a table of anchor points `(ax, ay)` per slot in `sim/tactics.py`, the same format as `FORMATIONS` in `sim/engine.py`. The skeleton keeps its own
anchors for `_nearest`; the micro-sim uses its anchors only for movement.

### 2.3 Posture: how tactics change with arc and score

A team is in one game-state posture at a time (`base`, `chase`, `protect`). `ten_men` is not one of them: it is a permanent modifier from the red card on,
applied first, and the game-state posture is applied on top of it (red_card arc: home is `ten_men` from 38' and `ten_men + chase` from 61', so the 10-man shape
is not lost when they chase; `chase` adds its forward to the 4-3-2 in-possession shape, giving 3-3-3). Postures change only at the triggers below, take effect at the **first restart** after the trigger (kick-off, throw-in,
free kick, corner, goal kick), or at the next possession change if no restart comes within 180 s. Each change is a `tactical_shift` and becomes one analyst
moment (7.3).

Posture rules, evaluated for each team with `d = own goals - opponent goals`, minute `m`, players on the pitch `n`:

| Posture | Enter when | Effect on the plan |
| --- | --- | --- |
| `base` | kick-off | table 2.1 |
| `ten_men` | a red card for this team (`n < 11`) | `shape_out` 4-4-1, `shape_in` 4-3-2, line -4 m, press intensity -0.10 |
| `chase` | `d < 0` and `m >= 60` | line +6 m, press +0.15, `shape_in` one more forward (4-4-2 to 3-4-3, 4-3-3 to 2-3-5, 4-2-3-1 to 2-3-5), width +4 m, tempo +0.05. Stays `chase` when level again |
| `protect` | `d > 0` and `m >= 75` | line -8 m, block low, press -0.15, `shape_out` 4-5-1 (5-4-1 if a full-back has `defensive_fullback`), tempo -0.05 |
| back to `base` (or `chase`) | a `protect` team loses its lead | |

Triggers: every goal, every red card, and the checkpoints at the start of minute 61 and minute 76 (`Sim._minute_t(61)`, `_minute_t(76)`). Nothing else changes a posture.

Applied to the three arcs (beats are fixed per arc, so the counts hold for every seed):

| Arc | Beats | Shifts | Count |
| --- | --- | --- | --- |
| comeback | A 14', H 71', H 89' | H `chase` at 61'; H `protect` and A `chase` after the 89' goal | 3 |
| red_card | H red 38', A 52', H 78' | H `ten_men` at 38'; H `chase` at 61'; A `protect` at 76'; A back to `base` after 78' | 4 |
| unlucky | A 64' | H `chase` after 64'; A `protect` at 76' | 2 |

Arc windows (`Window` in `arcs.py`) are not shifts. While a window boosts a side, the micro-sim adds `+4 m` line height and `+0.10` press intensity to that
side and `-3 m` line height to the other ("pinned back"). This matches the skeleton, which gives the boosted side more pressure events in the same window.

Known gap, stated: the skeleton's pass lengths and pressure probabilities do not react to a posture change (only to windows). Tracking and labels show the
new posture, event statistics only partly. Insights that read events (PPDA) and insights that read tracking (pressers near the ball) can therefore disagree for
a few minutes after a shift; 5.7 combines both and the analyst gets the posture label, not a raw PPDA.

---

## 3. Tracking frames and the micro-simulation

### 3.1 What a frame holds

Internal rate 10 Hz (`fi = round(10 * t)`). One frame:

| Field | Type | Unit | Note |
| --- | --- | --- | --- |
| `fi` | int | 0.1 s | frame id |
| `ball` | float x3 | m | `x`, `y`, `z` (absolute frame) |
| `pos` | float x44 | m | x, y per player in `hello.players` order (home 0..10, away 11..21); NaN when not on the pitch (sent off) |
| `vel` | float x44 | m/s | kept in memory for Interpret, not sent |
| `owner` | int8 | | player index in control, `-1` ball in flight or loose |
| `phase` | int8 x2 | code | per team, 5.1 |

Memory: a full match is 58,220 frames x (3 + 44 + 44) float32 = 21 MB in memory during generation; stored as int16 decimetres for positions only (2.7 MB at 5 Hz,
AUDIT section 5). Nothing is committed to the repo; demo matches regenerate in about a second (3.6).

### 3.2 Movement model (per player, per 0.1 s step)

Positions are computed in the attacking frame of the player's team, converted to absolute at output.

1. **Anchor.** `A = shape_anchor(slot, phase, posture)` from table 2.2 (in-possession shape when the team has the ball, out-of-possession shape otherwise).
2. **Block shift toward the ball** (the same rule the skeleton uses in `_nearest`, 0.35 on both axes):
   `Tx = A.x + 0.35 * (bx - A.x)`, `Ty = A.y + 0.35 * (by - A.y)` for outfielders. This does not make the skeleton's receivers the nearest tracked players:
   `_nearest` draws the receiver with weight `exp(-d / 11)`, so only 37 to 41% of completed passes go to the nearest team-mate by its own drifted anchors,
   about 30% go to the fourth nearest or further, and the receiver's drifted anchor is a median 20 m (p90 41 m) from the pass end (measured on comeback-135,
   comeback-7, red_card-7, unlucky-7, about 1,000 completed passes each). The receiver has to leave the shape early, which the planner does with appointments (3.4); the out-of-possession team then clamps every defender to
   `Tx >= line_x - 1.5`, where `line_x` is the team's current line height (2.3) shifted by `0.25 * (bx - 52.5)`.
3. **Compactness.** Out of possession, the vertical distance between the deepest and the highest outfielder is capped at 32 m (mid block) or 26 m (low block),
   by pulling forwards back first.
4. **Role offset.** Table 1.2 (inverted full-back tuck, winger width, anchor screen, poacher on the last line, target forward pinning).
5. **Off-ball runs** (3.4) replace the target while a run is active.
6. **Pressing** (3.5) replaces the target of the pressers.
7. **Goalkeeper.** `Tx = clamp(4 + 0.12 * (bx - 4), 1.5, 18)`, `Ty = 34 + 0.25 * (by - 34)`; `sweeper_keeper` +4 m when the line is high.
8. **Steering.** Desired velocity `v* = (T - p) * k` with `k = 1.2 s^-1`, limited to `vmax`; acceleration limited to 3.5 m/s^2 (5.0 when decelerating).
   `vmax = top_speed * (1 - 0.15 * fatigue_base)` when sprinting (run, press, chase of a loose ball), else `min(5.5, vmax)` (jog). `fatigue_base` is the
   event-free part of 5.10 (minutes on, stamina, work rate). It must not read sprints or distance from tracking: that would chain every segment to the
   ones before it and break the rule that a window and a full-match run give the same frames.
   Semi-implicit Euler: `v += clamp(v* - v, a_max * dt)`, `p += v * dt`.
9. **Separation.** Players closer than 1.2 m push apart by half the overlap (teammates and opponents alike).
10. **Jitter.** An Ornstein-Uhlenbeck offset per player (theta 0.5 s^-1, sigma 0.35 m), drawn from the segment stream, keeps lines from looking ruled.
11. **Bounds.** Players stay inside x -2..107, y -2..70 (they may step over a line at a throw-in or a corner).

### 3.3 Ball physics

The skeleton fixes where the ball starts and ends and when it is kicked. It does not fix a usable arrival time. `T = length / (ball_speed / 3.6)` is
short (median 0.52 s), and the skeleton then adds a dwell of `uniform(1.6, 4.6) / (0.6 + tempo)` before the next action. Measured on comeback-135: from the
arrival at `t + T` to the next event, the gap is at least 1.46 s, median 2.98 s, and never under 0.6 s. An incomplete pass reaches its end 1.5 to 4.6 s
(median 2.7 s) before the interception there, and a corner reaches the box 2.95 s before the header from it. Taken literally, `first_time`, `lay_off`,
volleys and headers from crosses could never happen, and the ball would sit still for seconds before every interception.

**Arrival retiming.** The micro-sim picks the arrival time `t_arr` in `[t + T, t_next - 0.25]` (`t_next` = the next skeleton event), by the height class:
a ground pass may slow down to an average of 8 m/s, a lofted ball may hang up to `min(3.8, 2 * sqrt(2 * 18 / g))` s. `first_time` follows when the remaining
gap is under 0.6 s, and a first-time action is chosen with a per-type probability from the segment stream (header from a cross or corner: always first time;
otherwise 15 to 25%). `ball_speed` has no consumer outside `sim/` (checked with grep), so the retimed flight changes nothing downstream; the annotation exports
the speed actually drawn. Every invariant below that says `t + T` means `t_arr`.

**Dwell filler.** What is left between `t_arr` and `t_next` is rendered, never frozen: a completed pass gives a hold (the receiver controls, shields or turns; the ball stays within 2 m of
the arrival point, because the skeleton's next action starts exactly there, so no carry fits); an incomplete pass gives a contested ball (heavy touch by the intended receiver, then a `loose_ball`
duel won by the interceptor at the interception time).

| Ball state | Horizontal | Height `z` |
| --- | --- | --- |
| ground pass | decelerating: `s(t) = v0 t - a t^2 / 2` with `v0 = 1.25 L / T`, `a = 0.5 L / T^2` (arrives at 0.75 of the start speed) | 0 |
| driven pass | linear in time | parabola `z = 4 h tau (1 - tau)`, `tau = t / T`, apex `h` 0.4..1.6 m |
| lofted pass, cross, switch, clearance, goal kick | linear in time | `h = min(g T^2 / 8, 18)` m (a 54 m switch in 2.7 s peaks at 8.8 m) |
| shot | linear in time | ends at the placement height (4.4), launch from 0.1 m |
| carry | ball pushed ahead of the carrier: a touch every 0.6..1.0 s, 1.0..2.5 m ahead | 0 |
| in control | at the owner's feet, 0.6 m ahead in the direction of travel | 0 |
| dead ball | at the restart spot | 0 |

Height class (4.2) is chosen first, then the physics follows it. `g = 9.81 m/s^2`.

### 3.4 Fitting movement to the skeleton

**Appointments.** Every skeleton event and sub-event creates hard appointments: the actor at the ball at the event time (within 1.0 m), the receiver at the pass end
at `t_arr` (within 1.5 m), a tackler at the carrier at the tackle time, the keeper at the save point. The planner looks ahead (allowed: generation is offline): an
appointment overrides a player's target from `t_app - d / (0.85 * vmax)` on, so the player arrives at a feasible speed. If an appointment is still infeasible
(the skeleton moved the ball faster than a person can follow), the last 0.5 s blends position linearly onto the appointment and counts a **violation**.
Floor, measured before any build: even if a receiver ran straight from its own previous appointment to the pass end, ignoring the shape, 0.2 to 0.6% of
completed passes per match need more than 9.8 m/s (comeback-135 0.2%, red_card-7 0.3%, unlucky-7 0.5%, comeback-7 0.6%). Holding the shape can only add
to that. Gate: violations under 1.5% of appointments per match, reported per kind, and zero inside the insert window. The gate "receiver among the 3 nearest
team-mates at arrival" is meaningless once appointments are enforced (the receiver is at the ball by construction); the realism measures are the off-shape
distance of each player (p50 and p90 metres from its shape target) and the share of completed passes whose receiver, at kick time, is more than 12 m from the
end point without being on a planned run.

**Gap repair.** The skeleton occasionally moves the ball with no event (measured on comeback-135: 3 ball jumps over 2 m and 3 actor changes without a pass in 1,047
consecutive same-team pairs, all in `_scripted_attack`). The repair inserts sub-events, flagged `implicit: true`:
- same team, different actor, no pass between: an implicit pass from the last holder to the next actor (type and height by the rules of 4.2);
- same actor, ball moved over 2 m: an implicit carry.

Example, the insert: event 1482 (Rasmussen to Tavares, 41.1 m, arrives at 4392.0 s) is followed by event 1483, Fontaine's goal from (25.0, 36.5) at 4393.7 s. The repair
adds `eid 23713` receipt by Tavares at 4392.0 and `eid 23714` an implicit pass Tavares to Fontaine (18.3 m), which becomes the goal's assist. That is the build-up a
commentator would call ("Tavares, inside to Fontaine...").

**Off-ball runs** (generated, labelled in `micro_truth`, never in the event stream):

| Run | When the generator plans it | Shape |
| --- | --- | --- |
| `in_behind` | a completed skeleton pass whose end lies beyond the opponent's last line at kick time | receiver starts onside, level with the line, 1.5..3.0 s before the kick, sprints to the end point |
| `overlap` | an `attacking_fullback` whose winger has the ball in the wide third | passes outside the winger, 70% when the team is in `chase` or a window |
| `underlap` | a `box_to_box` or `shadow_striker` when a wide player has the ball | inside channel run |
| `check` | a `complete_forward` or `advanced_playmaker` about to receive into feet | short run toward the ball |
| `decoy` | 0..2 per possession in the final third, drawn | a run that is not served |
| `late_box` | a cross or cut-back is coming | `box_to_box` arrives at the penalty spot |

**Restarts and segments.** Every restart (88 per match in comeback-135, median 50 s apart, longest 220 s) begins a segment. At the restart all players are at a
canonical layout for that restart type (kick-off, throw-in, corner, free kick with wall, goal kick), mirrored to its side and shifted by the restart spot. The
previous segment knows its next restart and steers everyone toward that layout during the dead ball, so it arrives without a jump (or with a short blend, counted
like a violation). A segment's random stream is `"{seed}:micro:{eid_of_restart}"`. A segment starts exactly on the canonical layout with zero velocity and a
reset jitter state, and depends only on the skeleton events from its restart up to and including the next restart (whose layout it steers toward) and on
`fatigue_base`, which is a function of the clock. So any window can be generated from its last restart, and a window and a full-match run give
byte-identical frames. A window is generated from its last restart, which can lie up to 220 s before it (longest gap between restarts, comeback-135), and
Interpret needs `LOOKBACK_S` before the window (0.1), so the cost is that of up to about 520 s of simulation, not of the window.

**Planned runs and foretelling.** A planned `in_behind` run exists because a pass will be played there, so a detector that calls every run would foretell the
pass. Decoy runs keep this honest: the share of `run_in_behind` insights that are served must stay between 30 and 60% per match (gate), so "in behind!"
is a call about movement, not a promise of the ball.

### 3.5 Pressing

At each step the out-of-possession team decides whether it presses: `press_on = trigger fired in the last 1.5 s or ball inside the press zone` where the press zone is
`ax >= 105 - (line_height + 35)` for a high press and the opponent half for a mid press. If on, the nearest defender becomes presser 1 (target: the carrier, at sprint),
the second nearest covers the most central pass lane (target: 40% of the way to the most dangerous free receiver), the rest shift. Intensity scales the reaction delay
(`0.9 - 0.6 * intensity` s) and the share of the press zone. Skeleton `pressure` events and `under_pressure` flags become appointments for presser 1, so the
picture and the event agree.

### 3.6 Determinism and cost

- Kernel arithmetic uses only `+ - * /` and `sqrt` (correctly rounded in IEEE 754) on float64; no `exp`, `sin` or `atan2` inside the step; no numpy
  reductions (`sum`, `mean`) whose order depends on the SIMD build: line heights and centroids are summed in a fixed Python order. Output is quantised to
  decimetres. Same `<arc>-<seed>`, same bytes in any request order and in two processes (test). "Any machine" is not claimed: the jitter draws use
  `random.gauss` (libm `log` and `cos`), and the skeleton itself already uses `math.exp` and `atan2`, so cross-platform identity is an assumption today. It is
  checked where it matters: the dev Mac and the Docker image must give the same SHA-256 for the insert window (test in the Phase 5 fresh-clone gate style).
- numpy is already in the venv (2.5.4, pulled in by a dependency); declare it in `pyproject.toml` (open source, vectorises the 22 players per step).
- Targets: full match under 3 s, a 75 s live window including its lead-in (last restart plus `LOOKBACK_S`, up to about 520 s simulated) under 300 ms, on the
  dev Mac. These are estimates: 58,220 steps at roughly 40 microseconds of numpy overhead each is already about 2.3 s before planning and pressing logic,
  so the first measurement in the micro-sim phase decides whether the internal rate drops to 5 Hz. Generated lazily per window; `Library` keeps tracking only
  for the windows it served.
- Tracking is opt-in per `Runner` (`tracking=True` for the server's WebSocket and the insert export). Evaluation, MCP replay tools and the existing tests do
  not generate it, so the 83 s test suite does not pay a full-match simulation per runner.

### 3.7 Wire encoding (`tk` message)

One `tk` per runner frame, sampled at the frame time (live at 1x: `dt = 0.2 s`, 5 Hz; replay x30: one per 1.5 match s). Never a fixed match-time rate, so speed
does not flood the socket (AUDIT section 5).

```json
{"k":"tk","t":4389.6,"fi":43896,"key":1,"b":[591,620,0],"o":3,"p":[52,331, 210,402, "...44 ints..."],"sh":[[440,286,512,1],[302,248,610,0]]}
{"k":"tk","t":4389.8,"fi":43898,"b":[7,-14,9],"o":-1,"p":[1,0, -2,3, "..."]}
```

| Field | Meaning |
| --- | --- |
| `fi` | frame id |
| `key` | `1` on a keyframe: `b` and `p` are absolute decimetres. Otherwise deltas against the previous `tk` (a delta fits in int8 at 5 Hz: 9.8 m/s x 0.2 s = 20 dm) |
| `b` | ball `x, y, z` |
| `o` | owner player index, `-1` none |
| `p` | 22 x (x, y); a player who is off sends `-32768, -32768` on the keyframe and is skipped in deltas |
| `sh` | keyframes only, per team `[line_dm, length_dm, width_dm, block]`: line height (attacking frame), team length, team width, `block` 0 low, 1 mid, 2 high |

Keyframe every 10 `tk` and on the first `tk` after `hello` or a catch-up. Catch-up before `hello.start` sends no `tk` except one keyframe at `start`.
At speeds above 5 one `tk` covers more than a second of match time, so straight-line interpolation would cut every pass short: the client then draws the
ball from the event rows (`end_x`, `end_y`, `t_arr`) as today and uses `tk` for the players only.

---

## 4. Enriched events

Two kinds of rows, both keyed by `eid`:
- **annotation rows** (`k = 0`): extra fields for a skeleton event;
- **sub-events** (`k = 1..15`): events the skeleton does not have, placed in the gap after skeleton event `i`, in time order.

Stream `"{seed}:micro:{eid_of_restart}"` (the segment stream), so annotations are stable per segment like the tracking. Every rule that reads positions reads the tracking
frame at the event time, which the micro-sim produced first.

### 4.1 Sub-event types

| `type` | Fields | When |
| --- | --- | --- |
| `receipt` | `player`, `x`, `y`, `touch` (`control`, `chest`, `head`), `facing` (`forward`, `side`, `own_goal`), `pressure` (4.3) | the arrival (`t_arr`, 3.3) of every completed pass, skeleton or implicit. Whether the touch was first time is only known at the next action, so it lives on that action's `first_time` (past), not on the receipt. Everything on the row is known at `t_arr` (0.1): `facing` is drawn from the direction the incoming pass travelled (never from the next action, which made 77% of the `own_goal` receipts lead to a loss), `pressure.under` is `null` until the micro-sim sets it from the frame (the skeleton has no flag for a receiver, and the next action's flag is a lookahead that made `under` true only on receipts that keep the ball) |
| `carry` | `player`, `x`, `y`, `end_x`, `end_y`, `distance_m`, `duration_s`, `max_speed` (m/s), `progress_m` (gain in `ax`), `into_box` | implicit carries (3.4); skeleton carries get the same fields as annotation |
| `pass` | as a skeleton pass plus `implicit: true` | gap repair |
| `take_on` | `player`, `defender`, `x`, `y`, `outcome` (`won`, `lost`), `style` (`pace`, `skill`, `nutmeg`, `cut_inside`) | a skeleton carry under pressure that ends past the nearest defender (won, timed at the carry's end, when it is known), or a skeleton tackle `won` that follows a carry (lost, timed at the tackle, defender = tackler) |
| `duel` | `kind` (`ground`, `aerial`, `loose_ball`), `players` [a, b], `winner`, `x`, `y` | aerial: a lofted pass, cross or goal kick arriving with a defender within 2 m of the receiver; ground: every skeleton tackle; loose_ball: an interception within 1.5 m of the intended receiver |
| `block` | `player` (blocker), `x`, `y`, `of` (`shot`, `cross`, `pass`) | skeleton shot `blocked`: blocker = the defender nearest the shot line at the frame |
| `clearance` | `player`, `x`, `y`, `body_part`, `height` | a header from a cross that the defending team wins in its own box (from the aerial duel) |
| `keeper` | `player`, `action` (`save`, `catch`, `parry`, `punch`, `claim`, `sweep`), `technique` (`diving`, `standing`), `x`, `y` | every skeleton save, plus claims of crosses into the six-yard box |

Expected volume per match (from the skeleton counts in AUDIT section 1, comeback-7): receipts about 1,000, take-ons 40 to 70, aerial duels 30 to 60, ground duels 23 (the
tackles), blocks about 6, keeper actions about 20. With receipts the ball-touch stream rises from 15 per minute (AUDIT 4) to about 25 per minute, one touch every 2.4 s
(comeback-135: 14.7 plus about 10 receipts per minute from 975 completed passes in 97 minutes).

Pass volume is not the problem AUDIT section 4 suspected: 1,153 to 1,279 passes per match are about 580 to 640 per team, inside the 400 to 650 per team I recall
for top-flight matches (recollection, unverified). So no change to the main random stream (rule R) is needed for volume.

The insert window, counted by the same definition (pass, carry, shot, receipt): pass 1481, receipt Rasmussen, pass 1482, receipt Tavares, implicit pass 23714,
receipt Fontaine, shot 1483 = 7 touches in 21 s, plus the loose-ball duel that ends in Ibsen's interception. Rasmussen holds the ball for 4.2 s (4385.4 to
4389.6), which is where a context line fits (7.2).

### 4.2 Pass annotation (skeleton passes and implicit passes)

| Field | Known at | Type | Values and rule (attacking frame, `dx = end.ax - start.ax`, `dy = |end.ay - start.ay|`, `L` = length) |
| --- | --- | --- | --- |
| `target` | kick | player | the intended receiver, on every pass: the skeleton `receiver` for a completed pass, the team-mate nearest the end point at the kick frame for an incomplete one. Commentary at the kick names `target`, never `receiver`, so naming a player does not reveal that the pass arrives |
| `pass_type` | kick | enum | first match wins: `corner`, `free_kick`, `throw_in`, `goal_kick`, `kickoff` from `set_piece`; `cross` if start `ay < 13.84 or > 54.16`, start `ax > 70`, end inside the box and `L >= 15` (without the length, 17 to 33 of the 54 to 77 crosses per match were under 12 m, down to a 0.8 m tap along the box edge, and 8 of 10 team-matches were above the 25 of the range; with it 5 to 21 on the demo matches, median 12 and 10 of 300 team-matches above 25 over 150 matches, 70 of 300 below 8 because the skeleton sends few balls wide); `cut_back` if start inside the box wide of the six-yard box and `dx < 0`; `switch` if `dy >= 40` and `L >= 40` (at least 60% of the width); `through` if the end is at least 10 m beyond the opponent's planned last line at kick time and `L >= 40` (the line height of the tactics plan, 2.1 and 2.3, shifted by `0.25 * (bx - 52.5)` as in 3.2; the first draft had no margin and no length, which gave 55 to 85 through balls per team, now 3 to 8 on the demo matches and a median of 5 over 150 matches; the micro-sim then plans an `in_behind` run for that pass, 3.4); `clearance` if the passer won the ball (interception or tackle) within the last 2 s within 3 m, or if the passer is a DEF in the own box under pressure, and `L >= 30`; `back` if `dx < -3`; `lay_off` if `L < 10` and the pass is `first_time` (the passer's own touch, past); `long` if `L >= 32`; else `short` |
| `height` | kick | `ground`, `driven`, `lofted` | `lofted` for cross, switch, clearance, goal kick, corner; for `long` passes lofted with probability rising linearly from 0.3 at 32 m to 0.8 at 50 m (stream); `driven` for a drawn kick speed of at least 70 km/h and `L >= 18`; else `ground`. No tracking input: the micro-sim places defenders so a lofted ball has a reason, not the other way round |

**Kick-time fields never read tracking.** Every field in this table is a function of the skeleton, the profiles (1) and the tactics plan (2) only, so the
enrichment can be built, frozen and voiced before the micro-sim exists (plan phase order), and the micro-sim conforms to it (appointments, planned runs).
Tracking adds its own fields (`pressure` object beyond the skeleton flag, shot cone, box counts at set pieces, aerial duels) and never rewrites these.
| `body_part` | kick | `left_foot`, `right_foot`, `head`, `other` | head if the ball arrived at the passer above 1.2 m; else the preferred foot, weak foot with probability `(5 - weak_foot) * 0.04` reversed when the angle favours it |
| `technique` | kick | `inswing`, `outswing`, `straight`, `chip` | corners and crosses: inswing when the foot is opposite to the side it is struck from; `chip` for `through` passes with `height lofted` |
| `pressure` | kick | object | 4.3, at kick time; the one tracking field in this table, added by the micro-sim; before it exists only `under` (the skeleton flag) is set |
| `first_time` | kick | bool | the passer received less than 0.6 s before (after arrival retiming, 3.3) |
| `t_arr` | kick | float | arrival time at the end point (3.3); the flight is visible, so this is not lookahead |
| `progressive` | receipt | bool | not stored: Interpret computes it (5.2) at the receipt |

There is no `assist` on the pass row: whether a pass leads to a shot is known only at the shot, so the shot carries `assist_eid` (4.4) and Interpret
attaches it to the pass when the shot happens.

Plausibility ranges the gate checks per team and match (my recollection of typical top-flight ranges, unverified; used only as a sanity gate, never quoted in a line):
short 60 to 78% of passes, long 8 to 16%, crosses 8 to 25, switches 3 to 12, through balls 1 to 8, lofted 12 to 25%, back passes 10 to 20%.

### 4.3 Pressure object (on passes, receipts, carries, shots)

| Field | Type | Unit | Rule |
| --- | --- | --- | --- |
| `pressers` | int | | opponents within 5 m of the ball at the event frame |
| `nearest_m` | float | m | distance of the nearest opponent |
| `closing` | float | m/s | that opponent's speed toward the ball |
| `under` | bool | | `nearest_m <= 2.0` (the "intense pressure" rule in DATA-FEEDS section 5) or the skeleton's `under_pressure` |

The skeleton's `under_pressure` flag is kept; the micro-sim places a presser within 2 m for every flagged event (appointment), so `under` is never false where the skeleton says true.

### 4.4 Shot annotation

| Field | Type | Values |
| --- | --- | --- |
| `xg` | float | existing, unchanged |
| `body_part` | `left_foot`, `right_foot`, `head`, `other` | skeleton `head` kept; `foot` resolved by preferred foot and the shooting angle |
| `technique` | `placed`, `driven`, `volley`, `header`, `chip`, `curled` | volley when the ball arrives above 0.5 m and `first_time`; curled for an `inverted_winger` from the edge of the box |
| `first_time` | bool | |
| `assist_eid` | int or null | the pass or implicit pass that set it up |
| `one_on_one` | bool | no defender inside the triangle shooter to the posts, keeper only |
| `defenders_in_cone` | int | defenders inside that triangle |
| `keeper_off_line` | float | m |
| `placement` | object | `y` (m across the goal from the left post, 0..7.32), `z` (m, 0..2.44), `zone` (`low_left`, `low_centre`, `low_right`, `high_left`, `high_centre`, `high_right`); `y` comes from the skeleton's `end_y`, `z` drawn (saved shots biased toward the keeper) |

### 4.5 Set pieces and fouls

| Event | Extra fields |
| --- | --- |
| corner | `delivery` (`inswing`, `outswing`, `short`), `target` (`near_post`, `six_yard`, `penalty_spot`, `far_post`, `edge`) from the skeleton's end point, `box_att` and `box_def` (players inside the box at the kick frame) |
| free kick | `distance_m` to goal, `direct` (shot or not, from the skeleton), `wall` (players within 9.15..10 m between ball and goal) |
| throw-in | `long` (end beyond 20 m) |
| goal kick | `short` (end inside the defending third) |
| foul | `foul_type` (`trip`, `push`, `holding`, `late_tackle`, `pull`), drawn by the fouler's role and the duel kind before it; `zone` (`defensive`, `middle`, `attacking`) |

### 4.6 Files

| File | Content | Committed |
| --- | --- | --- |
| `events.jsonl` | skeleton, unchanged | yes, byte-identical |
| `truth.json` | macro truth, unchanged | yes, byte-identical |
| `meta.json` | gains `Player.attrs`, `foot`, `role`, `traits`, ..., `TeamMeta.tactics` | yes (changes, additive) |
| `enriched.jsonl` | annotation rows and sub-events, sorted by `eid` | yes for the 4 demo matches (about 250 KB each, estimate) |
| `micro_truth.jsonl` | generator labels: planned runs with start, end, runner, kind, served; posture shifts with the restart eid; appointment violations | yes, for evaluation |
| tracking | never written; generated per window | no |

---

## 5. Insights (Interpret stage)

`backend/matchvoice/interpret/`. Each detector is fed in time order with the skeleton events, the enriched rows and the tracking frames, and may read only what has a
time at or before `now`. Every insight carries evidence: `ev` (eids) and `fr` (`[fi_from, fi_to]`). The outcome of a pass is known at its `receipt` (or the
loss), not at the kick: an insight about where a pass went is emitted at the receipt time.

| # | Insight | Definition | Emitted | Fields | Layer |
| --- | --- | --- | --- | --- | --- |
| 5.1 | `phase` | per team: `build_up` (own third, opponent not pressing), `progression` (middle third), `final_third`, `counter` (possession won in own half or middle third, then at least 15 m progress toward goal within 6 s with at least 2/3 of the path forward, after the counter rule in DATA-FEEDS section 2), `set_piece`; out of possession: `high_press`, `mid_block`, `low_block`, `counter_press` (pressing within 5 s of losing the ball) | on change, at most one per 3 s per team | `side`, `phase`, `since` | fast (counter, counter_press), context (blocks) |
| 5.2 | `progressive_pass` | completed pass that moves the ball at least 25% closer to the goal centre, start beyond own 40% of the pitch, or 10 m closer in the final third | at receipt | `eid`, `gain_m` | fast (expert wording) |
| 5.3 | `line_break` | completed pass whose segment crosses one or both opponent lines (midfield line: the opponent MID group by role; defensive line: back four or five), measured on the kick frame: start behind the line in `ax`, receipt beyond it, and the segment crosses the line between its outermost players' `ay` | at receipt | `eid`, `lines` (1 or 2), `bypassed` (players) | fast, analyst |
| 5.4 | `run_in_behind` | an attacker without the ball crosses the opponent's offside line (second-last defender) in `ax` at more than 5.5 m/s while the team has the ball, having been onside 1 s before | at the crossing frame; `served` added at the receipt if a pass ends within 3 m of the runner | `runner`, `fr`, `speed`, `served`, `eid` | fast ("in behind!"), analyst |
| 5.5 | `line_height` and `compactness` | line height: mean `ax` of the back line (the 4 deepest outfielders, 3 with a red card in defence), EMA 5 s; team length (deepest to highest outfielder); width; hull area of the 10 outfielders. Classes: line low < 32, mid 32..42, high > 42 m; compact < 600 m^2, stretched > 900 m^2 (Opta Vision thresholds, DATA-FEEDS section 5) | on class change held for 20 s, at most once per 2 minutes per team | `side`, `line_m`, `length_m`, `width_m`, `area_m2`, `class` | context, analyst |
| 5.6 | `offside_line` | x of the second-last defender per team, every frame | state, no message | `x` | board only |
| 5.7 | `press` | PPDA over the last 5 minutes (opponent passes in their own 60% divided by defensive actions there: tackles, interceptions, fouls, duels; Premier League definition in DATA-FEEDS) and from tracking the mean pressers within 5 m of the receiver and the median time from receipt to the first opponent within 2 m. Class `intense` when time-to-pressure under 1.5 s and pressers >= 1.5, `passive` when over 3 s | on class change held for 30 s | `side`, `ppda`, `ttp_s`, `pressers`, `class` | context, analyst |
| 5.8 | `tempo` | per team over the last 3 minutes of possession: passes per minute in possession, median dwell (receipt to next action), mean pass speed. Class `slow`, `measured`, `high` | on class change, at most once per 3 minutes | `side`, `ppm`, `dwell_s`, `class` | context |
| 5.9 | `duel_1v1` | the carrier in the final third with one defender within 4 m and no other defender within 8 m | when it opens (frame), resolved by the next `take_on`, shot, pass or tackle | `attacker`, `defender`, `edge` (`pace` if attacker pace exceeds defender pace by 10, `skill` if dribbling exceeds defending by 10, else `even`) | fast, context |
| 5.10 | `fatigue` | `fatigue_base = clamp((minutes_on / 90) * (1.25 - stamina / 100) * w, 0, 1)` with `w` 0.9 / 1.0 / 1.15 by work rate: a function of the clock and the profile only, used by the kinematics (3.2), the prompt (`people` flag) and the threshold. The insight may add `0.15 * sprints_last_10min / 6` from tracking for its own wording, but that term never reaches a prompt or the kinematics | when `fatigue_base >= 0.7` after minute 60, once per player per stream | `player`, `f` | context |
| 5.11 | `switch` | completed pass with `pass_type == "switch"` | at receipt | `eid`, `from_side`, `to_side` | fast |
| 5.12 | `overload` | in the final third, attackers within 15 m of the ball exceed defenders there by 2 or more | at most once per possession | `side`, `att`, `def` | analyst |
| 5.13 | `counters` | running counts for context: corners in the last 5 minutes, a player's fouls, shots, touches since coming on, a team's passes in this possession, first touch after a long spell (> 4 minutes) | on the event that makes the count notable (third corner in five minutes, fourth foul, possession of 10 or more passes) | `what`, `n`, `who` | context |
| 5.14 | `posture` | the planned posture shift (2.3), read from the tactics plan at the restart where it takes effect (the plan is a pure function of the score and clock so far, so it is not lookahead) | at that restart | `side`, `from`, `to`, `shape_in`, `shape_out`, `line_m` | analyst (`tactical_shift`) |

No-lookahead test: generate tracking and enriched rows once from the true skeleton. Then, for a set of cut times `now`, feed Interpret the same data with every
frame, skeleton event and enriched row after `now` replaced by noise (and, separately, deleted); every insight emitted at or before `now`, and its fields, must
be identical to the unperturbed run. Do not regenerate the tracking from a perturbed skeleton: the planner looks ahead by design, so the frames before `now`
would change and the test would fail for the wrong reason.

Start-independence test: for the insert and five other windows, run Interpret from kick-off and from `start - LOOKBACK_S`; the state functions that feed a
prompt (`shape`, press class, posture, `fatigue_base`, `build_up`) must be identical at every moment time inside the window. Emission rate limits ("at most
once per 2 minutes", "once per player") may differ between the two runs, which is why their output feeds only fast and context lines, never a prompt.

Precision test against the generator: `run_in_behind` and `line_break` are compared with `micro_truth.jsonl` (the planned runs and the generator's own line geometry).
Target precision and recall >= 0.8 on the three demo matches. This also produces a number for the pitch: the commentary detects what the simulated players did, it does
not read their labels.

---

## 6. Arcs and truth moments

| Rule | How it holds |
| --- | --- |
| Goals, red cards, their times and sides | decided by `Sim` and its arc beats, unchanged; `truth.json` byte-identical |
| Momentum swings | `Window` in `arcs.py` unchanged; the micro-sim renders them (2.3: line and press offsets), so a swing is now visible on the board |
| Scripted build-up of a goal | `_scripted_attack` still makes 2 to 4 forced passes and a forced shot; gap repair (3.4) adds the missing lay-off and the assist; the micro-sim adds a run in behind or a line-breaking label where the geometry fits |
| Posture shifts | a pure function of the beats and the clock (2.3), so the count per arc is fixed: comeback 3, red_card 4, unlucky 2 (checked by hand against `arcs.py`: comeback A 14', H 71', H 89'; red_card H red 38', A 52', H 78'; unlucky A 64'). Written to `micro_truth.jsonl`; not added to `truth.json`, so the existing coverage metric does not move |
| Insert | comeback-135, goal 2 at 4393.7 s (71'), `start` 4381, `until` 4402: unchanged. Its tracking is generated from the last restart before 4381 |
| Guided live | random `<arc>-<seed>`, window chosen by summed moment priority (`guided.py`). Must use skeleton moments only for the score, so the new dense fast layer does not move the window choice (fast-layer priorities are excluded) |

---

## 7. Commentary contract

Three layers. The booth is unchanged: Ewan Marsh (caller) speaks the fast layer, Nadia Rowe (colour analyst) the context and analyst layers.

### 7.1 Fast layer (caller, templates, 0 model calls)

New builder `commentary/fast.py` (`TouchBuilder`, ids `1_000_000 + 8 * eid + slot`, 0.2). Input: skeleton events, enriched rows and fast insights. Output: moments with `voice = "pbp"`,
priority 26 to 40 (above `min_priority = 25`), never interrupting.

| Kind | Trigger | Params | en expert | en beginner | ttl (viewer s) | voice wait (s) |
| --- | --- | --- | --- | --- | --- | --- |
| `touch` | receipt or skeleton pass/carry by a new player (the ball changed feet) | `player`, `dir` (`forward`, `back`, `inside`, `wide`) | "Rasmussen." / "Rasmussen, forward." | "Rasmussen has it." | 1.5 | 0.8 |
| `pass_kind` | pass with `pass_type` in switch, through, cross, long, lay_off, back under pressure | `player`, `target`, `pass_type`, `height` | "Ibsen switches it." / "Long for Tavares." | "Ibsen sends it all the way across." | 2.0 | 1.0 |
| `carry` | carry with `progress_m >= 10` | `player` | "Okafor drives on." | "Okafor runs with it." | 2.0 | 1.0 |
| `take_on` | sub-event | `player`, `defender`, `outcome`, `style` | "Okafor goes past Brandt." / "Nutmeg!" | "Okafor beats his man." | 2.0 | 1.0 |
| `duel` | aerial duel, or ground duel won | `winner`, `kind` | "Up goes Zeller, wins it." | "Zeller wins the header." | 2.0 | 1.0 |
| `press_on` | presser 1 within 2 m on a receipt in the press zone | `presser`, `player` | "Abara closing him down." | "Abara chases him." | 1.5 | 0.8 |
| `in_behind` | 5.4 at the crossing | `runner` | "Tavares in behind!" | "Tavares is through!" | 2.5 | 1.0 |
| `line_break` | 5.3 | `player`, `receiver`, `lines` | "Splits the lines, Tavares." | "Great pass through the middle." | 2.0 | 1.0 |
| `block`, `clearance`, `keeper` | sub-events | `player` | "Blocked by Ibsen!" | "Ibsen blocks it!" | 2.5 | 1.0 |
| `restart` | throw-in, goal kick, free kick awarded in own half | `team`, `side_of_pitch` | "Throw on the left for Wexmoor." | "Wexmoor throw it in." | 3.0 | 1.5 |
| `setpiece_setup` | corner or free kick in range, at the restart | `taker`, `delivery`, `foot` | "Lemaire over it, an inswinger." | "Lemaire will take it." | 4.0 | 2.0 |
| `duel_1v1` | 5.9 open | `attacker`, `defender` | "Okafor one on one with Brandt." | "Okafor against Brandt." | 2.0 | 1.0 |

Rules:
- The wording at the kick says only what the kick shows ("Long for Tavares" names `target`, 4.2, and the outcome line comes at the receipt).
- At most one fast line per 1.2 viewer seconds per channel; a newer fast moment replaces an older one still waiting (no queue of fragments).
- **Captions for the fast layer start with the voice.** A fast moment is captioned when the voice takes it, as one `say` with `s < e`; a fragment replaced
  before it is voiced is never shown and is not a skip. Without this, captions-first (Phase 8) would caption every touch at arrival and the skip share would
  pass 40% by construction (about 25 fast moments per minute against about 15 that fit). Skeleton and analyst lines keep captions-first.
- **No double call, and no outcome at the kick.** The skeleton pass calls `long_ball` (26) and `pass_final_third` (28) fire on the same passes the fast
  layer calls, they exist only for completed passes, and their wording presupposes the outcome ("Ibsen launches it forward, and Rasmussen gets onto it." at
  the kick). With the fast layer on, these two kinds are still built (so `MomentBuilder` ids do not move) but not pushed to the directors; the fast layer calls
  the kick with `target` and the receipt at `t_arr`. They are not model moments, so recordings and `ReplayMismatch` are unaffected. For every other eid that
  has a skeleton moment (`tackle_won`, shots, fouls, cards, corners, `sprint`) the fast builder emits nothing. While the ball is in play, skeleton play-by-play
  under priority 40 takes its shortest wording; the longer wordings are for dead balls. Without these rules the insert's first line (4.6 s) blocks the voice
  through Rasmussen's receipt and the fast layer adds nothing there.
- **Names are rationed.** At most every second fast fragment names a player when the same team keeps the ball; the others are name-less ("Good ball.",
  "Switched.", "Forward again."). Estimate without this rule: about 18 names in about 110 words per minute (16 per 100 words, gate 6 to 14) and about 80% of
  segments naming a player (profile 38%).
- Goals, saves and shots keep their existing skeleton moments and priorities. A fragment is never longer than 6 words (en), 7 (de), 7 (fr).

### 7.2 Context layer (analyst voice, templates, 0 model calls)

Kinds: `shape_note` (5.5), `press_note` (5.7), `tempo_note` (5.8), `fatigue_note` (5.10), `counter_note` (5.13), `player_note` (role, trait or season context of the
player on the ball, at most once per player per half), `phase_note` (5.1 blocks). Priority 30 to 45, ttl 8 s, voice wait 3 s. They speak only in a **dead-ball
window** (the ball is out: from the event that stopped play until the restart, which is known once play has stopped) or when no fast moment is waiting. Cap: in
open play one context line per 40 viewer seconds per channel; inside a dead-ball window one per 10 viewer seconds, at most 3 per window. Why the second cap:
19 to 25% of match time sits in gaps over 10 s (AUDIT 4), and with one line per 40 s that time would stay about 88% silent, which alone caps full-match
coverage near 80% of the open-play figure. Examples (en expert): "Wexmoor have pushed the line right up since the hour." "Tavares, real pace, and he never stops running." "Third corner in five minutes."
Each kind has 2 to 3 wordings per language and style, under the existing caster rules (no digits in template text, numbers only from params, at most one number,
no dashes, no gendered pronouns).

### 7.3 Analyst layer (Haiku, guarded)

Model kinds: the existing four (`momentum`, `goal_analysis`, `big_save_analysis`, `big_chance_analysis`, whose detection and ids do not change) plus
`tactical_shift` (2.3, id `2_000_000 + eid` of the restart). `PROMPT_VERSION` v5. The facts block gains three keys, capped at about 250 extra input tokens:

```json
"shape": {"home": {"posture": "chase", "since": "61", "shape_in": "3-4-3", "shape_out": "4-4-2", "block": "high", "press": "intense"},
          "away": {"posture": "base", "shape_out": "4-4-1-1", "block": "mid", "press": "passive"}},
"build_up": {"chain": [["Ibsen", "interception"], ["Ibsen", "switch", "lofted", "first_time"], ["Rasmussen", "long"],
                       ["Tavares", "short", "first_time"], ["Fontaine", "shot"]],
             "line_break": true, "run_in_behind": null, "assist": "Tavares"},
"people": {"Fontaine": {"role": "poacher", "traits": ["rapid"], "season_goals": 6},
           "Tavares": {"role": "box_to_box", "traits": ["engine"]}}
```

`build_up` is the current possession (skeleton plus sub-events, at most 6 entries, oldest dropped). `people` has only the players the moment names. Every value is known
at the moment's time. (Example flags: Ibsen's switch leaves at the instant of his interception, 4382.7 s, so it is first time; Tavares has 1.68 s from
receipt to the shot, so the implicit pass to Fontaine must be first time to fit; Fontaine's shot is first time only if the retimed arrival leaves under 0.6 s.)

**Continuity block (changed).** Today `Runner._said` holds the last 3 lines each channel captioned, minus lines the voice skipped. With the dense layer those
would be fragments ("Rasmussen.", "Long for Tavares.") that tell the analyst nothing, and every fast wording or voice-timing change would change the prompt and
miss the cache. v5 rule: continuity holds only lines of skeleton moments and analyst lines (ids under 1,000,000 and `tactical_shift`), by caption, without the
skip removal (a skip depends on how busy the voice was, which the fast layer now decides). The goal call stays in the block (it is a skeleton moment captioned in
the same tick, Phase 12). Consequence: fast and context wording can change after the recording without costing a call.

Measured, not assumed: with v4 today, a live run of comeback-7 or red_card-7 from kick-off (x30, unpaced, stub model that raises, 0 spend) finds none of its
prompts in `data/cache/analyst` (8 of 8 and 9 of 9 would need a call), because `precompute` builds continuity from the analyst lines published so far, while a
live run uses the director's captions. So "after precompute the demo matches run live for free" (CLAUDE.md, Known issues) no longer holds since v3, and v5 does
not change that. The recorded insert is unaffected: its cache entry was written by a live capture with the live continuity.

### 7.4 Who feeds what

| Insight or data | Fast | Context | Analyst |
| --- | --- | --- | --- |
| player on the ball, receipts, carries, pass type and height | yes | | `build_up` |
| take-ons, duels, blocks, clearances, keeper actions | yes | | `build_up` |
| run in behind, line break, switch, 1v1 | yes | | `build_up` flags |
| line height, compactness, press, tempo, phase blocks | | yes | `shape` |
| posture shifts | | | yes (`tactical_shift`) |
| roles, traits, season | | `player_note` | `people` |
| fatigue | | yes | `people` (flag only) |
| counters | | yes | |
| win probability, xG, score (existing) | | | `match` (unchanged) |

### 7.5 Verifier additions

- **Claims lexicon** per language: tactical words (`high line`, `deep`, `low block`, `pressing`, `in behind`, `switch`, `between the lines`, their de and fr equivalents)
  are allowed only when the moment's facts carry the matching insight or `shape` value; trait words only for players who have the trait.
- **Numbers**: `season_goals` and the counters join `allowed_for`; attribute ratings never do (a line never says a rating).
- **Names**: the fast layer may name every player in its params; the 60 s window rule of `verify_sentence` in MCP still holds.

### 7.6 Target metrics (density report, x1, per channel)

From `docs/COMMENTATOR.md` (EPL sample). Targets allow for the synthetic voice: `lang.est_seconds` plans `len / CPS + 0.3 s` per line with CPS 12.5 (en),
12.0 (de), 13.0 (fr). At 22 lines a minute the 0.3 s pauses take 6.6 s, so even 100% coverage gives about 667 characters, about 117 English words per minute
(at about 5.7 characters per word with space and punctuation); 70% coverage gives about 80. The broadcast 131 is out of reach for this voice and is not a target.
Words per minute is gated on the en channels only (German words are longer, French CPS differs, the profile is English); de and fr are gated on coverage.

Reachability, worked on the insert (en/expert, 4381 to 4402 s), with the 7.1 rules: loose-ball fragment, "Ibsen cuts it out." (4382.7), "Rasmussen." (4385.4),
one context line in Rasmussen's 4.2 s hold, "Long for Tavares." (4389.6), "Tavares, inside..." (4392.0), the goal call (4393.7, 3.4 s), the analyst (from 4397.1).
That is about 8 lines in 21 s (23 per minute) and about 84% coverage; without the context line about 66%. The context line in open play is what the coverage
target rests on.

| Metric | Broadcast profile | Now | Target | Gate |
| --- | --- | --- | --- | --- |
| Segments per minute | 22 | 11.4 (insert), 2.0 (full match) | 18 to 24 | >= 16 on the insert and on the median of 20 guided windows |
| Words per minute (en channels) | 131 | not measured | 80 to 110 | >= 75 |
| Speech coverage | about 90% | 76 to 81% (insert, measured on the recording), 16.6% (full match) | 75 to 90% | >= 75% on the insert (it is 76 to 81% today and must not fall), >= 70% on guided windows, >= 55% over full matches |
| Share of gaps over 3 s | 2.5% | not measured | <= 8% | <= 12% |
| Segments of 5 words or fewer | 56% | not measured | 45 to 65% | inside 40 to 70% |
| Segments of 12 words or more | 10% | not measured | 7 to 15% | inside 5 to 20% |
| Segments naming a player | 38% | not measured | 33 to 50% | 30 to 55% (an upper bound too: without name rationing the estimate is about 80%) |
| Names per 100 words | 9.3 | not measured | 7 to 12 | inside 6 to 14 |
| Words per minute, 30 s after a goal vs the match | +19% (156 vs 131) | not measured | +10 to +25% | > 0% |
| Captions skipped by the voice (skeleton and analyst lines; fast fragments are captioned only when voiced, 7.1) | n/a | 253 of 588 in the Phase 8 run | <= 30% | <= 35% |
| Analyst-voice lines per minute (context plus model) | about 2 (context, evaluation, tactics rows) | under 0.2 | 1.0 to 2.0 | >= 0.8 |

All metrics use the spoken lines (`say` plus `voice` starts in live), per channel, and are computed by `evaluation/density.py` into `docs/DENSITY.md`.

### 7.7 As built in phase 3 (what the density dry run changed in 7.1 and 7.2)

The dry run (`docs/DENSITY.md`, last section) showed that the rules as written left the voice about half idle in a guided window. Changes, all in code:

| Rule | As written | As built |
| --- | --- | --- |
| Pass fragments | `pass_kind` for switch, through, cross, long, lay-off, back under pressure; ttl 2.0 s | every pass kick except restarts and corners (a first-time pass is its own type); ttl and voice wait grow to the flight (`t_arr`), at most 4 s; a short pass only as a name chain since 7.8 |
| Other fast triggers | touch (receipt), carry from 10 m, press_on from tracking | also carry from 6 m, `press_on` from skeleton pressure events (presser = the event's player, pressed = whoever has the ball), `duel` (facet `interception`) from every interception, `restart` and `setpiece_setup` from the restart pass (a free kick within 32 m is a setup, a corner is the skeleton's own call) |
| Name rationing | every second fragment names a player while one team keeps the ball | every third (every fourth in 7.8; since 7.9 a name-less fragment only for a ball worth a word, never two in a row) |
| Captions | fast fragments captioned when voiced | fast and context lines |
| Context supply | one fact once per player per half; 7 kinds | also the score and the clock (about once a minute), the match so far (shots, corners, fouls, possession), more facts per player (assists, clean sheets, apps, captain, age, left foot, tallest), a fact comes back after 20 minutes (never since 7.8: once per match), the same player at most every 10 minutes |
| Context caps | one per 40 s in play, one per 10 s and 3 per window in a dead ball | one per 12 s in play, one per 7 s and 3 per window in a dead ball; dead-ball slots every 5 s from the stoppage; a receiver holding the ball 4.5 s opens a second slot |
| Context wording | any | shortest while the ball is in play, longest in a dead ball and after a long hold |
| Dead ball | known once play has stopped | a foul, a card, a shot that was saved, off target, hit the post or scored, and a pass that left the pitch (from its arrival); it ends with the next event |
| Skeleton calls | `long_ball` and `pass_final_third` replaced; shortest wording in play for play-by-play under 40 | same; the shortest wording in play applies to `tackle_won`, `sprint` and `shot_blocked` |

Kinds that fire in phase 3: `touch`, `pass_kind`, `carry`, `duel`, `restart`, `setpiece_setup`, `press_on`. `take_on` (a lost one shares its event with a skeleton tackle call),
`block` (a skeleton shot moment owns it), `in_behind`, `line_break` and `duel_1v1` (tracking) have their words and wait for phase 5. The fast layer is a flag on the
runner (`Runner(fast=True)`, off by default) and stays off until phase 6 switches it on together with the protocol and the updated tests.

**Review fixes to the wording (2026-10-21, Opus review of phase 3).**

| Finding | As built before | Now |
| --- | --- | --- |
| Name-less pass fragments were verdicts ("Good ball, and they keep it.", 32% of the en/expert segments of comeback-7, said at the kick before the ball arrived) | two or three generic lines per language | they say what the kick shows and nothing else: the pass type ("Switched.", "Short pass."), the lane where it starts ("Played short down the left."), the direction when the type does not already say it. No verdict, no outcome; a test fails on a verdict word in any `pass_kind` wording |
| `touch` read `dir` as the receiver's next action ("then forward it goes") | forecast, contradicted on screen in about 60% of the cases | `dir` is how the ball arrived and the wordings say so ("Forward to Rasmussen."); name-less touches say only that the ball is received |
| `press_on` said "presses high up here" for every pressure event | most of them in the presser's own half | the builder sets `facet` `high` only when the presser stands at 60 m or more up the pitch in his own attacking direction (`PRESS_HIGH_X`), otherwise `low` ("gets tight on the ball"); about one press in five is high |
| Claims lexicon (7.5) missing | not built | `verifier.CLAIMS` and `TRAIT_WORDS` in en, de and fr: a tactical phrase needs the claim in the moment's facts (`claims_of`: kind and facet, and the `shape` and `build_up` blocks of phase 7), a trait phrase needs a player with that trait named in the same sentence (the roster is the fact). Codes `claim_unsupported` and `trait_unsupported` |
| Context leads ("While the ball is dead, worth a mention:") | a third, meta wording for every context kind | removed, two wordings per kind. The long-share and after-goal gates had leaned on them (79 such lines of 1,542 segments is 5.1%, exactly the 5% gate), see docs/DENSITY.md |
| Dead-ball slots after saves, the post and goals | saved and post shots opened a dead ball; after a goal the last toucher got a note, often the conceding keeper | only a goal and an off-target shot (goal kick) open a dead ball here; after a goal the conceding side gets no `player_note` |
| German press and ten-men wordings | "lässt den Ball gern laufen" (possession play), "ist einen Mann weniger" | "presst kaum und lässt den Gegner kommen", "hat einen Mann weniger" |

### 7.8 Review fixes, round 2 (2026-10-21, second review of phase 3)

| Finding | As built before | Now |
| --- | --- | --- |
| The season-goals note used the pre-match number ("Fontaine has scored six this season" at 4616.8 s of comeback-135, 223 s after his goal) | `season_goals = season.goals` | The profile's season numbers are from before the match (1.1), so a note adds what the player has done in this match so far: goals (`season_goals`), assists (`count`), and the appearance (`apps + 1`). The goal itself is news in the dead ball after it: `counter_note` facet `tally` ("Fontaine now has seven goals this season") or `tally_first`. The analyst's `people` block (7.3) must add the same when phase 7 builds it |
| `lane` and `dir` read as the path of the ball ("Switched down the right" for a switch that ends on the left; fr "Joué court dans l'axe, dans l'axe." 12 to 24 times per channel) | `lane` = side of the start point, worded "down the left"; `dir` appended unless the type said it | `lane` is the flank the kick leaves from and is worded "from the left" ("Switched from the right.", "Verlagert von rechts.", "Jeu renversé depuis la droite."). A pass fragment has no `dir` any more (the type says it, or nothing does); `dir` stays on `touch`, where it is how the ball arrived |
| The volume layer narrated routine passes (`pass_kind` 53% of the segments, "Played short ..." 25 to 27%; the profile has ball movement at 2.7%) | every pass kick got a fragment | A short pass has no `pass_type` and `routine`: it is said only as a name chain ("Lindqvist to Lemaire.", expert also with the flank he stands in) and only on a turn that may name a player (`named_only`); on the other turns it says nothing. A first-time pass is `named_only` too. The special types (switch, through, cross, long, lay-off, cut-back, back, clearance) keep their wording. The share of pass fragments that name nobody is 5 to 6% of the segments, `pass_kind` as a whole 23% |
| Names | every third fragment | `NAMED_EVERY = 4`: the name chains and the places below fill what the mechanics used to |
| What a receipt says | "Under control.", "Settled on it." | where the receiver stands when the ball arrives, in his side's attacking direction (`third`: own, middle, final; `wing`: left, centre, right): "In the final third, left side.", "Tavares in the middle third." Known at the receipt. A name-less fragment stays at 6 words (en) and 7 (de, fr) |
| Tempo note fired when a side simply lacked the ball, for both sides at once, at the class limit | own completed passes per minute under 4.5 or over 8.0, no hysteresis | A side that has at least 55% of the completed passes of both sides over three minutes, enters "slow" below 3.5 a minute and leaves it above 4.5, enters "high" above 9.0 and leaves it below 8.0. Wording "in no hurry on the ball" (not "slowing the game right down"); `tempo_slow` and `tempo_high` join the claims lexicon (7.5) |
| The same player sentence came back 3 to 5 times per match | a fact could return after 1,200 s | A fact about a player is said once in the match, never twice in a row of one kind, and a live number (`passes`: the passes he has completed so far, from 12 up to 99, in steps of 12) is the one fact that comes back, because the number is different. Every spoken `player_note` of a full match is now distinct (was 42 to 44 of 115 to 124). 7.2's "once per player per half" is superseded |
| 12 s of silence after a goal; the first slot (1 s) was always dropped behind the call and the analysis | dead-ball slots at 1, 6, 11 ... s | After a goal the slots start at `GOAL_QUIET_S = 9` s (5 s apart): the move that led to the goal (`counter_note` facet `move`, up to three team-mates and the scorer, 13 words) and his tally. A stretch with nothing for 4, 10 and 16 s offers a slot in play (`QUIET_SLOTS_S`); a receipt keeps its two hold slots and adds the 10 and 16 s ones |
| A kick fragment ran past the arrival and cost the receipt its touch | longest fitting wording | The wording ends with the ball's flight plus 0.7 s (`arr` on the moment, `ARRIVAL_SLACK_S`); the receipt's touch waits 0.8 s for the voice |
| Near-identical loops ("Settled on it." 17% of a channel) | the longest wording that fits, every time | Fast fragments take turns (`ChannelDirector._turn`): of the wordings that fit, the one of that kind used longest ago (names do not count); the longest on a tie |
| Press wording in German and English | "bleibt eng am Ball" (the idiom for close control), "presst hoch an dieser Stelle", "presses high up here" | `press_on`: de "läuft früh an" (high) and "geht eng drauf" (low), en "presses high", fr "presse haut"; "läuft früh an" joins the `press_high` claim |

Gates after these changes are in docs/DENSITY.md. Held: every full-match gate but the 12-word one (1%), every window gate but segments per minute (14.4 against 16, failing in the first build too),
the insert stand-in but the 12-word one. Not held: the 12-word share (a fast fragment is capped at 6 words, the context lines are one fact each; see DENSITY.md), the insert's speech coverage on its worst channel (69 against 75) and its skipped captions (50%).

### 7.9 Review fixes, round 3 (2026-10-21, third review of phase 3)

The second review found that round 2 moved the pass mechanics instead of removing them: name-less receipt and zone fragments were 34 to 38% of the segments ("Under control." 231 times,
"In the final third." 215 times, a zone and its mirror image 110 times each). Gate numbers are in docs/DENSITY.md, which is regenerated by `python -m matchvoice.evaluation.density`.

| Finding | As built before | Now |
| --- | --- | --- |
| The volume layer sounded like a position readout | a receipt said the third and the side; a routine pass was a name chain on one turn in four; `NAMED_EVERY = 4` | Names and verbs: every routine kick is a name chain (`X to Y`, `X finds Y`, `X, under pressure, finds Y`, `X drives it to Y`, from `pressure` and `height` of the kick row), a receipt says who has the ball and how he took it (`touch`: control, chest, head; `facing`; the passer as `kicker`), a pass with a type always names its target (`pass_prep`: "Long ball for Tavares", "Switch to Rasmussen"; a clearance has none). The zone is a rare wording (`PLACE_EVERY_S`, one order, never the zone just said). A name-less fragment is for a ball worth a word (`bare_ok`) and never two in a row (`NAMED_EVERY = 2`) |
| The first-time pass of the insert's goal was lost | the receipt "Tavares in the middle third." was voiced, the pass to Fontaine was rationed away | A receipt is called `TOUCH_SETTLE_S` (0.5 s) after the ball arrives and is void if the receiver plays on first; it is not called when the kick already named him with its type. A name chain has priority 27, below the skeleton's foul and tackle calls; a kick fragment ends 0.2 s after the landing (`ARRIVAL_SLACK_S`), a routine pass has no landing limit so its rota is not reduced to one wording |
| The game state was the same formula every minute (46 to 67 lines a match), frozen in added time, said "nothing is decided" at minute 3 | `STATE_EVERY_S = 60` | Only when the score has moved or `STATE_STEP_S` (5 match minutes) have passed, never within `STATE_GAP_S`, not before the tenth minute unless a goal moved the score; facets `goalless`, `level`, `lead` with two wordings that take turns and `_added` for added time (no minute) |
| Counter notes looped word for word (the pass streak 21 times, the possession line 14 times) | streak 10, 15 and 20 every time, possession exempt from growth | A streak is news only when it is longer than the last one of that side (at most `STREAK_MAX` per match); a stat only when its value moved by `STAT_STEP`, at most `STAT_MAX` per team and fact, alternate wording; possession carries its percentage; a news item is said once. More facts to say: crosses, long balls, balls won back, shots on target, saves, throw-ins, goal kicks, the last three minutes of the ball, a side's spell without a shot |
| Dead-ball slots every 5 s, the director spaced them 7 s apart with a 3 s wait: a built slot was dropped and its fact lost (2 of 5 goals lost their tally) | slots every 5 s, six per stoppage | The builder follows the director: slots are `CONTEXT_DEAD_S + SLOT_SLACK_S` apart, a slot inside that distance of the last built line is not offered, `CONTEXT_PER_WINDOW` lines per dead-ball window, `CONTEXT_PLAY_S` in play. News is served by rank (the goal's move, then its tally, then the rest) and the "last kind to the back" rule does not separate them. The match facts wait for a dead ball or a long hold (none in play) |
| Meta leads on every long context wording | "Worth noting:", "Worth a mention:", "Good to know:", "Bemerkenswert:", "Auffällig:", "À noter :", "Regardez :" ... | gone. A context kind has a second wording only where the facts hold a longer sentence (`{note_long}`, `{also}`, `{more}`) |
| Bad wordings | de "{player}, auf der linken Seite, auf {target}." (two "auf"), "Lemaire, dead centre.", "X clears it to Y", "X gets tight on the ball" | `wing` is "links außen" / "out on the left" / "in the middle"; a clearance has no target; "X gets tight." |
| The 12-word share was 0 to 1% | context lines were one fact each | Longer connected sentences: the move before a goal or a chance, the move that ended in a stoppage, the tally with its assist, the state with the shots of both sides, a match fact against the other side's, two or three facts of one player in a dead ball; the beginner's explanation of a restart |
| The insert's analysis fallback was skipped behind a 5.2 s goal call | ttl 4 s from the goal | `STANDIN_BEHIND_GOAL_S`: its freshness starts when the call ends |

Gates after this round: windows hold every gate but naming a player and names per 100 words; the full matches hold all but those two and the share of five-word segments; the insert
holds segments, coverage, gaps, skipped captions. What does not hold, and why, is the last section of docs/DENSITY.md: a stream of names and verbs puts a name in more than 80% of the
segments, and the sentences a template can say without a name are not enough to carry the rest. The gates themselves were not changed.

### 7.10 Review fixes, round 5 (2026-10-21, fifth review of phase 3)

The fourth review found the double naming moved (the receipt named the receiver, then his own kick named him again: 237 to 404 pairs per match and channel) and the context layer a stats ticker
(125 of 184 context lines were counters). Gate numbers are in docs/DENSITY.md.

| Finding | As built before | Now |
| --- | --- | --- |
| A name was said by two fast lines in a row | "Inside to Wrenfield." then "Wrenfield gets it away." | `NAME_GAP_S` (6 s): a routine kick whose kicker a fast fragment, a skeleton tackle or a duel named a moment ago is not called, or, when it shows something (`pressed`, `driven`) and at most every `SHOWN_GAP_S`, called without him (`name_said`); a typed pass says only its target (`kicker_said`); a carry goes name-less; a turnover resets the rationing; a receipt does not name a kicker named a moment ago |
| Kicker-only lines repeated, "gets it away" read as a clearance | 5 wordings, one line 28 to 38 times a match | more wordings, six to eight for what the kick shows; "gets it away" gone |
| The match facts were a ticker | `STAT_MAX` 5, no spacing, every fact | `MINOR_GAP_S` between stats and minor news, `STAT_MAX` 3 and `STAT_MAX_BY`, `NEWS_MAX`, no stat while the ball is in play, a streak and the end of its move one fact (`streak_told`), the nth shot marks the shots stat, the pass count once per player |
| One idea four times (sit deep) | `TACTIC_GAP_S` 90 s per side | `TACTIC_IDEA`: an idea once per side in a match, whichever of shape, press and phase says it |
| "one times" | `{other} have gone long {m_word} times` | `m_times` ("once"), `sh_shots` ("one shot") |
| The 12-word share fell with the ticker | | player notes of two or three facts say the club, `PLAYER_GAP_S` 300 s, `PLAY_NOTE_GAP_S` for a one-fact note in play |

Open: naming a player, names per 100 words and the short share still fail on windows, matches and the insert; the insert has no segment of 12 words or more and never says the assist inside its window.

---

## 8. Protocol, UI, MCP, evaluation

### 8.1 Protocol v1, additive (stays `v: 1`)

| Change | Where | Old clients |
| --- | --- | --- |
| `hello.players[*]` gains `role`, `foot`, `traits`, `attrs` (array in the order of `hello.attrNames`), `h` (height_cm), `age` | hello | ignore unknown fields |
| `hello.attrNames`, `hello.subTypes`, `hello.subFields`, `hello.passTypes`, `hello.heights`, `hello.bodyParts` | hello | ignore |
| `hello.teams[*].tactics` (2.1) | hello | ignore |
| `hello.tracking`: `{"hz": 10, "fi": 0.1, "keyEvery": 10, "z": true}` | hello | ignore |
| `f.x`: enriched rows of this frame, fixed arrays named by `hello.subFields`: `[eid, sub_type, side, player, x, y, end_x, end_y, outcome, pass_type, height, body_part, pressers, flags, target, t_arr_ds]`; `flags` bit 0 implicit, 1 first_time, 2 under pressure, 3 into box. A row goes out in the frame of its time of knowledge (0.1): the kick row carries kick fields only (`outcome` 0 for passes), the outcome comes with the receipt or interception row; `assist_eid` travels on the shot row's annotation | frame | `f.e` is unchanged, `x` ignored. Note that `f.e` itself still carries the skeleton outcome at the kick (protocol v1, unchanged); the new commentary layers must not read it before `t_arr` |
| `tk` message (3.7) | new kind | ignored (UI `Sim.ingest`, MCP and evaluation skip unknown kinds) |
| new `log` insight kinds (`d.kind`): `line_break`, `run_in_behind`, `press`, `shape`, `tempo`, `fatigue`, `posture`, `duel_1v1`, `overload`; `d.ev` are eids, new `d.fr` frame range | log | additive per the compatibility rule |
| `say.m` may be >= 1,000,000 (fast) or >= 2,000,000 (new analyst) | say | ids are opaque keys |

The insight rate cap of `pipeline/insights.py` (3 per minute) stays for the log panel; the fast and context layers read insights directly, not the log.

Bandwidth (live, 1x, 5 Hz `tk`): about 140 bytes per `tk` as JSON deltas (AUDIT section 5) = 5.6 kbit/s, plus `f.x` rows (about 40 per minute with receipts,
about 70 bytes each, 0.05 kbit/s) and about 20 `say` per minute per channel x 6 channels (about 250 bytes each, 4.0 kbit/s), plus `voice` messages for
skeleton lines: about 10 kbit/s in total against 0.6 kbit/s today. Still irrelevant for a viewer; the earlier "under 9 kbit/s" left out the say arithmetic. The recorded insert grows from 13.5 KB by about 15 KB
(105 `tk`) plus the new lines. A full-match `replay.json` at x30 gains about 3,900 `tk` (0.55 MB raw); the static build ships the insert only.

Tests that change on purpose: `test_pipeline.py` message kind set (adds `tk` only where tracking is on), `test_evaluation.py` x1 speech share upper bound (0.4 becomes 0.95), `test_mcp.py` if it
counts lines at a time, `test_live_captions.py` where it asserts captions-first for every line (the fast layer captions at voice start).

### 8.2 UI board (`ui/src/pitch.ts`, `sim.ts`)

This reverses the Phase 14 decision that left out ambient player dots. It needs the user's yes (PLAN-DATA phase 0).

- `Sim` keeps a `Float32Array` ring of the last 4 s of `tk` (2 keyframes plus deltas, decoded on arrival, no React state), interpolated at render time inside the existing rAF loop.
- 22 dots in team colours (the existing `tune` contrast rules), shirt number inside at sizes where it fits, the player on the ball enlarged with the existing name tag.
- Ball: drawn at `(x, y)` with the shadow on the turf and the ball lifted by `z` (screen offset `z * 0.35` of the pitch scale, radius `+4%` per metre), so a switch or a cross reads as height.
- Shape: the out-of-possession team's back line as one thin line across the width at `sh.line`, fading in when it changes class; an offside line marker only during a `run_in_behind`.
- Insight marks, each tied to its evidence frames and fading in 2 s: an arrow along a run in behind, a ring on presser 1, a short bracket on a line-breaking pass.
- No new panels or controls. "Why this line" shows the insight and its `ev` and `fr` for fast and context lines, so evidence works for the dense layer.
- `prefers-reduced-motion`: dots step at 2 Hz without interpolation, no marks animate.
- Budget: 60 fps held (median 16.7 ms today), no frame over 20 ms in the goal window.

### 8.3 MCP (`mcp_server/tools.py`)

The seven tools stay as they are. Four new, read-only, no key:

| Tool | Returns |
| --- | --- |
| `player_profile(match, player, t=None)` | attrs, role, traits, foot, season, live counts and fatigue at `t` |
| `team_shape(match, t)` | posture, shapes, line height, length, width, compactness, press class and PPDA at `t`, with the frames used |
| `possession_chain(match, t)` | the possession running at `t`: skeleton and sub-events with pass types, heights, pressure, and the insights on it |
| `tracking_at(match, t)` | positions of all 22 players and the ball (x, y, z) at the frame of `t` |

`verify_sentence` applies the claims lexicon (7.5).

### 8.4 Evaluation

- `evaluation/density.py`: the metrics of 7.6 on the insert, 20 guided windows (fixed seeds 1001..1020, random arcs from a fixed stream) and the three demo matches at x1;
  writes `data/eval/density.json` and `docs/DENSITY.md`.
- Consistency report: appointment violations, max player speed (p99 and max), ball invariants (AUDIT 3.3), eid overflow, sub-event counts per kind against the
  plausibility ranges of 4.2.
- Detection report: precision and recall of `run_in_behind` and `line_break` against `micro_truth.jsonl`.
- The existing grounding, coverage, latency and speech metrics keep their definitions; `docs/EVAL.md` regenerates with no calls.

---

## 9. New modules

| Path | Content |
| --- | --- |
| `backend/matchvoice/sim/profile.py` | player attributes, roles, traits, season (1) |
| `backend/matchvoice/sim/tactics.py` | base plan, shapes, posture schedule (2) |
| `backend/matchvoice/sim/micro/` | `segments.py` (restart segmentation, streams), `kinematics.py` (3.2, 3.5), `ball.py` (3.3), `plan.py` (appointments, runs, gap repair), `enrich.py` (4), `encode.py` (`tk`) |
| `backend/matchvoice/interpret/` | one module per insight family (5), a `Feed` that the runner calls per event and per frame |
| `backend/matchvoice/commentary/fast.py` | `TouchBuilder` and the context builder (7.1, 7.2) |
| `backend/matchvoice/commentary/templates.py` | new kinds, en/de/fr x beginner/expert |
| `backend/matchvoice/evaluation/density.py` | 7.6 and 8.4 |
| `ui/src/tracking.ts` | `tk` decoder and ring |

## 10. Decisions this design needs from the user

The full list, with options and pro and contra, is in `docs/PLAN-DATA.md`, section "Open decisions for the user". The five original ones:

1. Architecture A (skeleton plus micro-sim) as described, with events and truth frozen.
2. The board shows all 22 players, the ball height and one shape line (reverses Phase 14).
3. The voice talks most of the time (target 75 to 90% coverage), which means many short fragments.
4. A Haiku budget for the re-recording (exact number in `docs/PLAN-DATA.md`).
5. Synthetic season numbers (`season.goals` and so on) may be spoken as context. They are invented like everything else; the alternative is to drop `season` and keep only match-internal context.

## 11. Review log (Opus adversarial pass, 2026-10-21)

Checked by reading `sim/engine.py`, `sim/arcs.py`, `commentary/analyst.py`, `moments.py`, `precompute.py`, `pipeline/runner.py`, `guided.py`, `demo.py`,
`protocol.py` and by small runs of the simulator and the pipeline (scripts in the session scratchpad, no model call, no ElevenLabs call, port 8000 untouched,
`data/cache/analyst` still 38 entries afterwards).

| # | Finding | Evidence | Fix in this document |
| --- | --- | --- | --- |
| 1 | `first_time`, `lay_off`, volleys and headers on arrival could never fire: the skeleton adds 1.3 to 4.6 s of dwell after every arrival | comeback-135: arrival to next event min 1.46 s, median 2.98 s, 0% under 0.6 s; incomplete pass end to interception median 2.7 s; corner arrival to header 2.95 s | arrival retiming and dwell filler (3.3) |
| 2 | Receivers are often far from the pass end, so appointments pull players out of shape and violations have a floor | 37 to 41% of receivers are the nearest by `_nearest`'s own geometry, median 20 m from the end; 0.2 to 0.6% of passes infeasible even in the best case | measured floor, gate 1.5%, realism measures replace the "3 nearest" gate (3.4); 0.40 corrected to 0.35 (3.2) |
| 3 | Fatigue fed by tracking sprints chained every segment to earlier ones, breaking window equals full-match | 3.2 step 8 read `fatigue`, 5.10 used sprints from tracking | `fatigue_base` (3.2, 5.10) |
| 4 | Counter-based moment ids differ between a live run from mid-match and a run from kick-off; `tactical_shift` ids are recording keys | `MomentBuilder._next` pattern; `Runner._prepass` looks recordings up by id | derived ids (0.2) |
| 5 | Kick-time rows carried future facts (`assist`, receipt `first_time`); naming `receiver` at the kick reveals completion; the existing `long_ball` template already says "gets onto it" at the kick | `encode_event` sends `outcome` at the kick; recorded insert caption at 4382.7, receipt at 4385.4 | time of knowledge (0.1), `target` and no pass `assist` (4.2), `f.x` timing (8.1), the fast layer replaces `long_ball` and `pass_final_third` (7.1) |
| 6 | The no-lookahead test as written would fail for the wrong reason (the planner looks ahead) | 5, test definition | test redefined, start-independence test added (5) |
| 7 | Continuity block would fill with fragments: prompt churn, useless context, fragile insert | `Runner._said`, `RECENT_LINES = 3`, skip removal | v5 continuity rule (7.3) |
| 8 | Live runs of demo matches already miss the cache | stub-model run: 8 of 8 (comeback-7), 9 of 9 (red_card-7) prompts uncached | stated (7.3), plan cache table corrected |
| 9 | Insert coverage figure: 53% not reproducible | `ui/public/insert/replay.json`: 76 to 81% per channel, 4 lines, 11.4 per minute | table 0 and 7.6 corrected; the insert gap is segments, not seconds |
| 10 | Fast layer would double-call passes that already have skeleton moments, and the long skeleton line blocks the insert | `long_ball` 26 and `pass_final_third` 28 fire on the same passes (56 and 37 times in comeback-7, AUDIT 3.4); first insert line 4.6 s | the two kinds are replaced, the rest deduplicated, shortest wording in play (7.1) |
| 11 | Captions-first for every touch would push skips past 40% | about 25 fast moments per minute | fast captions at voice start (7.1) |
| 12 | Names per 100 words would land near 16 (gate 14) | arithmetic in 7.1 | name rationing (7.1) |
| 13 | Words per minute target unreachable for the voice | `lang.CPS`, `PAUSE_S` | target 80 to 110, gate 75, en only (7.6) |
| 14 | Dead-ball time stays silent with one context line per 40 s | 19 to 25% of time in gaps over 10 s | dead-ball cap one per 10 s (7.2) |
| 15 | `ten_men` and `chase` could not hold at once | red_card arc, 38' and 61' | postures compose (2.3) |
| 16 | Determinism claimed for any machine; cost targets unmeasured and optimistic | `random.gauss` and skeleton `math.exp`; step count arithmetic | claim narrowed, Docker check, targets marked as estimates, tracking opt-in (3.6) |
| 17 | Bandwidth total understated | say arithmetic | about 10 kbit/s (8.1) |
| 18 | Insert touches overstated (gate asked 10) | event list 1479 to 1483 plus gap repair | 7 touches, listed (4.1) |
| 19 | AUDIT's "pass volume 30 to 50% low" contradicts its own counts | 1,153 to 1,279 passes per match | stated, no rule R change needed (4.1) |
