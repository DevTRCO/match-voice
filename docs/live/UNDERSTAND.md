

# Report (adc2af76acb8b7610)

## Deployment area: findings and an exact path to Azure Container Apps (read-only, 0 model calls, 0 credits, .env not opened)

### 1. Current state
- **Dockerfile** has two stages. `node:22-slim` runs `npm run build`, which is the server build, not `build:static`, so `ui/dist` still holds `mock*.html` (Dockerfile:7, docs/DEPLOY.md:17-19). `python:3.12-slim` installs the deps from pyproject (Dockerfile:16-17) and does an editable install so `ROOT=/app` (Dockerfile:20, config.py:9). It copies `data/matches`, `data/replays`, `data/cache` (Dockerfile:21-23) and runs as the non-root user `app` (Dockerfile:25-26). Env defaults are `MATCHVOICE_HOST=0.0.0.0`, `PORT=8000`, `MATCHVOICE_LIVE_CALLS=0` (Dockerfile:11-12). The `HEALTHCHECK` (Dockerfile:28) is **ignored by Container Apps**, so probes must be set on the app.
- **Server env vars** (server/__main__.py):
  - Base: `MATCHVOICE_HOST` :22, `PORT` :23, `MATCHVOICE_LIVE_CALLS` :24.
  - Live limits: `MATCHVOICE_LIVE_FRESH=1` :26, `MATCHVOICE_LIVE_MAX_SECONDS` (default 75) :28, `MATCHVOICE_LIVE_RUNS_PER_DAY` (default 150, UTC day, in memory) :30, `MATCHVOICE_WORLD_CALLS` :32.
  - Voice: `MATCHVOICE_TTS_CREDITS` (default 300, tts/guarded.py:24,155), `MATCHVOICE_TTS_DELIVERY` (guarded.py:157).
  - Keys: `MATCHVOICE_NO_DOTENV` (config.py:11). Anthropic key lookup order is `ANTHROPIC_API_KEY_2`, `ANTHROPIC_API_KEY`, `ANTHROPIC_KEY` (config.py:16), environment first, then .env. ElevenLabs is `ELEVENLABS_API_KEY` (config.py:25).
  - Uvicorn runs as a single process with no `proxy_headers` or `forwarded_allow_ips` (__main__.py:56).
- **What the caps really cover today:**
  - `MATCHVOICE_LIVE_CALLS` is a budget for the life of the process, not a daily cap (`CallBudget` analyst.py:182-189, created in runner.py:162).
  - The runs-per-day limit is real but held in memory (runner.py:71-121).
  - The TTS budget is counted from `data/cache/tts/ledger.jsonl` (guarded.py:49-51). `.dockerignore:14` excludes `data/cache/tts`, so every new container starts with a full 300 credits. In practice it is a cap per container lifetime.
  - So "global daily caps" need new code: a day-keyed counter for model calls and voice credits.
  - Every deploy or restart resets all in-memory counters.
- **CORS:** `allow_origins=["*"], allow_methods=["GET"]` is hardcoded (server/app.py:49). CORS does not cover WebSocket. `/ws` (app.py:235) accepts any Origin.
  - A POST endpoint for "New run" would be refused by the preflight, because only GET is allowed.
  - Proposal: a new env var `MATCHVOICE_ALLOWED_ORIGINS=https://happy-bush-012530710.5.azurestaticapps.net` (plus `http://localhost:5173` for dev), used by both the CORS middleware and an Origin check in `/ws`. Leave the ingress-level CORS in Container Apps off so it is not handled twice.
- **Per-session limits across origins:** the page is on SWA and the API is on `*.azurecontainerapps.io`, so a cookie would be a third-party cookie (blocked by Safari, and increasingly by Chrome).
  - SWA "linked backend" (same origin) needs the Standard plan, about 9 USD a month. `encara-demo` is on Free.
  - Recommendation: the server issues an HMAC-signed session token (new secret `MATCHVOICE_SESSION_SECRET`), the page keeps it in `sessionStorage` and sends it as a query param on `/ws`.
  - For per-IP limits behind Envoy, set env `FORWARDED_ALLOW_IPS=*` (uvicorn reads it). Otherwise `client.host` is the proxy's IP.
- **The page has no API base today.** `mock4.html` only fetches static files (mock4.html:1726, 1788-1790). It is a `public/` file that Vite does not process, so the API URL must be a constant in the page (with an optional `?api=` override) or a small `public/api.json`.
- **comeback-135 needs nothing on disk.** `Library.bundle` simulates any `<arc>-<seed>` in memory (library.py:18, 66-81), and the runner enriches in memory (runner.py:339). `data/matches/comeback-135/enriched.jsonl` is not read at runtime.
- **Analyst cache:** `data/cache/analyst` (280 KB) is baked in (Dockerfile:23). A scene whose prompts are already cached is served as "Cached" (no call). Use `MATCHVOICE_LIVE_FRESH=1`, or pick windows that are not cached, if the founder wants real calls to be visible.

### 2. Secrets and build context
- **No secrets in the image.**
  - `.env` is excluded (.dockerignore:3), and it is the only `.env*`, `*.pem` or `*.key` file in the tree (checked with find).
  - The Dockerfile copies only named paths, so the four stray root `*.json` files are not copied.
  - A grep for `sk-ant`, `xi-api-key` and `ELEVENLABS_API_KEY=` in data, ui/public and backend found only the variable names in config.py and tts/client.py.
- **Real problem: the build context is too big.** `.dockerignore` does not exclude `video/` (1.5 GB, including `video/founder` recordings) or `data/corpus` (81 MB). `az acr build` would upload about 1.6 GB of private material to Azure. Add these lines before building: `video`, `data/corpus`, `docs`, `/*.json`, `**/.env`.

### 3. Local tooling
- az CLI 2.91.0, logged in as vu.minh@tranconsulting.de, subscription "Azure subscription 1" (dd216149-…), state Enabled. The `containerapp` command group is available.
- **The Docker daemon is broken.** `docker version` returns a 500 from the socket, so `az acr build` (cloud build) is the way to go.
- `encara-rg` is in **westeurope** and holds only `encara-demo` (Free plan, centralus, host happy-bush-012530710.5.azurestaticapps.net).
- **`Microsoft.App`, `Microsoft.ContainerRegistry` and `Microsoft.OperationalInsights` are NotRegistered.** They must be registered first.
- No ACR exists.
- Container Apps lists both West Europe and Central US. Only Static Web Apps refused westeurope.
- **Region choice (founder decides):**

