# Submission text

Everything for the hackathon form and YouTube, one block per field. Copy the text inside each box. The character count
under each box counts the box content only (spaces and line breaks included). Every number comes from CLAUDE.md,
docs/EVAL.md, docs/DENSITY.md, docs/DEPLOY.md, the code or a file in `data/` or `ui/public/insert/`; the source is named
where the number appears. Replace `VIDEO_URL` once the video is on YouTube.

Checked on 2026-10-26: `python -m pytest -q` gives 770 passed, 1 xfailed (no key, about 5 minutes); the demo URL answers 200.
The verifier figures below follow docs/EVAL.md as regenerated on 2026-10-26 at 23:54 (895 lines at x30).

## 1. Project name and tagline

Name:

```text
encara
```

Characters: 6

Tagline (max 80):

```text
Real-time football commentary in nine languages, checked against match data
```

Characters: 75

## 2. Elevator pitch

```text
A football match broadcast is usually made for one audience in one language. encara is a real-time commentary engine that clubs, leagues and streaming services can plug into their own apps. From a live stream of match events it writes and speaks commentary in nine languages, at beginner or expert level. Agents on the Microsoft Agent Framework split the work: a spotter tracks each team's habits over the half, Claude writes the analysis and every line in six of the languages, templates call the play-by-play in English, German and French, and plain code checks the names and numbers in every model line against the match data before it is spoken. The public demo runs on Azure Static Web Apps.
```

Characters: 696

## 3. Full description

```text
What it does

encara turns a live stream of football match events into spoken commentary. Nine languages run today on twelve channels, each with a fictional commentator at beginner or expert level. English, German and French have a two-person booth at both levels; Spanish, Italian, Portuguese, Dutch, Turkish and Japanese each have a solo commentator.

Clubs, leagues and streaming services plug it in through one documented stream: captions, voice timing and evidence arrive as messages over WebSocket or server-sent events (docs/PROTOCOL.md), and an MCP server exposes the match data, the commentary and the verifier as 7 tools (docs/MCP.md). The demo page plays a recording of that stream.

In the demo the spotter finds a habit during a quiet 68th minute. Since half-time Wexmoor has won the ball 11 times in its own half, and every first pass after those wins was short; none went across the pitch. The commentator points it out. At 71' Wexmoor wins the ball, switches it about 50 m across and scores, and the commentator refers back to the earlier line.

The problem

A match broadcast is usually made for one audience in one language. A language model can write a commentary line for each language and level. A line with a wrong number or the wrong scorer misleads viewers, and a live line has to arrive within a few seconds of the event.

How it works

The work is split into five roles. Two call a model; the other three are plain code, so facts and timing do not depend on a model.
- Spotter (code): reads every event in order with no lookahead, detects moments and keeps state over the half to find a team's habit and the goal that breaks it.
- Analyst and world booth (two Claude Haiku 5.5 agents): get the facts of one moment and the lines the booth said before it. One call writes the lines for the six core channels, a second call the lines for the six world-language channels.
- Verifier (code): checks the numbers, scorelines, player names, claims about habits and records, language and length of every model line against the match data.
- Publisher (code): releases the lines that pass.
- Directors (code, one per channel): decide what is said and when, and drop lines that come too late.

Play-by-play in English, German and French comes from a bank of fixed template lines, and the analyst adds the analysis. In the six world languages the world booth writes every line.

Analyst, Verifier and Publisher form a Microsoft Agent Framework workflow with conditional edges. A rejected line goes back to the Analyst once with the reason. If it fails again, the core languages use a template line and the world languages say nothing for that moment.

Microsoft and Azure technologies used

- Microsoft Agent Framework (Python): the newsroom workflow, its executors and edges, and both model agents.
- Azure Static Web Apps (Free plan): hosts the public demo.
- A Dockerfile for the live server, built and run locally, and a documented Azure Container Apps setup that has not been deployed.

The model is Claude Haiku 5.5 from Anthropic, called through the Agent Framework's Anthropic connector (agent-framework-anthropic), not Azure OpenAI. The demo's voices were generated ahead of time with ElevenLabs Eleven v4. In live mode the page uses the browser's own speech voice; the server's optional ElevenLabs voice covers English, German and French.

What I measured

- Verifier on injected errors, three recorded matches, the six core channels, 895 lines (docs/EVAL.md): swapped scorelines caught 43 of 43, changed numbers 203 of 203, swapped players 625 of 626. The one miss is a German genitive. The six world languages are not in this test yet.
- World booth in the demo insert, in a paid run at match pace: 10 calls took 1.1 to 2.6 s each (median 1.3 s). World-language captions came a median 2.6 s after the event, at most 5.7 s, and 1.2 to 4.4 s behind the English booth.
- Core analyst: one fresh call wrote all six core lines in 2.1 s (a single measurement).
- Template captions: 2 to 3 ms after the event for goals in an earlier live test, and at most 5 ms for every template line in a run with a stand-in model on 2026-10-20.
- Estimated cost per 90-minute match, from measured prompt and answer sizes (no token counts were logged): under one cent of model calls for the six core channels, and about $1.60 to $3.20 of ElevenLabs voice per channel.
- 770 automated tests pass.

Limits

All match data is synthetic and every club, player and commentator is fictional. The public demo is a recording made at match pace from cached model answers. The answers come from real calls in an earlier run, and the page makes no model calls. Nobody has had the languages read by a native speaker. The engine reads match events only and has no player tracking data.

The verifier checks names, numbers, scorelines, some claims, language and length. It does not check positions on the pitch, who a number belongs to, or which player played a pass first time. Three world-language lines in the demo say Tavares was on the left, and two say the first-time pass went to him; the verifier let them through. The injected-error test covers the core languages only.

The live page offers English, German and French. The six world channels run on the server in live mode but are not shown there yet, and a full match with all six has not been run.

What's next

Native-speaker review, a licensed live data feed, the live server on Azure Container Apps, one voice stream per channel shared by all its listeners, and more languages. Each new language needs a prompt section and word lists for the verifier. The voice model, ElevenLabs Eleven v4, supports more than 90 languages.
```

