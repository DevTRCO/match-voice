# Submission text

Everything for the hackathon form and YouTube, one block per field. Copy the text inside each box. The character count
under each box counts the box content only (spaces and line breaks included). Every number comes from CLAUDE.md,
docs/EVAL.md, docs/DENSITY.md, docs/DEPLOY.md, the code or a file in `data/` or `ui/public/insert/`; the source is named
where the number appears. The demo video (110 s) is on YouTube: https://youtu.be/zhjO5KfLils

Checked on 2026-10-27: `python -m pytest -q` gives 899 passed, 1 xfailed (no key, about 6 minutes); the demo URL and the live server's /api/health answer 200.
The verifier figures below follow docs/EVAL.md as regenerated on 2026-10-26 at 23:54 (895 lines at x30).

## 1. Project name and tagline

Name:

```text
encara
```

Characters: 6

Tagline (max 80):

```text
Live football commentary in nine languages, checked against match data
```

Characters: 70

## 2. Elevator pitch

```text
A football broadcast speaks one language at one level, and an AI commentator that gets a scorer wrong loses the viewer. encara is a live commentary engine that clubs, leagues and streaming services plug into their apps. It turns a stream of match events into spoken commentary in nine languages, at beginner or expert level. Five agents split the work. A spotter tracks each team's habits over the half. An analyst (Claude Haiku 5.5) writes the analysis and all lines in six more languages. A verifier checks the names and numbers in every model line against the match data. A publisher releases what passes. A director per channel times each line. Analyst, verifier and publisher are one Microsoft Agent Framework workflow. Templates call the English, German and French play-by-play. On 895 lines with injected errors, the verifier caught 43 of 43 swapped scorelines, 203 of 203 changed numbers and 625 of 626 swapped players. On Azure a generated run starts talking 2.0 s after the click.
```

Characters: 990

## 3. Full description