| Region | Pro | Contra |
|---|---|---|
| westeurope | Closer to EU viewers, same as the RG | Might be refused like SWA was (unknown) |
| centralus | Same region as the SWA, known to work for this subscription | About 100 ms further for EU viewers, which does not matter for a WebSocket stream |

### 4. Deploy commands
Zsh. Keys go in without being printed. The keys are loaded through `matchvoice.config`, so nothing ever reads or prints .env.
```
cd /Users/vmt/MicroSaaS/match-voice
RG=encara-rg; LOC=westeurope            # fallback: centralus
ACR=encaramv$(openssl rand -hex 3); APP=encara-live; ENV=encara-env
az provider register -n Microsoft.App --wait
az provider register -n Microsoft.ContainerRegistry --wait
az acr create -n $ACR -g $RG -l $LOC --sku Basic -o none
TAG=$(date +%Y%m%d-%H%M); az acr build -r $ACR -t match-voice:$TAG .   # after fixing .dockerignore
az containerapp env create -n $ENV -g $RG -l $LOC --logs-destination none -o none
az containerapp create -n $APP -g $RG --environment $ENV \
  --image $ACR.azurecr.io/match-voice:$TAG --registry-server $ACR.azurecr.io --registry-identity system \
  --ingress external --target-port 8000 --transport auto \
  --min-replicas 1 --max-replicas 1 --cpu 0.5 --memory 1.0Gi --revisions-mode single \
  --env-vars MATCHVOICE_NO_DOTENV=1 FORWARDED_ALLOW_IPS='*' MATCHVOICE_LIVE_CALLS=0 -o none
# secrets: values never echoed, never in shell history
ANTH=$(.venv/bin/python -c "from matchvoice.config import anthropic_api_key as k; print(k() or '')")
EL=$(.venv/bin/python -c "from matchvoice.config import elevenlabs_api_key as k; print(k() or '')")
SESS=$(openssl rand -hex 32)
az containerapp secret set -n $APP -g $RG --secrets anthropic-key="$ANTH" elevenlabs-key="$EL" session-secret="$SESS" -o none
unset ANTH EL SESS
az containerapp update -n $APP -g $RG -o none --set-env-vars \
  ANTHROPIC_API_KEY=secretref:anthropic-key ELEVENLABS_API_KEY=secretref:elevenlabs-key \
  MATCHVOICE_SESSION_SECRET=secretref:session-secret \
  MATCHVOICE_ALLOWED_ORIGINS=https://happy-bush-012530710.5.azurestaticapps.net \
  MATCHVOICE_LIVE_CALLS=<N> MATCHVOICE_LIVE_MAX_SECONDS=75 MATCHVOICE_LIVE_RUNS_PER_DAY=<R> \
  MATCHVOICE_TTS_CREDITS=<C> MATCHVOICE_WORLD_CALLS=0
az containerapp show -n $APP -g $RG --query properties.configuration.ingress.fqdn -o tsv
```
- The secret values briefly appear in the az process arguments (visible to `ps` on the Mac). That is acceptable here. Key Vault references are the stricter option.
- The new env vars (ALLOWED_ORIGINS, SESSION_SECRET and the daily caps) do nothing until the code reads them.

**Probes.** Run `az containerapp show -n $APP -g $RG -o yaml > app.yaml` (the output carries no secret values). Under `template.containers[0]`, add:
```
probes:
- {type: Startup, httpGet: {path: /api/health, port: 8000}, periodSeconds: 2, failureThreshold: 30}
- {type: Readiness, httpGet: {path: /api/health, port: 8000}, periodSeconds: 10}
- {type: Liveness, httpGet: {path: /api/health, port: 8000}, periodSeconds: 30, timeoutSeconds: 3}
```
Then run `az containerapp update -n $APP -g $RG --yaml app.yaml`. `/api/health` is cheap (app.py:140-155).

**WebSocket:** Container Apps HTTP ingress (`--transport auto`) supports WS natively. The idle timeout is 240 s, well above a 75 s run with heartbeats, and session affinity is not needed with one replica.

**Smoke test:** `curl -s https://<fqdn>/api/health`.

**Redeploy:**
```
TAG=$(date +%Y%m%d-%H%M); az acr build -r $ACR -t match-voice:$TAG . && az containerapp update -n $APP -g $RG --image $ACR.azurecr.io/match-voice:$TAG -o none
```
A new revision resets all in-memory counters, and the old and new revisions overlap briefly. The SWA redeploy stays as in docs/DEPLOY.md:47-50, after the page gets the API URL.

### 5. Replicas: options (founder decides)

| Option | Pro | Contra |
|---|---|---|
| A. `min=1, max=1` (recommended) | In-memory session and daily limits hold, no cold start | Always billed |
| B. `min=0, max=1` | Nearly free within the grant | Cold start (Python plus agent-framework imports, several seconds) on the first click; every scale-from-zero resets the call, run and TTS counters (as docs/DEPLOY.md:97-99 notes), so the daily caps leak |
| C. A, plus Azure Files mounted on `data/cache` | TTS ledger and analyst answers survive restarts | Mount setup work, a few cents a month |

`max=1` is required in every option, otherwise each replica keeps its own counters.

### 6. Cost
Consumption plan: 0.5 vCPU and 1 GiB for 30 days, minus the monthly grant (180k vCPU-s, 360k GiB-s).

| Item | Monthly |
|---|---|
| vCPU idle (1.116M s × 0.000003) | about 3.35 USD |
| Memory (2.232M GiB-s × 0.000003) | about 6.70 USD |
| **Container, mostly idle** | **about 10 USD** |
| Container, worst case active all the time (vCPU 1.116M s × 0.000024 = 26.8 USD, plus memory) | about 33.5 USD |
| ACR Basic (about 0.167 USD a day) | about 5 USD |
| Logs (`--logs-destination none`) | 0 |
| Egress (small mp3 files) | negligible |

For the judging window to 2026-11-10 (about 2 weeks), expect roughly 7 to 8 USD in total plus model and voice spend. Model and voice spend is bounded only by the caps the code enforces.

### 7. Other risks noticed
- `pyproject.toml` has no lock file. A fresh `acr build` may pull newer `agent-framework-core` or `agent-framework-anthropic` (a prerelease pin) than the local `.venv`. Consider a `pip freeze` constraints file.
- `python-dotenv` is only a transitive dependency (via agent-framework-core and pydantic-settings), not declared.
- The `tts/voices.py` voice table covers en, de and fr only (per the notes). Flash voices for the six world channels would need entries.

