# Pitch: match-voice

Text for the submission form, written against the five judging criteria. Every number comes from the code or from
[EVAL.md](EVAL.md). Teams, players and matches are fictional.

## One line

Every fan gets their own football commentator, in their language and at their level. Model-written lines are checked
against the facts before release, template lines use only fact-engine values, and all 818 spoken lines in the
evaluation pass the check.

## Short description (for a character-limited field)

match-voice turns a stream of match events into live commentary in English, German and French, for beginners and
experts. Six voices run side by side and the fan switches at any time. Play-by-play comes from templates in
milliseconds. Analysis comes from an Analyst agent (Claude Haiku on the Microsoft Agent Framework) and a Verifier
that rejects invented numbers, wrong scorelines and wrong players before a model line is released. A rejected line goes
back once with the reason, and a template line takes over if the retry fails. In our evaluation 818 spoken lines
across three matches all pass the verifier, which catches 99.8 to 100% of injected errors. The demo replays a
recorded run of the same pipeline, so it needs no key. An MCP server lets any AI client ask about a match and test
a sentence against its facts.

## The problem

Commentary is written for one imagined fan. A newcomer hears "xG" and "half-space" and gives up. An expert hears
"the ball goes forward" and tunes out. A fan who does not speak the broadcast language gets subtitles that lag the
game, or nothing. AI can write for each of them, but a model that invents a number or swaps a scoreline in live
commentary is worse than no commentary. The hard part is trust, so that is where this project spends its effort.

## 1. Technology

- **Microsoft Agent Framework** runs the newsroom as a workflow of three executors (Analyst, Verifier, Publisher)
  with conditional edges: failing lines loop back to the Analyst once, passing lines go to the Publisher. Claude is the
  model through `agent-framework-anthropic`.
- **One pipeline, two modes.** `live` writes analysis while the match streams; `replay` runs the same code on recorded
  analyst lines. A test asserts that the static `replay.json` equals what the WebSocket sends.
- **Compact overlay protocol (v1).** Frames are arrays and numbers, decoded by tables sent once. For one match at
  x30, `replay.json` holds 1,374 frames, 347 spoken lines and 56 log entries in 281 KB (54 KB gzipped). The UI draws the pitch
  on a canvas and the win-probability chart with uPlot from one animation-frame loop, and re-renders React only on
  rare topics.
- **Open source, not custom code.** FastAPI, the official `mcp` SDK, Vite, React, uPlot, pydantic, orjson, SSE.
- **Tested.** 186 tests (pytest), including a subprocess MCP test over stdio and a WebSocket smoke test.
- **Spend control.** Every model call goes through `GuardedLLM`: a disk cache and a hard call budget. Building all
  three demo matches took 23 Haiku calls.

## 2. Agentic design

| Agent | Model | Responsibility |
| --- | --- | --- |
| Analyst | Claude Haiku | Writes six lines for one moment (3 languages x 2 styles) from the facts it is given, at most 150 characters each |
| Verifier | none | Deterministic. Rejects numbers the facts do not support, a scoreline that is not the real one, players who are not part of the moment, the wrong language, lines that are too long |
| Publisher | none | Releases passed lines, swaps in a template line for any that failed twice |
| Director | none | One per channel. Chooses what is said, when, in which words; keeps silence; interrupts for goals and red cards |

Design choices that matter:

- **The verifier is not a model.** A second model grading the first would share its blind spots. The check is
  code, so it is cheap, fast and the same every time.
- **Failure feeds back.** A rejection carries its reason into the retry. After one retry the system falls back to a
  template, so model commentary never goes out unchecked and never goes missing. Template lines skip the Verifier because they
  are built only from fact-engine values; the evaluation re-checks all of them.
- **Fast path and slow path.** Templates answer a shot in milliseconds. The Analyst takes a median 6.2 s, so the
  Director decides whether its analysis still fits before the next moment and uses a shorter wording if it does not.
