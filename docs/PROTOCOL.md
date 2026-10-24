# Overlay protocol v1

The single contract between the pipeline and everything that shows or reads a match: the one-screen UI, the
MCP server, tests. One stream, three transports, same messages. The encoder is
`backend/matchvoice/pipeline/protocol.py`; if this document and the code disagree, fix the code or this file,
never a client.

## Transports

| Transport | URL | Use |
| --- | --- | --- |
| WebSocket | `ws://host/ws?match=<id>&mode=replay&speed=30` | primary, one JSON message per text frame |
| Server-sent events | `GET /sse?match=<id>&mode=replay&speed=30` | fallback, `event:` is the kind, `data:` the message |
| Static file | `GET /api/matches/<id>/replay.json?speed=30` | no server needed, `python -m matchvoice.pipeline export` writes the same files |

Query parameters (WebSocket and SSE):

| Name | Default | Meaning |
| --- | --- | --- |
| `match` | required | match id, from `GET /api/matches`, or any `<arc>-<seed>` (`comeback-4242`): the server simulates it on request, nothing is written, the same id is always the same match and hits the same caches |
| `mode` | `replay` | `live` is the real-time mode: events are fed at match pace and the commentary is made as they arrive (fast path templates, analyst newsroom while play continues, no lookahead, no recorded lines). It needs a key and a server call budget. By default the server reuses its answer cache (`data/cache/analyst`), so on the three demo matches the analyst lines are cached answers from earlier calls: they are marked `cached` on `say` and `ready`, and the log says so. Start the server with `--live-fresh` (or `MATCHVOICE_LIVE_FRESH=1`) and live never reads the cache, so every analyst line is a real call made during the run; `GET /api/health` reports `live.fresh`. `replay` is a recorded run: the analyst lines were written earlier and are played back tape-delayed, no key needed. The overlay UI defaults to `live` and says "Recorded run" when it falls back |
| `start` | `0` | live only (a client resuming a running stream sends the newest frame time plus 0.1, so no event repeats): match seconds to start from. Earlier events are folded into the facts and sent at once as catch-up frames with `t` below `start`, without commentary. Rejected with `bad_request` in replay mode |
| `speed` | `30` | match seconds per wall second, 0.1 to 600. 1 is real time, 60 plays the 97 minutes of a match in about 97 seconds. The UI plays the demo insert at 1. Paced by the server's monotonic clock, so a hidden browser tab does not change it |
| `analyst_from` | `start` | live only, between 0 and `start`: a restarted stream asks again for the analyst moments detected from this match second on that were still being written. Their answer comes from the call under way or the cache, so a restart makes no second call. Nothing else about the skipped stretch is said. Rejected with `bad_request` in replay mode |
| `until` | none | live only, greater than `start` and at most the match length: the stream feeds no event after this match second, lets the commentary drain (at most 20 viewer seconds), and ends. It makes a short live insert, such as the demo insert, a self-contained run. `hello.until` echoes it. Rejected with `bad_request` in replay mode. A server started with a run length cap (`--live-max-seconds`, default 75) refuses a live run whose `until - start` is larger, and a live run without `until`, with `bad_request` |
| `paced` | `true` | `false` sends everything as fast as possible (tests, tooling). Message content does not change |

Other endpoints: `GET /api/health` (`{ok, protocol, replay, live: {available, code, reason, calls_left, fresh, runs_left, runs_per_day, max_seconds}, tts: {available, reason, voice, model, credits_left, credits_max}}`; `live.available` turns
`false` with code `no_budget` once `calls_left` reaches 0, or with code `no_runs_today` once `runs_left` reaches 0, and new live runs are then refused. `runs_left`, `runs_per_day` and `max_seconds` are `null` when that cap is off or live is not configured; `code` is one of `ok`, `no_key`, `no_budget`, `no_runs_today`),
`GET /api/demo-insert` (the preset live window: `{match, arc, seed, start, until, goal_t, goal_clock}`), `GET /api/guided-live` (see "Guided live run"), `GET /api/tts` (see "Spoken lines"),
`GET /api/matches` (list with title, teams, final score, duration, `replay` flag), `GET /api/matches/<id>`
(that summary plus a `hello` message).