## Risks
- Client and network: .dockerignore misses video/ (1.5 GB incl. founder recordings) and data/corpus (81 MB); az acr build would upload them to Azure as build context
- Microsoft.App, Microsoft.ContainerRegistry, Microsoft.OperationalInsights are NotRegistered in the subscription; first deploy fails until registered
- Local Docker daemon returns 500; only az acr build (cloud) works now, which requires an ACR (about 5 USD/month)
- MATCHVOICE_LIVE_CALLS is a per-process budget, not daily; TTS credit ledger lives in data/cache/tts which is excluded from the image, so every container start refills 300 credits; daily caps need new code
- In-memory counters (calls, runs per day, sessions) reset on every revision update, restart or scale-from-zero; min-replicas 0 makes the caps leak
- CORS is hardcoded allow_origins=* GET only (server/app.py:49); a POST endpoint fails preflight; /ws has no Origin check
- Cross-origin SWA page means session cookies are third-party and blocked; per-session limit needs a signed token in sessionStorage
- uvicorn.run without forwarded_allow_ips: client IP is the Envoy proxy unless FORWARDED_ALLOW_IPS=* is set
- Baked analyst cache makes already-cached scenes 'Cached' (no real call) unless MATCHVOICE_LIVE_FRESH=1 or uncached windows are chosen
- Dockerfile HEALTHCHECK is ignored by Container Apps; probes must be set via YAML
- No dependency lock: acr build may install newer agent-framework prereleases than the tested .venv
- Server image built with npm run build ships mock*.html at /mock*.html on the container
- westeurope availability for this subscription is unverified (only SWA was refused); centralus is the known-good fallback

## Key files
- /Users/vmt/MicroSaaS/match-voice/Dockerfile
- /Users/vmt/MicroSaaS/match-voice/.dockerignore
- /Users/vmt/MicroSaaS/match-voice/docs/DEPLOY.md
- /Users/vmt/MicroSaaS/match-voice/ui/vite.config.ts
- /Users/vmt/MicroSaaS/match-voice/ui/public/staticwebapp.config.json
- /Users/vmt/MicroSaaS/match-voice/ui/public/mock4.html
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/config.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/server/__main__.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/server/app.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/pipeline/runner.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/pipeline/library.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/tts/guarded.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/commentary/analyst.py
- /Users/vmt/MicroSaaS/match-voice/pyproject.toml

# Report (a6e9ce8e99b8d33fe)

Scope: /Users/vmt/MicroSaaS/match-voice/ui/public/mock4.html (1824 lines, one inline script, no modules), plus ui/src/feed.ts, player.ts, speech.ts, sim.ts. Read only. No edits, no model calls, no credits spent, .env not read.

## Answer first
The page can be driven live with little change, because story.json already is a capture of the live protocol (hello, f, say, voice, log, hb, end). The design below rests on three ideas.
1. Collect the WebSocket messages into the same `{demo, hello, messages}` shape and rebuild D, P, RUNS and INTEL from everything received so far, about 4 times a second. build(), buildPlay(), buildIntel() and draw() can then stay as they are.
2. Play the board about 3 s behind the stream: `nowW = since hello - DELAY`. Every short lookahead in the page reaches at most about 2.5 s ahead (the pass receipt, a run that starts 1.9 s before the kick, the 0.9 s board tilt, label hand-over, and voice start, which is known at the `voice` message). With the delay, all of these are known by the time the board gets there. Lags still show their real values, because the delay is the same for every message.
3. When the run ends, the stream in memory is a recording. Seek, Watch again and "hear it with another commentator" then work unchanged.

There is one hard gap. The board's player and ball motion comes from insert/micro.json (enriched rows). Those rows are a separate static file and are not in the stream. A live branch needs a new additive message carrying the enriched rows, sent at the time each row becomes known.

## 1. How the page loads and plays now
- load() (1784-1817) fetches insert/story.json, insert/micro.json and insert/story-audio/manifest.json, then runs `D=build(st, mi.rows)` (1791). After that it works out the dead ball and restart (1793-1798), `P=buildPlay(D)` (1799), `com=pickDefault()` (1800), `RUNS=buildRuns()` (1802), GOAL_FROM and ATTACK_FROM (1803-1806), `INTEL=buildIntel()` (1807) and the team abbreviations, then tease() and setCom().
- build(st, micro) (543-616):
  - COMS comes from `makeComs(hello.channels, says)` (493-506). BOOTH0 (491) only covers the names before the data loads. A solo booth is read from `c.solo` (502).
  - Parts give `off`, `wOf`, `tOf`, `partOf` and `cuts` (548-557). `LEN = demo.length || off[L]+lens[L]` (558).
  - Skeleton events E come from the frames' `e` arrays through hello.eventFields (570-575). Which goal each side attacks comes from shots (577-579).
  - Enriched rows are filtered to the parts plus catch-up (582-584).
  - Says are grouped per moment into LINES (587-610). Each line has per-channel `ws` (when the line is spoken: voice.w if voiced and not cut, else the caption w), `dur` (voice e-s, or caption e-s, or text length/14+0.6), `lat` (+ settle for a touch), `who` and `ins`.
  - WP holds win chance and score from frames (613).
