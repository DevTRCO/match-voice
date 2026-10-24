# Football data feeds: field catalogue for the synthetic data layer

Research A. Purpose: list what real football data feeds provide, so the synthetic layer (see the problem statement in docs/COMMENTATOR.md:
thin events, sparse commentary) can model football-realistic fields. Only public documentation was read. Nothing here is copied from
a source and no real data is redistributed; all descriptions are my own summaries. The synthetic data stays fictional.

Sources read (all public):

| Short name | What | URL |
| --- | --- | --- |
| SB-EV | StatsBomb Open Events spec v4.0.0 (PDF, last updated 2019) | https://github.com/statsbomb/open-data/blob/master/doc/Open%20Data%20Events%20v4.0.0.pdf |
| SB-360 | StatsBomb Open 360 Frames spec v1.0.0 (PDF) | https://github.com/statsbomb/open-data/blob/master/doc/Open%20Data%20360%20Frames%20v1.0.0%20(1).pdf |
| MET-README | Metrica Sports sample data README | https://github.com/metrica-sports/sample-data |
| MET-DEF | Metrica event definitions (PDF) | https://github.com/metrica-sports/sample-data/blob/master/documentation/events-definitions.pdf |
| MET-G1 / MET-G3 | Metrica sample files: Game 1 CSV (tracking + events), Game 3 EPTS/FIFA XML + JSON | https://github.com/metrica-sports/sample-data/tree/master/data |
| FOT | Friends of Tracking tutorials on Metrica data (speed, pitch control, EPV) | https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking |
| SC | SkillCorner open data (broadcast tracking, dynamic events, phases) | https://github.com/SkillCorner/opendata |
| OPTA-KL | Opta F24 ids as used by the open-source kloppy parser | https://github.com/PySport/kloppy/blob/master/kloppy/infra/serializers/event/statsperform/deserializer.py |
| OPTA-SA | Opta F24 ids as used by socceraction | https://github.com/ML-KULeuven/socceraction/blob/master/socceraction/spadl/opta.py |
| OPTA-VIS | Opta Analyst article on Opta Vision tracking stats | https://theanalyst.com/articles/opta-vision-stats-tracking-data-premier-league |
| PPDA-PL | Premier League explainer on passes per defensive action | https://www.premierleague.com/en/news/4250153 |
| LINE-ARX | arXiv study on back-four line height and compactness (LaLiga) | https://arxiv.org/abs/2511.06191v1 |
| DRIB | Driblab Arrigo (line height, block depth, compactness product note) | https://www.driblab.com/blog/arrigo-spatial-coverage |

Evidence limits, stated up front:

- Opta's own F24 documentation is behind a client login. Opta ids below come from two open-source parsers that implement it
  (OPTA-KL, OPTA-SA). Ids marked (os) are confirmed in that code; names of other qualifiers are not claimed.
- Hawk-Eye and Second Spectrum (the Premier League tracking feed since 2013 has been TRACAB, then Genius/Second Spectrum) do not publish
  schemas. What broadcasters show is known only from vendor articles (OPTA-VIS, DRIB, SC), so the "broadcast insight" section lists
  metric definitions, not feed fields.
- Ball z: not found in any open tracking format read here. Metrica and SkillCorner tracking carry ball x,y only (SC does not document ball
  keys beyond "ball_data"). Ball height in event feeds is categorical (pass height, shot goal-mouth z), not a trajectory.

---

## 1. Player attributes and roles

| Field | Meaning | Where |
| --- | --- | --- |
| player id, name, jersey number | identity of the actor and the people around them | SB-EV Lineups, MET-G3 metadata (`ShirtNumber`) |
| position (25-value role list: GK, RB, RCB, CB, LCB, LB, RWB, LWB, RDM, CDM, LDM, RM, RCM, CM, LCM, LM, RW, RAM, CAM, LAM, LW, RCF, ST, LCF, SS) | tactical role at the moment of the event, not just line (DEF/MID/FWD) | SB-EV Appendix 1 |
| position per event | the role the actor occupied when the event happened (a left back can be seen as a winger) | SB-EV `position` |
| starting position (type and a normalised x,y on the pitch) | where each player lines up at kick-off | MET-G3 metadata `position_type`, `position_x/y` |
| substitution (replacement player, reason injury or tactical) | who came on and why | SB-EV Substitution; Opta type 18/19 (os) |
| lineup with formation | the XI with roles | SB-EV Starting XI; Opta F24 formation qualifiers 130/30/131 (os) |
| preferred foot, height, age, nationality | not in the open specs read; kept in club/roster databases, not in event feeds | n/a (not documented in the sources above) |
| physical profile: top speed, high-intensity counts, distance (e.g. PSV99) | season-level player physical metrics | SC (season aggregates, glossary referenced) |