- **The agents are visible.** An agent log with one lane per agent (Detector, Analyst, Verifier, Publisher, Voice; a lamp
  while it works, bars for the real busy intervals) and a "why this line" box under the caption (the event row, the model
  call and its latency, a rejected number and the retry, the verifier's check), all built from the real log of the run.

## 3. Real-world impact for fans

- **Language.** The Analyst writes natively in English, German and French; the lines are not translations. A fan
  hears the game in their own language with the same facts as everyone else.
- **Level.** Beginner style explains terms in a few words and leaves out xG and percentages. Expert style takes one sharp
  analytical thought per line and may use a win probability when that is the thought. xG is out of the
  play-by-play and the share variants are gone. Same moment, different commentary.
- **Accessibility.** Captions are always on, in a live region (`aria-live="polite"`), so the commentary can be read as
  well as heard. Voice comes from the browser, so it works with no account and no key. Space pauses, `m` mutes,
  controls are real buttons, and `prefers-reduced-motion` is respected. This helps fans who are deaf or hard of hearing,
  fans listening in a second language and fans who cannot watch the screen, and it needs no special hardware.
- **Trust.** A fan can ask the MCP server whether a sentence is true. The example in [MCP.md](MCP.md): "Lemaire
  makes it 1-0" is rejected because scores are always home-away and the real score is 0-1.
- **Honest limits.** Most spoken lines are templates (the analyst wrote 9.9% of lines at x30), the verifier checks facts and
  not judgement, and German and French have not been read by native speakers. All of this is in the README.

## 4. UX and presentation

- One calm light screen (warm paper, one green accent), never scrolls: a guided run in two steps, the recorded insert around an equaliser (21 s), then a live
  match that is new every time (60 s). Language and style are two switches; the rest is Play, Go live, the caption, the two
  logs and "why this line". The only modals are the two full logs (icon button on each log).
- Switching language or style changes the caption and the voice without restarting the insert.
- The demo needs no setup: it plays a recorded run, with a static build that runs from any file host.
- Docs a judge can read without running anything: README with screenshots and a GIF, [ARCHITECTURE.md](ARCHITECTURE.md),
  [EVAL.md](EVAL.md), a two-minute video script in [VIDEO.md](VIDEO.md).

## 5. Category fit

Entered for **Best Multi-Agent System** (Microsoft Agent Framework). Against what that category looks for:

| Question | Evidence |
| --- | --- |
| Distinct roles | Analyst (model), Verifier (code), Publisher (code), Director (code, one per channel) |
| Coordination and handoffs | `WorkflowBuilder` conditional edges in `newsroom.py` (lines 155-158): passing lines go to the Publisher, failing lines go back to the Analyst; each step passes an immutable snapshot |
| Recovery from failure | `MAX_RETRIES=1`: a rejection carries its reason into one retry, then a template line takes over; covered by `test_newsroom` |
| A result one agent could not reach | Commentary that is written by a model for each fan yet cannot state a wrong score or player, in six voices at once |

The brief's pipeline maps onto the code stage by stage; the table is in the README:

| Stage | Where |
| --- | --- |
| Ingest | seeded match generator, about 2,000 events per match, plus ground truth |
| Interpret | fact engine (possession, xG, momentum, win probability) and 21 kinds of detected moments |
| Explain | templates plus the Analyst and Verifier workflow |
| Render | director, runner, overlay protocol, canvas UI |
| Personalize | 3 languages x 2 styles, six channels at once |

The data is synthetic and fictional by design, so there is nothing to license and nothing real to misuse. The
overlay protocol and the MCP server mean the same commentary can feed a broadcast graphic, an app or an AI assistant.

## Evidence

| Claim | Number | Source |
| --- | --- | --- |
| Spoken lines checked | 818 (3 matches, 6 channels, x30), 100.0% accepted | EVAL.md |
| Verifier on injected errors | scoreline swapped 100.0% of 53, number changed 100.0% of 270, player swapped 99.8% of 589 | EVAL.md |
| Truth moments found | 93.8% importance-weighted, 11 of 12 | EVAL.md |
| Analyst lines in recorded runs | 144 recorded, 0 rejected or replaced | CLAUDE.md status, `data/replays` |
| Analyst latency | median 6.2 s, p95 7.9 s, max 8.4 s | EVAL.md |
| Model calls to build everything | 23 of a budget of 40 | `data/cache/analyst` |
| Tests | 186 passed | `python -m pytest -q` |
| Real-time speech share | 16.6% of match time | EVAL.md |

## What it is not

It is not connected to real match data, it has not been checked by native German or French speakers, and the live
mode was not exercised in the browser in this build. The evaluation measures agreement with a simulator label, not
with a human editor. We list these in the README rather than hide them, because the project is about not saying
things we cannot back up.