- Clock: `CLOCK0=180` is hard-coded (513) and applied to every t (514). It is only right in comeback-135's second half.
- tick() (1116-1152, the rAF loop) uses a `done` Set of once-keys. It handles cuts (1126-1131), scene 1's intro card (1133), lane 1 rows `"r"+k` (1134), the gap row (1135-1137), INTEL `"i"+k` and `"o"+k` (1138), and lines `"l"+k`, which call showLine and goal() (1140). It also runs the win graphic plan WPP (1141-1145), insight off (1146-1147), flowTick (1148), finish at LEN (1149) and draw (1150).
- Subtitles: showLine() (1065-1073) sets #fsay with words() (816), fitSubs() (1062) and plate() and hear(). It sets talkUntil and calls speak(), and starts insight() when `line.ins` is set. recast() (1014-1023) moves the line to a newly chosen booth.
- Voice: speak() (793-808). A baked mp3 is used only when the manifest caption equals the subtitle (`audioUrl`, 788-789). Otherwise the browser SpeechSynthesis is used with BCP lang (790). A line that started more than 0.4 s ago with no file stays silent (804). The stadium bed and roar are in start() (1724-1727) and goal() (1250). The UI never says which voice is in use (grep finds no "Browser voice" or "ElevenLabs" label). CLAUDE.md asks for that label.
- Score bug: reset() takes the score from the last WP at or before parts[0][0], or demo.score (1110). goal() (1240-1251) takes the score from the first WP at or after the goal, and plans the win graphic.
- Scenes and cards: recState and anaSpan (1156, 1400-1407) need a pattern insight AND D.cuts[0]. sceneCard, scene1Sub, laterText, sceneName and REC_TXT are at 1158-1169. teaseEnd (1175) and anaUi (1176-1178) handle the hand-over from the start screen.
- Insight montage: insight() (1076-1087), insEnd (1089-1092), drawInsight (1661-1718), setupLane and payLane (1613-1626). The evidence is `say.ins` (zone, dots, arrows, players, wins, across).
- Board: buildPlay(D) (619-697) produces ball keys K, actor anchors A, labels LB, pressure PR, possession POS, flights FL, interceptions IC and moves MV. buildRuns (716-748) builds the off-ball runs. positions(w) (1480-1512) gives the shape (targetOf, shapeOf), runs, anchors, spacing, pressure and calm() smoothing; SM is global state (1515-1524). draw(w) (1525-1608) draws the trail, arcs, players, ball, goal flash, labels and cut fade.
- How mode:
  - Flow band: stampsOf (1269-1304, cached in STC 1268 and never cleared), flowPick and flowTick (1306-1327).
  - Lane 1: rawRow and noteRow (942-951) show enriched rows with their raw JSON.
  - Lane 2: intelItem and intelOut (953-963) render INTEL from buildIntel (876-922).
  - Lane 3: hear() and nowLine (976-1004), with flags for every channel.
- Progress and seek: the bar width and time label are in tick (1124-1125). seek(w) (1739-1752) calls start(w) and marks earlier lines and cuts done (1731-1733). Scrubbing is at 1753-1760 and arrow keys at 1777.
- Picker: renderPick, pickCentre and keyboard (1192-1233). The default is ja (`want`, 529-530).

## 2. Every place that assumes the whole run is known in advance
- 558 `LEN` (demo.length or the end of the parts). Used at 1113, 1121, 1124-1125, 1149-1150, 1392, 1741, 1754-1755 and 1819.
- 548-557: parts, off and cuts are taken from the whole message list. off[k] is the first hb or say inside part k.
- 582-584: rows are filtered by part, and catch-up is worked out from all frames.
- 587-610: LINES. `ws`, `dur` and `who` need the later `voice` message. `w = min over channels` and the sort assume all channels have arrived.
- 613 WP: the whole frame list.
- 631-636: buildPlay's dead-ball and restart placement uses D.restart from load 1793-1798. That is a lookahead: it uses the next micro row after the last event.
- 643, 696: the cuts.
- 657 `rec=R.find(receipt with pass_eid)`: the receipt comes later, up to the pass flight time. 660 `r.t_arr`.
- 687: `key(D.LEN+60, ...)`.
- 689-694: label w0 and w1 depend on the NEXT label (694).
- 724-745 buildRuns: runs start before the event (`f.wk-1.9`, 727), use `f.wa` (pass arrival), and react to the interception list.
- 866 waitedFor: scans all LINES.
- 876-922 buildIntel: n channels, logs, boothsOf, and `D.WP.find` after the goal (897). The payoff `P.LB.find` is at 920.
- 1082: `D.LINES.find(set-up)`.
- 1089-1092 insEnd: the next story line and the next cut.
- 1110-1113 reset: first WP, demo.score, parts[0][0], LEN.
- 1133, 1159, 1175, 1181, 1400-1403: whether an insight line exists, and its w (teaseEnd, anaSpan, tease, scene1Sub).
- 1162 hasGoal (all rows), used by sceneName and the end title.
- 1241 goal(): WP after the goal (the frame arrives with the goal, so this is fine live).
- 1263 and 1803-1806: ATTACK_FROM and GOAL_FROM come from the goal shot and the last pass in all rows.
- 1269-1304 stampsOf: needs every later log step (analyst_wrote, verified) and the voice. Its STC cache is never invalidated.
- 1306-1309 flowPick: in-flight lines need t[4].
- 1606: cut fade.
- 1731-1733 and 1739-1752: seek and start(fromW) mark everything before w as done, and need LINES and cuts.
- 1812 the "fine" note (rows.length) and 1813 timingNote (925-939): whole-run numbers.
- 1134 and 1138-1140 done keys are array indexes (`"r"+k`, `"i"+k`, `"l"+k`). They break as soon as the arrays are rebuilt with new items in between.

## 3. Live design, least change
### A. Transport
- Copy openStream from /Users/vmt/MicroSaaS/match-voice/ui/src/feed.ts:80-102 as plain JS. Keep: the wss URL from the base, the `error` message before close, and close codes 4000 bad_request and 4001 no_runs_today.
- Also copy fetchHealth and detectBackend (27-36), the fetchGuided error mapping (54-64), and noteOf (player.ts:27). These are the fallback rules: health fails or a JSON parse fails (SWA rewrites /api to index.html) means static, recorded only.
- mock4 is not a module, so the code is copied, not imported. sim.ts and Player are not needed, because mock4's build() does that job.
- The live branch passes `{demo:{match,start,until,clock,score,parts:[[start,until]]}, hello, messages}` into build(). The demo part is put together from the scene answer.

### B. Rebuild instead of rewriting
- On each non-hb message, mark the state dirty. In tick, at most every 250 ms, run `D=build(...); P=buildPlay(D); RUNS=buildRuns(); INTEL=buildIntel()`. About 100 to 300 rows in a 60 s window keeps this cheap.
- Changes needed:
  - Stable once-keys: `"l"+line.m`, `"r"+row.eid`, `"i"+k` becomes `"i"+(line?line.m:det+w)`.
  - Clear STC on rebuild.
  - Carry over `l.pos` (label hysteresis, 1596) and `pr.by` (presser, 1507) by key, or labels and pressers can jump.
  - Compute D.restart and deadBall inside the rebuild, once rows after the start exist.
  - Clock from the frame `c` (or CLOCK0 only when `p===2`).
  - Set the score bug from the first frame when it arrives, not in reset().
