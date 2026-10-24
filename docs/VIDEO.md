# Demo video script

Target length 1:50, hard limit 2:00. Voice-over only: no music, no real logos or marks, no real people. Every shot
is the real app or a real file from this repository. All teams and players are fictional.

## Setup before recording

```bash
source .venv/bin/activate
python -m matchvoice.server --port 8000 --live-calls 3   # optional: a live run of the insert; without it the page plays the recorded insert
```

Chrome at 1920x1080, one clean window, bookmarks bar hidden, notifications off. Record the screen at 30 fps and the
voice-over separately in a quiet room. Open `http://localhost:8000/?mute=1` so the narration is clear; the captions carry the
commentary. Use a Chrome app or kiosk window (`--app=URL`) so no browser toolbar or logo shows. The page has one flow: the
demo insert, a 30 second window around an equaliser at 71' (comeback-135, Wexmoor Athletic trail 0-1). There is nothing else
to configure, so every shot below is the same screen.

## Shots

| # | Time | On screen | Narration |
| --- | --- | --- | --- |
| 1 | 0:00 to 0:10 | The start screen: scoreboard 0-1 at 70', the dimmed pitch, one line "Wexmoor Athletic trail 0-1. 70th minute.", the Play the moment button. Slow push-in. | Commentary is written for one imagined fan. A newcomer gets jargon. An expert gets the obvious. Another language gets almost nothing. |
| 2 | 0:10 to 0:24 | Press Play. A long ball is captioned with the Template tag and the agent line "Detector caught the event, template wording". Then the goal: the caption shouts GOAL with the scorer, the pitch flashes, the score turns 1-1. | match-voice gives every fan their own commentator. This is a fictional match, played from synthetic events. The play-by-play caller is fast: a template, on screen in milliseconds. |
| 3 | 0:24 to 0:40 | Right after the goal the caption changes to the analyst's line (tag Analyst) and the agent line reads "Analyst wrote it ..., verifier checked every number, published". Zoom on that line. | The colour analyst is an agent, Claude on the Microsoft Agent Framework. It reads the goal while play goes on. A verifier checks every number it wrote. It is plain code, not a second model. A failed line goes back once with the reason, then a template takes over. |
| 4 | 0:40 to 0:58 | Press Replay the moment, then switch DE and Beginner in the top bar. The goal and the analyst line come back in German, plain words. Zoom on the two switches. | Same moment, now in German, for a beginner. The words are written for that fan, not translated. Three languages, two styles, six voices from one pipeline. |
| 5 | 0:58 to 1:14 | Terminal, large font. Run the two commands below, one after the other. The first prints `ok: False` and the violation text about home and away, the second prints `ok: True`. | The same check is exposed to any AI client as a tool on an MCP server with seven tools. Here we call it on a sentence that reverses the score. It says no, and why. |
| 6 | 1:14 to 1:30 | `docs/EVAL.md` in a browser, the Results at x30 table, then the injected errors table. Highlight "818", "100.0%" and "99.8%". | We measured 818 spoken lines on three matches. The verifier accepts all of them and catches 99.8 to 100% of errors we injected on purpose. The weak spots are listed too: most lines are still templates. |
| 7 | 1:30 to 1:44 | `docs/img/architecture.svg` full screen, then a cut back to the UI. Zoom on the five stage headers. | The pipeline follows Ingest, Interpret, Explain, Render and Personalize. The static build plays the recorded insert from any file host and needs no key. |
| 8 | 1:44 to 1:52 | The UI after the insert (Replay the moment visible, score 1-1), then the project name and repository link as plain text on a dark card. | Every fan gets their own commentator, and every line is built from checked facts. This is match-voice. |

Shot 5 commands (they call the tool function the MCP server exposes, with the same verifier as the pipeline, no key needed):

```bash
python -c "from matchvoice.mcp_server import tools as t; r = t.verify_sentence('comeback-7', 800, 'Lemaire makes it 1-0', 'en'); print('ok:', r['ok']); print(r['violations'][0]['detail'])"
python -c "from matchvoice.mcp_server import tools as t; r = t.verify_sentence('comeback-7', 800, 'Lemaire makes it 0-1', 'en'); print('ok:', r['ok'])"
```

Real output of the first: `ok: False` and `1-0 has home and away reversed; scores are always home-away, the real scoreline is 0-1`.
Real output of the second: `ok: True`.

## Timing check

Narration is about 240 words, about 100 seconds at a calm 145 words a minute, on a 112 second timeline, which leaves roughly
12 seconds of pauses for the screen to breathe. If the cut runs long, trim shot 6 first, then shot 7.

## Do not show

- The `.env` file, a terminal with an API key in the environment, or any key.
- Any real club, player, league logo, broadcaster mark or music. No browser toolbar or logo: use the app or kiosk window.
- A live run unless the footer says "Live run". Without a key the footer says "Recorded insert"; say so, do not claim live.

## Captions and delivery

Burn in English subtitles for the narration. Keep the on-screen text to the app itself; no extra title cards except
the last one. Export as MP4, 1920x1080, under 2:00 on the timeline.
