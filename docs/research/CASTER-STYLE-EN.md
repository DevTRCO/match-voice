# How real commentators handle a goal: what the corpus shows

Paper only. Nothing in the code, prompts, templates or data was changed for this note, no model or voice call was made.
Source: SoccerNet-Echoes `data/corpus/echoes/v3_en.arrow` (CC BY 4.0, Whisper v3, 726 halves, 679,738 segments, 555 hours).
Scripts lived in the session scratchpad only. Our own examples use the fictional insert (Wexmoor Athletic, Tamsworth Wanderers;
Ibsen, Rasmussen, Tavares, Fontaine; 0-1 at 70', equaliser at 71').

## 0. Read this first: what the corpus is

1. **The "English" set is almost all machine translation.** Whisper translated the broadcast language into English. Of the 136 goals
   used below, 44 are Serie A (Italian and Russian-language feeds), 36 Champions League (mostly Spanish-language feeds by the
   wording), 33 LaLiga, 10 Bundesliga, 8 Premier League (a Spanish feed, see docs/COMMENTATOR.md) and 5 Ligue 1. Structure, timing, what gets said and how often all carry over. Exact
   English wording does not ("Isco brand on the chest" is a calque of "marca Isco").
2. **One half is native English broadcast:** `europe_uefa-champions-league/2015-2016/2015-09-29 - 21-45 Arsenal 2 - 3 Olympiakos Piraeus/2`
   (BT Sport, a play-by-play caller plus a co-commentator called Martin). It holds two goals 59 s apart. Found by ranking all halves on
   British idiom density ("tap-in", "fires it home", "nil"); its score is 5.1 per 1,000 words, the next half 3.4 (a German translation).
   Most of the English wording advice below comes from this half; the counts come from the 136 goals.
3. **Timestamps are Whisper segments,** often stretched over silence or crowd noise, and some halves have a 1 s or 2 s grid. Pauses are
   lower bounds. Speakers are not labelled, so caller versus co-commentator is inferred from markers ("I think", "Yes", "you know").

## 1. The short version

1. **Nobody reads out a model.** In 136 post-goal windows (30 s each) there are 0 percentages and 0 win probabilities. Across all 555
   hours, a numeric win probability occurs 0 times; "percent" occurs 1.6 times per 90 minutes and is almost always possession or duels.
   "Wexmoor glaubt wieder an den Sieg, die Siegchance steigt auf 36 Prozent" has no counterpart anywhere in the corpus.
2. **The build-up is names.** 58% of the segments in the 40 s before a goal carry a player name, 0.84 names per segment. The typical
   segment is 5 words. The pass verbs we assumed are rare: "finds" is 1 per 10,000 words, "lays it off" 0, "switch" 0.5.
3. **The call is short and names the scorer at once.** Median call unit 6 words over about 5 s. The scorer is named in the call unit
   in 67% of goals, within 12 s in 96%, first name at a median of +2.0 s.
4. **The score is said in under half of the goals,** once, around +11 s. Minute in 24%. Stats or a tally in 16%. Crowd in 14%.
5. **The replay talk is about HOW and WHO,** in 60% of goals, starting around +14 s: the touch, the foot, the pass that made it, the
   defender who failed. Meaning for the match ("back level", "back in the game") in 39%, around +14 s.
6. **Energy rises by getting shorter, not by talking more.** Words per second fall slightly in the last 10 s before the goal
   (2.17 against 2.31) while segments shorten from 6.1 to 4.8 words. There is no silence before the call: median gap 0.0 s, over 1 s
   in 4% of goals.

## 2. Method

- **Goal calls.** A segment of at most 9 words matching a call shape ("Goal!", "And the goal", "It's a goal", "Goal by X",
  elongated "Gooool"), not "goal kick/keeper/line/difference", first one per 120 s. 2,518 loose candidates; 304 passed a window check
  (repetition of one line at most 3 times, at most one non-Latin segment, at least 4 segments before, a score word, scoreline or
  "goal by X" in the 30 s after, no ad or subtitle credit text).
- **Manual review.** I read the first 160 of the 304 one by one: 24 were not a fresh call (replay talk about an earlier goal, a goal
  kick, a "goal of the week" item, Whisper garbage), so precision is 85%. Disallowed goals were kept: the call is real. **All numbers
  below use these 136 reviewed goals** from 94 matches (Serie A 44, Champions League 36, LaLiga 33, Bundesliga 10, Premier League 8, Ligue 1 5), unless marked.
  The unreviewed 304 give the same picture (0 percentages after a goal, 27% with a scoreline, numbers within 3 points elsewhere).