Gap note: the open feeds give role and number but no player traits. Commentators still talk about traits (quick, left-footed, aerial threat),
so these must be invented per synthetic player (see section 7).

## 2. Team tactics

| Field | Meaning | Where |
| --- | --- | --- |
| formation string (e.g. 4-3-3) | the declared shape | SB-EV `tactics.formation`; Opta qualifier 130 (os) |
| tactical shift event | the team changes shape mid-match; new formation and role map | SB-EV "Tactical Shift"; Opta type 40 formation change (os) |
| play pattern (regular, corner, free kick, throw-in, counter, goal kick, keeper, kick-off) | how the current passage of play started | SB-EV `play_pattern` |
| counter-attack rule | counter = possession started by an open-play turnover outside the final third, at least 75% direct, at least 18 yards toward goal (derived, not collected) | SB-EV `play_pattern` 6 |
| possession id and possession team | numbered spell of control by one team | SB-EV `possession`, `possession_team` |
| phases of play | labelled in-possession and out-of-possession phases with start and end frame | SC phases file |
| counterpress flag | pressing actions within 5 s of an open-play turnover | SB-EV (on pressure, duel, block, 50-50, interception, dribbled past, foul) |
| Opta counter-attack qualifier | event is part of a counter | Opta qualifier 23 (os) |
| lane and area division | pitch split into 5 horizontal lanes and 3 vertical areas for reference | MET-DEF |
| team-level out-of-possession blocks (low block etc.) | named defensive shape types, time share per block | OPTA-VIS (named, not defined there) |

## 3. Tracking frames

| Field | Meaning | Where |
| --- | --- | --- |
| frame number, period, time in seconds | one row per frame; 25 Hz in Metrica (`FrameRate` 25 in the EPTS metadata), 10 fps in SkillCorner | MET-G1, MET-G3 metadata, SC |
| player x,y for all 22 | position of every player each frame | MET-G1 (CSV, one x/y pair per jersey), MET-G3 (semicolon list per frame), SC |
| ball x,y | ball position each frame; no z in the Metrica or documented SkillCorner data | MET-G1, SC |
| normalised coordinates 0..1, origin top-left; pitch 105 x 68 m | Metrica convention; tutorials convert to metres from the centre | MET-README, FOT (Metrica_IO) |
| centre-origin metres | SkillCorner convention | SC |
| pitch size per match | needed because pitches differ in size | MET-G3 metadata `FieldSize`, SC match file |
| NaN for off-pitch or missing players | substitutes and unseen players have no coordinates | MET-G1 |
| `is_detected` per player | whether the player was seen or extrapolated (broadcast-based tracking) | SC |
| possession per frame (player id, side) | who has the ball now | SC |
| visible-area polygon | which part of the pitch the camera saw | SB-360, SC (`image_corners_projection`) |
| body pose (29 joints per player, 25 fps, two matches) | skeleton and orientation | SC |
| tracking-event sync | event rows carry start and end frame and x,y so events line up with frames | MET-G1 events, MET-G3 events |
| 360 freeze frame | per event, a snapshot of visible players: x,y, teammate flag, actor flag, keeper flag, no identity | SB-360 |
| shot freeze frame | per shot, players near the action: x,y, player, position, teammate flag | SB-EV Appendix 3 |

## 4. Event qualifiers

### 4.1 Event types

| Source | Types (own grouping) |
| --- | --- |
| SB-EV | pass, ball receipt, carry, dribble, dribbled past, duel, 50/50, shot, pressure, block, clearance, interception, ball recovery, dispossessed, miscontrol, error, shield, foul committed, foul won, offside, goalkeeper action, bad behaviour (card), substitution, tactical shift, injury stoppage, own goal for/against, half start/end |
| MET-DEF | set piece, recovery, pass, ball lost, ball out, shot, fault received, challenge, card |
| Opta F24 (os) | pass 1, offside pass 2, take-on 3, foul 4, ball out 5, corner awarded 6, tackle 7, interception 8, clearance 12, miss 13, post 14, saved 15, goal 16, card 17, player off/on 18/19, save 10, claim 11, punch 41, keeper pick-up 52, smother 54, recovery 49, aerial 44, challenge 45, ball touch 61, blocked pass 74, formation change 40 |