- Lines in live: a `say` with s==e is a caption that waits for its voice. Do not show it until its `voice` message arrives. Then ws = voice.w and dur = e-s, which build() already does at 597-600. A `skip` is shown as subtitle only, at the skip's w. Under the delay, every voiced line is known DELAY s before the board reaches it.

### C. Delay
- The live clock is `nowW = (now - tHello)/1000 - DELAY`, with DELAY about 3 s. This is the largest client-side lookahead, given the receipt (657), runs at -1.9 s (727), labels (694) and TILT_S 0.9 (1404).
- Prefetch the voice mp3 when its `voice` message arrives, so the ElevenLabs Flash latency is hidden in the delay.
- Optional: a lighter buffered segment in .ctrl .tl that shows data that has arrived ahead of the playhead.
- Make one fine-print line say it honestly: "picture 3 s behind the generator".

### D. Length, progress, seek
- LEN = until - start, from the window answer. Extend it by talkUntil, and finish only after `end` arrives and the voice has ended (1149).
- During the run: hide or disable seek (the pointerdown guard at 1756 and the arrows at 1777) and keep pause working (the buffer just grows).
- After `end`: freeze the messages and set `D.live=false`. Seek, Watch again, alts (1263, with ATTACK_FROM computed at end) and the How lanes then behave like the recorded run, at 0 extra cost. If the stream dies mid-run, finish with what arrived and say where it stopped.

### E. Scenes, cuts and the montage in a one-part live run
- `cuts=[]`. anaSpan returns null, so there is no tilt and recState is "rec".
- Add a REC_TXT state "now" with long "Live, generated now" and short "Live", using the existing `--live` red only as a small dot.
- sceneCard at start: `Scene 3, ${MIN(clock)}` with sub "Generated now, same match".
- sceneName and the end title must not assume a goal ("Hear the same scene with another commentator" when there is no goal).
- If a pattern insight does arrive live, anaSpan needs a live end of `insEnd + tilt out` with an ease-out. Today the way out is hidden by the cut (1402-1407).

### F. Showing the generated events and the agents at work
Everything needed is already in the stream:
- Lane 1 rawRow shows each enriched row with its JSON as it arrives.
- Lane 2 shows detections and agent results.
- The flow band lights Data in, Understood, Written, Checked, Spoken at their real times.

Live changes needed:
1. stampsOf must allow missing later steps. Light what has arrived. The next step uses the existing `.next` wait pulse (gold), with a running count-up label ("writing, +1.4 s") until analyst_wrote arrives, then the real latency.
2. Lane 2 gets an open item when `log step=queued` or `writing` arrives ("Analyst writing", with the counter). It is filled by intelOut on analyst_wrote, verified/rejected and ready (rejected and retried shows as the existing "1 rejected and rewritten").
3. Director decisions (voice cut and skip) show as the existing "waited for the ..." notes and a "not spoken, too late" note.

Where to show it, two options:
- (a) A live run opens in How mode. Pro: zero new layout, and it is exactly "show what happens". Con: the picture is smaller.
- (b) The picture stays full and the bottom ctrl row gets one text line naming the latest agent step ("Verifier, 6 of 6 pass, 2 ms"). Pro: big picture. Con: new element, and it competes with the subtitles.

I recommend (a), with the H key and "Back to the match" still working. Style: existing tokens only (royal panels, gold `--signal`, Barlow Condensed for times and codes, Schibsted for text), no bars, pills, "·" or em dashes. One existing conflict: lane 1 JSON numbers are mint `#8fd0a8` (mock4.html:347, `.rw code .n`), which goes against the no-green rule. Use `--gold-hi` or `--mute` instead.

### G. Voice in live
- `audioUrl` becomes `api/tts?run=${hello.run}&ch=${com.id}&m=${line.m}`, but only when health.tts.available and the language has a voice. Fetch only for the chosen channel.
- Keep the onerror and play().catch fallback to the browser voice (805). Add the honest label in the plate title or recn ("ElevenLabs voice" or "Browser voice"). Borrow `spokenForm` from /Users/vmt/MicroSaaS/match-voice/ui/src/speech.ts:130 for German "1:1".
- tts/voices.py:24 has voices for en, de and fr only (Flash). The page defaults to ja (mock4.html:529), so the default viewer would always get the browser voice live.

### H. Start, limits, fallback
- "New run" goes on the end screen next to Watch again (.end .row, 470-472) and as a second button on the start overlay. It shows the session's runs left as plain text ("2 runs left in this session").
- A refusal (no_runs_today, a session cap, no_budget, offline) puts one sentence in .recn. Recorded keeps working.
- Between the click and hello, playbig shows real steps only ("Asking for a scene", "Simulating", "Connected").

## 4. What the server must add for this page (outside my area, but the page depends on it)
1. A row message carrying the enriched rows (micro.json today comes from data/matches/comeback-135/enriched.jsonl 4200-4410, written by no script in the repo). It should be sent at the time each row becomes known; buildPlay and lane 1 need fields such as eid, i, t, type, team, target, pass_type, height, t_arr and pass_eid.
2. `/ws` live uses `Runner(bundle, mode, spd, paced, live, t0, carry, end_at)` (server/app.py make_runner, about line 123) without `fast=True`, `world=` or `booth=`. A live run would have no dense fragments, no `who`, only 6 channels (no ja/es/it/pt/nl/tr) and no pattern booth. The page's default ja channel would then fall back to en/expert without saying so.
3. A scene endpoint for the same match (comeback-135), unlike /api/guided-live which picks a random arc and seed. It should return start, until, clock, score, goal_t, runs_left and session_left.
4. Session limits. SWA and Container Apps are different origins, and cookies on a cross-origin WebSocket are unreliable (third-party cookie blocking). Prefer either an SWA linked backend (same origin, /api and /ws) or a session token from a POST that goes on the ws and tts query. The page also needs a configurable API base (today everything is relative).

