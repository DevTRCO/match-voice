# Insight set-up and pay-off for the story insert

Built on 2026-10-26 (option A, see the CLAUDE.md status entry "Insight set-up and pay-off"): `commentary/patterns.py`, prompt v7, the re-exported story insert and mock4. This note was written before that, as paper.
Goal: in part 1 of the story insert (68', 0-1, quiet spell) the co-commentator points out a pattern the viewer cannot see,
computed only from events before the set-up moment; in part 2 the 71' equaliser comes exactly that way and the co line
refers back to it. This note finds the pattern, proves it from the data, and writes the lines and the board cues.

## 0. Data and the no-lookahead rule

- `data/matches/comeback-135/` holds only `enriched.jsonl`. `meta.json`, `events.jsonl` and `truth.json` were regenerated
  into the scratchpad with `python -m matchvoice.sim --arc comeback --seed 135`, twice: byte-identical runs
  (events `fdc429dd`, meta `82a5f1f2`, truth `14af3d23`, sha1 prefixes). `python -m matchvoice.sim.micro --match comeback-135`
  on that output reproduces `enriched.jsonl` byte for byte (`53329422`), and the events match `story.json` (Petrov's save
  i1441 at 4229.5, Ibsen's interception i1479 at 4382.7). Nothing was written to `data/`.
- `meta.json` carries tactics and posture shifts: Wexmoor 4-4-2, mid block, line 33.2, shift to **chase** at 3819.1 s (64');
  Tamsworth 4-2-3-1, **low block**, line 29.7, no posture shift until 5522.3 s (89').
- Set-up moment: the co line in part 1 (about 4241 s). Every set-up fact below uses only events with `t < 4239.0`.
  The last event the pattern rests on is i1412 (4140.1 s). The fact engine run to 4239 has no fact that states it
  (its second-half facts are `momentum_phase` 56' and 65', `big_save` 65' and 68'), so the pattern is a new fact (section 6).
- Coordinates: absolute pitch metres as in the events (105 x 68). In period 2 Wexmoor defend the goal at x 105 and attack
  towards x 0. "Left" and "right" are Wexmoor's, in the attacking frame `fast.py side_of` uses (left = frame y < 22.7).

## 1. The example pattern is not true here

"Since the 60th minute Tamsworth sit deeper, and every time Wexmoor switch play to the left, Rasmussen has space."

| Claim | Data before 4239 | Verdict |
| --- | --- | --- |
| Tamsworth sit deeper since 60' | Tamsworth defensive actions (pressure, tackle, interception), mean distance from their own goal: 1st half 32.0 m (57% in own third), 46' to 60' 13.9 m (86%), 60' to 68' 28.5 m (73%). No Tamsworth posture shift before 89' | false: deeper since half-time, and since 60' they came out a little |
| Wexmoor switch play | 0 Wexmoor switches (`pass_type` switch, 40 m across) in the whole match before the goal; the goal's ball (i1481) is the first, the only other is i1583 at 77'. 0 of 184 Wexmoor passes in the second half moved 30 m or more across (widest 24.9 m) | false |
| Rasmussen has space on the left | Rasmussen received 19 completed passes before 4239, 4 on the left, none from a switch. Wexmoor passes from the left were under pressure as often as from the right in the second half (10 of 44, 23%, against 17 of 73, 23%); since the chase shift more often (7 of 21 against 2 of 12) | false |

## 2. Candidates, ranked by how clearly the goal proves them

| Rank | Pattern (set-up, true before 4239) | What the goal shows | Proof a viewer sees |
| --- | --- | --- | --- |
| **1** | **Ibsen keeps winning the ball, then Wexmoor play it short; nobody plays it across.** Ibsen 11 interceptions (team high, next Petrov 5). Second half: Wexmoor won the ball in their own half 11 times, the first pass was short every time (11 of 11, widest 24.9 m across); 0 passes of 30 m or more across in the half. In the 63rd minute Ibsen won it three times in 41 s, and three times Tamsworth had it back within 7.4 s | Ibsen wins it (i1479), and the first ball is the switch, 49.5 m across, at once (i1481); 11.0 s later it is 1-1 | **high**: the first two beats of the move are the pattern and its break, both on the board; "this time it goes across" is literally what the viewer watches |
| 2 | **Tamsworth keep looking for Lindqvist, and Ibsen reads it.** Lindqvist is the target of 106 of 429 Tamsworth passes (25%, most; next Zeller 14%); 25 of them were lost, Ibsen won 8 (next Tavares 3) | The move starts with Ibsen cutting out Arnaud's pass meant for Lindqvist (pass eid 23648, target A11) | medium-high: very visible, but it explains only the first touch, not why it became a goal |
| 3 | **Wexmoor are slow after winning it back.** Second half: of 11 ball wins in their own half, 2 reached the final third within 12 s (i978, i1135); their three shots from such wins came after 29, 44 and 140 s of possession, all saved | Own half to goal in 11.0 s, three passes | medium: a contrast, the viewer has to feel the tempo; no single picture on the board |

Candidate 1 contains candidate 2 (the set-up can name Lindqvist where the room allows). Candidate 3 is a fallback if the
set-up must avoid naming a player.

## 3. Best pattern: the facts and their evidence

Event ids are `i` in `events.jsonl`; `eid` are rows in `enriched.jsonl`.

### 3.1 Set-up facts (all `t < 4239`)

| Id | Fact | Evidence |
| --- | --- | --- |
| S-F1 | Ibsen has 11 interceptions, the most at Wexmoor (Petrov 5, Moreau, Dacosta, Fontaine, Tavares, Becker-Lyle 4) | i127, i199, i319, i534, i675, i686, i977, i1168, i1312, i1324, i1335 |
| S-F2 | 8 of them were passes meant for Lindqvist (enriched `target` A11) | i199 (pass eid 3168), i319 (5088), i534 (8528), i686 (10960), i977 (15616), i1168 (18672), i1324 (21168, a cut-back), i1335 (21344, a cross) |
| S-F3 | Second half: 11 Wexmoor ball wins in their own half, first pass short (`pass_type` short or back) in all 11, at most 24.9 m across | wins i956, i977, i1098, i1134, i1144, i1168, i1312, i1324, i1335, i1349, i1410; first passes i958 (eid 15328), i979 (15664), i1100 (17600, back), i1137 (18192), i1146 (18336), i1170 (18720), i1314 (21024), i1327 (21232), i1338 (21408), i1351 (21616), i1412 (22592) |
| S-F4 | Second half: 0 of 184 Wexmoor passes moved 30 m or more across; 0 switches in the match | all H passes 2892 to 4239; the last 30 m ball across was i898 (45+1') |
| S-F5 | 63rd minute: Ibsen wins it three times, each time the ball goes short and Tamsworth have it back: i1312 (3914.0) to i1314 short to Abara, lost i1316 (3921.4, Zeller, 7.4 s); i1324 (3939.5) to i1327 0.6 m towards Rourke, lost i1328 (3941.7, Pellegrin, 2.2 s); i1335 (3954.6) to i1338 short to Sundberg, lost i1339 (3960.9, Lindqvist's tackle, 6.3 s) | i1312, i1314, i1316, i1324, i1327, i1328, i1335, i1338, i1339; eids 20992, 21024, 21184, 21232, 21360, 21408 |
| S-F6 (context) | Wexmoor have 63% of the passes in the second half (184 to 110), 136 of their 184 passes aimed into the final third; Tamsworth in a low block (meta) and Wexmoor chasing since 64' (posture shift 3819.1) | passes 2892 to 4239; `meta.json` tactics and postures |

Between the set-up and the goal nothing contradicts it: one Wexmoor ball win in their own half (i1456, Moreau, 69', short
first pass, kept 28 s), no ball 30 m across except the corner i1442 (a set piece), and Ibsen's next interception is the goal's.

### 3.2 Pay-off facts (the goal move, all in `story.json` part 2)

| Id | Fact | Evidence |
| --- | --- | --- |
| P-F1 | Ibsen intercepts Arnaud's pass meant for Lindqvist, Wexmoor's right, 25 m from his own goal | i1478 (pass eid 23648, target A11), i1479 (eid 23664), 4382.7 |
| P-F2 | His first ball is the switch: lofted, left foot, from (79.7, 12.5) to Rasmussen at (59.1, 62.0), 49.5 m across, right to left, played at the moment of the interception (same `t`) | i1481, eid 23696 (`switch`, `lofted`); the first Wexmoor switch of the match and the first long first ball after a ball win in the second half |
| P-F3 | Rasmussen on the chest, then a long ball to Tavares, not under pressure | eid 23697 (`chest`), i1482 / eid 23712 (`long`, `pressure.under: false`) |
| P-F4 | Tavares first time to Fontaine, Fontaine first time, 1-1, 11.0 s after the interception | eid 23714 (`first_time`), i1483 / eid 23728, 4393.7 |

## 4. Lines per channel

Set-up: the co-commentator in part 1. Pay-off: the co line after the goal call (slot G2 in `docs/INSERT-SCRIPT.md`
section 2), replacing today's HOW line, because the pay-off is a HOW line itself (the switch).
Lengths are estimated as in INSERT-SCRIPT: en 2.1 and fr 2.35 words a second, German 0.345 s a syllable (co pace).
Rules kept: no percentage or count in the pay-off, no player pronoun ("he", "er", "il"; ball pronouns "ihn" are fine),
"switch", "Verlagerung", "transversale" only because P-F2 has `pass_type` switch. Not one line says "again" about the
switch: there was no switch before. "Again" belongs to Ibsen winning the ball.

### 4.1 English, Daniel Price

| Channel | Set-up (part 1) | Est. | Pay-off (after the call) | Est. / room |
| --- | --- | --- | --- | --- |
| en/expert | Ibsen keeps winning it, then it goes short. Not one switch since the break. | 6.7 s | There it is. Ibsen wins it, and this time it goes across. | 5.7 / 6.3 s |
| en/beginner | Ibsen keeps winning it back, but this half it always goes short. Never across. | 6.7 s | There you go! Ibsen wins it, and this time it goes across. They're back in this! | 7.1 / 7.7 s |

Why: the set-up is the co's observation over a dead ball (EN 5.2, the HOW layer, here before the goal); "Not one switch since
the break" is S-F4, "keeps winning it" S-F1, "goes short" S-F3. The pay-off opens with the second-voice marker real colour
voices use ("There it is", EN 5.1 "as you said" family), then the picture. en/expert drops "Game on": the call already says
"Wexmoor are level" and the room is 6.3 s. Optional set-up if the slot grows to 8 s (S-F5, one count of a pictured thing):
"Just after the hour Ibsen won it three times, and three times it came straight back." (16 words, 7.6 s).

### 4.2 German, Kim Berger

| Channel | Set-up (part 1) | Est. | Pay-off (after the call) | Est. / room |
| --- | --- | --- | --- | --- |
| de/expert | Ibsen holt die Bälle, dann immer kurz. Wo ist die Verlagerung? | 18 syl, 6.2 s | Genau das meinte ich. Ibsen holt ihn, diesmal sofort rüber. | 16 syl, 5.5 / 5.7 s (tight) |
| de/beginner | Ibsen holt die Bälle, aber seit der Pause immer kurz. Nie rüber. | 18 syl, 6.2 s | Da ist es! Ibsen holt ihn, und diesmal geht's rüber. Alles wieder offen. | 19 syl, 6.6 / 6.8 s (tight) |

Why: the Experte speaks in fragments and asks the rhetorical question (DE 3.4, "Und dann?"); "Genau das meinte ich" is the
Experte's own callback opener (DE 3.4, "Und das ist genau das, was ich vorhin meinte", shortened to fit). "Verlagerung" is
the expert word, "rüber" the beginner's picture (DE 3.5, as in the build-up "Rüber, Rasmussen"). "sofort" is P-F2 (pass at
the interception's time). "geht's" instead of "geht er" keeps the pronoun test green. "Alles wieder offen" is DE 3.3.

### 4.3 French, Sacha Morel

| Channel | Set-up (part 1) | Est. | Pay-off (after the call) | Est. / room |
| --- | --- | --- | --- | --- |
| fr/expert | Ibsen récupère ballon sur ballon, mais derrière, toujours court. Pas une transversale depuis la pause. | 15 words, 6.4 s | Voilà ! Ibsen récupère, et cette fois, transversale tout de suite. | 10 words, 4.3 / 4.7 s |
| fr/beginner | Ibsen récupère le ballon, mais depuis la pause, toujours court. Jamais de l'autre côté. | 14 words, 6.0 s | Et voilà ! Ibsen récupère, et cette fois, de l'autre côté ! Tout est relancé ! | 14 words, 6.0 / 6.5 s |

Why: "ballon sur ballon" and "et derrière" are consultant French (FR 4.4, "et derrière on est en infériorité"); "récupère
tout" would be false (S-F1 is 11, not all). "transversale" is the expert word (FR 4.5), "de l'autre côté" the beginner's
picture, as in the build-up "Rasmussen, de l'autre côté". If the fr/expert room grows by 1.7 s, open with the consultant's
callback: "C'est ce que je disais : Ibsen récupère, et cette fois, transversale tout de suite." (14 words, 6.0 s).

All lines are paper: no native German or French speaker has read them, and the estimates come from word and syllable counts.

## 5. What the board highlights

### 5.1 At the set-up (part 1, while the co speaks, about 4241 to 4248)

- **Player:** Ibsen (H3, number 5) ringed in Wexmoor purple; Lindqvist (A11, number 10) with a faint amber ring (only when
  the line names him, otherwise leave him out).
- **Zone:** Wexmoor's own half shaded (x 52.5 to 105), label "Ball won: 11 times this half. Played across: 0" (numbers are
  fine on a graphic, never in speech).
- **Dots:** Ibsen's five second-half interceptions at (83.6, 36.9), (95.3, 20.1), (103.0, 55.4), (103.0, 18.3), (103.0, 23.4).
- **Arrows:** the 11 short first passes after the second-half ball wins, thin and grey: (103.0, 39.6) to (81.8, 36.4),
  (83.6, 36.9) to (70.8, 52.8), (96.9, 31.9) to (100.4, 7.0), (44.9, 23.1) to (41.7, 26.5), (57.1, 22.2) to (46.7, 32.3),
  (95.3, 20.1) to (98.3, 16.7), (103.0, 55.4) to (97.6, 52.6), (103.0, 18.3) to (103.0, 17.7), (97.4, 18.8) to (91.5, 35.0),
  (103.0, 31.2) to (100.2, 14.9), (78.9, 15.3) to (79.3, 21.5). For the S-F5 variant, only the three 63' arrows, each ending
  in a small amber cross where Tamsworth won it back: (76.0, 47.5), (103.0, 17.7), (91.5, 35.0).
- **No ghost arrow** across the pitch: it would draw a ball nobody has played, and it would point at the goal before it happens.
- Note: several interceptions sit 2 m from Wexmoor's goal line (19 of 42 before the cut, the sim pins crosses and cut-backs
  there). The dots are true but crowd the byline; at board scale draw them at 6 px and let the zone carry the idea.

### 5.2 At the goal (part 2)

| Time | Highlight |
| --- | --- |
| 4382.7 | Ibsen ringed at (79.7, 12.5); the five set-up dots fade in for 1 s and out again ("again"). Lindqvist's faint ring as the pass meant for him is cut out |
| 4382.7 to 4385.96 | **The switch:** thick purple arrow (79.7, 12.5) to (59.1, 62.0), the far band (y 45.3 to 68, Wexmoor's left) lit while the ball flies; label "across", the word the set-up used |
| 4385.96 | Rasmussen (H4) ringed at (59.1, 62.0) |
| 4389.6 to 4392.1 | Arrow (59.1, 62.0) to (39.8, 25.7), Tavares (H7) ringed |
| 4392.3 to 4393.45 | Arrow (39.8, 25.7) to (25.0, 36.5), Fontaine (H10) ringed |
| 4393.7 | Shot line (25.0, 36.5) to the goal (0, 36.5); afterwards the whole move stays drawn under the pay-off line, the switch brightest, the set-up's grey short arrows shown once more beside it for the length of the co line |

The board has no highlight layer today (`ui/src` draws players and the ball); this is the spec for one.

## 6. What it needs (not changed, for the plan owner)

1. **Room for the set-up in part 1.** Part 1 is 4238 to 4246 and holds the lead's story note (4239.5, up to 6.5 s). The ball
   is dead from Petrov's save (4229.5) to the corner (4249.6), so there is room before the corner.
   - Option A, part 1 from 4234 to 4249: the lead's story note at about 4235, a breath, the co's set-up at about 4241.7 (up to
     7 s), cut before the corner. Pro: both lines, the real order (caller's record, then the co's observation). Contra: the
     insert grows by about 7 s to about 44 s, and must be re-exported.
   - Option B, part 1 unchanged, the set-up replaces the story note. Pro: length unchanged. Contra: the comeback record goes,
     and the insert opens with the co instead of the caller.
   - Option C, keep the story note and fit the set-up behind it (4246 to 4249.4): 3.4 s, too short for any line above. Not usable.
   - My suggestion: **A**. The record and the pattern are two different promises, and the pattern needs the 63rd minute it
     points to, which only a longer part 1 can hold.
2. **A new fact with evidence ids**, computed live without lookahead: per side and half, own-half ball wins and the type of
   the first pass after each, passes 30 m or more across, interceptions per player and the intended target (enriched
   `target`). The set-up fires on a dead ball once the habit is clear (for example 8 or more ball wins, 0 across); the pay-off
   fires when a goal move starts with a ball win whose first pass breaks the habit, and only then (no pay-off without the set-up).
3. **Verifier claims:** "always short", "never across", "keeps winning it", "this time" need entries in the claims lexicon
   (`CLAIMS`), backed by that fact; today they would pass unchecked or be blocked as traits.
4. **Prompt:** the analyst's goal co line would get the set-up line in `recent` and the habit fact, with the rule "refer back
   in the opening words, then the picture, no number".
5. **Voices:** six new co lines to bake if the insert keeps baked audio (`story-audio`), none today.
