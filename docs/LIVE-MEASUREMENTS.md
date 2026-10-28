# Live measurements

Each number below has a date, a method and the place in the repo where it is recorded. Some were measured on earlier
builds of this code; the date and the source entry say which. Numbers that are not in the repo are not here.

Short version: a generated run on Azure starts 2.0 s after the click. A voice line is ready a median 0.48 s after the
page asks for it. Template captions leave the server within 5 ms of the event. A model call takes 1.1 to 2.6 s.

## Generated run on Azure

| What | Result | Date | Method | Source |
| --- | --- | --- | --- | --- |
| Click to commentary | 2.0 s (session, scene, socket, 1 s buffer) | 2026-10-27 | One real English run against the deployed server (image `20261027-1603`, revision `encara-live--0000005`), real model and voice. Final score 2-1, no errors | CLAUDE.md, entry "Live picture 1 s behind instead of 3" |
| Voice line ready after request (`/api/tts`) | median about 0.48 s, 19 of 21 under 1 s, max 1.06 s | 2026-10-27 | Same run, 21 ElevenLabs Flash lines | same entry |
| Click to commentary on the local dev server | 1.1 s | 2026-10-27 | `docs/live/devserver.py` with fake model and voice, en at 1430x769 and ja at 390x844 | same entry |

One run is one sample. The start time and the voice median are not a distribution over many viewers.

## Model calls

| What | Result | Date | Method | Source |
| --- | --- | --- | --- | --- |
| World booth call (six world languages in one call) | 1.1 to 2.6 s, median 1.3 s, 10 calls | 2026-10-26 | Paid run of the demo insert, paced at match speed, real Haiku calls | CLAUDE.md, entry "German and French set-up and pay-off fix, and six world channels"; README Evidence table |
| World-language caption after the event | median 2.6 s, max 5.7 s; 1.2 to 4.4 s behind the English booth | 2026-10-26 | Same run | same entry; docs/SUBMISSION.md |
| Core analyst call (en, de, fr, both levels, one call) | 2.14 s, all six lines accepted first time | 2026-10-25 | One fresh prompt (red_card-11 goal, moment 114, cache off, private cache dir) after model thinking was switched off. Before the switch the same kind of call took 16.4 s | CLAUDE.md, entry "Analyst latency fix" |

The core analyst figure is a single measurement. Treat it as an order of magnitude, not a median.

## Captions and voice timing

| What | Result | Date | Method | Source |
| --- | --- | --- | --- | --- |
| Template caption after the event | max 0.005 s (5 ms) | 2026-10-20 | Fake model at 5 s, comeback-7 from kick-off to 50', speed x10, six channels, WebSocket client | CLAUDE.md, entry "Phase 8 done" |
| All captions after the event | median 0.002 s, p90 0.003 s, max 5.06 s (before the change: median 1.44 s, max 15.16 s) | 2026-10-20 | Same measurement. The max is an analyst line: 5.007 s model call, 0.043 s newsroom | same entry |
| Voice behind its caption | play-by-play max 3.02 s (limit 3 s), analyst max 3.91 s (limit 6 s); 588 captions, 335 spoken, 253 skipped | 2026-10-20 | Same measurement | same entry |
| Score line after a goal in a generated scene | +10.6 s before, +4.1 s after (co line 0.7 s later) | 2026-10-27, night | Fake model at 4 s latency, against commit `82a4004`. The score line now goes out with the goal and the co line waits behind it | CLAUDE.md, entry "Live timing fix" |

## The pitch picture

| What | Result | Date | Method | Source |
| --- | --- | --- | --- | --- |
| Receivers more than 2 m off the ball at arrival, picture 1 s behind | 26 of 115 without run cues (16 m worst), 4 with run cues (the same as at 3 s behind) | 2026-10-27 | Live-arrival emulator, 8 seeds, 115 passes, board rebuilt every 0.25 s from what the server had sent | CLAUDE.md, entry "Live picture 1 s behind instead of 3" |
| Player positions off the full-knowledge board by more than 1 m | 0.1% of player frames, opening second only | 2026-10-27 | Same emulator | same entry |
| Receivers offside at the kick | 43 before, 0 after; other attackers 214 to 0; goal moves offside 39 of 80 to 0 | 2026-10-27, evening | 40 seeds of the generated scene; runs in behind kept (32), recorded run byte-identical | CLAUDE.md, entry "Booth memory, offside, live voice energy" |
| Frame time in the browser | median 16.7 ms, max 16.8 ms, no frame over 20 ms | 2026-10-21 | `requestAnimationFrame` timing through a recorded and a live run | CLAUDE.md, entry "Guided run UI done" |

## Public limits

The public server caps spend. These are the values in code and on the Azure deployment.

| Limit | Value | Source |
| --- | --- | --- |
| Live runs per browser session | 1 on Azure (code default 3) | docs/DEPLOY.md (`MATCHVOICE_SESSION_RUNS`); `backend/matchvoice/server/public.py` |
| Live runs per client address per UTC day | 10 | docs/DEPLOY.md; `server/public.py` |
| Live runs at once | 3 | docs/DEPLOY.md; `server/public.py` |
| Live runs per UTC day, all visitors | 150 | docs/DEPLOY.md (`MATCHVOICE_LIVE_RUNS_PER_DAY`) |
| Longest live run | 75 match seconds | docs/DEPLOY.md (`MATCHVOICE_LIVE_MAX_SECONDS`) |
| Model calls per UTC day, core and world booth | 600 | docs/DEPLOY.md (`MATCHVOICE_DAILY_CALLS`) |
| ElevenLabs credits per UTC day | 3,000 | docs/DEPLOY.md (`MATCHVOICE_TTS_DAILY_CREDITS`) |
| ElevenLabs credits per session / per address per day | 900 / 1,500 | docs/DEPLOY.md; `server/public.py` |
| Voiced channels per run | 2 (the one watched plus one switch) | docs/DEPLOY.md; `server/public.py` |

All counts live in memory on one replica and reset at midnight UTC or on a restart.

## What these numbers do not show

- The Azure figures come from one run. We have not load-tested the server with many viewers.
- The template and caption timings use a fake model with a fixed delay. They measure our pipeline, not the model.
- The world booth numbers come from the paid run that wrote the demo insert. The shipped insert replays those answers
  from cache.
- Nobody but the author has timed the public demo.
