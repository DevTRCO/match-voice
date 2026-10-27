# encara

encara is a real-time football commentary engine that clubs, leagues and streaming services can plug into their own
apps. Commentary is usually produced in a few languages and at one level, because each extra booth needs its own
commentators. encara turns a stream of match events into spoken commentary in nine languages, for beginners or experts.
Before any line the model wrote goes out, a checker compares every name and number in it with the match data.

[![The encara demo](docs/img/demo.jpg)](https://happy-bush-012530710.5.azurestaticapps.net)

- Demo (no key, no sign-in): https://happy-bush-012530710.5.azurestaticapps.net. Generate run on the same page
  commentates a new scene live on Azure Container Apps.
- Demo video (under 2 minutes): https://www.youtube.com/watch?v=4TRUr6I2D6E. The video was recorded before the page got
  its three steps at the top. The match, the commentators and the lines are the same.
- Built for the Microsoft x Premier League "Inside the Game: Developer Hackathon", category Best Multi-Agent System.
  Solo entry by Vu Minh Tran.

All names and match data are fictional ([details](#fictional-names-and-synthetic-data)).

## Try the demo

About one minute, no key, no install.

1. Open the demo link.
2. Choose a commentator by language and level.
3. Press play. The 46-second clip opens in a quiet 68th minute.
4. Watch for the "Pattern spotted" card when the co-commentator names Wexmoor's habit, then for the switch and the
   equaliser at 71', when the co-commentator refers back to it.
5. Pick another commentator and hear the same moment in another language.
6. Click "How does it work". The same run replays with the raw feed, what the spotter found and each line's path from
   data to voice.
7. Click "Generate run" for a new scene of the same match, commentated live on Azure. One generated run per browser
   session, and a small number a day; when they are used up the page says so.

Demo and How does it work replay a recorded live run of the pipeline; Generate run is live (see
[Limitations](#limitations)).

## What it does

encara is built to sit behind someone else's app. A club, a league or a streaming service sends match events in and
gets commentary lines back per channel over WebSocket or SSE ([docs/PROTOCOL.md](docs/PROTOCOL.md)) or through an MCP
server. Each line carries its speaker, its timing and the event ids behind it, so an editor can audit any line. In this
build the events come from a built-in match simulator. An endpoint for an outside event feed is not written yet, and it
is the missing piece for production.

Today it runs twelve channels in nine languages. English, German and French run at two levels, beginner and expert,
each with a lead commentator and a co-commentator. Spanish, Italian, Portuguese, Dutch, Turkish and Japanese run at one
level each with a solo commentator. Adding a language means a prompt section and word lists for the checker. The voice
layer is ElevenLabs, whose Eleven v4 models cover more than 90 languages.

The demo centres on a moment that templates cannot cover, a pattern found in a quiet spell and called back when a goal
breaks it. Wexmoor Athletic trail 0-1 and the game has gone quiet in the 68th minute. The spotter has noticed that
Wexmoor won the ball 11 times in their own half since half-time, played every first pass short and never switched play.
The co-commentator says so: "Ibsen keeps winning it, and every time it's short. Nothing across." At 71' Ibsen wins the
ball, the first pass is a 49.5 m switch to the other flank, and Fontaine equalises. The co-commentator calls back to the
line from the 68th minute: "There it is. Ibsen wins it, and this time it goes across, long and lofted." Both lines were
written by the model and passed the verifier before they were spoken.

## How it works

encara uses five agents with separate jobs. Three of them run as one Microsoft Agent Framework workflow (`WorkflowBuilder`
with conditional edges in [`newsroom.py`](backend/matchvoice/commentary/newsroom.py)).

```
Spotter -> Analyst -> Verifier -> (one retry with the reason) -> Publisher -> one Director per channel
```

| Agent | Runs as | Job |
| --- | --- | --- |
| Spotter | plain code, [`moments.py`](backend/matchvoice/commentary/moments.py), [`patterns.py`](backend/matchvoice/commentary/patterns.py) | Finds moments worth a line from events and live facts. Detects a team habit in a quiet spell and the goal that breaks it. Sees only events up to now, no lookahead (tested). |
| Analyst | Agent Framework executor, Claude Haiku 5.5 via `agent-framework-anthropic` | Writes the lines for one moment, one per channel, from the facts of that moment and the last lines each channel said. Two booths share this executor. The core booth (English, German, French) writes analysis only. The world booth (Spanish, Italian, Portuguese, Dutch, Turkish, Japanese) writes every line for all six channels in one call per moment. |
| Verifier | Agent Framework executor, plain code | Checks every model line for invented numbers, wrong scorelines, players who are not part of the moment, unsupported tactical or trait claims, wrong language and length. Rejects with a reason. |
| Publisher | Agent Framework executor, plain code | Releases lines that pass. A rejected line goes back to the Analyst once with the reason. If it fails again, English, German and French fall back to a template line; the six world languages say nothing. |
| Director | plain code, one per channel, [`director.py`](backend/matchvoice/commentary/director.py) | Decides what is said, when and in which wording. Keeps quiet spells for stories, lets goals interrupt, drops a line that arrives too late. |

Only the Analyst calls a model, in two booths: one for English, German and French, one for six more languages. The other
agents are plain code on purpose, so that facts, timing and release decisions are deterministic and can be tested.

The agents share state. When the Spotter flags a habit, the Analyst writes the set-up line and the booth stores what
each channel said. At the goal, the Spotter checks whether the goal broke the habit and gives the Analyst the pay-off
facts together with the stored set-up lines, so the callback refers to what was actually said. The Verifier returns a
reason code such as `claim_unsupported` or `player_unsupported`, and the Analyst gets that reason on its retry.

### How the agents share state

| State | Written by | Read by | Code |
| --- | --- | --- | --- |
| Match so far: score, every goal with minute and scorer, red cards | Fact engine | Analyst (in every live prompt), Verifier (match history) | `FactEngine.so_far`, [`engine.py:188`](backend/matchvoice/facts/engine.py#L188); added to the prompt at [`runner.py:712`](backend/matchvoice/pipeline/runner.py#L712) |
| Set-up lines: the habit and what each channel said about it | Spotter, then the channels' captions | Analyst at the goal that breaks the habit | `booth['setups']`, [`runner.py:698`](backend/matchvoice/pipeline/runner.py#L698) (written) and [`runner.py:751`](backend/matchvoice/pipeline/runner.py#L751) (read) |
| Habits fired, so a habit is pointed out once per side and half | Spotter | Spotter | `booth['fired']`, [`runner.py:392`](backend/matchvoice/pipeline/runner.py#L392) |
| Recent lines: the last lines each channel showed or spoke | Directors | Analyst | `WriteRequest.recent`, [`newsroom.py:39`](backend/matchvoice/commentary/newsroom.py#L39); filled at [`runner.py:888`](backend/matchvoice/pipeline/runner.py#L888) |
| Rejection reasons per channel | Verifier | Analyst on its retry | `WriteRequest.feedback`, [`newsroom.py:36`](backend/matchvoice/commentary/newsroom.py#L36) |

This is how a line at 71 minutes can refer back to what the booth said at 68 minutes.

### When something fails

| Failure | What happens | Code | Test |
| --- | --- | --- | --- |
| The verifier rejects a line | One retry of the failing channels only, with the reason | [`newsroom.py:148`](backend/matchvoice/commentary/newsroom.py#L148), retry edge [`newsroom.py:205`](backend/matchvoice/commentary/newsroom.py#L205) | `test_newsroom.py:36` |
| The retry fails too | A template line (English, German, French) or silence (the six world languages) | [`newsroom.py:182`](backend/matchvoice/commentary/newsroom.py#L182) | `test_newsroom.py:52` |
| Model error, empty answer or call budget used up | Straight to the fallback with no retry; the failed prompt's cache entry is discarded | [`newsroom.py:99`](backend/matchvoice/commentary/newsroom.py#L99) | `test_newsroom.py:62`, `test_newsroom.py:69`, `test_empty_answer.py` |
| A moment's job times out (90 s) | Template lines for that moment; the stream keeps running | [`runner.py:902`](backend/matchvoice/pipeline/runner.py#L902) | none |
| A line arrives too late | Its director drops it | [`director.py:122`](backend/matchvoice/commentary/director.py#L122) | `test_live_captions.py:87`, `test_live_captions.py:143` |
| The voice service fails | The page reads the line with the browser voice | [`mock4.html:952`](ui/public/mock4.html#L952) | none |

Play-by-play in English, German and French comes from templates filled with fact-engine values, so it is on screen in
milliseconds.

The rules ask for five stages. They map to the code like this:

- Ingest: the match simulator (`sim/`).
- Interpret: the fact engine and the spotter (`facts/`, `moments.py`, `patterns.py`).
- Explain: the newsroom and the templates.
- Render: the director, the runner and the overlay protocol.
- Personalize: the twelve channels.

Details, data flow and the wire format are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[docs/PROTOCOL.md](docs/PROTOCOL.md).

## Evidence

The evaluation numbers come from the generated reports. They cover English, German and French on three synthetic
matches; the six world languages are not in the evaluation yet.

| Check | Result | Source |
| --- | --- | --- |
| Spoken lines the verifier accepts | 895 of 895 (3 matches, 6 channels, replay at x30) | [EVAL.md](docs/EVAL.md) |
| Injected errors caught | scoreline swapped 100.0% of 43, number changed 100.0% of 203, player swapped 99.8% of 626 | [EVAL.md](docs/EVAL.md) |
| Scripted key moments found | 11 of 12 (93.8% importance-weighted) | [EVAL.md](docs/EVAL.md) |
| Time from a moment being queued to its analyst lines being released, evaluation recordings (made before the model's thinking was switched off) | median 6.2 s, p95 7.9 s | [EVAL.md](docs/EVAL.md) |
| Share of spoken lines written by the model (core languages) | 8.6% at x30, the rest are templates | [EVAL.md](docs/EVAL.md) |
| Commentary density over 3 full matches | 17.2 segments a minute, 70% speech coverage | [DENSITY.md](docs/DENSITY.md) |
| Model call in the paid run that wrote the demo's answers, six world languages in one call | 1.1 to 2.6 s (median 1.3 s); captions 1.2 to 4.4 s behind the English booth | CLAUDE.md (project notes) |
| Rejections in the recording | The story line overstated Wexmoor's record in Spanish ("ha ganado"), Portuguese ("virou") and Japanese ("逆転勝ち"). The record counts points after being behind, and wins are only part of that. The verifier rejected all three with that reason, and the one retry passed (a real call when it was recorded, a cache hit in the file). | `ui/public/insert/story.json`, verifier log steps |

## Microsoft and Azure technologies

| Technology | Where it is used |
| --- | --- |
| Microsoft Agent Framework (`agent-framework-core`) | The newsroom workflow: Analyst, Verifier and Publisher executors, a conditional retry edge and a publish edge ([`newsroom.py`](backend/matchvoice/commentary/newsroom.py)). |
| Azure Static Web Apps (Free plan) | Hosts the public demo, deployed 2026-10-26 ([docs/DEPLOY.md](docs/DEPLOY.md)). |
| Azure Container Apps | The live server behind Generate run: WebSocket stream, model calls and voice, one replica in Central US, keys as Container Apps secrets, per-session, per-address and daily limits ([docs/DEPLOY.md](docs/DEPLOY.md)). |
| Azure Container Registry | The server image. |
| MCP server | Seven tools over stdio, including the newsroom's own verifier ([docs/MCP.md](docs/MCP.md)). |

The model is Claude by Anthropic, connected through the Agent Framework's Anthropic package. Azure OpenAI is not used.

## Limitations

- **All data is synthetic.** The truth file that scores key moments comes from the same simulator, and nothing here has
  run on real match data.
- **Demo and How does it work replay a recording.** The pipeline ran at match speed with model answers from an earlier
  paid run, so model latency is not in that timing. Generate run is live: the server on Azure simulates a new scene and
  makes real model and voice calls, within a small daily budget.
- **No language has been checked by a native speaker.** Some lines are known to be weak, for example the Spanish wording
  for a switch of play. Some build-up lines in the recording state a wrong detail that the verifier did not catch.
  Italian, Dutch and Japanese put Tavares on the left, and Turkish and Japanese say the first-time pass went to Tavares,
  when Tavares played it to Fontaine.
- **The verifier checks names and numbers only.** "They dominate" passes if its numbers are right. It does not check
  whose number a count is ("Ibsen keeps winning it, eleven times" would pass; 11 is the team's count, Ibsen has 5). It
  missed a swapped player in a German genitive in the evaluation.
- **Most core-language lines are templates** (see Evidence). That keeps play-by-play instant, and it limits variety.
- **No tracking data.** Events only, so the pitch shows the ball and the player on it. Moments that need positions of all
  22 players (line breaks, runs in behind) have wordings and never fire.
- **Voices.** The demo uses ElevenLabs voices (premade and Voice Library), and nobody has compared them with native
  speech. Speaking times for the six world languages are estimates.
- **Density gates that fail** are listed in [docs/DENSITY.md](docs/DENSITY.md); the main one is that too many segments
  name a player.

## Quick start

Requirements: Python 3.11 or newer, Node 20.19 or newer.

### Static demo, no key, no Python

Plays the 46-second recording with its pre-generated ElevenLabs audio, the same files as the public demo.

```bash
cd ui && npm ci && npm run build:static        # writes ui/dist-static
cd dist-static && python3 -m http.server 8080  # open http://localhost:8080
```

### Local server in replay mode, no key

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" -c constraints.txt   # constraints.txt pins the versions the tests ran on
(cd ui && npm ci && npm run build)             # the server serves ui/dist
MATCHVOICE_NO_DOTENV=1 python -m matchvoice.server --port 8000
```

`MATCHVOICE_NO_DOTENV=1` ignores any `.env`, which shows that replay needs no key. The story demo is at
http://localhost:8000/mock4.html (the public demo serves the same page as its start page), the guided run at
http://localhost:8000, and `/api/health` reports why live mode is off.

### Live run, with a key and a call budget

Put `ANTHROPIC_API_KEY=...` in a git-ignored `.env` at the repository root. Live mode refuses to start without a key or
without a positive call budget.

```bash
python -m matchvoice.server --port 8000 --live-calls 12                    # English, German, French
python -m matchvoice.server --port 8000 --live-calls 12 --world-calls 12   # plus the six world languages, own budget
python -m matchvoice.server --port 8000 --live-calls 12 --live-fresh       # never read the answer cache
```

Every model call goes through a disk cache (`data/cache/analyst`) and a hard call budget. Cached answers are reused and
marked as cached; `--live-fresh` makes every analyst line a real call. A live run is capped at 75 match seconds
(`--live-max-seconds`) and 150 runs per UTC day (`--live-runs-per-day`). In the guided run page, "Go live" starts a new
random match.

Live runs on the server use the core layers: templates, the Analyst, the Verifier and the Publisher. The habit detector
and the dense play-by-play run when the story insert is recorded (`python -m matchvoice.pipeline export-story-insert`)
and in fast live runs. With `--world-calls` the six world languages are in the WebSocket and SSE
stream. The demo page shows all nine languages; the older local guided page in `ui/src` shows English, German and French
only.

The live run in the local guided page speaks with the browser voice. The server also has an ElevenLabs endpoint
(`/api/tts`, `eleven_flash_v2_5`, all nine languages) for lines a live run published. It needs `ELEVENLABS_API_KEY` and has
its own credit cap (`--tts-credits`, default 300). The demo page's Generate run voices the chosen channel through it with
Flash v2.5 and falls back to the browser voice.

### Tests

```bash
python -m pytest -q        # 899 passed, 1 xfailed on 2026-10-27, no key, about 6 minutes
```

### MCP server

Seven tools over stdio: list matches, match summary, key moments, commentary at a time, win probability, player stats,
and `verify_sentence`, which runs the pipeline's own verifier on any sentence. They cover English, German and French. No
key needed. Setup for Claude Desktop and Claude Code is in [docs/MCP.md](docs/MCP.md).

```bash
python -m matchvoice.mcp_server
```

### Evaluation

```bash
python -m matchvoice.evaluation           # rewrites data/eval/results.json and docs/EVAL.md, no key, no calls
python -m matchvoice.evaluation.density   # rewrites data/eval/density.json and docs/DENSITY.md, no key, no calls
python -m matchvoice.pipeline export-story-insert   # re-records the story insert from the answer cache, 0 calls by default
docker build -t encara . && docker run --rm -p 8000:8000 encara   # replay server in a container, no secrets in the image
```

## Repository layout

```
backend/matchvoice/
  sim/            match simulator, player profiles, tactics, event enrichment, club and player stories
  facts/          fact engine: live stats, momentum, win probability
  commentary/     spotter, templates, analyst, world booth, verifier, newsroom workflow, director
  pipeline/       one runner for live and replay, overlay protocol, exports
  server/         FastAPI: WebSocket, SSE, replay files, the built UI
  tts/            optional ElevenLabs voice with a credit ledger
  mcp_server/     MCP server, 7 tools
  evaluation/     evaluation and density reports
backend/tests/    pytest suite
ui/               Vite, React and TypeScript; ui/public/mock4.html is the demo page (the public demo serves it as the
                  start page), ui/public/insert the recording
data/             generated matches, recorded analyst lines, answer cache
docs/             architecture, protocol, evaluation, deploy, MCP, pitch, video script
```

`CLAUDE.md` holds the project notes: decisions, measurements and what is not verified.

## Credits and licences

- **Code:** MIT, see [LICENSE](LICENSE).
- **Language model:** Claude Haiku 5.5 by Anthropic, through the Microsoft Agent Framework.
- **Libraries:** Microsoft Agent Framework (`agent-framework-core`, `agent-framework-anthropic`), FastAPI, React and Vite;
  on the demo page driver.js 1.3.1 and flag-icons 7.2.3 (both MIT, loaded from jsDelivr).
- **Voices:** ElevenLabs, Eleven v4 for the recorded demo and Flash v2.5 for live runs, with the voices Charlie, Liam,
  Marcus, Leo, George, Will, Daniel, Anna, Bill, Sarah, Matilda, Eric, Lily, Brian and Jessica. The audio in `ui/public/insert/story-audio` was generated with them.
- **Crowd sound:** `ui/public/audio` (`stadium-bed.mp3`, `stadium-roar.mp3`) is a community recording from Freesound,
  low-passed and looped.
- **Commentator faces:** `ui/public/faces` were generated with OpenAI gpt-image-2.5 and show people who do not exist.
- **Fonts:** Schibsted Grotesk, Barlow Condensed and JetBrains Mono, all under the SIL Open Font License 1.1.

## Fictional names and synthetic data

Every club, player, commentator and match in this repository is invented and generated by this project, including
Wexmoor Athletic, Tamsworth Wanderers and the Synthetic League. Any resemblance to real people or clubs is coincidental.
No real match data, logos, broadcaster marks or music are used. The project is not affiliated with or endorsed by the
Premier League or any club.