```text
What it does

encara turns a live stream of football match events into spoken commentary. Twelve channels cover nine languages, each with a fictional commentator at beginner or expert level. English, German and French have a two-person booth at both levels; Spanish, Italian, Portuguese, Dutch, Turkish and Japanese each have a solo commentator.

Clubs, leagues and streaming services integrate through one documented stream: captions, voice timing and evidence arrive as messages over WebSocket or server-sent events (docs/PROTOCOL.md). An MCP server exposes the match data, the commentary and the verifier as 7 tools (docs/MCP.md).

The demo has three steps. Demo plays a recorded insert. In a quiet 68th minute the spotter finds a habit. Since half-time Wexmoor has won the ball 11 times in its own half, and every first pass after those wins was short. The commentator points it out. At 71' Wexmoor wins the ball, switches it about 50 m across and scores, and the commentator refers back to the earlier line. How does it work shows, line by line, what arrived, what the system understood, what was written, what the verifier checked and when it was spoken. Generate run plays a new scene of the same match, simulated and commentated live with real model calls: 1-1 in the 88th minute, a new attack each run and a late winner.

The problem

A match broadcast is made for one audience in one language. A language model can write a line for every language and level, but one wrong number or wrong scorer misleads the viewer. A live line also has to arrive within a few seconds of the event.

How it works

Ingest: the server streams synthetic events (passes, receipts, shots, tackles, pressure, possession, metadata) one by one, with no lookahead. Interpret: every pass carries its length, a difficulty rating from 0 to 1 and the ball speed; every shot its xG and speed. A fact engine keeps live statistics, momentum, win probability, a rhythm reading (controlled, balanced or chaotic) and the match so far. Explain: five agents; only the analyst calls a model, in two booths.
- Spotter (code): detects moments and keeps state over the half to find a team's habit and the goal that breaks it.
- Analyst (Claude Haiku 5.5, two booths): gets the facts of one moment, the match so far and the lines the booth said before. The core booth writes the lines for the six English, German and French channels in one call. The world booth writes the six world-language channels in a second call.
- Verifier (code): checks the numbers, scorelines, player names, the match history, claims about habits and records, language and length of every model line against the match data.
- Publisher (code): releases the lines that pass.
- Directors (code, one per channel): decide what is said and when, and drop lines that come too late.
Render: captions, voice and an animated pitch with the players' runs. Personalize: the viewer picks a language and a level, and can switch commentator mid-match; the same moment reads differently for a newcomer and an expert.

Analyst, verifier and publisher form one Microsoft Agent Framework workflow with conditional edges. A rejected line goes back to the Analyst once with the reason. If it fails again, the core languages use a template line and the world languages say nothing for that moment.

Microsoft and Azure technologies used

- Microsoft Agent Framework (Python): the newsroom workflow, its executors and edges, and the analyst in both booths.
- Azure Container Apps: the live server (WebSocket stream, model calls, voice), one replica in Central US, with per-session, per-address and daily limits on runs, model calls and voice credits. Runs need a signed session token, streams are accepted only from the demo's origin, the per-address cap ignores client-written forwarding headers, and the keys are Container Apps secrets, never in the image.
- Azure Container Registry: the server image.
- Azure Static Web Apps (Free plan): the demo page.

The model is Claude Haiku 5.5 from Anthropic, called through the Agent Framework's Anthropic connector (agent-framework-anthropic), not Azure OpenAI. The recorded demo's voices were generated ahead of time with ElevenLabs Eleven v4. A generated run is voiced as it happens with ElevenLabs Flash v2.5 for the chosen commentator; the browser's own speech voice takes over if the voice service is unavailable or over its daily budget.

What I measured

- Verifier on injected errors, three recorded matches, the six core channels, 895 spoken lines, 77 written by the model and 818 by templates (docs/EVAL.md): swapped scorelines caught 43 of 43, changed numbers 203 of 203, swapped players 625 of 626. The one miss is a German genitive. The six world languages are not in this test yet.
- World booth in the demo insert, in a paid run at match pace: 10 calls took 1.1 to 2.6 s each (median 1.3 s). World-language captions came a median 2.6 s after the event, at most 5.7 s.
- Generated run on Azure: commentary starts 2.0 s after the click, and a voice line is ready a median 0.48 s after it is requested. The picture runs 1 s behind the generator, so each player's run is known before it is drawn.
- Template captions: at most 5 ms after the event.
- Estimated cost per 90-minute match, from measured prompt and answer sizes: under one cent of model calls for the six core channels, and about $1.60 to $3.20 of ElevenLabs voice per channel. Hosting the live server costs about $15 a month (docs/DEPLOY.md); daily caps bound spend at 600 model calls and 3,000 voice credits.
- 899 automated tests pass.

Limits

All match data is synthetic and every club, player and commentator is fictional. Nobody has had the languages read by a native speaker. The engine reads match events only and has no player tracking data. In the six world languages every line is written by the model, so they speak later than English, German and French. The public server allows one generated run per browser session and caps runs, model calls and voice credits per day. Events come from the built-in match simulator. An endpoint that takes an outside event feed is not written yet; the output side (WebSocket, server-sent events, MCP) is.

The verifier checks names, numbers, scorelines, the match so far, some claims, language and length. It does not check positions on the pitch or which player played a pass first time. The injected-error test covers the core languages only.

What's next

First, native-speaker review and an input endpoint for a licensed live event feed. Then one voice stream per channel shared by all its listeners, which pays the voice once per channel instead of once per listener. After that, favourite-club and player modes and more languages; each new language needs a prompt section and word lists for the verifier.
```

Characters: 6,799

## 4. Category fit: Best Multi-Agent System

```text
Roles: five agents. The spotter tracks team habits over the half. Only the analyst calls a model, in two booths: en, de and fr at two levels, and six more languages. The verifier checks names, numbers and match history. The publisher releases what passes. Twelve directors time each channel. Analyst, verifier and publisher run as one Microsoft Agent Framework workflow.

Shared state and handoffs: every prompt carries the match so far and the booth's recent lines. The 68' habit reaches the analyst with the 71' goal, so the call-back recalls a line from three minutes earlier.

Recovery: a rejected line goes back once with the reason; only failing channels are rewritten. The recorded es, pt and ja rejections were claim_unsupported; the retry passed. A second failure, model error, timeout or spent budget gives a template or silence.

Outcome: twelve checked channels from one stream. The MCP server exposes the verifier as verify_sentence, so outside agents check lines by the same rules.
```