- **Window.** 40 s before the call, 30 s after. Segment shapes, names and topics with small lexicons and a capitalised-word name
  detector (a stop list removes sentence openers like "Again", "Hit", "Goal"). Lexicon counts are lower bounds.
- **Recall is low on purpose.** The 359 matches with both halves have 1,207 real goals; the detector finds 591 calls in them. Many calls
  are lost to translation ("Gol" heard as "Well", calls merged into longer segments). For style that does not matter, for frequency
  of goals it would.

## 3. Build-up: the 40 s before the goal

### 3.1 Rhythm

| Measure (136 goals) | Whole 40 s | Last 10 s |
| --- | --- | --- |
| Segments | 17.7 (26.5 a minute) | |
| Words per segment, mean | 5.6 | 4.8 |
| Words per second | 2.27 (136 a minute) | 2.17 |
| Speech coverage of the window, median | 88% | |
| Segments that name a player | 58% | 60% |
| Segments with "!" | 1% | 2% |

Corpus-wide the rate is 126 words a minute and 4.1% of gaps are longer than 3 s (docs/COMMENTATOR.md). A goal build-up is a little
faster than average, and the last seconds are cut into shorter pieces rather than filled with more words. The native half runs at
144 words and 20.4 segments a minute.

### 3.2 What a segment looks like

| Shape | All 40 s (2,406 segments) | Last 15 s (973) |
| --- | --- | --- |
| No name, at most 6 words ("Put the center into the area.", "Hit.") | 34% | 34% |
| Name plus a short verb phrase, at most 6 words ("Suárez starts") | 24% | 25% |
| Name only ("Rafinha.", "Bruno Perez.") | 13% | 16% |
| Name inside a sentence of 7 or more words | 13% | 10% |
| No name, 7 or more words (story, analysis) | 11% | 10% |
| Two names joined ("X for Y", "X to Y") | 3% | 4% |
| Same name twice in a row ("Neymar, Neymar") | 1% | 1% |