### 4.2 Pass qualifiers

| Field | Meaning | Where |
| --- | --- | --- |
| height: ground / low / high | ground = never leaves the turf, low = lifts but stays below shoulder height, high = above shoulder | SB-EV `pass.height` |
| body part: head, left foot, right foot, drop kick, keeper arm, other, no touch (deliberate dummy) | what struck the ball | SB-EV `pass.body_part` |
| type: corner, free kick, goal kick, kick-off, throw-in, interception, recovery | restart or one-touch type | SB-EV `pass.type` |
| technique: through ball, inswinging, outswinging, straight | how the pass was delivered | SB-EV `pass.technique` |
| flags: cross, switch of play, cut-back, backheel, deflected, shot assist, goal assist, miscommunication, no touch | special pass kinds | SB-EV |
| recipient, length (yards), angle (radians, 0 = straight ahead), end location | who, how far, which direction, where it ended | SB-EV |
| outcome: incomplete, out, offside, injury clearance, unknown (blank = complete) | result | SB-EV |
| Opta qualifiers: long ball 1, cross 2, head pass 3, through ball 4, free kick 5, corner 6, penalty 9, chipped 155, launch 157, flick-on 168, switch of play 196, assist to shot 210, second assist 218 (os) | same ideas as above in Opta ids | OPTA-KL, OPTA-SA |
| Opta pass end x,y: 140/141 (os) | where the pass ended | OPTA-KL |
| attempt subtype: clearance, cross, through ball, deep ball, goal kick | attempt intent of a pass | MET-DEF |
| definition of through ball: ground pass through opposing defenders to a player behind the line; deep ball is the same without the ground restriction | useful as a template for wording | MET-DEF |
| definition of cross: pass into the box from any lane but the centre, in the opponent's defensive area | geometry rule for a cross | MET-DEF |

### 4.3 Carries, dribbles, duels

| Field | Meaning | Where |
| --- | --- | --- |
| carry with end location and duration | player moves with the ball at feet | SB-EV Carry (v4.0.0 added it) |
| dribble outcome (complete or incomplete); flags nutmeg, overrun, no touch | take-on attempt and its style | SB-EV Dribble |
| dribbled past | the defender who got beaten | SB-EV |
| duel types: aerial lost, tackle; outcomes: won, lost, success to team, success to opposition | contest and who ends with the ball | SB-EV Duel |
| 50/50 with outcome | two players challenge for a loose ball | SB-EV |
| challenge with fault and result subtypes | duel as defined by Metrica (roughly equal chance at the start) | MET-DEF |
| Opta take-on 3, tackle 7, aerial 44, challenge 45 (os) | same ideas | OPTA-KL |
| shield | player screens the ball out of play | SB-EV |
| miscontrol, dispossessed, error leading to shot | bad touch, tackled without dribbling, mistake before a shot | SB-EV |

### 4.4 Shots and goalkeeper

| Field | Meaning | Where |
| --- | --- | --- |
| body part, technique (normal, volley, half volley, lob, backheel, overhead, diving header) | how the shot was struck | SB-EV `shot.*` |
| type: open play, corner, free kick, penalty, kick-off | origin | SB-EV |
| outcome: goal, saved, saved off target, saved to post, off target, wayward, blocked, post | result | SB-EV |
| flags: first time, follows dribble, open goal, deflected, redirect, one-on-one, aerial won | context of the shot | SB-EV |
| xG (`statsbomb_xg`), key pass id | quality of the chance, link to the assist | SB-EV |
| end location in 3D (x, y, z) in goal-mouth coordinates | where in the frame of the goal it was going | SB-EV Appendix 2 |
| goalkeeper action types: shot saved, goal conceded, collected, punch, smother, keeper sweeper, penalty saved; technique diving or standing; position set, moving, prone; body part | what the keeper did and how | SB-EV Goalkeeper |
| Opta xG 321 and post-shot xG 322 (os); goal-mouth y/z 102/103 (os) | same ideas | OPTA-KL |
| shot direction subtype: on target, off target; deflection subtype: woodwork, referee hit, handball | shot classification | MET-DEF |

### 4.5 Defending, pressure, referee

