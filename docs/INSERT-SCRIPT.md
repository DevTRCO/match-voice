# Insert script: the 30 s story insert, as a real booth would call it

Paper only. No code, prompt, template, test or data file was changed for this note, no model or voice call was made.
It is the line-by-line script of the two-part story insert (`ui/public/insert/story.json`, match `comeback-135`) for all six
channels, written the way a real TV booth would speak it, with today's line next to each new one.
Research it rests on: `docs/research/CASTER-STYLE-EN.md` (EN), `docs/research/CASTER-STYLE-DE-FR.md` (DE-FR).
Nothing here has been read by a native German or French speaker yet; that read is still needed before anything is voiced.

## 1. What the insert shows (the facts every line may use)

All facts come from `story.json` (frames, events, `say` slots) and, where marked, from `data/matches/comeback-135/enriched.jsonl`
(the same events with pass type, touch, foot, first-time and pressure). Nothing else is used: no opener scorer, no season goals for
Fontaine, no tactics (the match has no `meta.json` on disk), no substitution (Fontaine started).

| Fact | Value | Source |
| --- | --- | --- |
| Match, ground | Wexmoor Athletic (home, 4-4-2) v Tamsworth Wanderers (away, 4-2-3-1), Wexmoor Athletic Ground | `hello.match` |
| State in part 1 | 68', Wexmoor trail 0-1 at home | frames at 4222 to 4229 |
| Just before part 1 | Petrov's shot is saved (event 1441, 4229.5 s), 6.5 s before the insert opens | frame 4229.5 |
| Story | Wexmoor have come from behind to take points three times this season | `story_note` at 4239.5 |
| The cut | part 1 ends at 4246.0, part 2 starts at 4381.0 (70', still 0-1) | `demo.parts` |
| 1 | Ibsen (CB, 5) intercepts a Tamsworth pass meant for Lindqvist, 25 m from his own goal | event 1479; enriched 23664 (pass 23648 to A11) |
| 2 | Ibsen switches it across, lofted, left foot, to Rasmussen (CB, 4) on the other side | event 1481; enriched 23696 `switch`, `lofted` |
| 3 | Rasmussen takes it on the chest (arrives 4385.96) | enriched 23697 `touch: chest` |
| 4 | Rasmussen, under no pressure, plays a long lofted ball to Tavares (CM, 8) in the Tamsworth half | event 1482; enriched 23712 `long`, `pressure.under: false` |
| 5 | Tavares lays it first time, left foot, short, to Fontaine (ST, 9) | enriched 23714 `first_time: true` |
| 6 | Fontaine shoots first time, right foot, driven, high, from about 25 m, no one closing him down: 1-1, 71' | event 1483; enriched 23728 `first_time`, `driven`, `pressure.under: false`, x 25.0 m |
| After | Wexmoor's first goal of the match, Fontaine's first; about 19 minutes plus added time left | score, clock |
| Move length | interception to goal in 11.0 s (4382.7 to 4393.7) | event times |
| Win probability | Tamsworth 67 to 22 after the goal | `facts` insight log: **stays a graphic, never spoken** |

Both centre-backs start the move, and the last two touches are first time. Those are the pictures a real co-commentator
reaches for. The win probability is the one fact on this list nobody in a booth reads out (EN 1.1, DE-FR 1.5).

## 2. Timing slots

Times are stream seconds (`t` in `story.json`); `w` is seconds into the insert. **Room** is the time from a line's start to
the next line's start (or to the cut); a line longer than its room is cut off or skipped by the director. Today's line length
is its `say` `s` to `e`. Estimated length of a new line uses the rates of today's voiced lines: en 2.1, de 1.7, fr 2.35 words a second,
shouts a little slower.

| Slot | Start `t` (`w`) | Room en / de / fr | Today's length en/b, en/x, de/b, de/x, fr/b, fr/x |
| --- | --- | --- | --- |
| S1 story (part 1) | 4239.5 (3.6) | 6.5 s to the cut, 9.3 s hard max (to Ibsen, the voice then runs over the cut) | 7.98, 6.46, 8.38, 6.05, 7.45, 6.15 |
| P1 interception | 4382.7 (12.9) | 1.74 / 2.05 / 1.92 | 1.74, 1.74, 2.05, 2.05, 1.92, 1.92 |
| P2 switch | 4384.44 / 4384.75 / 4384.62 | 2.02 / 1.71 / 1.84 | 1.34 en, 1.47 de, 1.45 fr |
| P3 chest | 4386.46 (16.7) | 3.14 (nothing is said from 4387.8 to 4389.6 today) | 1.34 en, 1.39 de, 2.00 fr |
| P4 long ball | 4389.6 (19.8) | 2.70 | 2.06 en, 2.63 de, 2.22 fr |
| P5 lay-off | 4392.3 (22.6) | 1.40 (the goal cuts in) | 1.26 en, 1.38 de and fr |
| G call | 4393.7 (23.9) | until the co line starts | 5.10, 3.42, 5.22, 3.13, 4.99, 3.07 |
| G co line | voice from call end | to today's voice end: 4404.54, 4403.90, 4405.13, 4403.13, 4404.15, 4402.07 | 5.74, 6.78, 6.21, 6.30, 5.46, 5.30 |
| G score (new) | after the co line | **no slot today** (`until` is 4401.0, the last voice ends at 4405.13) | none |

One deliberate change of speaker: the story line S1 is the **lead's** (today it has `voice: analyst`). In a quiet spell the caller
reads the club's record from his notes (DE-FR model line 14, "C, before the build-up"; EN 6 and 7.4).

## 3. Pattern ids used in the tables

| Id | Pattern | Research |
| --- | --- | --- |
| B1 | bare name, or the name as the start of a phrase the next slot finishes ("Rasmussen... mit der Brust") | EN 3.2, 7.1; DE 3.2 chain; FR 4.2 chain |
| B2 | name plus a short active verb ("Ibsen cuts it out", "Ibsen geht dazwischen", "Ibsen intercepte") | EN 7.1; DE 3.2; FR 4.2 |
| B3 | the pass as its receiver: "to / for X", "auf X", "pour X" | EN 3.3; DE 3.2; FR 4.2, 4.6 |
| B4 | flight or technique word only on the last balls of the move (lifted, lang, transversale, first time, direkt, remise) | EN 3.3, 7.1 |
| B5 | name-less fragment that says what the ball does now ("Chested down", "Mit der Brust runter") | EN 3.2, 7.1 |
| C1 | call: the shout, then the scorer at once, 4 to 9 words | EN 4, 7.2; DE 3.1; FR 4.1 |
| C2 | meaning in the call instead of the score ("Wexmoor are level", "Der Ausgleich", "Wexmoor égalise") | EN 7.2; DE 3.1; FR 4.1 |
| A1 | co: HOW, the concrete touch or pass in pictures | EN 5.2, 7.3; DE 3.4; FR 4.4 |
| A2 | co: who failed, concrete ("nobody closed it down", "keiner geht drauf", "personne ne sort") | EN 7.3 (#10); DE 3.4; FR 4.4 |
| A3 | co: what it means, in idiom, never in a number ("Game on", "Wexmoor ist zurück", "Le match est relancé") | EN 5.2 (#4, #5); DE 3.3; FR 4.1, 4.3 |
| S1 | the score once, spoken form, after the call ("one-all", "eins zu eins", "un partout") | EN 5.1; DE 3.1; FR 4.1 |
| S2 | back to play: time left ("just under twenty minutes left", "noch knapp zwanzig Minuten") | EN 7.3; DE-FR 2 |
| Q1 | quiet spell: a team record that is true and short, plus the open question | EN 6, 7.4; DE-FR 7 line 14 |
| R1 | beginner: plain words, club named, the stakes said simply, no term without its picture | DE 3.5; FR 4.5 |
| R2 | expert: names the technique (switch, first time, Verlagerung, direkt, transversale, en une touche) | DE 3.5; FR 4.5 |
| X1 | no percentage, probability, xG or stat in speech; numbers only score, minute, tally, time left | EN 1.1; DE-FR 5 |
| X2 | no ticker passive, no caption noun, no calque ("Abgefangen von", "Brustannahme.", "Vers", "netzt ein", "fait mouche") | DE 3.2, 3.6; FR 4.2, 4.6 |

Fit column: **fits** (inside the room), **tight** (within 0.5 s of the room), **NEEDS SLOT** (longer than the room or no slot today).

## 4. English

### 4.1 en/expert: Charlie Hale (lead), Daniel Price (co)

| # | Time | Event | Who | Today | New line | Est. / room | Fit | Why |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 68', 4239.5 | quiet spell, 0-1 | Hale (was co) | Wexmoor have already come from behind to take points three times this season. | Wexmoor have taken points from losing positions three times this season. | 5.2 / 6.5 | fits | Q1 in the expert register: "points from losing positions" is the stat-graphic phrase a lead reads off his notes; one count, no stakes sentence (the open question was writerly) |
| P1 | 70', 4382.7 | Ibsen intercepts | Hale | Ibsen cuts it out. | Ibsen cuts it out. (keep) | 1.7 / 1.74 | tight | B2, already a real form (the EN catalogue example) |
| P2 | 4384.44 | Ibsen's switch, lofted | Hale | To Rasmussen. | Across to Rasmussen. | 1.4 / 2.02 | fits | B3; "across" is how a British caller says a cross-field ball live. "Switched to" is a past participle off a stats feed, and centre-back to centre-back is not what a caller calls a switch |
| P3 | 4386.46 | chest | Hale | Chested down. | Chests it down. | 1.4 / 3.14 | fits | B5 in the present tense, the way it is spoken over the picture; "Chested down." reads like a ticker |
| P4 | 4389.6 | long ball | Hale | Long ball for Tavares. | Long ball for Tavares. (keep) | 2.1 / 2.70 | fits | B3, the corpus form ("ball for Y"); "Long ball, lifted towards" stacked two flight words and "towards" says the ball may not arrive. No "!" yet: Tavares is only just over halfway |
| P5 | 4392.3 | Tavares first time | Hale | To Fontaine. | First time, Fontaine! | 1.3 / 1.40 | tight | B4 plus R2, the first "!" of the move; read with a beat on the comma, the caller is cut off by the shot as on TV |
| G1 | 71', 4393.7 | Fontaine, 1-1 | Hale, peak | GOAL! Fontaine buries it, and it's 1-1! | Oh, what a strike! Kenji Fontaine! Wexmoor are level! | 4.3 / open | fits | C1 plus C2; "what a strike" is the British form ("what a hit" is rarer), earned by a first-time driven shot from outside the box; the full name on the goal is what a lead shouts; the score moves to G3 |
| G2 | about 4398.5 | over the goal | Price | Wexmoor's chance of a win jumps to 36 percent, and Tamsworth have to start again. | Doesn't let it settle, and nobody closes the shot down. Game on. | 5.2 / 6.3 | fits | A1 (first-time shot in a picture), A2 (`pressure.under: false` on the shot), A3 ("Game on", native quote #4); X1. Shorter than before so a second of crowd sits between call and co line. Does not repeat P5's "first time" |
| G3 | about 4404 | back to play | Hale | (none) | One-all, and twenty minutes or so to go. | 3.8 / none | NEEDS SLOT | S1 plus S2; "or so" covers 19 minutes plus added time without a wrong number |

Optional instead of G2 (one true timing fact, the kind EN 5.2 quotes once, "59 seconds"): "Eleven seconds from Ibsen winning it to the ball in the net. Game on." (13 words, about 6.2 s, tight). It needs the move length as a fact (section 7). The old wording "Ibsen to the back of the net" said Ibsen took the ball there.

### 4.2 en/beginner: Owen Carter (lead), Daniel Price (co)

| # | Time | Event | Who | Today | New line | Est. / room | Fit | Why |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 68', 4239.5 | quiet spell, 0-1 | Carter (was co) | Do not write Wexmoor off yet, they have come from behind to take points three times this season. | Don't write Wexmoor off. They've come from behind three times this season. | 5.7 / 6.5 | fits | Q1 plus R1: the spoken form of today's idea ("Don't", "They've"), two short sentences, ends before the cut; the scoreboard already says they trail |
| P1 | 70', 4382.7 | Ibsen intercepts | Carter | Ibsen cuts it out. | Ibsen wins it back. | 1.7 / 1.74 | tight | B2 plus R1: "wins it back" says what happened without the jargon; no "!" on a ball won 25 m from his own goal |
| P2 | 4384.44 | switch | Carter | To Rasmussen. | Over to Rasmussen. | 1.5 / 2.02 | fits | B3 plus R1: "over" pictures the ball crossing the pitch |
| P3 | 4386.46 | chest | Carter | Chested down. | Takes it on the chest. | 2.4 / 3.14 | fits | B5 plus R1, a plain verb phrase |
| P4 | 4389.6 | long ball | Carter | Long ball for Tavares. | Long ball up to Tavares. | 2.3 / 2.70 | fits | B3, "up" says the direction; the "!" waits for the last ball |
| P5 | 4392.3 | Tavares to Fontaine | Carter | To Fontaine. | Now Fontaine! | 1.0 / 1.40 | fits | B1, the name only, last second before the shot, first "!" |
| G1 | 71', 4393.7 | Fontaine, 1-1 | Carter, peak | GOAL for Wexmoor Athletic! Fontaine finds the net, it's 1-1! | Goal! Kenji Fontaine! Wexmoor are level! | 3.0 / open | fits | C1 plus C2, club named for the beginner (R1), full name on the goal; "finds the net" was a cliché, the score moves to G3 |
| G2 | about 4398 | over the goal | Price | Wexmoor are level now, and that changes the whole feel of this game. | Won back in their own half, and seconds later it's in. Wexmoor are back in this! | 7.1 / 7.7 | fits | A1 in plain words (interception in their own half, goal 11 s later), A3 idiom; "From their own half to the net in no time" sounded written, "changes the whole feel" was abstract |
| G3 | about 4405 | back to play | Carter | (none) | It's one-all, and there are about twenty minutes left. | 4.3 / none | NEEDS SLOT | S1 plus S2, plain |

## 5. German

German writes 1:1; every number below is spoken in words (DE 3.1). Daniel Price speaks German in this booth.

### 5.1 de/expert: Jonas Weber (lead), Daniel Price (co)

Lengths in both German tables are re-estimated per syllable from today's German audio (play-by-play about 0.31 s, co about 0.345 s,
beginner lead about 0.4 s a syllable), not per word: German words are long, and the word rate made some slots look as if they fit.

| # | Time | Event | Who | Today | New line | Est. / room | Fit | Why |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 68', 4239.5 | quiet spell, 0-1 | Weber (was co) | Wexmoor hat in dieser Saison schon drei Mal nach Rückstand gepunktet. | Dreimal hat Wexmoor diese Saison nach Rückstand noch gepunktet. Und heute? | 6.4 / 6.5 | tight | Q1; "nach Rückstand noch gepunktet" is the stock Sky phrase (the "noch" carries the comeback); "diese Saison" is spoken, "in dieser Saison" written; "dreimal" in one word |
| P1 | 70', 4382.7 | Ibsen intercepts | Weber | Abgefangen von Ibsen. | Ibsen geht dazwischen. | 1.9 / 2.05 | fits | B2, X2: the ticker passive goes; no "!" yet, the energy rises only on the last two balls |
| P2 | 4384.75 | switch | Weber | Auf Rasmussen. | Rasmussen... | 1.0 / 1.71 | fits | B1, the DE 3.2 chain. "Verlagerung auf Rasmussen" is 8 syllables, about 2.5 s, and does not fit 1.71 s; the expert's technique words move to the co line |
| P3 | 4386.46 | chest | Weber | Brustannahme. | ...mit der Brust. | 1.2 / 3.14 | fits | B5, finishes P2's name ("Rasmussen... mit der Brust"), DE-FR model line 1; the silence after it is a real breath before the long ball |
| P4 | 4389.6 | long ball | Weber | Lang geschlagen auf Tavares. | Und lang auf Tavares! | 1.9 / 2.70 | fits | B3, the DE 3.2 form; the "Und" is how a German caller lifts the pace; first "!" |
| P5 | 4392.3 | Tavares first time | Weber | Auf Fontaine. | Direkt... Fontaine! | 1.3 / 1.40 | fits | B4 plus R2: "direkt" is Tavares's first-time ball, the pause keeps it from reading as "Fontaine direkt"; "legt ab" would be wrong, the pass goes 18 m forward |
| G1 | 71', 4393.7 | Fontaine, 1:1 | Weber, peak | TOR! Fontaine macht ihn rein, 1-1! | Tooor! Fontaine! Was für ein Hammer! | 3.7 / open | fits | C1; "Hammer" is earned (first time, driven, about 25 m, high); the meaning moves to G3, so "Ausgleich" and "eins zu eins" are not said back to back |
| G2 | about 4397.4 | over the goal | Price | Wexmoor glaubt wieder an den Sieg, die Siegchance steigt auf 36 Prozent. | Tavares direkt, Fontaine direkt. Da muss doch einer drauf. | 5.8 / 5.7 | tight | A1 plus R2 (both touches first time), A2 (no pressure on the shot) in the Experte's complaint form (DE 3.4); no exclamation, no mood sentence; X1 |
| G3 | about 4403.6 | back to play | Weber | (none) | Eins zu eins. Und jetzt ist hier wieder alles drin. | 4.4 / none | NEEDS SLOT | S1 plus A3 in the caller's mouth ("hier ist wieder alles drin", DE 3.1); the expert channel assumes the time left |

### 5.2 de/beginner: Felix Brandt (lead), Daniel Price (co)

| # | Time | Event | Who | Today | New line | Est. / room | Fit | Why |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 68', 4239.5 | quiet spell, 0-1 | Brandt (was co) | Wexmoor sollte man nicht abschreiben, die Mannschaft hat schon drei Mal nach Rückstand gepunktet. | Wexmoor hat diese Saison schon dreimal einen Rückstand aufgeholt. | 6.4 / 6.5 | tight | Q1 plus R1: "einen Rückstand aufgeholt" is the plain form of "gepunktet"; the 0-1 is on the board, and the earlier "Wexmoor liegt hinten. Aber..." was about 7.6 s at the beginner pace, 1.1 s over the cut; no "sie" for the team |
| P1 | 70', 4382.7 | Ibsen intercepts | Brandt | Abgefangen von Ibsen. | Ibsen geht dazwischen. | 1.9 / 2.05 | fits | B2, X2; same as the expert, as in DE-FR 7 ("C, both") |
| P2 | 4384.75 | switch | Brandt | Auf Rasmussen. | Rüber, Rasmussen. | 1.7 / 1.71 | tight | B3 plus R1: "rüber" pictures the ball crossing the pitch; "Rüber auf Rasmussen" is over the room, and "rüber auf" wants a side, not a player |
| P3 | 4386.46 | chest | Brandt | Brustannahme. | ...mit der Brust. | 1.2 / 3.14 | fits | B5, X2 |
| P4 | 4389.6 | long ball | Brandt | Lang geschlagen auf Tavares. | Lang nach vorne, Tavares! | 2.2 / 2.70 | fits | B3 plus R1: "nach vorne" says where |
| P5 | 4392.3 | Tavares to Fontaine | Brandt | Auf Fontaine. | Fontaine! | 0.8 / 1.40 | fits | B1 |
| G1 | 71', 4393.7 | Fontaine, 1:1 | Brandt, peak | TOR für Wexmoor Athletic! Fontaine netzt ein, es steht 1-1! | Tooor! Fontaine! Der Ausgleich für Wexmoor! | 4.6 / open | fits | C1 (the scorer at once, then the meaning) plus C2, club named (R1); X2: "netzt ein" is print German |
| G2 | about 4398.3 | over the goal | Price | Der Ausgleich verändert alles, Wexmoor glaubt jetzt wieder an den Sieg. | Ball hinten gewonnen, schnell nach vorne, drin. Jetzt ist alles wieder offen. | 6.5 / 6.8 | fits | A1 in plain words (the move as three pictures), A3 "alles wieder offen" (DE 3.3); DE 3.4: "glaubt wieder an den Sieg" is not analysis |
| G3 | about 4405 | back to play | Brandt | (none) | Eins zu eins, noch knapp zwanzig Minuten zu spielen. | 5.2 / none | NEEDS SLOT | S1 plus S2, plain; "knapp zwanzig" is true at 71' (19 plus added time) |

## 6. French

French writes 1-1, says "un partout" (FR 4.1). Daniel Price speaks French in this booth (his voice is not verified for French, see docs/VOICE-CAST.md).

### 6.1 fr/expert: Hugo Martin (lead), Daniel Price (co)

| # | Time | Event | Who | Today | New line | Est. / room | Fit | Why |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 68', 4239.5 | quiet spell, 0-1 | Martin (was co) | Wexmoor a déjà pris des points après avoir été mené trois fois cette saison. | Wexmoor sait revenir : déjà trois fois cette saison après avoir été mené. | 5.1 / 6.5 | fits | Q1; "sait revenir" is how a caller frames a club's habit; "Et aujourd'hui ?" dropped, it is the German "Und heute?" translated, a French caller does not tag a record with it |
| P1 | 70', 4382.7 | Ibsen intercepts | Martin | Intercepté par Ibsen. | Ibsen intercepte ! | 1.2 / 1.92 | fits | B2, X2: the passive goes (FR 4.2) |
| P2 | 4384.62 | switch | Martin | Vers Rasmussen. | Transversale pour Rasmussen. | 1.7 / 1.84 | fits | B3 plus R2: "transversale" is the switch, "pour" not "vers" (FR 4.6) |
| P3 | 4386.46 | chest | Martin | Amorti de la poitrine. | Contrôle poitrine... | 1.2 / 3.14 | fits | B5, finishes P2's name in one breath (FR 4.2 chain) |
| P4 | 4389.6 | long ball | Martin | Long ballon vers Tavares. | Ballon long pour Tavares ! | 1.7 / 2.70 | fits | B3, "pour" not "vers" (FR 4.6), first "!"; "le jeu long" is a style ("il choisit le jeu long"), not a call on one ball |
| P5 | 4392.3 | Tavares first time | Martin | Pour Fontaine. | Une touche, Fontaine ! | 1.3 / 1.40 | tight | B4 plus R2: the first-time pass; not "remise", the ball goes 15 m forward on the ground (enriched 23714, x 39.8 to 25.0), a remise is a lay-off back or square |
| G1 | 71', 4393.7 | Fontaine, 1-1 | Martin, peak | BUT ! Fontaine ne tremble pas, 1-1 ! | BUUUT ! Fontaine ! Quelle frappe ! | 3.0 / open | fits | C1 (one long vowel, FR 4.1); "Quelle frappe !" is earned (first time, driven, 25 m, unpressured) and is what a Canal+ caller shouts on a strike from range; the equaliser meaning moves to G3, the score too |
| G2 | about 4397.4 | over the goal | Price | Wexmoor reprend confiance, ses chances de gagner grimpent à 36 %. | Tavares en une touche, Fontaine sans contrôle, et personne ne sort ! | 4.7 / 4.7 | tight | A1 plus R2 (both touches first time, said two ways that are not synonyms: "en une touche" for the pass, "sans contrôle" for the shot), A2 "personne ne sort" (`pressure.under: false` on the shot, FR 4.4); the old "en une touche ... en première intention" said the same thing twice; "le match est relancé" is the caller's line, not the consultant's; X1 |
| G3 | about 4403.2 | back to play | Martin | (none) | Un partout. Le match est relancé, il reste une vingtaine de minutes. | 5.1 / none | NEEDS SLOT | S1, A3 (the caller's idiom, FR 4.3) plus S2; "une vingtaine" covers 19 minutes plus added time |

Shorter G2 if the slot cannot grow: "Deux touches, et personne ne sort sur la frappe." (3.8 s).

### 6.2 fr/beginner: Théo Laurent (lead), Daniel Price (co)

| # | Time | Event | Who | Today | New line | Est. / room | Fit | Why |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 68', 4239.5 | quiet spell, 0-1 | Laurent (was co) | Attention à Wexmoor, qui a déjà pris des points trois fois cette saison après avoir été mené. | Wexmoor est mené, mais attention : déjà trois fois cette saison, ils sont revenus. | 5.5 / 6.5 | fits | Q1 plus R1: the state first, "attention" as French callers use it (FR 4.2); "Wexmoor est mené ... ils" is normal spoken French for a club; "revenus" after "mené" needs no "au score" |
| P1 | 70', 4382.7 | Ibsen intercepts | Laurent | Intercepté par Ibsen. | Ibsen récupère le ballon ! | 1.7 / 1.92 | fits | B2 plus R1, X2 |
| P2 | 4384.62 | switch | Laurent | Vers Rasmussen. | Rasmussen, de l'autre côté. | 1.7 / 1.84 | tight | B1 plus R1: "de l'autre côté" is the picture of the switch for a beginner (Rasmussen receives at y 62 of 68, the far side) |
| P3 | 4386.46 | chest | Laurent | Amorti de la poitrine. | Contrôle de la poitrine. | 1.7 / 3.14 | fits | B5, finishes P2 |
| P4 | 4389.6 | long ball | Laurent | Long ballon vers Tavares. | Long ballon pour Tavares ! | 1.7 / 2.70 | fits | B3, "pour" (FR 4.6) |
| P5 | 4392.3 | Tavares to Fontaine | Laurent | Pour Fontaine. | Fontaine ! | 0.6 / 1.40 | fits | B1 |
| G1 | 71', 4393.7 | Fontaine, 1-1 | Laurent, peak | BUT pour Wexmoor Athletic ! Fontaine fait mouche, c'est 1-1 ! | BUT ! BUT de Fontaine ! Wexmoor égalise ! | 3.5 / open | fits | C1 plus C2, club named (R1); "BUT de Fontaine" is the FR 4.1 form |
| G2 | about 4397.7 | over the goal | Price | Wexmoor revient à égalité, et Tamsworth doit tout reprendre à zéro. | Ballon récupéré dans son camp, trois passes, et c'est au fond ! Tout est relancé ! | 6.0 / 6.5 | fits | A1 in plain words ("trois passes" is true: switch, long ball, first-time pass; "quelques passes" was vague), A3 "tout est relancé" (FR 4.1); "tout reprendre à zéro" was the flat idiom |
| G3 | about 4404.4 | back to play | Laurent | (none) | Un partout ! Il reste une vingtaine de minutes. | 3.4 / none | NEEDS SLOT | S1 plus S2 |

## 7. What the slots need

The build-up fits today's slots in all six channels (four lines are tight, none is longer than its room). Two places do not fit:

1. **The score line G3 has no slot.** Call, co line and score need about 13 to 14 s after the goal (to about 4407.5); today the insert
   ends at `until` 4401.0 and the last voice at 4405.1.
   - Option A, run part 2 to about 4408 and win the time back from the two lead-ins (part 1 opens 3.5 s before its line, part 2 opens
     1.7 s before Ibsen): about 33 s in total. Pro: the order the user asked for (call, co, score) and real TV order. Contra: a little
     over 30 s, the insert must be re-exported.
   - Option B, keep 30 s and put the score at the end of the call ("Goal! Fontaine! Wexmoor are level! One-all!"), no G3. Pro: no
     timing change. Contra: score before the co line, which real callers do in only about a quarter of goals (EN 4).
2. **The co line comes in early.** On TV the co-commentator speaks over the replay, about 12 s after the goal (EN 5.2); here he starts
   3 to 4 s after it, because the insert has no replay. A 0.5 to 1 s breath of crowd between call and co line is the minimum (DE-FR 2,
   "Breath"). fr/expert G2 needs 0.8 s more, or the shorter line.

Also: the story line S1 should end at the cut (6.5 s); en/beginner and de/beginner run 0.2 and 0.6 s over it. Today three lines already
run 1 to 1.9 s over the cut.

## 8. What this implies for the prompt and the templates (not changed)

Note first: the shipped `story.json` still speaks the v4-style analyst lines ("36 percent", "Siegchance") although `analyst.py` is at
`PROMPT_VERSION` v5, which already forbids them. The insert needs a re-export after any change below.

`analyst.py` SYSTEM:

1. **Booth names.** SYSTEM still names Ewan Marsh and Nadia Rowe ("she"); the cast is a lead per channel plus Daniel Price. Use the
   channel's lead and Daniel Price, so the prompt and the voices agree.
2. **Goal analysis has a fixed order:** HOW first (the last pass or touch and the finish, in pictures), then one idiom for what it means.
   Never a mood sentence on its own ("glaubt wieder an den Sieg", "changes the whole feel of this game", "reprend confiance"); add today's
   three such lines to the bad list.
3. **Give the move its real facts** from the enriched rows: per step pass type (switch, long), touch (chest), first time, foot, technique
   (driven), and on the shot `pressure.under` and the distance band (outside the box). Today the facts give only "move" and "chain", so
   the model cannot say "one touch from Tavares, one from Fontaine" or "nobody closed it down".
4. **"switch" is a fact when the data says so.** SYSTEM forbids "switch" as a tactical label; allow it (and Verlagerung, transversale)
   when `pass_type` is `switch`.
5. **Length in seconds, per channel:** pass the room (call end to slot end) and the language's speaking rate, instead of 60 to 120
   characters. A French co line of 120 characters does not fit 4.7 s.
6. **Numbers:** keep "no percentage, probability, xG or count"; the score is the caller's line after the co line, not the analyst's.
   Optionally allow one timing fact a viewer can picture (the move length, "in eleven seconds") when it is given as a fact.
7. **Good examples** in the HOW then idiom shape, per language, with idioms from the research: "Game on.", "They're right back in this.",
   "Da muss doch einer drauf.", "Jetzt ist alles wieder offen.", "Le match est relancé !", "Tout est relancé !".
8. **Beginner co line:** the move in plain words ("from their own half to the net in no time"), the meaning in plain idiom, no
   term without its picture. **Expert co line:** the technique words (first time, direkt, en une touche, en première intention).

`templates.py` and `fast.py`:

1. **Goal call (`shot_goal`, line 51 area):** shout, scorer, meaning; drop the score from the call when a score line follows
   ("Goal! Fontaine! Wexmoor are level!", "Tooor! Fontaine! Was für ein Hammer!" for de/expert, "Tooor! Fontaine! Der Ausgleich für Wexmoor!" for de/beginner, "BUUUT ! Fontaine ! Quelle frappe !" for fr/expert, "BUT ! BUT de Fontaine ! Wexmoor égalise !" for fr/beginner).
   Remove "netzt ein", "fait mouche", "finds the net". German name twice is real (DE 3.1).
2. **New template kind after the co line:** score in spoken form plus time left ("One-all, just under twenty minutes left.",
   "Eins zu eins. Noch knapp zwanzig Minuten.", "Un partout. Le match est relancé, il reste une vingtaine de minutes."). Today `shape_for_tts` says
   "un à un"; French callers say "un partout".
3. **Ticker words out (WORDS tables, lines 710 and 744 area):** de `Abgefangen` -> "X geht dazwischen", `Brustannahme` ->
   "...mit der Brust" (after the name in the slot before), `Lang geschlagen auf` -> "Und lang auf"; fr `Intercepté par` -> "X intercepte", `Vers` -> "Pour",
   `Long ballon vers` -> "Ballon long pour".
4. **Name the technique in expert play-by-play only on the last balls:** switch ("Switched to", "Transversale pour"; German has no switch word short enough for the slot, the Experte names the touches in the co line),
   first-time lay-off ("First time, X!", "Direkt... X!", "Une touche, X !"; French "remise" only for a ball played back or square). Beginner gets the picture word instead ("Over to", "Rüber, X").
5. **German and French chains split one phrase over two slots:** "Rasmussen..." then "...mit der Brust." That
   satisfies `NAME_GAP_S` and is how DE 3.2 and FR 4.2 describe the chain; a name-less fragment is fine when the previous slot named
   the player.
6. **Energy by shortening:** the last two build-up lines get shorter and take the first "!" (EN 1.6); no exclamation before that.
7. **Story notes are the lead's voice,** not the analyst's (`story_note` today has `voice: analyst`).
8. **Pronouns:** these lines avoid player pronouns, so the test rule holds. Pronouns for the ball ("ihn", "le") are not player pronouns;
   if the rule is ever relaxed for male squads, "Den macht er!" and "il le met au fond" become available (DE-FR 8.2).

## 9. fr producer notes

Read as a Canal+/beIN producer against FR 4.1 to 4.6, `story.json` and the enriched rows 23664 to 23728. Only the fr lines changed; the "Today" column is
as shipped (checked against the `say` messages of channels 4 and 5). Estimates use 2.35 words a second.

Changed:

1. **S1 expert:** "Et aujourd'hui ?" removed. It is "Und heute?" in French; a French caller does not hang a question on a record. "sait revenir" carries the habit.
2. **S1 beginner:** shortened to 5.5 s (was 6.4, 0.1 s under the cut); "au score" dropped because "mené" already says from what.
3. **P2 beginner:** "Pour Rasmussen." became "Rasmussen, de l'autre côté." The beginner gets the picture of the switch, as "Over to" and "Rüber auf" do.
4. **P4 expert:** "Le jeu long pour Tavares !" became "Ballon long pour Tavares !". "Le jeu long" names a style of play, a caller calls the ball.
5. **P5 expert:** "Remise... Fontaine !" was a factual error. Tavares's pass goes 15 m forward on the ground (x 39.8 to 25.0), and a remise is a ball played
   back or square. Now "Une touche, Fontaine !".
6. **G1 expert:** "BUUUT ! Fontaine ! Quelle frappe !". A first-time, driven, unpressured strike from 25 m is the textbook case for "Quelle frappe !".
   "Wexmoor égalise" moved to the caller's G3 ("Le match est relancé").
7. **G2 expert:** it said the same thing twice ("en une touche" and "en première intention" both mean first time) and closed with a caller's idiom. Now it gives the
   two touches and the defensive failure the data proves (`pressure.under: false`): "Tavares en une touche, Fontaine sans contrôle, et personne ne sort !".
   4.7 s, so it now fits the room it was 0.8 s over.
8. **G2 beginner:** "quelques passes" became "trois passes" (switch, long ball, first-time pass), which is concrete and true.
9. **Section 8 fr quotes** (goal call, jeu long, remise) updated to match.

Kept on purpose: "Ibsen intercepte !" and "Ibsen récupère le ballon !" (both real), "Transversale pour Rasmussen." (the data calls it a lofted switch
to the far side, y 62), "Contrôle poitrine..." and "Contrôle de la poitrine." (chained to the name 1.8 s before), "BUT ! BUT de Fontaine ! Wexmoor égalise !",
"Un partout !" with "une vingtaine de minutes" (19 minutes plus added time).

Still weak:

- **No pronouns.** A real caller says "il contrôle de la poitrine", "il allonge pour Tavares", "personne ne sort sur lui". Without "il" and "lui", P3 and G2
  read a little like captions (DE-FR 8.2). The best real P4, "Rasmussen allonge pour Tavares !", is blocked by the 6 s name gap.
- **No "oui", "allez" or "attention" in the build-up gaps.** FR 4.2 says French callers fill gaps that way. The slots are one fragment each, so the chain
  sounds a little German.
- **The co line comes 3 to 4 s after the goal, with no replay.** A French consultant starts on the replay with "Regardez...". Here that opener does not fit 4.7 s.
  If the slot grows (section 7, option A), add "Regardez," to both G2 lines.
- **G3 has no slot,** and fr/expert now leaves the equaliser meaning to it. With option B (no G3), use "BUUUT ! Fontaine ! Quelle frappe ! Un partout !" for the expert call.
- **Daniel Price as a French consultant** is an English booth name with a borrowed voice (VOICE-CAST.md). A French viewer hears that as dubbed.
- No native French speaker has heard any of this. These estimates come from word counts, not audio.

## 10. en producer notes

Read as a Sky or BBC producer would: would the lead or co say exactly this, live, over this picture? Every claim was checked against
`story.json` and the enriched rows of the move (23664 to 23728).

**Changed (en/expert)**
- S1: "points from losing positions" is the phrase a Premier League lead reads off the stats sheet. "They need a fourth." was a
  writer's button, not something said over a quiet spell.
- P2: "Across to Rasmussen." replaces "Switched to Rasmussen.". The participle is feed language, and a ball from one centre-back to
  the other is not called a switch on air, even when `pass_type` says switch. The technique word for the expert now sits on P5 only.
- P3: "Chests it down." Callers speak in the present tense over the picture.
- P4: back to today's "Long ball for Tavares.", which is already the real form. "Long ball, lifted towards" doubled the flight words.
- G1: "Oh, what a strike! Kenji Fontaine!" The full name on the goal is the British habit; "what a hit" is rarer.
- G2: "Doesn't let it settle, and nobody closes the shot down. Game on." The shot is first time and unpressured in the data. The old
  "One touch from Tavares, one from Fontaine" repeated P5. Under 6.3 s it leaves about a second of crowd after the call.
- G3: "twenty minutes or so to go". At 71' that is 19 minutes plus added time, so "just under twenty" was only true without added time.

**Changed (en/beginner)**
- S1: today's idea in spoken form ("Don't write Wexmoor off."), 5.7 s, so it ends before the cut. The 0.2 s overrun is gone.
- P1, P4: no exclamation marks before the last ball.
- G1: full name. G2: "Won back in their own half, and seconds later it's in." That is the move in words a new viewer can follow,
  with no number.

**Facts deliberately not used:** the keeper (no keeper row on the goal, so not "nothing the keeper could do"); "top corner" (the
placement is `high_left`, z 1.93 m, which is high but not shown as the corner); "25 yards" (the shot is from 25 m, about 27 yards,
and a British caller would say yards); "lay-off" (Tavares plays an 18 m first-time ball forward, not a lay-off); Petrov's save
(the viewer never sees it, the insert opens 6.5 s later); the win probability.

**Still weak**
- The co line comes in 4 to 5 s after the goal with no replay. On Sky the co talks over the replay at about +12 s, starting with
  "Look at..." or "Watch...". Without a replay, any co line here is early.
- "Game on." and "back in this" both carry the meaning the call already gave with "level". Real booths say it twice, but if the
  rule is never twice on one page, cut A3 from G2 and leave the meaning to the call.
- "First time, Fontaine!" has to be read with a beat on the comma, or it sounds as if Fontaine played first time. The TTS needs the
  pause.
- G3 still has no slot (section 7).
- Section 7 option B and the section 8 examples still quote the old en call ("Goal! Fontaine! Wexmoor are level!"). With the full
  name they should read "Kenji Fontaine". Not changed, because those sections are not the en tables.
- The en word rate (2.1 per second) is from today's voiced lines. A British lead calling a goal runs slower, so G1 is estimated at
  4.3 s, not 3.4 s.

## 11. de producer notes

Read as a German TV producer against `CASTER-STYLE-DE-FR.md` and the `story.json` facts (checked again in `enriched.jsonl`: switch
lofted left foot, chest, long lofted, Tavares first time 18.3 m forward, shot first time, right foot, driven, high left, no pressure).
Only the de/expert and de/beginner rows of section 5 and the German strings in section 8 were changed.

What changed and why:

- **Lengths were wrong in three German slots.** The word rate (1.7 a second) undercounts German. Per syllable from today's audio,
  "Verlagerung auf Rasmussen" is about 2.5 s for a 1.71 s room, and the old beginner S1 is about 7.6 s for 6.5 s. Both tables now carry
  syllable estimates.
- **P2 expert:** "Verlagerung auf Rasmussen" -> "Rasmussen...". It did not fit, and a switch between the two centre-backs is not
  what a Sky caller calls a "Verlagerung" live anyway: he says the name and lets the picture work. The technique moves to the co line.
- **P3 both:** "Mit der Brust runter." -> "...mit der Brust." "Runter" alone, with no verb, is half a phrase; the real chain is
  "Rasmussen... mit der Brust..." (DE-FR model line 1).
- **P1 both:** "!" removed. The script's own energy rule (section 8, item 6) keeps the first "!" for the last two balls.
- **P4 expert:** "Und lang auf Tavares!" The "Und" is the German caller's accelerator.
- **P5 expert:** "Direkt, Fontaine!" -> "Direkt... Fontaine!" Without the pause it can be heard as "Fontaine, first time".
  "Legt ab" is not used, because Tavares's ball goes 18 m forward, not back or square.
- **P2 beginner:** "Rüber auf Rasmussen" -> "Rüber, Rasmussen." "Rüber auf" takes a side ("rüber auf links"), not a player, and it
  was over the room.
- **G1 expert:** "Tooor! Fontaine! Fontaine! Der Ausgleich!" -> "Tooor! Fontaine! Was für ein Hammer!" The shot is a first-time,
  driven strike from about 25 m, and a German caller reacts to the hit. "Der Ausgleich" and then "Eins zu eins" in G3 says the same
  thing twice; the meaning now comes in G3 as "Und jetzt ist hier wieder alles drin."
- **G1 beginner:** scorer before the club ("Tooor! Fontaine! Der Ausgleich für Wexmoor!"), as pattern C1 says.
- **G2 expert:** "..., und keiner geht drauf. Wexmoor ist zurück!" -> "Tavares direkt, Fontaine direkt. Da muss doch einer drauf."
  "Wexmoor ist zurück!" with an exclamation mark is the caller's line, not the Experte's. "Da muss doch einer drauf" is the Experte's
  complaint form (DE 3.4) and says the true fact (no pressure on the shot). It also got 0.2 s shorter. The old line was 6.0 s for 5.7.
- **G2 beginner:** "Hinten den Ball erobert" -> "Ball hinten gewonnen" ("erobert" is print German), no "!" in the co line, now
  inside the room.
- **S1 expert:** "nach Rückstand noch gepunktet", "diese Saison" (spoken) instead of "in dieser Saison" (written).
- **S1 beginner:** "Wexmoor hat diese Saison schon dreimal einen Rückstand aufgeholt." It fits now (6.4 s), drops "sie" for the team
  (it reads as "she" to the pronoun test), and leaves the 0-1 to the scoreboard. Section 7's remark that de/beginner runs 0.6 s over the
  cut no longer holds.
- **G3:** the expert gets the meaning ("hier ist wieder alles drin"), the beginner the time left ("noch knapp zwanzig Minuten zu
  spielen"). Both still have no slot (section 7).

Still weak:

- **Daniel Price in a German booth.** An English-named co speaking German sounds dubbed. A German Experte name (persona decision)
  would help more than any wording.
- **The co line comes 3 to 4 s after the goal**, with no replay (section 7, item 2). A real Experte would open with "Schau dir das an"
  over the replay. Without a replay that opener would be false, so it is left out, and the line sounds a little abrupt.
- **Tight lines:** S1 both (6.4 / 6.5), P2 beginner (1.7 / 1.71), G2 expert (5.8 / 5.7). Measure them on the real voice. If G2 expert
  is cut, use "Zweimal direkt, und keiner geht drauf." (about 4.0 s).
- **"Und heute?"** is fine on Sky but only works if the caller's voice rises on it. It is flat in the browser voice.
- **"Tooor"** must be checked on ElevenLabs; the voice may say "Toor" short or spell it. Fall back to "Tor!" if it does.
- **Ball pronouns:** "Nimmt ihn mit der Brust runter" and "Den macht er!" would be more natural still. They are left out because of
  the pronoun test (section 8, item 8).
- Nobody has heard these lines spoken yet. Treat the estimates as paper until a native speaker listens to one take.