So, close to the goal: one segment in six is a bare name, one in four is a name with a verb, one in three is a nameless fragment that
says what the ball does ("Watch out for the shot.", "Ball that turns around.", "Shot and goal."). Longer sentences drop from 24% to
20% of segments. Name repetition is rare as a pattern (1%), but when it happens it is at the very end ("Suarez, Suarez, Suarez,
Suarez" before a Barcelona goal), the tension marker of the caller.

### 3.3 How passes are described

Per 10,000 words, whole corpus (4.1 million words) against the native half (6,469 words):

| Phrase | Corpus | Native half |
| --- | --- | --- |
| "to " (mostly "X to Y", "now to Y") | 272 | 288 |
| "for " (mostly "ball for Y", "X for Y") | 134 | 147 |
| "cross" / "center" (translated cross) | 23 | 29 |
| "puts it" | 3.3 | 0 |
| "back to" | 2.4 | 6.2 |
| "plays it" | 1.2 | 1.5 |
| "finds" | 1.0 | 0 |
| "switch" | 0.5 | 0 |
| "lifted", "dinks", "floated", "pulls it back" | 0.1 or 0 | 1.5 to 3.1 each |
| "lays it off" | 0 | 0 |

A pass is mostly not a verb at all. It is the receiver's name, with "to" or "for" in front, or two names in a row. When the native
caller uses a verb, it is about the flight of the ball (lifted, floated, dinked, pulled back), and it comes on the ball that matters,
the last or second-to-last pass. In the 40 s before the 136 goals, the most frequent verbs are "plays" (25), "pass" (24), "leaves"
(12), "puts it" (12); "finds" occurs once.

## 4. The goal call

| Feature (136 goals) | Share |
| --- | --- |
| Opens with a bare "Goal" ("Goal!", "Goal.") | 50% |
| Opens with "And the goal" / "And a goal" | 24% |
| The goal word once | 63% |
| Twice or three times | 31% |
| Four or more ("goal, goal, goal, goal...") | 6% |
| "!" in the call | 29% (translation drops many) |
| "What a goal / what a shot" | 4% |
| Scorer or team named in the call unit | 67% |
| A name within 12 s | 96% |
| Team in the call ("goal of Barça", "Real Madrid scores") | 20% |
| Minute in the first 12 s ("of Barça in '59") | 12% |
| Score in the first 12 s | 24% |
| How it went in, in the first 12 s | 21% |
| Call unit length | median 6 words (25 to 75%: 4 to 9), about 5 s |

The call has a fixed order: the shout, then WHO, then (optionally) WHOSE and WHEN, then the score. The finish itself is mostly left to
the replay. Typical sequences from the reviewed set: "Goal! / Goal! / of Barça in '59 / goal by Luis Suárez with that counter action";
"Goal by Aritz Adúriz. / Once again the red and white team entered from the right."; "And a goal! / 3-0. / Bruno Perez.".

Pause after the call: within the first 12 s, 23% of goals show a gap of 2 s or more and 9% of 4 s or more (lower bounds: Whisper
stretches segments over crowd noise). In the native half Whisper wrote "FANS ROAR" 86 times, so the crowd is part of the soundtrack.

**English in the native half.** The equaliser: "Theo Walcott lifted in towards Alexis Sanchez!" then the finish in one picture, then
"Game on." Then the go-ahead goal 59 s later: "and it's scored!" and "Olympiacos are back in front." The caller's own sentences do not repeat
"goal"; a free-standing "Goal! Goal! Goal!" segment sits about 19 s after "fires it home", which looks like a timing artefact or crowd
audio rather than the caller's call (not verifiable from text).

## 5. The first 30 s after

### 5.1 What comes when

| First mention in the 30 s after the call | Goals with it | Median time |
| --- | --- | --- |
| A player name | 99% | +2.0 s |
| Any digit (mostly minute and score) | 61% | +11.0 s |
| The score | 47% | +11.3 s |
| The minute | 24% | +11.5 s |
| Meaning for the match (lead, level, back in the game, tie) | 39% | +14.2 s |
| How it was scored (foot, head, corner, rebound, shot type) | 60% | +14.3 s |
| Stat or tally (season, in a row, his ninth) | 16% | +15.0 s |
| Second voice markers ("I think", "Yes", "as you said") | 22% | +16.2 s |
| Crowd or stadium | 14% | +16.2 s |
| Percent or probability | **0%** | |

Score mentions per goal: 0 in 84 goals (62%), once in 38 (28%), twice or more in 14 (10%). When it is said, it is said as a scoreline
or as "Arsenal 2, Olympiacos 3", or replaced by its meaning ("back level", "puts Sporting ahead again", "to tie the game").

### 5.2 Caller versus co-commentator

The order in the reviewed windows (and in the native half) is stable:

1. **0 to 3 s, caller:** the shout and the scorer.
2. **3 to 12 s, caller:** whose goal, when, the score, often one evaluation ("Stunning.", "Tremendous mistake by Handanovic.").
3. **12 to 30 s, co-commentator over the replay:** how it happened, in pictures. The pass that made it ("look how he just dinks this one
   into his path"), the finish ("with his right foot he finishes off"), the error ("What a mistake in Chelsea's defense."), the
   keeper ("nothing the keeper could do"). In 60% of goals this HOW layer is there; an explicit assist word (pass from, cross from, delivery, gift) shows up in 10%.
4. **Somewhere in 10 to 30 s, either of them:** what it means. Comeback language beats numbers: "back in the game", "back level",
   "back to square one", "a mountain to climb again".
5. **Back to play:** in the native half the caller goes back to the next phase within seconds of the second goal ("Straight under
   pressure though at the other end"). Several Spanish windows return to play-by-play at +15 to +25 s.

The only number-like facts after a goal are the minute, the score, a tally ("his ninth goal in the championship", "first goal of the
season") and, once, a timing fact ("59 seconds between the Arsenal equaliser and the go-ahead goal"). Every one of them is a count of
something the viewer can picture, not a model output.

## 6. Quiet spells and story lines

- Outside goal windows (more than 4 minutes from any call, 567,414 segments), a background lexicon (season, years ago, signed,
  contract, career, debut, injury, last week, coach, record, loan, former) hits 1.7% of segments, about one line every three minutes
  at 20 segments a minute. 18% of quiet segments are long (10 words or more).
- The native half shows what story lines are hung on: **the player who just came on or just touched the ball.** A substitute gets his
  birthday, appearance count and medal record; a player on the ball gets "seven years since he scored a goal in the Champions League"
  or "11 of his 37 Arsenal goals have been scored in the Champions League". Club history comes once ("the last time Arsenal won a
  European trophy, 1994 in Copenhagen").
- Numbers in the native half: 0.6 segments a minute contain a digit over 45 minutes. All of them are game state ("11 minutes into the
  second half, 2-1 down", "less than 20 minutes to go", "Olympiakos leading 3-2"), a player's record, a result elsewhere
  ("Bayern Munich 5-0 up against Dynamo Zagreb") or broadcast promotion. One possession figure (354 passes) in 45 minutes. No percent.
- Game state comes back on its own: about every 5 to 10 minutes in the native half, always as score plus time left, never as a chance.

## 7. Pattern catalogue

Templates are shown with our fictional names. Brackets are optional parts. Shares are from section 3 to 5.

### 7.1 Build-up (the volume layer)

| Pattern | Example (insert) | Use |
| --- | --- | --- |
| `<name>.` | "Rasmussen." | about 1 in 6 segments near a goal |
| `<name> <short verb>.` | "Ibsen cuts it out." | about 1 in 4 |
| `to <name>.` / `for <name>.` | "To Fontaine." | the default pass, no verb |
| `<passer> for <receiver>.` | "Tavares for Fontaine." | 3 to 4%, the decisive pass |
| `<flight verb> <direction> <name>!` | "Long ball, lifted towards Tavares!" | only the last or second-last ball |
| `<nameless fragment>` | "Watch out for the shot." / "Shot!" | 1 in 3 segments, the ball's state |
| `<name>, <name>!` | "Fontaine, Fontaine!" | 1%, only in the last 3 s |

### 7.2 The call

| Pattern | Example | Share in corpus |
| --- | --- | --- |
| `Goal! [Goal!] <scorer>!` | "Goal! Fontaine!" | bare "Goal" opener 50% |
| `And the goal! <scorer>.` | "And the goal! Fontaine." | 24% |
| `And it's <in/scored>! [<scorer>]` | "And it's in! Fontaine!" | native English form |
| `<scorer> <finish in one picture>.` | "Fontaine just gets there and fires it home." | native English form |
| `Goal by <scorer>.` | "Goal by Fontaine." | frequent in Spanish feeds |
| `<scorer>! <team> are level!` | "Fontaine! Wexmoor are level!" | meaning instead of score |

Call length target from the corpus: 4 to 9 words, scorer inside it in two of three goals, never a number other than the score.

### 7.3 After the call

| Time | Who | Pattern | Example |
| --- | --- | --- | --- |
| +3 to +12 s | caller | `<team> [are back] level[, <minute>].` / `<score>.` (in under half of goals, once) | "Wexmoor are level. One-all." |
| +3 to +12 s | caller | `<one-word or short verdict>.` | "Game on." |
| +12 to +30 s | colour | `Look at <passer>, <what the pass did>.` | "Look at Tavares, he just lays it into his path." |
| +12 to +30 s | colour | `<scorer> <how>: <foot or head>, <where>.` | "First time, left foot, nothing the keeper could do." |
| +12 to +30 s | colour | `<who failed> <what they did wrong>.` | "Tamsworth stood off him, far too easy." |
| +10 to +30 s | either | `<meaning in idiom>.` | "And they're right back in this." |
| +15 to +30 s | either | `<tally>, only if true and short.` | "His first goal of the season." |
| after | caller | `<back to play>.` | "Twenty minutes left. Can they go on?" |

### 7.4 Quiet spell

| Pattern | Example |
| --- | --- |
| `<player on the ball>, <one fact about him>.` | "Tavares, on for his first league start." |
| `<score>, <time left>[, <who needs what>].` | "Still 0-1, twenty minutes to go." |
| `<record> <of this player in this competition>.` | "Three goals in his last four at home." |

## 8. What this says about our current lines

| Our line type | What real commentary does instead |
| --- | --- |
| Win probability in percent after a goal ("die Siegchance steigt auf 36 Prozent") | 0 of 136 goals, 0 in 555 hours. Say the meaning in idiom ("Wexmoor are back in it"). The number can stay on screen. |
| "Wexmoor glaubt wieder an den Sieg" (abstract mood) | Real lines point at a picture: the manager, the scorer celebrating, the fans. "Arsene Wenger with a smile on his face at last." |
| Score and minute in the call | Score in the first 12 s in 24%, minute in 12%. Put the scorer in the call, the score after it, once. |
| Name-less pass fragments as volume | One in three build-up segments is nameless, but it says what the ball does now ("Shot!"), not the type of pass. |
| "finds", "lays it off", "switches it" in every pass | Rare (0 to 1 per 10,000 words). Default is "to <name>". Keep verbs for the last pass. |
| Analyst opens right at the goal | The colour voice comes in around +12 to +16 s, over the replay, about HOW and WHO. |

## 9. Short quotes (CC BY 4.0, SoccerNet-Echoes)

Match ids:
M1 `europe_uefa-champions-league/2015-2016/2015-09-29 - 21-45 Arsenal 2 - 3 Olympiakos Piraeus/2` (native English);
M2 `europe_uefa-champions-league/2015-2016/2015-11-04 - 22-45 Barcelona 3 - 0 BATE/2`;
M3 `spain_laliga/2016-2017/2017-03-18 - 18-15 Ath Bilbao 1 - 2 Real Madrid/2`;
M4 `spain_laliga/2014-2015/2015-05-23 - 19-30 Barcelona 2 - 2 Dep. La Coruna/2`;
M5 `england_epl/2015-2016/2016-04-09 - 19-30 Manchester City 2 - 1 West Brom/1`;
M6 `spain_laliga/2016-2017/2016-08-27 - 21-15 Real Madrid 2 - 1 Celta Vigo/2`;
M7 `spain_laliga/2016-2017/2017-04-08 - 21-45 Malaga 2 - 0 Barcelona/1`.
M2 to M7 are Whisper translations.

| # | Moment | Quote | Match |
| --- | --- | --- | --- |
| 1 | build-up | "Bellerín infield then to Ramsey..." | M1 |
| 2 | build-up, last pass | "Theo Walcott lifted in towards Alexis Sanchez!" | M1 |
| 3 | finish | "The little man just gets into position and fires it home." | M1 |
| 4 | verdict | "Game on." | M1 |
| 5 | meaning | "and Arsenal back level here at the Emirates." | M1 |
| 6 | picture, not mood | "Arsene Wenger with a smile on his face at last," | M1 |
| 7 | second goal | "Almost straight from the kick-off," | M1 |
| 8 | second goal | "and it's the substitute Finn Bogeson and Olympiacos are back in front." | M1 |
| 9 | how | "Fortunis Bogeson there, just a tap-in." | M1 |
| 10 | who failed | "Shocking defending from Arsenal, nothing the keeper could do this time." | M1 |
| 11 | the one stat | "59 seconds between the Arsenal equaliser and the go-ahead goal for Olympiacos." | M1 |
| 12 | meaning | "So, Arsenal back to square one." | M1 |
| 13 | replay, co-commentator | "I mean, look how he just dinks this one into his path." | M1 |
| 14 | game state | "11 minutes into the second half, 2-1 down," | M1 |
| 15 | story on a sub | "On the day of his 31st birthday, his 49th appearance in the Champions League." | M1 |
| 16 | build-up to call | "Neymar for Luis Suárez who finds space, Suárez hits him, goal" | M2 |
| 17 | after call | "goal by Luis Suárez with that counter action" | M2 |
| 18 | call | "Goal by Aritz Adúriz." | M3 |
| 19 | score | "Atlético Club 1. Real Madrid 1." | M3 |
| 20 | how | "Lucas just nailed it into the right corner on the turn." | M4 |
| 21 | meaning | "puts the Deportivo de La Coruña team back in the game." | M4 |
| 22 | call, scorer | "What a whip from STEFAN SESENYÓN." | M5 |
| 23 | score with place | "That puts the score at 0-1 at the Etihad Stadium." | M5 |
| 24 | score after scorer | "Celta scores, Fabián Orellana scores, Real Madrid 1, Real Club Celta 1." | M6 |
| 25 | tally | "He has just scored his ninth goal in the championship" | M7 |

## 10. Limits

- One native English half, two goals. English idiom beyond it is my reading of broadcast English, not a corpus count.
- Most goals come from Spanish-, Italian- and Russian-language feeds; these repeat "goal" more than British callers. The 6% with four or
  more is their habit, not an English one.
- Name detection is heuristic (capitalised words minus a stop list); translation sometimes mangles names ("Sesenyón" for Sessègnon).
- Detector recall is about half the real goals; nothing above is a goals-per-match figure.