| Field | Meaning | Where |
| --- | --- | --- |
| pressure event with duration | a defender presses the ball receiver, carrier or passer, for a time span | SB-EV Pressure |
| `under_pressure` on events | the action overlapped a pressure event or is naturally contested | SB-EV, Appendix 7 |
| interception, block (save block, deflection, offensive), clearance (head, aerial won), ball recovery (offensive, failure) | defensive actions | SB-EV |
| foul committed (type, card, advantage, penalty, offside variant), foul won (defensive flag) | fouls | SB-EV |
| card values: yellow, second yellow, red | discipline | SB-EV, Opta qualifiers 31/32/33 (os), MET-DEF |
| set piece subtypes: free kick (direct, indirect), corner, throw-in, penalty, kick-off, retaken | dead-ball taxonomy | MET-DEF |
| `out` flag | the event ended with the ball out of bounds | SB-EV |
| `off_camera`, `duration`, `related_events` | data-quality flag, event length, links (shot to block to keeper action) | SB-EV |
| pressure and difficulty ratings: 8 measures with 1 to 5 scale (no pressure to very high pressure; very easy to very hard) | per-possession ratings of how constrained a player was | SC dynamic events |
| EPV columns on player-possession rows | value of the possession and the pass, start and end | SC dynamic events |

## 5. Derived metrics (computed from the fields above)

| Metric | Meaning | Needs | Where documented |
| --- | --- | --- | --- |
| player speed, acceleration | frame-to-frame displacement; raw values need smoothing | tracking | FOT, SC (smoothing warning) |
| pitch control | probability that a team controls the ball if it arrives at a location | tracking | FOT (model of Spearman) |
| expected possession value (EPV), expected threat (xT) | value of holding the ball in a place; xT-from-runs is the change in shot chance within 10 s | events, tracking | FOT, SC, OPTA-VIS |
| compactness | area covered by the defending outfield players; under 600 m2 = high, over 900 m2 = low | tracking | OPTA-VIS |
| relative line height, block depth | height of the defensive line (average distance of the deepest defenders to own goal) and depth of the block | tracking | LINE-ARX, DRIB; a simple event-based variant uses where defensive actions happen |
| local compactness near the ball | tightness of the five defenders closest to the ball; better predictor of defensive success than team-wide compactness | tracking | LINE-ARX |
| PPDA (passes per defensive action) | opponent passes divided by tackles, interceptions, challenges and fouls in the opponent's 60% of the pitch nearest their goal; low = intense press | events | PPDA-PL |
| intense pressure | at least one opponent within 2 m of the ball carrier | tracking | OPTA-VIS |
| overload | more attackers than defenders near the ball | tracking | OPTA-VIS |
| overlap / underlap | off-ball run outside or inside the ball carrier | tracking | OPTA-VIS |
| run in behind, sprint-speed run | off-ball run past the defensive line while the team has the ball | tracking | OPTA-VIS |
| line-breaking pass | a pass that beats one, two or three lines of the opposition shape | tracking + events | OPTA-VIS |
| progressive play phase | team moves the ball toward goal with the ball closer to goal than the midpoint of defenders | tracking | OPTA-VIS |
| pass length / angle / ball speed | geometry of a pass; progressive and direct passes follow from it | events | SB-EV (length, angle) |
| possession share, pass counts, shots, xG running totals | scoreboard-type stats | events | standard, SB-EV |
| counterattack flag | see section 2 | events | SB-EV |

## 6. What a commentator uses, per topic of docs/COMMENTATOR.md

"Have" = the current schema (`backend/matchvoice/schema.py`): event type, team, player, x/y, end_x/y, outcome, receiver, set_piece, length, difficulty,
ball_speed, speed, xg, shot_speed, body_part, keeper, under_pressure, card, score; players with number, pos and group; formation string. "New" = a field to add.