## Time

Every message has `t`, the **emission time** in match seconds since kick-off (half-time break excluded, so
`t` is continuous). A client plays a stream by sending each message at wall time `t / speed` after the start.
`t` never decreases from one message to the next. A WebSocket or SSE client simply renders messages as they
arrive; only a static `replay.json` player has to schedule them itself. In live mode there is nothing to schedule and
nothing to seek: the server paces the stream, the client shows the newest `t`, and a viewer cannot scrub a running match.

Live commentary uses no lookahead: a line is chosen from the moments known at that instant, so it picks longer wordings
and is cut more often than a recorded run, which hands its director every moment up front.

Live separates the caption from the voice. A line is **captioned the instant its moment arrives** (play-by-play: the event
itself, analyst lines: the moment the verified text is ready), whatever the voice is doing. Only the voice queues. It starts a
captioned line at most 3 viewer seconds after its caption (6 for the analyst's voice), otherwise the line is skipped: shown,
never spoken. Goals, red cards and the whistles at 90 or more are exempt from that limit. A template line, also one in the
analyst's voice (`shot_milestone`) or a template stand-in for a failed analyst line, that would arrive more than 4 viewer
seconds after its event is dropped without a caption (the same exemption). A recording keeps the old behaviour: a line is
shown when it is spoken.

Messages describing something earlier than their emission carry that time separately (`say.s`, `log.at`). A line is emitted within one frame (`dt`) of its start `s`.

## Messages

All messages are JSON objects with a kind in `k`. `hello` comes first, `end` or `error` last.

### `hello`

Sent once. Everything needed to decode frames, so a client hard-codes nothing but the version.

| Field | Meaning |
| --- | --- |
| `k` | `"hello"` |
| `v` | protocol version, `1` |
| `t` | `0` |
| `mode` | `replay` or `live` |
| `speed` | the speed this stream was scheduled for. A static replay must be played at this speed, because speech durations in `say` are match seconds computed from it. Fetch `replay.json?speed=N` for another one |
| `start` | match seconds the stream starts from, `0` unless a live `start` was requested |
| `dt` | length of a frame in match seconds, `max(0.5, speed / 20)` in replay, `max(0.2, speed / 20)` live |
| `duration` | match length in match seconds (time of the last event) |
| `match` | `id`, `title`, `competition`, `venue`, `arc`, `pitch` (`[105, 68]` metres), `teams` (two objects: `side` `H` or `A`, `name`, `short`, `color`, `formation`) |
| `players` | flat list, home team first. An event's `player` field indexes into it. Each: `id`, `side`, `n` (shirt number), `name`, `pos`, `grp` (`GK`, `DEF`, `MID`, `FWD`) |
| `scale` | `10`: coordinates are integer decimetres, divide by it for metres |
| `types`, `outcomes`, `setPieces` | code tables, the code is the index |
| `stats` | names of the team statistics, the index is the stat key used in `st` |
| `eventFields` | names of the positions of an event array |
| `until` | optional, live only: the match second a live insert ends at (see the `until` query parameter) |
| `run` | optional, live only: the id of this run. `GET /api/tts` finds the lines the server published in it by this id |
| `channels` | the six commentary channels: `id`, `key` (`en/expert`), `lang` (`en`, `de`, `fr`), `style` (`beginner`, `expert`). `say.ch` is the `id` |

### `f` (frame)

The high-volume message, about 20 per wall second at most. Arrays and numbers only. A frame is the state of
the match after the events it carries, so a client that drops a frame loses only those events.

| Field | Meaning |
| --- | --- |
| `t` | match time of the last event in the frame |
| `c` | display clock of that event, e.g. `"67"` or `"45+2"` |
| `p` | period, `1` or `2` |
| `s` | score `[home, away]` |
| `wp` | win probability in permille `[home, draw, away]`, sums to 1000 within rounding |
| `mo` | momentum in permille, `-1000` all away to `1000` all home |
| `e` | events since the previous frame, see below. At least one |
| `st` | optional. Stat **deltas**, `[homeChanges, awayChanges]`, each an object `{statIndex: newValue}`. Omitted when nothing changed. The first frame sends every stat. A client keeps the latest value per key |

Event array, fixed length, positions named in `hello.eventFields`:

| Pos | Field | Meaning |
| --- | --- | --- |
| 0 | `i` | event id, unique in the match, increasing |
| 1 | `type` | index into `hello.types` |
| 2 | `side` | `0` home, `1` away (the team that has the ball or commits the act) |
| 3 | `player` | index into `hello.players`, `-1` none |
| 4, 5 | `x`, `y` | position, decimetres. x runs 0 to 1050 left to right, y 0 to 680. Home attacks right in period 1 and left in period 2 |
| 6, 7 | `end_x`, `end_y` | pass or carry end, `-1` none |
| 8 | `outcome` | index into `hello.outcomes`; for a card event it is `yellow` or `red` |
| 9 | `set_piece` | index into `hello.setPieces`, `0` none |
| 10 | `xg` | expected goals of a shot times 100, `0` otherwise |

Type codes: 0 kickoff, 1 pass, 2 carry, 3 shot, 4 tackle, 5 interception, 6 pressure, 7 foul, 8 card,
9 possession_change, 10 period_end. Outcome codes: 0 none, 1 complete, 2 incomplete, 3 out, 4 goal, 5 saved,
6 blocked, 7 off_target, 8 post, 9 won, 10 free_kick, 11 half_time, 12 full_time, 13 yellow, 14 red.
Set piece codes: 0 none, 1 corner, 2 free_kick, 3 goal_kick, 4 throw_in.
Stat keys: 0 possession (%), 1 shots, 2 on_target, 3 xg, 4 passes, 5 pass_acc (%), 6 corners, 7 fouls,
8 yellow, 9 red, 10 tackles. Always read the tables from `hello`; these lists describe v1.

### `say`

One line of commentary on one channel.

| Field | Meaning |
| --- | --- |
| `t` | emission time (the clock at which the director committed the line) |
| `ch` | channel id |
| `m` | moment id. `(ch, m)` identifies the line |
| `kind` | moment kind, e.g. `shot_goal`, `corner`, `goal_analysis` |
| `voice` | `pbp` (play-by-play) or `analyst` |
| `text` | the sentence, already in the channel's language and style, checked by the verifier |
| `s`, `e` | start and end of the speech in match seconds. `e - s` is the estimated speaking time times `speed` |
| `cut` | `0`, or `1` when a more important moment interrupted the line |
| `src` | `analyst` when the model wrote this exact text, `template` otherwise (template wording, or a shorter template variant chosen because time was short) |
| `cached` | optional, `1` when the analyst line came from the answer cache (an earlier call), not from a call made in this run. Absent otherwise |
| `w` | paced live only: wall seconds since the stream started, at emission |
| `lat` | paced live only: wall seconds from the event (when it was due at the stream's pace) to this caption. Play-by-play is captioned within milliseconds, an analyst line after the model call (voice queueing is not in it, see `voice`). Absent in replay, and for an analyst moment a restarted stream picked up (the event happened in the old stream) |

**Recording (`mode=replay`).** A line is sent when it starts, with `cut: 0` and its planned `e`. If it is interrupted, a
**second `say` with the same `(ch, m)`**, `cut: 1` and `e` set to the cut time replaces it. A client stops audio at `e` on
that update, and may show the first text in a transcript either way. Lines on a channel never overlap after
the cut is applied. A line can still be speaking when `end` arrives: let it finish.

**Live.** One `say` per line, sent as the caption, `cut` always `0`. If the voice takes the line at that very instant,
`s` and `e` are its speech window as above. If the voice is busy, `s == e == t` (no speech planned yet) and a `voice`
message follows when the line starts, is cut or is skipped. `lat` is the caption latency. Voices on a channel never overlap.

### `voice`

Live only. The voice side of a line that a `say` already captioned, found by `(ch, m)`.

| Field | Meaning |
| --- | --- |
| `k` | `"voice"` |
| `t` | emission time |
| `ch`, `m` | channel and moment of the captioned line |
| `s`, `e` | speech window in match seconds. With `skip` both are the time the voice gave up |
| `cut` | optional, `1`: a more important moment interrupted the line at `e`, stop audio |
| `skip` | optional, `1`: the voice will not speak this line (it waited too long), leave it as a caption |
| `w`, `lat` | as on `say`, at the moment of this message: `lat` is event to voice start |

A start is a `voice` without `cut` and `skip`. A client that speaks should also check the age itself: not start a line more
than its limit after the caption, and not when its picture lags the stream. Clients that do not know `voice` still show
every caption.

### Spoken lines (`GET /api/tts`)

Optional, live runs only. `GET /api/tts?run=<hello.run>&ch=<say.ch>&m=<say.m>` returns `audio/mpeg` for one line the server
published in that run (the text of the `say` with that channel and moment id, in the channel's language). Nothing else can
be asked for: there is no text parameter, an unknown run, channel or moment is `404 unknown_line`, and a replay run has no
`run` at all. The client asks only when its voice actually starts a line (after the `say`/`voice` skip, stale and cut rules
above), never for skipped or dropped lines, and stops the audio when a `voice` message cuts the line or a goal or red card
cuts in. The audio element's real duration, not the planned `e`, ends the line's slot (it is sped up at most 1.25x to fit).

| Status | Body `detail.code` | Meaning, client behaviour |
| --- | --- | --- |
| 200 | | mp3. Headers `X-Voice-Cached` (`1` when served from the disk cache, no credits), `X-Voice-Credits-Left`, `X-Voice-Credits-Spent` |
| 402 | `tts_over_budget` | the credit budget cannot cover this line (checked before any request, never a partial spend). The client switches to the browser voice |
| 404 | `unknown_line` | not a line of a run this server remembers (the last 16 runs). The browser voice reads this one line |
| 502 | `tts_unavailable` | the speech service failed. The browser voice reads the line; two failures in a row switch the page to the browser voice |
| 503 | `tts_off` | no ElevenLabs key on this server. The browser voice speaks |

`GET /api/health` `tts.available` is `false` without a key or when the budget is spent; the UI then labels the voice "Browser voice".
The key is never in a response, a log line or an error message. Model `eleven_flash_v2_5` is billed at 0.5 credit per
character (constant `CREDITS_PER_CHAR`; the first real call was checked against `GET /v1/user/subscription`); each line is
synthesised once per model, voice, language and text, then served from `data/cache/tts`, with every real request in
`data/cache/tts/ledger.jsonl`.

### Guided live run (`GET /api/guided-live`)

A fresh random match and the 60 seconds of it with the most going on, for a live run that is never the same twice.

```json
{"match": "comeback-378736", "arc": "comeback", "seed": 378736, "start": 782.0, "until": 842.0,
 "window_s": 60.0, "goal_t": 790.6, "fresh": false, "runs_left": 149}
```

| Field | Meaning |
| --- | --- |
| `match` | `<arc>-<seed>`, the id the protocol already knows: same id, same match. Pass it as `match` of `/ws` or `/sse` with `mode=live&start=<start>&until=<until>` |
| `arc`, `seed` | the parts of `match`. The seed comes from the operating system's random source (1 to 999999) and the arc from `comeback`, `red_card`, `unlucky` |
| `start`, `until` | match seconds, whole numbers. `until - start` is `window_s`, at most 60, so it always passes the run length cap |
| `window_s` | `until - start` |
| `goal_t` | match time of the goal the window is built around, `null` when the match has none (then the highest-priority moment is the anchor) |
| `fresh` | the server's `--live-fresh` flag, as in `/api/health` `live.fresh`. The seed is new, so the analyst prompts are not in the answer cache either way: expect real model calls (about one per analyst moment in the window) |
| `runs_left` | live runs left today (`/api/health` `live.runs_left`), `null` when uncapped or live is off |

The window runs from 40 seconds before the goal to 14 seconds after it (about 54 seconds): the simulator is silent for about 50 seconds after a goal, so a longer tail would be a frozen pitch. Among several goals the window whose moments (the ones the live commentary would detect) have the largest summed priority is chosen, the earlier one on a tie. Picking is simulation and the fact engine only: no model call, and asking for a window does not count as a live run. The run counts when the live stream starts.

### Live limits

Two limits a client cannot raise, set by server flags; both off at 0:

| Flag (env) | Default | Rule |
| --- | --- | --- |
| `--live-max-seconds` (`MATCHVOICE_LIVE_MAX_SECONDS`) | 75 | A live run lasts at most this many match seconds, `until - start`, whatever the `speed`. A live run without `until` is refused. Refusal: `bad_request`, the message names the cap |
| `--live-runs-per-day` (`MATCHVOICE_LIVE_RUNS_PER_DAY`) | 150 | Live runs that may start per UTC day, counted on the server when the stream is accepted (after every other check, so a refused request costs no run; counting is under a lock). In memory only: **a server restart resets the count**. Refusal: `no_runs_today`, `/api/health` shows `live.available: false` and `runs_left: 0` until 00:00 UTC |

Replay is never limited. The model call budget (`--live-calls`) stays the last guard under both.

### `log`

One step of the agent pipeline, for the live log panel.

| Field | Meaning |
| --- | --- |
| `t` | emission time |
| `at` | match time the step happened, never later than `t`. Logs of the newsroom arrive when its lines are ready, so they look back in time |
| `agent` | `detector`, `analyst`, `verifier`, `publisher`, `director` or `facts` |
| `w` | paced live only: wall seconds since the stream started, the real time of the step (`at` is the same instant in match time) |
| `step` | `queued`, `writing` (live: model call started), `lookup` (live: answer found in the cache, no call), `analyst_wrote`, `verified`, `rejected`, `retry`, `fallback`, `ready`, `analyst_unavailable`, `analyst_error`, `timeout`, `cut`, `insight` |
| `m` | moment id or `null` |
| `msg` | one readable line, safe to print as is |
| `ch` | optional, set for per-channel steps (`cut`) |
| `d` | optional detail object from the agent trail, e.g. the rejected text and the verifier's reason |

The steps of a moment appear in this order: `queued` (detect), `writing` (live only, sent when the call starts) or `lookup` (live only, instead of `writing` when the answer is cached; `analyst_wrote` then has `d.cached: true` and `d.wall_s`, the time this run waited, while `d.latency_s` is the original call's),
then (once its lines are ready) `analyst_wrote`, `verified`, optionally `rejected` / `retry` / `fallback`, and `ready`
(publish). In a paced live run the steps carry their real times in `w`; in a replay `at` is mapped from the recorded
latency and there is no `w`.

**Insights** (live only, agent `facts`, step `insight`, `m` is `null`): a short true sentence about the match, from numbers the fact
engine computes at that instant. No model call, no lookahead (`at` is the event's time, a later event cannot change it), a replay has none.
`msg` is the sentence, `d.kind` says which, `d.ev` lists the event ids it follows from. At most 3 per 60 match seconds across kinds, at most
one per kind and event, and a minimum gap per kind. Kinds and their `d` (besides `kind` and `ev`):

| `d.kind` | When | Fields |
| --- | --- | --- |
| `wp_swing` | one event moves the win probability of a side by 10 points or more (rounded percent). Before minute 4 only a goal or red card is reported | `side` (`H`/`A`), `team`, `before`, `after` (percent), `delta` (`after - before`), `score` (`[home, away]` after the event) |
| `momentum` | the engine's five-minute pressure phase: one side has 75% of the attacking threat | `side`, `team`, `share` (percent), `shots`, `possession` (percent), `minutes` (5) |
| `shots` | the engine's shot milestone: a player's 3rd or 5th shot | `side`, `team`, `player`, `shots` (the player's), `team_shots`, `on_target` (team) |

```json
{"k":"log","t":4393.7,"at":4393.7,"agent":"facts","step":"insight","m":null,"w":12.702,
 "msg":"Win probability for Tamsworth Wanderers fell from 67% to 22% (-45 points)",
 "d":{"kind":"wp_swing","ev":[1483],"side":"A","team":"Tamsworth Wanderers","before":67,"after":22,"delta":-45,"score":[1,1]}}
```

### `hb`

Paced live only: `{"k": "hb", "t", "w"}`, sent after 0.25 wall seconds without any other message, so a client's match
clock keeps moving between events. Clients that do not know it ignore it.

### `end`

`{"k": "end", "t", "score": [h, a], "events": n, "says": n, "calls": n | null}`. `says` is the number of lines said (non-cut `say` messages in live, lines started in a recording). `calls` is the number of
model calls this run used (not the server total), `null` for a replay. The stream stops commentary at most 20 seconds of viewer
time after the final whistle; lines that have not started by then are not said.

### `error`

`{"k": "error", "code", "message"}`, then the connection closes. Codes: `not_found` (unknown match),
`bad_request` (missing `match`, bad `mode`, `speed` or `paced`, a live run over the length cap or without `until` when the cap is set), `no_key` (live mode without an API key), `no_budget` (live mode
without a call budget, or with the budget spent; the server starts with `--live-calls N`), `no_runs_today` (the daily cap of live runs is used up, see "Live limits"). WebSocket close codes: 4004, 4000, 4001 (also for `no_runs_today`).
Over SSE the same problems are HTTP 404, 400, 429 (`no_runs_today`) and 409 (the rest) with `{"detail": {"code", "message"}}`.

## Static replay file

`replay.json` is `{"v": 1, "speed": 30, "hello": {...}, "messages": [...]}`. `messages` are exactly what the
WebSocket would send after `hello`, in order, each with its emission time `t` (a test asserts equality).
About 280 KB, 54 KB gzipped, per match at speed 30. A player does:

```js
const start = performance.now();
for (const msg of replay.messages) {
  await sleepUntil(start + (msg.t / replay.speed) * 1000);
  handle(msg);
}
```

To seek to match time T, fold all messages with `t <= T`: take score, win probability and momentum from the
last frame, accumulate `st` deltas, and replay `say` messages by `(ch, m)` so a later cut wins.

## Sample

Abridged from a real `comeback-7` replay at speed 30, in emission order. Home is Tamsworth United, away is Marlow Bay United.

```json
{"k":"hello","v":1,"t":0.0,"mode":"replay","speed":30,"dt":1.5,"duration":5822.0,
 "match":{"id":"comeback-7","title":"Late comeback after an early away goal","competition":"Synthetic League",
  "venue":"Tamsworth United Ground","arc":"comeback","pitch":[105.0,68.0],
  "teams":[{"side":"H","name":"Tamsworth United","short":"TU","color":"#0ea5e9","formation":"4-2-3-1"},
           {"side":"A","name":"Marlow Bay United","short":"MBU","color":"#e11d48","formation":"4-3-3"}]},
 "players":[{"id":"H1","side":"H","n":1,"name":"Bastian Soriano","pos":"GK","grp":"GK"}, "..."],
 "scale":10,"types":["kickoff","pass","carry","shot","tackle","interception","pressure","foul","card","possession_change","period_end"],
 "outcomes":["","complete","incomplete","out","goal","saved","blocked","off_target","post","won","free_kick","half_time","full_time","yellow","red"],
 "setPieces":["","corner","free_kick","goal_kick","throw_in"],
 "stats":["possession","shots","on_target","xg","passes","pass_acc","corners","fouls","yellow","red","tackles"],
 "eventFields":["i","type","side","player","x","y","end_x","end_y","outcome","set_piece","xg"],
 "channels":[{"id":0,"key":"en/beginner","lang":"en","style":"beginner"},{"id":1,"key":"en/expert","lang":"en","style":"expert"}, "..."]}

{"k":"say","t":772.0,"ch":0,"m":21,"kind":"shot_off","voice":"pbp","text":"Kowalczyk shoots, and misses.","s":772.0,"e":839.0,"cut":0,"src":"template"}

{"k":"f","t":790.6,"c":"14","p":1,"s":[0,1],"wp":[48,113,839],"mo":-569,
 "e":[[288,3,1,20,250,460,0,323,4,0,25]],"st":[{},{"1":4,"2":2,"3":0.42}]}

{"k":"say","t":790.6,"ch":0,"m":21,"kind":"shot_off","voice":"pbp","text":"Kowalczyk shoots, and misses.","s":772.0,"e":790.6,"cut":1,"src":"template"}
{"k":"say","t":790.6,"ch":0,"m":32,"kind":"shot_goal","voice":"pbp","text":"GOAL for Marlow Bay United! Lemaire scores, and it's 0-1.","s":790.6,"e":913.6,"cut":0,"src":"template"}
{"k":"log","t":790.6,"at":790.6,"agent":"detector","step":"queued","m":33,"msg":"Moment 33 (goal_analysis, 14') queued for the analyst"}

{"k":"log","t":965.4,"at":964.88,"agent":"analyst","step":"analyst_wrote","m":33,"msg":"Analyst wrote 6 lines (model call, 5.81s)","d":{"attempt":0,"lines":6,"cached":false,"latency_s":5.81}}
{"k":"log","t":965.4,"at":964.88,"agent":"verifier","step":"verified","m":33,"msg":"Verifier accepted 6 lines, 0 failing","d":{"attempt":0,"accepted":6,"failing":0}}
{"k":"log","t":965.4,"at":964.88,"agent":"publisher","step":"ready","m":33,"msg":"Moment 33 ready: 6 of 6 lines by the analyst"}

{"k":"end","t":5987.0,"score":[2,1],"events":2031,"says":323,"calls":null}
```

The goal frame decodes as: event 288, a shot (type 3) by the away side, player index 20 (Lemaire), from
(25.0 m, 46.0 m) to (0.0 m, 32.3 m), outcome `goal`, xG 0.25. The score is 0-1, always home-away.
The recorded runs had no rejections. For the format only, a rejection would look like this (illustrative, not from
the recording):

```json
{"k":"log","t":965.4,"at":962.1,"agent":"verifier","step":"rejected","m":33,"msg":"Verifier rejected en/expert: score_swapped: ...","d":{"attempt":0,"key":"en/expert","text":"... 1-0 ...","why":"score_swapped: ..."}}
```

## Compatibility

`start`, `w`, `lat`, the `writing` step, the `facts` agent with the `insight` step, `GET /api/guided-live`, the `no_runs_today` code, the `live.runs_left` health fields, `hb`, `analyst_from`, the live `voice` message, `until`, `hello.run`, `hello.until`, `<arc>-<seed>` match ids and `/api/tts` were added to v1 this way.

Additive changes (new optional fields, new `log.step` values, new code table entries at the end) keep `v: 1`.
Clients ignore unknown fields and unknown message kinds. Anything else bumps `v`.