Characters: 5,678

## 4. Category fit: Best Multi-Agent System

```text
A prompt that sees one moment at a time cannot connect a quiet 68th minute to a goal at 71'. The spotter keeps state over the whole half and finds the habit at 68'. When the goal at 71' breaks it, the spotter says so, and the runner hands the analyst the line the booth said at 68', so the call-back refers to a line the viewer heard about three minutes earlier. The analyst writes, a deterministic verifier checks the names and numbers in each model line against the match data, and the Agent Framework workflow routes a rejected line back once with the reason before a template or silence takes over. The check is plain code, so it does not depend on the model that wrote the line. One analyst call writes the lines for six channels, a second call those for six more languages, and twelve directors each decide timing for their own channel: one waits for a goal call to finish, another drops a line that arrived too late. Two roles call a model and three are plain code, each tested on its own.
```

Characters: 996

## 5. Testing instructions

```text
1. Public demo, no setup, no key
Open https://happy-bush-012530710.5.azurestaticapps.net in a desktop browser and turn the sound on. Press Play to hear the 46-second insert: the quiet 68th minute, the pattern, then the 71st-minute goal and the call-back. Use "Choose your commentator" to switch to another of the twelve channels (nine languages, beginner or expert), and "Hear the same goal with another commentator" at the end. "How does it work?" shows what arrives, what the system understands and what you hear, in sync with the match. The page plays a recording of the pipeline running at match pace. The model's lines in it were written by real calls in an earlier run and read from the answer cache while it was recorded, so they appear sooner than a live call would. The page makes no model calls.

2. Run it locally without a key (Python 3.11+, Node 20+)
git clone https://github.com/DevTRCO/match-voice && cd match-voice
cd ui && npm ci && npm run build:static
cd dist-static && python3 -m http.server 8080
Open http://localhost:8080. This is the same page as the public demo.

Backend and tests, still no key, from the repository root:
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
python -m matchvoice.evaluation
python -m matchvoice.pipeline play --match comeback-7 --speed 60 --channel de/expert
The tests take about 5 minutes. The evaluation rewrites docs/EVAL.md from recorded data. The last command prints German expert commentary in the terminal.

3. Live, with an Anthropic API key
Put ANTHROPIC_API_KEY=... in a .env file at the repository root, build the server UI and give the server a call budget:
cd ui && npm ci && npm run build && cd ..
python -m matchvoice.server --port 8000 --live-calls 12
Open http://localhost:8000 and choose Go live. The server simulates a new match and plays about a minute around a goal while the analyst writes. This page offers English, German and French. --world-calls N also runs the six world channels on the server; the live page does not show them yet. Every call goes through a disk cache and a hard call budget.

All data is synthetic.
```

Characters: 2,144

## 6. Links

```text
Demo: https://happy-bush-012530710.5.azurestaticapps.net
Code: https://github.com/DevTRCO/match-voice
Video: VIDEO_URL
```

Characters: 118

## 7. YouTube

Title (max 70):

```text
encara: real-time football commentary in nine languages, fact-checked
```

Characters: 69

Description:

```text
encara is a real-time football commentary engine, built solo for the Microsoft x Premier League "Inside the Game" hackathon (Best Multi-Agent System).

In a quiet 68th minute the spotter, plain code that has followed the whole half, finds a habit in one team's play, and the commentator points it out. At 71' the team wins the ball, switches it about 50 m across and scores, and the commentator refers back to the earlier line.

The work runs on the Microsoft Agent Framework. Claude writes the analysis and every line in six of the languages, play-by-play in English, German and French comes from templates, plain code checks the names and numbers in every model line against the match data, and a director per channel times each line. It runs twelve channels in nine languages, each at beginner or expert level.

Try the demo: https://happy-bush-012530710.5.azurestaticapps.net
Code: https://github.com/DevTRCO/match-voice

All clubs, players, commentators and match data are synthetic. The demo is a recording at match pace, with model lines from an earlier paid run.

#football #AI #MicrosoftAgentFramework
```

Characters: 1,110

## 8. Cost per match


This is an estimate. The API does not report token counts back to the project and none were logged, so tokens are
estimated from measured prompt and answer sizes. Prices checked 2026-10-26: Claude Haiku 5.5 at $0.10 per million input
tokens and $0.50 per million output tokens (Anthropic price list); ElevenLabs API text to speech at $0.08 per 1,000
characters for multilingual models such as Eleven v4 and $0.04 for Flash (elevenlabs.io/pricing/api). All figures in USD.

What was measured (0 model calls, 0 credits):

| Input | Value | Source |
| --- | --- | --- |
| Model moments per match | 8, 9 and 7 on the three demo matches | prompts rebuilt offline from `precompute.MODEL_KINDS`; DEPLOY.md says about 8 |
| Core system prompt | 16,431 characters | `len(analyst.SYSTEM)`, prompt v8 |
| Core user prompt | median about 3,600 characters, max 4,508 | `build_prompt` over all 24 moments |
| Core answer | median 796 characters, max 1,015 | the 70 cached answers in `data/cache/analyst` |
| World system prompt | 8,007 characters | `len(world.WORLD_SYSTEM)` |
| World user prompt | median about 1,100 characters before continuity lines | `build_world_prompt` |
| World calls in the demo insert | 10, plus 1 retry | CLAUDE.md |
| Voice per spoken line | 42.3 credits on Eleven v4 (5,075 credits for 120 lines, 1 credit per character) | `ui/public/insert/story-audio/manifest.json` |
| Voice per spoken line, Flash v2.5 | 31 credits (251 credits, 495 characters, 8 lines; 0.5 credit per character) | `data/cache/tts/ledger.jsonl` |
| Spoken words per minute, full match, dense layers on | 79.7 (English channels, median) | DENSITY.md |
| Characters per word | 5.65 (English lines of the insert) | the same manifest |

Assumptions: 3.5 characters per token for prompts (mostly English), 3 per token for answers (six languages); output
rounded up to 350 tokens (core) and 400 (world); one retry per match; a 90-minute match; no prompt caching (the code
does not use it).

If the real token counts are about 30% higher than these ratios give (Haiku 5.5 may use a newer tokenizer), the core
analysis comes to about $0.009 per match, still under one cent.

| Item | Arithmetic | Per match |
| --- | --- | --- |
| Core analyst call | (16,431 + 4,508) / 3.5 = about 6,000 input tokens x $0.10/M = $0.00060, plus 350 output x $0.50/M = $0.00018 | $0.0008 per call |
| Core analysis, six channels | 9 calls (8 moments + 1 retry) x $0.0008 | about $0.007 |
| World call | (8,007 + about 2,000) / 3.5 = about 3,000 input tokens = $0.00030, plus 400 output = $0.00020 | $0.0005 per call |
| World lines, demo insert (46 s) | 11 calls x $0.0005 | about $0.006 |
| Voice, one channel, Eleven v4 | 79.7 words x 5.65 characters x 90 min = about 40,500 characters x $0.08 per 1,000 | about $3.24 |
| Voice, one channel, Flash v2.5 | 40,500 characters x $0.04 per 1,000 | about $1.62 |
| Hosting of the demo | Azure Static Web Apps, Free plan | $0 |

The model costs under one cent per match for the six core channels. The voice is most of the cost, about $1.60 to
$3.20 per channel and match. If one channel is streamed to all of its listeners, the voice is paid once per channel and
not per listener. The current demo server makes a separate run for each visitor, so that saving is a deployment choice
still to be built.

Not backed yet, left open on purpose:

- TODO: world channels over a full match. The world booth makes one call per moment the English booth captions, and no
  full match has been run with it. If that is close to the 17.2 segments a minute of a dense full match (DENSITY.md),
  it would be about 1,550 calls and roughly $0.80 per match, but that is extrapolated and has not been measured.
- TODO: real token counts. Log `usage` from each call (or run `count_tokens`) and replace the 3.5 and 3 characters per
  token assumptions.
- TODO: euro figures and a per-viewer price. Both depend on the exchange rate and the ElevenLabs plan used.