## 5. Reuse from ui/src
- Reuse as is (copied to plain JS): feed.ts openStream, fetchHealth, detectBackend, fetchGuided error handling and CLOSE_CODES (feed.ts:27-102), player.ts noteOf and the liveBlock wording (27, 107-120), and speech.ts spokenForm (130).
- Do not reuse: sim.ts (mock4's build() replaces it), Player (React state), and speech.ts's queue. mock4 follows the server's `voice` messages directly; speech.ts's stale and skip rules (player.ts:14-24, 242-247) are already enforced by the server director, so mock4 only needs `skip` and `cut` handling.

## Risks
- The board's movement and labels come from insert/micro.json (enriched rows), and those rows are not in the WebSocket protocol. Without a new message carrying the enriched rows, the live board has only skeleton frames: no receipts, labels, runs or pass types.
- /ws live builds Runner without fast=True, world or booth (server/app.py make_runner). A live run would have only 6 channels and no dense fragments, and the default ja commentator (mock4.html:529) would silently fall back to en/expert.
- ElevenLabs voices exist only for en, de and fr (backend/matchvoice/tts/voices.py:24). Live ja, es, it, pt, nl and tr always use the browser voice, and the page has no label saying which voice is in use (CLAUDE.md requires one).
- CLOCK0=180 (mock4.html:513-514) is right only in comeback-135's second half. A first-half scene would show the clock 3 minutes early. Use the frame's c or period.
- The once-keys in tick are array indexes ("r"+k, "i"+k, "l"+k at mock4.html:1134-1140). Rebuilding arrays live would replay or skip rows and lines unless the keys become stable (eid or moment id).
- The STC cache in stampsOf (mock4.html:1268-1304) is never cleared, so live flow-band times would freeze at the first, incomplete state.
- Label hysteresis (l.pos, 1596) and the chosen presser (pr.by, 1507) live on objects that a rebuild throws away, which causes label or presser flicker unless carried over by key.
- Without a playout delay of about 3 s, the receipt lookup (657), runs that start 1.9 s before the kick (727), label hand-over (694) and the 0.9 s tilt (1404) have no data in time. The delay must be stated honestly on the page.
- D.restart and deadBall (1793-1798) read the next micro row after the last event, which is a lookahead. In live they must be recomputed once rows arrive.
- Cross-origin hosting (SWA page, Container Apps server) makes cookie-based per-session limits on WebSocket unreliable. A linked backend (same origin) or a token in the query is needed, and mock4 needs a configurable API base.
- Lane 1 JSON numbers use mint #8fd0a8 (mock4.html:347), which breaks the no-green rule.
- anaSpan (1400-1403) relies on a cut to hide the camera tilt back. A live one-part run with a pattern insight would need an added ease-out.

## Key files
- /Users/vmt/MicroSaaS/match-voice/ui/public/mock4.html
- /Users/vmt/MicroSaaS/match-voice/ui/public/insert/story.json
- /Users/vmt/MicroSaaS/match-voice/ui/public/insert/micro.json
- /Users/vmt/MicroSaaS/match-voice/ui/src/feed.ts
- /Users/vmt/MicroSaaS/match-voice/ui/src/player.ts
- /Users/vmt/MicroSaaS/match-voice/ui/src/speech.ts
- /Users/vmt/MicroSaaS/match-voice/ui/src/protocol.ts
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/server/app.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/pipeline/export.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/tts/voices.py
- /Users/vmt/MicroSaaS/match-voice/ui/public/staticwebapp.config.json

# Report (a2b98bde60302ebe8)

## Backend live path for the "New run" button (comeback-135), read-only map

No files were edited. I made no model calls and spent no ElevenLabs credits. I did not read .env. Scene numbers come from an offline simulation (`Library().bundle("comeback-135")`, FactEngine, MomentBuilder). Call counts come from an unpaced live `Runner` with a fake LLM that counts calls (scripts in the scratchpad: scan.py, win.py).

### How a live run starts and streams
- **Endpoints**
  - `/ws` is at backend/matchvoice/server/app.py:235-255.
  - `/sse` is at app.py:257-270.
  - Both use `make_runner` (app.py:101-131).
- **Query parameters**
  - `/ws` and `/sse` accept `match, mode, speed, paced, start, analyst_from, until`. There is **no `channels` parameter** and **no `fast` parameter**.
  - `match` can be any `<arc>-<seed>`. comeback-135 is not on disk (no meta.json), so `Library._generate` simulates it (pipeline/library.py:66-90).
- **Checks, in order**
  1. `parse_*`
  2. `lib.bundle`
  3. live configured (app.py:119)
  4. global call budget (app.py:121)
  5. `Runner.__init__`, which applies `LiveLimits.check_span` / `check_carry` (runner.py:240-243)
  6. `limits.claim_run()` last (app.py:125)
- **Run id**: `run_id` and `runner.lines` are registered for /api/tts, last 16 runs (app.py:126-130).
- **The server builds `Runner(bundle, mode, spd, paced, live, t0, carry, end_at)`** (app.py:123). It never passes `fast`, `booth`, `patterns` or `world`. So a server live run:
  - has **no** fast or context layer (no touch/pass_kind/player_note/story_note lines);
  - has **no** pattern detector, so no `pattern_insight` and no `ins` (runner.py:304: patterns = fast and live);
  - gets the world channels whenever the server has a world booth (runner.py:259-263).
  - The recorded story insert, by contrast, was made with `fast=True, booth=…, world=…` (pipeline/export.py:90).
- **LiveLimits** (runner.py:70-121)
  - `max_seconds`: default 75 (server/__main__.py:28). A run without `until` is refused.
  - `runs_per_day`: default 150. Counted in memory under a lock, rolls over at UTC midnight, and a restart resets it.
  - `check_carry` stops `analyst_from` reaching back more than `max_seconds`.
  - There is no per-session, per-IP or concurrency limit.
- **Call budgets**
  - `CallBudget` (commentary/analyst.py:182-189) is a **lifetime per-process** counter, not daily.
  - `_RunBudget` (runner.py:165-174) counts per run and spends from the shared budget.
  - `GuardedLLM` (analyst.py:311-375) adds a disk cache, shares calls already under way, takes **one extra call on an empty answer** (analyst.py:357-363), and skips the cache in fresh mode.
  - The newsroom does at most 1 retry after the verifier (newsroom.py:27, 148). Worst case per moment is 4 calls; the realistic figure is about 1.
- **World booth**
  - `--world-calls N` (env MATCHVOICE_WORLD_CALLS, server/__main__.py:32) builds `LiveConfig.world_call/world_budget` (runner.py:139-162).
  - One sequential call per moment the English booth captions (runner.py:669-673, 695-718, 775-776), including fast-layer fragments. One call writes all six world languages.
  - There is no staleness check before a call, so moments that will be dropped are still billed.
  - When the world budget is spent the world channels go silent. /api/health does not report the world budget.
- **Cache behaviour**: without `--live-fresh`, `recent_memo` (runner.py:136-138, 613-632) plus the disk cache make a second run of the same scene cost 0 calls, and its lines are marked `cached:1`.
- **guided.py** (pipeline/guided.py:22-47): a random arc and seed (`SystemRandom`), with a window from 40 s before a goal to 14 s after (54 s). It does not pick another scene of comeback-135. `demo.py` fixes the insert (demo.py:12-61).

### (1) Other good 40-60 s scenes in comeback-135 (Wexmoor Athletic H vs Tamsworth Wanderers A)
There are 1975 events in the match. Goals are at 802.8 (14', A), 4393.7 (71', H, the insert) and 5471.4 (89', H). There is **no red card**; the only card is a yellow at 3104.6 (49', H). The pattern detector fires once, at 4057.1 (65', H habit).

| Scene | Window | Skeleton events | Enriched rows | Model moments (core calls) | World calls, server default / fast | What happens |
|---|---|---|---|---|---|---|
| **A. 89' winner (recommended)** | **5431-5485** | 16 | 26 | goal_analysis 5471.4 (1) | 3 / 17 | Score 1-1. Build-up; shot_goal 5471.4 by Gabriel Tavares (xG 0.31) makes it 2-1; then goal_analysis and score_line "Two-one". Fits as part 3 after the insert's equaliser. |
| B. 14' opener | 762/763-816/817 | 9 | 19 | goal_analysis 802.8 (1) | 4 / 15 | Foul and free kick at 776.2, then shot_goal 802.8 by Joel Okonkwo (A, xG 0.36), 0-1. The momentum moment at 855.8 is outside the window. The pitch is thin. |
| C. 65' big save | 3995-4049, or 4005-4065 | 19 | 31 | shot_saved 4029.4 (Moreau, xG 0.849, Ostrander saves), big_save_analysis and momentum (2). Plus pattern_insight at 4057.1 with fast on, if the window is extended to 4065 (3). | 5 / 16 | No goal. The fast-on set-up is the same "Ibsen" habit the insert already shows. |
| Weak options | 1815-1869 (31' save, xG 0.47, no model moment); 2664-2718 (45+1' save 2704.0 plus momentum 2699.7; only 4 events) | | | | | |

### (2) What a live run streams (docs/PROTOCOL.md; encoder pipeline/protocol.py)
- **`hello`** (protocol.py:56)
  - Contains `mode, speed, start, until, run, dt, duration`, teams, players, code tables.
  - `channels` lists 6 entries, or 12 with world on (protocol.py:39). Each has `lead`/`co` `{name, gender}`.
- **Catch-up frames**: frames from 0 to `start` are sent at once with no commentary. For start=5431 that is about 1,380 messages in the first burst.
- **`f` frames**: score, win probability, momentum, events, stat deltas.
  - They carry **skeleton events only**. The enriched micro rows (receipts, carries) that mock4 reads from insert/micro.json are **not streamed**.
  - micro.json has no producer script in the repo; its `source` field names data/matches/comeback-135/enriched.jsonl.
  - A new scene needs a micro source: a deterministic endpoint (e.g. `/api/micro?match&from&to`, built with `enrich()`), an additive stream message, or baked JSON per scene.
- **`say`** (protocol.py:113, emitted at runner.py:795-813)
  - Fields: `ch, m, kind, voice` (pbp/analyst), `who` (speaker name), `text, s, e, src` (analyst/template), `cached, w, lat` (event to caption, in wall seconds).
  - `ins` is present only when patterns are on, so **never on the server today**.
- **`voice`**: start, cut and skip with `w` and `lat`.
- **`log`**
  - Agents are `detector, analyst, verifier, publisher, director, facts`.
  - Steps: `queued, writing/lookup, analyst_wrote` (`d.latency_s`, `d.wall_s`, `d.cached`), `verified, rejected, retry, fallback, ready, cut, insight, pattern, payoff, dropped`.
  - World steps carry `d.world: true`. Every log has `w` (real wall time).
- **`hb`, `end`** (`calls` = the run's calls including world), **`error`**.
- **Gaps for the page**
  - No micro rows.
  - No `ins` unless fast/patterns are enabled.
  - No per-line director log apart from `cut`.

### (3) Server-side changes needed
- **Per-session limits**: there is no session concept. Options for the session id:
  - **Server-issued HMAC token** from a new endpoint, sent as a query param on /ws and /api/tts (needs a secret env var). Recommended.
  - **Client-generated id** in sessionStorage. Trivial to bypass.
  - **Cookie**. Unreliable cross-site from SWA to ACA because of third-party cookie rules.
  - Wherever the id comes from, add per-IP limits as a backstop. On ACA, uvicorn needs `forwarded_allow_ips`/`proxy_headers` (server/__main__.py:56 passes neither), otherwise `client.host` is the proxy.
  - Hook points: `make_runner` (app.py:101-131) and LiveLimits (runner.py:70-121). Bind each run id to its session and enforce per-session credits in /api/tts (app.py:166-192).
  - Add a semaphore for concurrent live runs; none exists.
- **Global daily caps**
  - `CallBudget` needs a UTC-day roll like `LiveLimits._roll` (runner.py:98-101), for both the core and world budgets.
  - `GuardedTTS.spent` sums the **whole ledger** (tts/guarded.py:58-71). Filter it by `at >=` today's UTC midnight, since the ledger has an `at` field.
  - All counters are in memory or on the ephemeral filesystem. With `--min-replicas 0` (docs/DEPLOY.md:80, 97-99) every cold start resets them. Either persist the counters and the ledger on an Azure Files volume, or run min=max=1 replica. More than one replica would also split `runs` (app.py:52), so /api/tts would 404.
- **Whitelist the match**: `match` currently accepts any `<arc>-<seed>`. Restrict it to comeback-135 and the prepared windows, so the public server cannot be used for arbitrary fresh seeds that never hit the cache.
- **CORS** (app.py:49 is `allow_origins=["*"], allow_methods=["GET"]`)
  - Add `expose_headers` for `X-Voice-*` if the page uses fetch.
  - Add POST if a session endpoint uses it.
  - CORS does not cover WebSockets: add an `Origin` allowlist check in `ws()` before `accept()` (app.py:239).
  - The page is https, so it must connect with `wss://`.
  - SWA linked backends do not proxy WebSockets, so the page should call ACA directly.
- **World channels in a live run**
  - Today they are all-or-nothing per server: `--world-calls` turns them on for every run.
  - Add a query param such as `world=1`, passed to the existing `Runner(world=…)` (runner.py:224, 260-262), so world calls are made only when the viewer picks a world channel.
  - Also pass `fast=True` from the server (a query param or server flag) if the run should look like the insert: dense voice, story notes, patterns, `ins`.
  - Report the world budget in /api/health.
- **Flash voices per commentator for all 9 languages**
  - tts/voices.py:23-25 maps only en/de/fr, all to Daniel.
  - `voice_for("es")` raises KeyError (guarded.py:110). /api/tts does not catch it (app.py:182-189), so **every world line returns HTTP 500 today**.
  - `runner.lines` stores only `(text, lang)` (runner.py:784). Store `who` as well, and map person to voice id using `CAST` in backend/scripts/bake_story_audio.py:42-59 (15 voices).
  - The insert was baked with `eleven_v4` (bake_story_audio.py:38); live must stay `eleven_flash_v2_5`. The same voice ids work on Flash, with a slightly different sound.
  - Pass the voice into `GuardedTTS.speak`; the cache key already includes the voice id (guarded.py:83).
  - Add es/it/pt/nl/tr/ja to `LANGUAGE_CODES` (client.py:24 already falls back to the raw code).
  - Flash v2.5 supports all 9 languages: it covers the v2 set (en, ja, de, fr, pt, it, es, nl, tr and others) plus hu, no, vi, per the ElevenLabs docs.
  - Consider turning on `--tts-delivery`: `shape_for_tts` handles the world languages (commentary/delivery.py:170-211).

### (4) Expected cost per 54 s run
Model calls (Haiku 5.5). One call writes all 6 core languages, and one world call writes all 6 world languages. So a single core channel costs the same as all six, and with world on all 12 cost the same as one world channel.

| Configuration | Winner (A) | Opener (B) | Big save (C) |
|---|---|---|---|
| Server as-is, world off | 1 | 1 | 2 |
| Server as-is, world on | 1+3 = 4 | 1+4 = 5 | 2+5 = 7 |
| Fast on, world on | 1+17 = 18 | 1+15 = 16 | 2+16 = 18 (3+16 if the window includes the 4057 pattern) |

- Retries add about 0-20%.
- For comparison, the recorded story insert (46 s) took 2 core plus 11 world calls (10 moments, 1 retry, 3 rejected).
- With the answer cache on, a repeat run of the same scene costs 0 calls but shows `cached`.

ElevenLabs Flash credits (0.5 credit per character). Only lines whose voice actually starts on the viewer's channel are requested, and the disk cache makes repeated identical lines free.

| Configuration | One core channel | One world channel | All 12 channels |
|---|---|---|---|
| Fast off | 107-298 chars, about 55-150 credits | 3-5 lines, about 100 credits | |
| Fast on | 430-620 chars, about 215-310 credits | 195 (ja) to 460 chars per 46 s, about 100-270 credits | 4,699 chars per 46 s measured, about 5,500 chars, **about 2,750 credits** per 54 s run (only if a client voiced every channel) |

- The default `--tts-credits` is 300 for the whole lifetime, which is about one run.
- Plan daily caps per run as roughly 1-2 calls (world off) or about 18 calls (fast plus world), and about 250 credits per listener.
- ElevenLabs concurrency (the bake script notes the account allows 3) can produce 502 `tts_unavailable`, and the page then falls back to the browser voice.

## Risks
- Server live runs never pass fast=True (app.py:123): no dense voice, no story notes, no pattern_insight and no `ins`, so a 'New run' will look much sparser than the recorded insert unless a fast flag or query param is added.
- /api/tts returns HTTP 500 for every world-channel line: voice_for raises KeyError for es/it/pt/nl/tr/ja (tts/voices.py:24-32, guarded.py:110) and app.py:182-189 does not catch KeyError.
- All caps reset on a cold start: CallBudget, LiveLimits and runs are in memory, and the TTS ledger is on the ephemeral filesystem. The documented deployment uses --min-replicas 0, so the caps can be bypassed by idle time. More than one replica also splits the run registry, so /api/tts would 404.
- CallBudget and GuardedTTS budgets are lifetime totals, not daily. The world budget is not shown in /api/health, and world channels go silent when it runs out.
- There is no WebSocket Origin check and no match whitelist, so any site can open live runs on any <arc>-<seed> and spend calls up to the global caps. No per-session, per-IP or concurrency limit exists.
- With the world booth on, every live run pays for world calls (one per English-captioned moment, about 15-17 per 54 s with fast on) even when the viewer listens to English. The calls run one after another with no staleness check, so lines that end up dropped are still billed.
- The live stream carries skeleton events only (9-19 per scene). The micro rows the mock4 board animates from (insert/micro.json) are not streamed and have no producer script, so the board needs a new micro source per scene.
- With the answer cache on (default), a repeat of the same scene costs 0 calls but every analyst line is marked cached. Real live generation needs --live-fresh, which costs calls on every run.
- comeback-135 has no red card. Scene C's pattern set-up repeats the insert's Ibsen habit, and the opener scene is thin (9 events).
- Call counts come from an unpaced simulation with a fake model that always failed, so retries were forced. I halved the counts to get first-attempt calls. The paced director may caption slightly different fragments, so world call counts are approximate (plus or minus a few).

## Key files
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/server/app.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/server/__main__.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/pipeline/runner.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/pipeline/protocol.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/pipeline/guided.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/pipeline/demo.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/pipeline/library.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/pipeline/export.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/commentary/analyst.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/commentary/newsroom.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/tts/voices.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/tts/guarded.py
- /Users/vmt/MicroSaaS/match-voice/backend/matchvoice/tts/client.py
- /Users/vmt/MicroSaaS/match-voice/backend/scripts/bake_story_audio.py
- /Users/vmt/MicroSaaS/match-voice/docs/PROTOCOL.md
- /Users/vmt/MicroSaaS/match-voice/docs/DEPLOY.md
- /Users/vmt/MicroSaaS/match-voice/Dockerfile
- /Users/vmt/MicroSaaS/match-voice/ui/public/insert/story.json
- /Users/vmt/MicroSaaS/match-voice/ui/public/insert/micro.json
- /private/tmp/claude-501/-Users-vmt-MicroSaaS/c6d532b4-6aab-4045-9e93-9f8e4236c75b/scratchpad/scan.py
- /private/tmp/claude-501/-Users-vmt-MicroSaaS/c6d532b4-6aab-4045-9e93-9f8e4236c75b/scratchpad/win.py