Characters: 995

## 5. Testing instructions

```text
1. Public demo, no setup, no key
Open https://happy-bush-012530710.5.azurestaticapps.net in a desktop browser and turn the sound on. The bar at the top has three steps; a glowing Next button leads through them.
- Demo: press Play to hear the 46-second recorded insert: the quiet 68th minute, the pattern, then the 71st-minute goal and the call-back. The row under the subtitle switches to any of the twelve commentators (nine languages, beginner or expert) at the same moment.
- How does it work: a short guided tour, then the same insert with what arrives, what the system understands, the line's way through the pipeline with real times, and what you hear.
- Generate run: the live server on Azure simulates a new scene of the same match (1-1, 88th minute) and commentates it as it happens, with real model calls and voice, in about a minute. Every language can be switched to during the run. One generated run per browser session.
If the day's runs are used up, the page says so and Demo and How does it work still work. Limits reset at midnight UTC. If the voice budget is spent, the browser's voice reads the lines.

2. Run it locally without a key (Python 3.11+, Node 20.19+)
git clone https://github.com/DevTRCO/match-voice && cd match-voice
cd ui && npm ci && npm run build:static
cd dist-static && python3 -m http.server 8080
Open http://localhost:8080. This is the demo page; Generate run calls the public server.

Backend and tests, still no key, from the repository root:
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" -c constraints.txt
python -m pytest -q
python -m matchvoice.evaluation
python -m matchvoice.pipeline play --match comeback-7 --speed 60 --channel de/expert
The tests take about 6 minutes. The evaluation rewrites docs/EVAL.md from recorded data. The last command prints German expert commentary in the terminal.

3. Your own live server, with an Anthropic API key
Put ANTHROPIC_API_KEY=... in a .env file at the repository root, build the server UI and give the server a call budget:
cd ui && npm ci && npm run build && cd ..
python -m matchvoice.server --port 8000 --live-calls 12 --world-calls 12
Every call goes through a disk cache and a hard call budget. docs/DEPLOY.md describes the Azure Container Apps setup.

All data is synthetic.
```

Characters: 2,298

## 6. Links

```text
Demo: https://happy-bush-012530710.5.azurestaticapps.net
Code: https://github.com/DevTRCO/match-voice
Video: https://youtu.be/zhjO5KfLils
```

Characters: 137

## 7. YouTube

Title (max 70):

```text
encara: one football match, live commentary in nine languages
```

Characters: 61

Description:

```text
encara is a live football commentary engine for clubs, leagues and streaming services. Built solo for the Microsoft x Premier League "Inside the Game" hackathon, category Best Multi-Agent System.

The video opens with one goal called in Japanese, German, Spanish and Turkish. In a quiet 68th minute the spotter, which runs without a model and has followed the whole half, finds a habit: since half-time Wexmoor has won the ball 11 times in its own half and played every first pass short. The commentator points it out. At 71' Wexmoor wins the ball, switches it about 50 m across and scores, and the commentator calls back to the earlier line.

Five agents split the work. A spotter tracks each team's habits. An analyst (Claude Haiku 5.5) writes the analysis and every line in six of the languages. A verifier checks the names and numbers in every model line against the match data. A publisher releases what passes. A director per channel times each line. Analyst, verifier and publisher run as one Microsoft Agent Framework workflow. Templates call the play-by-play in English, German and French.

The same moment reads differently for an expert and a newcomer. All twelve channels in nine languages come from one match stream.

Try the whole demo: https://happy-bush-012530710.5.azurestaticapps.net
Generate run on the page commentates a new scene live, on Azure Container Apps.
Code: https://github.com/DevTRCO/match-voice

All clubs, players, commentators and match data are synthetic. The video shows the recorded insert, with model lines from an earlier paid run. The page's top bar has changed since recording; the match, commentators and lines are the same.

#football #AI #MicrosoftAgentFramework
```

Characters: 1,706

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