| Topic (EPL share) | What the commentator says | Fields used | Have | New (synthetic) |
| --- | --- | --- | --- | --- |
| Identity of the player on the ball (fast layer, about 22 short lines a minute) | "Rice. Saka. Back to Rice." | actor at every touch, ball receipt, recipient | only for events | a touch/receipt stream so someone has the ball every 2 to 3 s; carries with start and end; position per player |
| Game state (4.6%) | time, score, lead, "level at the break" | clock, score, period | yes | none |
| Context and statistics (4.2%) | "his third shot", "first corner in ten minutes", "fourth foul" | running counters per player and team, possession id, play pattern | derivable | possession spells; per-player season-style context fields (invented history) |
| Evaluation (4.1%) | "great ball", "poor touch", "dangerous" | pass difficulty, outcome, xG, miscontrol, error, key pass | partly | miscontrol, error, dispossessed, pass quality words from height, length, angle |
| Ball movement (2.7%) | "short pass", "switches the play", "lofted into the box", "over the top" | pass height, length, angle, body part, technique (through, switch, cross, cut-back, long ball), end location | length only | pass height, technique and flags, body part on every pass |
| Goal (2.4%) | scorer, assist, how it was struck, build-up | shot technique and body part, key pass id, assist chain, goal-mouth y/z, keeper position | scorer, xg, body_part | assist and second assist, shot technique, goal-mouth placement, keeper action (dive, set) |
| Chance and shot (1.9%) | "snapped at it", "right at the keeper", "one-on-one" | xG, first-time, one-on-one, open goal, goal-mouth y/z, keeper outcome, defender block | xg, outcome | one-on-one, first-time, shot placement, freeze frame (defenders and keeper at the shot) |
| Set pieces (1.8%) | "inswinger to the far post", "short corner", "wall of five" | set piece type, technique (in/outswinging), delivery target, runner positions | set_piece | corner delivery type and target zone, wall size, who is in the box |
| Referee, fouls, cards (1.2%) | "advantage", "booked for the tackle from behind" | foul committed/won, card, foul type, advantage | card, reason | foul type list, advantage, location of foul, repeated fouls by a player |
| Tactics (1.0%) | "high press", "dropping into a 4-4-2", "sit deep", "counter" | formation, tactical shift, line height, block depth, compactness, PPDA, counterpress flag, play pattern, phase | formation string | live team shape from player positions, line height, compactness, pressing phase, tactical shifts, counter flag |
| Duels and dribbles (0.9%) | "wins the header", "goes past him", "nutmeg" | duel type and outcome, dribble outcome and flags, dribbled past | tackle outcome | aerial duel, dribble, nutmeg, 50/50, shield |
| Off-ball runs and space (0.6%) | "runs in behind", "overlapping", "plenty of space", "offside trap" | all 22 positions over time, speed, run start and end, line height, space (pitch control) | no | synthetic movement for all players: runs in behind, overlaps, offside line, free player flags |

Rhythm points from COMMENTATOR.md and what feeds them:

| Rhythm fact | Needs |
| --- | --- |
| about 22 segments a minute, 56% of 5 words or fewer, 38% name a player | a touch-level stream (receipt, carry, pass) with the player name; ball movement words from pass height and length |
| context about one segment a minute | running counters (shots, fouls, corners, possession streaks, pass counts) |
| a goal lifts words per minute by about a fifth | event importance and energy flag, which already exist |
| tactics and off-ball are rare, but are the differentiator | positions of all players plus shape metrics, used on key moments |

## 7. How this maps to the hard constraints

This is a research note, not a design, but the catalogue is built so the constraints can hold.

- Deterministic per seed: every field in sections 1 to 4 can be derived from a seeded process (the position grid, an event stream, a simple physics
  step for movement). Nothing in the catalogue needs external data at run time.
- Real-time, no lookahead: sections 3 and 5 metrics are all computable from the past frame and earlier (speed, line height, compactness,
  PPDA window). Metrics that need the future (xT from a run's end, line-breaking pass targets) are only valid after the run ends and must be
  announced late or as a recap.
- Five-stage pipeline: tracking and events are Ingest; derived metrics (section 5) are Interpret; the topic table in section 6 is the Explain input;
  facts for the verifier need every spoken number to be backed by a field in this catalogue.
- Protocol and consumers: anything added to the stream must stay optional in overlay protocol v1, or the UI, MCP server and evaluation break.
  Dense tracking should be compact (arrays per frame, lower rate than 25 Hz, for example 5 Hz is enough for line height and runs).
- Fictional only: formats can follow StatsBomb, Metrica and Opta naming so the data looks realistic; no real names, ids or values are used.
- Model budget: richer data feeds the deterministic fast layer first (names, ball movement, counters); the guarded model call keeps its cost.

## 8. Open questions

- Opta's authoritative qualifier list was not read (client login). If exact ids matter for a demo claim ("Opta-style qualifiers"), only the
  ids marked (os) can be cited as verified.
- No public source documents how broadcasters compute run speeds or off-ball run labels. The definitions in OPTA-VIS are the closest.
- Player trait fields (foot, height, pace) appear in no open event spec, so they would be synthetic inventions, not a copy of a real schema.
- Hawk-Eye and Second Spectrum schemas are not public. This document does not claim to describe them.
