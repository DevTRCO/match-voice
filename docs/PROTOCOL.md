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
| `fast` | `0` | live only, `1`: run like the recorded story insert: the dense voice (fast and context layers, `touch`, `pass_kind`, the stories), the pattern detector on (`say.ins`, the `pattern` and `payoff` steps), the booth's memory per run, and the `row` messages. Additive (2026-10-27) |
| `world` | server default | live only, `1`: this run gets the world channels 6 to 11 (one world call per moment the English booth calls); `0`: it does not, so a viewer of a core channel never pays for them. Absent: the server's default (on when it was started with `--world-calls N`), except on a public server, where absent means `0`. `1` on a server without a world booth, or with its calls used, is refused with `no_world`. Additive (2026-10-27) |
| `rows` | `0` | live only, `1`: the `row` messages without the dense voice (`fast=1` implies it). Additive (2026-10-27) |
| `token` | none | the session token from `GET /api/session`. Required for a live run on a public server, ignored elsewhere. Additive (2026-10-27) |
| `seed` | none | live only, a whole number 0 to 999999: the play of a generated scene (see "Public live server"). Only on a server that is not public and only with a generated scene's exact `match`, `start`, `until`; otherwise `bad_request`. Additive (2026-10-27) |

Other endpoints: `GET /api/health` (`{ok, protocol, replay, live: {available, code, reason, calls_left, fresh, runs_left, runs_per_day, max_seconds}, tts: {available, reason, voice, model, credits_left, credits_max}}`; `live.available` turns
`false` with code `no_budget` once `calls_left` reaches 0, or with code `no_runs_today` once `runs_left` reaches 0, and new live runs are then refused.
Additive (2026-10-27): `live.code` may also be `no_calls_today` (the daily model call cap) or `no_session_secret` (a public server without a session secret), `live.calls_left` is the smaller of the lifetime budget and today's calls, and two more objects follow,
`today: {runs_left, calls_left, calls_per_day, voice_credits_left, voice_credits_per_day, world, world_calls_left}` (what a page needs to offer a live run; `world` says whether `world=1` can be asked for; `null` where a cap is off) and
`public: {on, sessions, session_runs, ip_runs, concurrent, active, busy, scenes}`; `tts` gains `credits_per_day` and `credits_today_left` when the voice has a daily cap. `runs_left`, `runs_per_day` and `max_seconds` are `null` when that cap is off or live is not configured; `code` is one of `ok`, `no_key`, `no_budget`, `no_runs_today`),
`GET /api/demo-insert` (the preset live window: `{match, arc, seed, start, until, goal_t, goal_clock}`), `GET /api/guided-live` (see "Guided live run"), `GET /api/tts` (see "Spoken lines"),
`GET /api/session` and `GET /api/scene` (see "Public live server"),
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
| `scene_seed` | optional, live only: the seed of a generated scene's play (see "Public live server"). Additive (2026-10-27) |
| `channels` | the six commentary channels: `id`, `key` (`en/expert`), `lang` (`en`, `de`, `fr`), `style` (`beginner`, `expert`). `say.ch` is the `id`. Additive (2026-10-26): `level` (same value as `style`), `solo` (true for a one-person booth), `lead` and, in a two-person booth, `co`, each `{name, gender}` (`man` or `woman`). A run with the world booth lists twelve channels: ids 6 to 11 are appended after 0 to 5, so no existing id moves (see "World channels" below) |

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
| `kind` | moment kind, e.g. `shot_goal`, `corner`, `goal_analysis`, `score_line` (the lead after the co-commentator's goal line: the score in its spoken form and the time left; moment id 900000 plus the goal analysis id), `pattern_insight` (the co-commentator points out a habit of one side in a quiet spell; live runs with the dense voice only; moment id 800000 + 4 x (half - 1) + 0 for home, 1 for away) |
| `voice` | `pbp` (the channel's lead: play-by-play, the dossier story notes, the score line after a goal) or `analyst` (its co-commentator: the model's lines and the other context notes) |
| `who` | optional, additive (older clients ignore it): the person in the channel's booth who says the line, the lead for `voice: pbp` and the co-commentator for `voice: analyst`. Booths: en/beginner Owen Carter and Daniel Price, en/expert Charlie Hale and Daniel Price, de/beginner Felix Brandt and Kim Berger, de/expert Jonas Weber and Kim Berger, fr/beginner Théo Laurent and Sacha Morel, fr/expert Hugo Martin and Sacha Morel (`commentary/lang.py` `BOOTH`). Fictional names. The world channels are solo booths: `who` is the lead for every line, analysis included (es/expert Lucía Romero, it/beginner Giulia Conti, pt/expert Rafael Souza, nl/beginner Sanne de Vries, tr/expert Emre Aydın, ja/beginner Yuki Tanaka) |
| `text` | the sentence, already in the channel's language and style, checked by the verifier |
| `s`, `e` | start and end of the speech in match seconds. `e - s` is the estimated speaking time times `speed` |
| `cut` | `0`, or `1` when a more important moment interrupted the line |
| `src` | `analyst` when the model wrote this exact text, `template` otherwise (template wording, or a shorter template variant chosen because time was short) |
| `ins` | optional, additive (older clients ignore it): set on a `pattern_insight` line and on the goal analysis line that pays a pattern off, the same object on every channel. What the overlay may highlight, in absolute pitch metres (x 0 to 105, y 0 to 68, as the events). See **Insight evidence** below |
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

Optional, live runs only. `GET /api/tts?run=<hello.run>&ch=<say.ch>&m=<say.m>[&token=<session>]` returns `audio/mpeg` for one line the server
published in that run (the text of the `say` with that channel and moment id, in the channel's language), in the voice of the person who
says it (`say.who`: each of the 15 commentators of the nine languages has their own ElevenLabs voice, `tts/voices.py` `CAST`, the cast of
the recorded insert; model `eleven_flash_v2_5`). On a public server `token` must be the session that started the run (its signature is
checked, not its day, so a run that crosses midnight UTC keeps its voice), and a run voices at most two channels (the one watched plus
one switch; the first lines asked for fix them). Nothing else can
be asked for: there is no text parameter, an unknown run, channel or moment is `404 unknown_line`, and a replay run has no
`run` at all. The client asks only when its voice actually starts a line (after the `say`/`voice` skip, stale and cut rules
above), never for skipped or dropped lines, and stops the audio when a `voice` message cuts the line or a goal or red card
cuts in. The audio element's real duration, not the planned `e`, ends the line's slot (it is sped up at most 1.25x to fit).

| Status | Body `detail.code` | Meaning, client behaviour |
| --- | --- | --- |
| 200 | | mp3. Headers `X-Voice-Cached` (`1` when served from the disk cache, no credits), `X-Voice-Credits-Left`, `X-Voice-Credits-Spent`, `X-Voice-Name` (the ElevenLabs voice, for the "which voice" label) |
| 401 | `session_required` | public server: no valid session token. Browser voice |
| 402 | `tts_over_budget` | the credit budget cannot cover this line (checked before any request, never a partial spend). The client switches to the browser voice |
| 402 | `tts_daily_limit` | today's credits (UTC day) are used. Browser voice until midnight UTC |
| 402 | `tts_session_limit` | public server: this session's credits are used. Browser voice for the rest of the session |
| 402 | `tts_ip_limit` | public server: this address's credits of today (UTC) are used. Browser voice until midnight UTC |
| 404 | `unknown_line` | not a line of a run this server remembers (the last 16 runs), or a run of another session. The browser voice reads this one line |
| 409 | `no_voice` | no voice exists for this line's language or speaker. The browser voice reads it (never a 500) |
| 409 | `tts_channel_limit` | public server: this run already voices its two channels. The browser voice reads lines of any other channel |
| 502 | `tts_unavailable` | the speech service failed. The browser voice reads the line; two failures in a row switch the page to the browser voice |
| 503 | `tts_off` | no ElevenLabs key on this server. The browser voice speaks |

Every answer above except 200 and 404 carries `detail.fallback: "browser"` and the header `X-Voice-Fallback: browser` (exposed to
cross-origin pages): a page that sees it speaks the line with the browser voice and labels the voice "Browser voice".

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

**Insight evidence (`say.ins`).** No lookahead: every field is computed from events before the line (`commentary/patterns.py`).

| `ins.kind` | Fields |
| --- | --- |
| `pattern` | `habit` (`short_after_win`: the side keeps winning the ball in its own half and every first pass after it goes short, no open-play ball 30 m or more across in the half), `side` (`H`/`A`), `team`, `half`, `zone` (`[x0, y0, x1, y1]`, the side's own half), `dots` (`[x, y]` of each ball win counted), `arrows` (`[x0, y0, x1, y1]` of the first pass after each win), `players` (player ids: the one who keeps winning it, when one does), `wins`, `short`, `across` (0), `widest_m` (the widest first pass sideways), `winner_wins` (optional), `ev` (event ids: the wins, then their first passes) |
| `payoff` | `habit`, `side`, `half`, `arrow` (`[x0, y0, x1, y1]`, the first pass after the ball win that broke the habit), `zone` (the third of the pitch's width where it landed, full length), `players` (the ball winner and the receiver), `ev` (the win and the pass), `of` (moment id of the set-up), `setup_t` and `setup_clock` (when the set-up was detected) |

A goal analysis carries `payoff` only when this broadcast said the set-up for the scoring side and half (a client can find it by `of`) and the
goal's possession began with a ball win in its own half whose first pass went across. The story insert is one broadcast in two parts: a set-up
in part 1 is paid off in part 2.

```json
{"k":"say","t":4234.8,"ch":1,"m":800004,"kind":"pattern_insight","voice":"analyst","text":"Ibsen keeps winning it, and the first pass is always short. Nothing across.",
 "s":4234.8,"e":4241.1,"cut":0,"src":"analyst","who":"Daniel Price","cached":1,"w":1.8,"lat":0.302,
 "ins":{"kind":"pattern","habit":"short_after_win","side":"H","team":"Wexmoor Athletic","half":2,"zone":[52.5,0.0,105.0,68.0],"dots":[[103.0,39.6],"..."],
        "arrows":[[103.0,39.6,81.8,36.4],"..."],"players":["H3"],"wins":11,"short":11,"across":0,"widest_m":24.9,"ev":[956,"..."],"winner_wins":5}}
```

### `row` (enriched rows)

Additive (2026-10-27), live runs with `fast=1` or `rows=1` only; clients that do not know it ignore it. The enriched rows of the match
(`sim/micro/enrich.py`, the shape of `ui/public/insert/micro.json` `rows`: `eid, i, k, t, type, team` and per type `target, pass_type, height,
body_part, technique, first_time, t_arr, ball_speed, pass_eid, player, x, y, touch, facing, pressure, assist_eid, placement, ...`; coordinates
in metres, not decimetres) are sent **when the stream reaches each row's time `t`**, never earlier: a pass row at its kick (it names the
target and the planned arrival `t_arr`, as the file does), the receipt at the arrival, a shot at the strike.

```json
{"k":"row","t":5465.2,"rows":[{"eid":29760,"i":1860,"k":0,"t":5465.2,"type":"pass","team":"H","target":"H8","pass_type":"short",
 "height":"ground","body_part":"right_foot","technique":"straight","pressure":{"under":false},"first_time":false,"t_arr":5467.152,"ball_speed":44.8}],"w":34.203}
```

| Field | Meaning |
| --- | --- |
| `t` | emission time; every row in it has `row.t <= t`. Rows of one instant come right after that instant's frame |
| `w` | paced live only: wall seconds since the stream started |
| `rows` | the rows that became known since the last `row` message, ordered by `t`, then `eid`. Each row is sent once. A run sends none after `until` |

### `run` (run cues for the board)

Additive (2026-10-27), sent whenever `row` messages are (rows on); clients that do not know it ignore it. One cue per pass row that
names a target, sent `RUN_LEAD_S` (2.5 match seconds) before the kick: the moment the receiver may set off. It lets the page run its
picture 1 s behind the generator (was 3 s) and still start a receiver's run before the ball is played. A cue is off-ball movement only:
who runs (`player`), from whose pass (`by`, `pass_type`, whether the passer is pressed, `under`), to which spot (`x, y`, the receipt's,
else the pass end) and when the ball is due (`t`, `t_arr`), plus the kick spot (`sx, sy`). It has no outcome, the booth never reads it
(a run with rows off says the same lines at the same times, `tests/test_run_cues.py`), and the page draws nothing from it but motion:
the ball, the labels and lane 1 wait for the pass row.

```json
{"k":"run","t":5418.0,"rows":[{"eid":29424,"t":5420.3,"t_arr":5422.069,"player":"A8","by":"A3","pass_type":"short","under":true,
 "x":38.0,"y":53.8,"sx":16.4,"sy":48.0}]}
```

Catch-up with rows on: before `start` the stream sends only the frames of the last 15 match seconds (the newest one always; its stat
deltas cover everything folded, so the state at `start` is the same as with the full catch-up) and one `row` message with the rows of
those 15 seconds. Without rows the catch-up is unchanged: for the winner scene (start 5415) that is 1,363 frames, about 196 KB, sent
at once; folded it is 1 frame, about 0.3 KB (the 15 s before 5415 hold only the ball going out and the goal kick being set up, which
make no rows). The folded catch-up has no shot before `start`, so a page that reads the attack
direction from shots takes it from `GET /api/scene` `attack` instead.

### Public live server

Additive (2026-10-27). A server started with `MATCHVOICE_PUBLIC=1` (docs/DEPLOY.md) runs live only for its whitelisted scenes, at speed 1,
paced, for a browser session, under these caps (all counted in memory and reset by a restart; the daily ones roll over at 00:00 UTC):

| Cap | Default (env) | Refusal |
| --- | --- | --- |
| scene whitelist: `match`, `start`, `until` exactly as `GET /api/scene` gives them; `speed=1`, paced, no `analyst_from`, no `seed` | | `bad_request` |
| a valid session token (`token=`) | | `session_required` (`no_session_secret` when the server has no secret) |
| live runs per session | 3 by default, 1 on the Azure demo (`MATCHVOICE_SESSION_RUNS`) | `session_limit` |
| live runs per client address per UTC day (behind the proxy: the rightmost `X-Forwarded-For` entry, the one the ingress appends, `MATCHVOICE_TRUSTED_HOPS=1`; a client-written entry is never counted) | 10 (`MATCHVOICE_IP_RUNS`) | `ip_limit` |
| live runs at once | 3 (`MATCHVOICE_LIVE_CONCURRENT`) | `busy` |
| live runs per UTC day, all visitors | 150 (`MATCHVOICE_LIVE_RUNS_PER_DAY`) | `no_runs_today` |
| model calls per UTC day, core and world (also on a server that is not public) | 600 (`MATCHVOICE_DAILY_CALLS`) | `no_calls_today`; a call during a run past the cap falls back like a spent budget |
| voice credits per UTC day, per session, per client address per UTC day | 3,000 (`MATCHVOICE_TTS_DAILY_CREDITS`), 900 (`MATCHVOICE_SESSION_CREDITS`), 1,500 (`MATCHVOICE_IP_CREDITS`) | `/api/tts` 402 with the browser fallback; the demo page starts a run in the browser voice when `/api/scene` shows fewer than 250 credits left on any of the three, so a cap does not strike in the middle of a run |
| voiced channels per live run | 2 (`MATCHVOICE_RUN_VOICE_CHANNELS`) | `/api/tts` 409 `tts_channel_limit` with the browser fallback |

A refused request costs nothing: every check runs before a run is counted. Replay is never limited. With `MATCHVOICE_ALLOWED_ORIGINS`
set, a WebSocket from another origin (or without an `Origin` header) is refused before it is accepted: the handshake answers HTTP 403,
which a browser sees as a failed connection (`onerror`, close code 1006, no `error` message; never 4003). An `/sse` request from another
origin is HTTP 403 `origin_refused`, and CORS answers only those origins. The server's own origin (a page it serves itself, whose `Origin`
host equals the request's `Host`) is always allowed.

`GET /api/session[?token=<token>]`: a valid token comes back unchanged with what is left, anything else gets a new session.
`{token, id, day, enforced, session_runs_left, session_runs, ip_runs_left, session_credits_left, ip_credits_left, busy}`
(`ip_credits_left` additive 2026-10-27, null where the cap is off). The token is
`<id>.<UTC day>.<signature>`, valid on its day and the next; the page keeps it in `sessionStorage`. A server that is not public answers
`token: null, enforced: false` and needs none. A public server without a secret answers 503 `no_session_secret`.

`GET /api/scene[?id=winner][&token=<token>]`: the scene a "New run" starts, from the simulation (no model call):

```json
{"id":"winner","match":"comeback-135","start":5415.0,"until":5490.0,"clock":"88","score":[1,1],"goal_t":null,"goal_window":[5462.0,5471.5],
 "title":"The winner, 89 minutes","attack":{"H":0.0,"A":105.0},"session":true,"session_runs_left":3,"session_runs":3,"ip_runs_left":10,
 "session_credits_left":900.0,"ip_credits_left":1500.0,"busy":false,"today":{"runs_left":150,"calls_left":600,"calls_per_day":600,"voice_credits_left":3000.0,"voice_credits_per_day":3000.0,
 "world":true,"world_calls_left":600},"fresh":true}
```

`attack` (additive 2026-10-27): the x of the goal each side attacks during the scene (fixed per half; the home side attacks x = 105 in the
first half, x = 0 in the second). A page draws the board from it instead of inferring the direction from shots, because the folded
catch-up (rows on) carries no shot before `start`.

The page starts it with `/ws?match=<match>&mode=live&speed=1&start=<start>&until=<until>&fast=1&token=<token>` (plus `world=1` for a
viewer of channels 6 to 11).

The winner scene is generated per run (additive 2026-10-27, `backend/matchvoice/sim/scene.py`). Everything up to Tamsworth's goal kick at
5408.6 (score 1-1, clock 88) is the plain match. From the goal kick (taken 7 to 9 s later, inside the window) the server plays a new
phase: Tamsworth build up from the back while Wexmoor press, Wexmoor win the ball (an interception in midfield, or a pressed ball back cut
out near Tamsworth's box), then attack under Tamsworth's pressure and score the 2-1 inside `goal_window` (89'). How the goal comes
(through ball, switch and cross, cutback, a one-two at the edge, a full back's cross) and who scores (Wexmoor's attackers and central
midfielders; Gabriel Tavares about 30 percent of the time) change with the run's seed, so `goal_t` is `null` before a run and `goal_window`
says where the goal will land. The seed is drawn by the server for every run (`secrets`) and announced in `hello.scene_seed` (additive) and
in one log (`agent: facts`, `step: scene`, `msg` "Play generated for this run, seed N", `d.seed`). The seed identifies the play: the log
line says nothing about it, but anyone with the source code can rebuild the whole scene from the seed (`Library.scene_bundle`), goal
included, so the seed is an id for checks, not a secret. The variation is
simulated when the run starts, as a full match always was; rows and events are still released only when the stream reaches them, with
no lookahead the server would not have. In a generated scene the booth calls only the play from Wexmoor's ball win to the goal (no story,
table or stats line), a carry counts as play from its first stride, and the ball that makes the chance (cross, cutback, through ball)
is called ahead of a touch or a press. One wording choice there uses what the simulation already holds: a short pass that is cut out about a
second later is not called "plays it on" (the interception's call has the moment); nothing is sent before its time. The goal call, the co-commentator's analysis and the lead's score line fall inside the window
(at least 18.5 s after the latest possible goal), checked with the fake model over several seeds.

`seed=<0..999999>` fixes the play of a generated scene, for tests and local checks: only on a server that is NOT public, and only with
the exact `match`, `start` and `until` of a generated scene; anywhere else, or a value that is not a whole number up to six digits, is
`bad_request`. The same seed gives the same events and rows. A public server answers any `seed` with `bad_request`. Every other live
window of the same match (any other `start` or `until`) plays the plain match and has no `scene_seed`.

### `log`

One step of the agent pipeline, for the live log panel.

| Field | Meaning |
| --- | --- |
| `t` | emission time |
| `at` | match time the step happened, never later than `t`. Logs of the newsroom arrive when its lines are ready, so they look back in time |
| `agent` | `detector`, `analyst`, `verifier`, `publisher`, `director` or `facts` |
| `w` | paced live only: wall seconds since the stream started, the real time of the step (`at` is the same instant in match time) |
| `step` | `queued`, `writing` (live: model call started), `lookup` (live: answer found in the cache, no call), `analyst_wrote`, `verified`, `rejected`, `retry`, `fallback`, `ready`, `analyst_unavailable`, `analyst_error`, `timeout`, `cut`, `insight`, `pattern` (agent `detector`: a habit found in a quiet spell, `m` is the `pattern_insight` moment, `d` is its `say.ins`), `payoff` (agent `detector`: a goal broke a habit the broadcast pointed out, `m` is the goal analysis, `d` is its `say.ins`), `too_late` (agent `director`, `d.world: true`, additive 2026-10-27: a served live run's world booth skips a moment whose line would be too old to say by the time a call returns, so no call is made for it; the waiting moment with the highest priority is written first, a goal before older fragments) |
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

Additive codes (2026-10-27, see "Public live server"):

| Code | WebSocket close | SSE HTTP | Meaning, page behaviour |
| --- | --- | --- | --- |
| `no_calls_today` | 4029 | 429 | today's model calls are used: say so, offer the recorded run |
| `session_limit` | 4029 | 429 | this session's live runs are used |
| `ip_limit` | 4029 | 429 | this address's live runs of today are used |
| `busy` | 4029 | 503 | the concurrent runs are taken: try again shortly |
| `session_required` | 4003 | 401 | no valid session token: fetch `/api/session` and retry once |
| `no_session_secret` | 4001 | 409 | the server issues no sessions: recorded run only |
| `no_world` | 4001 | 409 | `world=1` is not available: start without it (core channels) |
| `origin_refused` | (handshake HTTP 403) | 403 | the page's origin is not allowed (`MATCHVOICE_ALLOWED_ORIGINS`): play the recorded run |

A WebSocket refused for its `Origin` is refused at the handshake (HTTP 403) with no `error` message. A browser does not see 4003 there:
it gets `onerror` and close code 1006, the same as a server that is offline. A page treats a close before `hello` with no `error` message
as "not allowed or offline" and falls back to the recorded run; it must not read 4003 as `session_required` in that case (only an `error`
message with `code` says which it is).

### World channels (ids 6 to 11)

Additive (2026-10-26). Six more channels, one level each, approved by the user: 6 `es/expert`, 7 `it/beginner`, 8 `pt/expert`,
9 `nl/beginner`, 10 `tr/expert`, 11 `ja/beginner`. Only a live run whose server has the world booth lists them
(`python -m matchvoice.server --world-calls N`, off by default; `export-story-insert` records them), so replays and every
recording made before keep their six channels.

- Every line of a world channel comes from the model, play-by-play included: the core channels speak templates at once, the world
  channels have none. For each moment the English booth (channels 0 and 1) captions, one call of the world booth (a second Agent Framework
  agent, `commentary/world.py`) writes the line of all six world channels. The calls run one after another. A recorded export (world_skip_late
  off) calls the moments in the order the English booth called them. A served live run (every server started with `python -m
  matchvoice.server`) calls the waiting moment with the highest priority first and skips, with a `too_late` log step and no call, any moment
  whose line would be too old to say by the time the call returns. World viewers of a served run therefore get mainly the goals, the
  analysis, the score lines and some context notes; most play-by-play before a goal is skipped. Every line passes the same verifier as the core analysis (numbers, scores, players, claims, traits, counts, language,
  length, punctuation).
- `say` on a world channel: `src` is `analyst` for every line (the model wrote it, whatever its `voice`), `cached` as usual, `who` the lead.
  `kind` and `voice` are the moment's (`pbp` for play-by-play). A line that fails the verifier twice is not said: there is no template.
- Scores are written 1-1 (es, it, pt, nl, tr) and 1対1 (ja); the goal call opens with the language's shout ("¡GOOOL!", "GOOOL!",
  "GOAL!" or "Doelpunt!", "ゴール！"). Japanese writes player names in katakana; the verifier maps them to the roster (consonant skeleton).
- `log` steps of the world booth carry `d.world: true`: `lookup` or `writing` (one per moment, "World booth looks up moment 163 for es, it,
  pt, nl, tr, ja"), then `analyst_wrote`, `rejected`, `retry`, `verified` and `ready` ("Moment 163 ready on the world channels: 6 of 6 lines
  by the analyst"). New step `dropped` (agent `publisher`, `d.keys`): the world lines that failed and are not said.
- Latency (measured on the recorded export, which keeps the English booth's calling order; a served live run skips late moments instead,
  see above): a world line exists only after its call. In the shipped story insert (re-exported from the answer cache) the world lines start
  with the English booth's. Measured once with real calls (the paid export run of the story insert, paced at 1x on the wall clock, the same
  runner as live): each call took 1.1 to 2.6 s (median 1.3 s); world captions came 1.2 to 4.4 s after the English caption of the same moment
  (event to caption `lat` median 2.6 s, max 5.7 s, 58 lines); play-by-play fragments 1.2 to 1.6 s behind, still inside their 2 to 3.5 s life;
  the analysis 3.0 s and the score line 4.2 s behind, because the calls queue. 58 of 60 lines were captioned. A quicker move than this
  one, or a slower call, makes fragments go stale before their line exists (dropped, no `say`). This is one run, not a live load test.

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

`start`, `w`, `lat`, the `writing` step, the `facts` agent with the `insight` step, `say.ins` with the `pattern_insight` kind and the `pattern` and `payoff` steps, `GET /api/guided-live`, the `no_runs_today` code, the `live.runs_left` health fields, `hb`, `analyst_from`, the live `voice` message, `until`, `hello.run`, `hello.until`, `<arc>-<seed>` match ids, `/api/tts`, the channel fields `level`, `solo`, `lead`, `co`, the world channels 6 to 11, `log.d.world` and the `dropped` step were added to v1 this way,
and so were (2026-10-27) the `fast`, `world`, `rows` and `token` parameters, the `row` message, the `too_late` step, `/api/session`, `/api/scene`,
the health objects `today` and `public`, the error codes `no_calls_today`, `session_limit`, `ip_limit`, `busy`, `session_required`,
`no_session_secret`, `no_world` with close codes 4003 and 4029, the SSE code `origin_refused`, the `/api/scene` fields `attack` and
`goal_window` (and `goal_t` null for a generated scene), the `seed` parameter, `hello.scene_seed`, the `scene` step of the `facts` agent, the
`/api/session` field `ip_credits_left`, and the `/api/tts` codes `session_required`, `tts_daily_limit`, `tts_session_limit`, `tts_ip_limit`,
`tts_channel_limit`, `no_voice` with `detail.fallback`.

Additive changes (new optional fields, new `log.step` values, new code table entries at the end) keep `v: 1`.
Clients ignore unknown fields and unknown message kinds. Anything else bumps `v`.
