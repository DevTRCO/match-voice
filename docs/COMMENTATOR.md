# What a TV commentator says, and how often

Source: SoccerNet-Echoes (CC BY 4.0), Whisper v3 transcripts of full broadcasts, English set, 726 halves (33,300 minutes), of which 28 halves
are Premier League. Script: `backend/scripts/commentator_profile.py`. Only counts are kept here; no transcript text is stored in this repo
and the corpus (`data/corpus/`) is git-ignored.

Caveat: the English set is a machine translation of the broadcast language. The Premier League sample I looked at is a Spanish-language broadcast
translated to English. Rates and structure carry over, wording and topic lexicons do not, and the lexicon counts below are lower bounds.

## Rhythm

| Measure | Premier League sample | All leagues |
| --- | --- | --- |
| Speech per minute (median, words) | 131 | 126 |
| Segments per minute | 22 | 20 |
| Share of gaps longer than 3 s | 2.5% | 4.1% |
| Segments of 5 words or fewer | 56% | 56% |
| Segments of 12 words or more | 10% | 11% |
| Segments that name a player | 38% | 35% |
| Names per 100 words | 9.3 | 8.8 |
| Words per minute in the 30 s after a goal call | 156 | 150 |

Reading: a commentator talks almost without pause. More than half of everything said is a short play-by-play fragment, mostly a name or a
name with a verb. Long explanations are one segment in ten. A goal speeds the pace up by about a fifth, it does not change the mode.

## Topics (share of segments touching the topic, lexicon based)

| Topic | Per minute (EPL) | Share |
| --- | --- | --- |
| Game state (time, score, lead) | 1.0 | 4.6% |
| Context and statistics (season, record, history) | 0.9 | 4.2% |
| Evaluation (great, poor, mistake, danger) | 0.9 | 4.1% |
| Ball movement (pass, cross, clearance) | 0.6 | 2.7% |
| Goal | 0.5 | 2.4% |
| Chance and shot | 0.4 | 1.9% |
| Set pieces | 0.4 | 1.8% |
| Referee, fouls, cards | 0.3 | 1.2% |
| Tactics (press, shape, transition) | 0.2 | 1.0% |
| Duels and dribbles | 0.2 | 0.9% |
| Off-ball runs and space | 0.1 | 0.6% |

The rows add up to a quarter of all segments. The rest is name chains and fragments the lexicons cannot classify.

## What it means for a persona and for our data

1. **Volume comes from a thin layer.** The fast layer is identity of the player on the ball, about 22 short utterances a minute. It needs only
   "who has it now", at roughly one update per three seconds. Our events already come at that pace.
2. **Insight is a minority and mostly not tactical.** Score and time, context and evaluation are about one segment a minute each. A persona
   needs a source for context ("first goal for him this season", "third corner in five minutes"), which we can compute from the event stream.
3. **Off-ball runs and dribble detail are rare in real commentary** (about one every ten minutes by this lexicon, probably undercounted by
   translation). Synthetic movement is still worth building because it is what no event feed offers, but as a differentiator on key moments,
   not as the main volume.
4. **Silence is not the style.** Real commentary has almost no gaps; ours speaks a line per moment. Closing that gap means a cheap, constant
   short layer (names and ball movement) under the expensive analyst layer, not more analyst calls.
5. **Pace follows the match, mildly.** About +20% words per minute around a goal. Energy should change delivery more than word count.

## Not measured yet

Per-event timing (how long after the action the call comes), sentence openers and verbs per energy level, and commentator pairs (caller versus
colour). Those need event timestamps; the transcripts carry only speech time.
