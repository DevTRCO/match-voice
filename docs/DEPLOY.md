# Deploy

Live: the demo page on Azure Static Web Apps (A) and the live server on Azure Container Apps (B, app `encara-live`, Central US,
one replica, deployed 2026-10-27). GitHub Pages is prepared and not used.

## GitHub Pages (static demo, prepared, not switched on)

`.github/workflows/pages.yml` runs only when started by hand (`workflow_dispatch`): `npm ci` and `npm run build:static` in `ui/`,
a check that `index.html` and `insert/story.json` are there and no design mock is, then it uploads `ui/dist-static` and
deploys it with `actions/deploy-pages`. The site would be `https://devtrco.github.io/match-voice/`.

- The build uses relative URLs (`base: "./"` in `ui/vite.config.ts`, every fetch resolves against `document.baseURI`),
  so the same files work at `/` and under `/match-voice/`. Checked locally (2026-10-25): the static build served by
  `python3 -m http.server` under `/match-voice/` and at `/`, loaded in a headless Chrome: no console errors, no failed
  request, Play runs the story insert (68' to 71', score 0-1 to 1-1, the eight baked en/expert mp3 files fetched).
- `ui/public/mock*.html` are design mocks for the dev server. The static build removes them (`dropMocks` in
  `ui/vite.config.ts`) and the workflow fails if one is left. The server build (`npm run build`) still contains them.
- `staticwebapp.config.json` is copied into the build; Pages ignores it.

To switch it on: repository Settings, Pages, Source "GitHub Actions". **GitHub Pages on a private repository needs a
paid plan (Pro, Team or Enterprise); on a free account the repository has to be public. That is the owner's decision,
nothing here changes the visibility.** The workflow does nothing useful until Pages is enabled (the deploy job fails).

## Check locally first

```
docker build -t match-voice .
docker run --rm -p 8000:8000 match-voice          # replay mode, no key, http://localhost:8000
cd ui && npm ci && npm run build:static           # writes ui/dist-static
npx serve dist-static                             # any static server works, no backend needed
```

The image holds no secrets. Without a key and with `MATCHVOICE_LIVE_CALLS=0` (the default) live is off and the page
plays the recorded insert, labelled as such. Real-time commentary exists only with a key and a call budget.

## A. Static Web Apps (replay only, free plan): live

Deployed 2026-10-26: **https://happy-bush-012530710.5.azurestaticapps.net** (subscription "Azure subscription 1",
resource group `encara-rg`, app `encara-demo`, Free plan; westeurope did not accept new Static Web Apps, so the
resource sits in centralus, the content is served from Azure's global edge). The start page is the game-first demo
(`ui/public/mock4.html`, renamed to `index.html` by the static build); the older React guided run is `app.html`.
Redeploy after a change:

```
cd ui && npm run build:static
TOKEN=$(az staticwebapp secrets list -n encara-demo -g encara-rg --query properties.apiKey -o tsv)
npx -y @azure/static-web-apps-cli@2.0.2 deploy dist-static --deployment-token "$TOKEN" --env production
```

The original plan, kept for reference:

The static build bundles `insert/story.json`, the recorded 30 second story insert, and its baked audio, so no server is
needed. It is labelled as recorded and is not real-time commentary. `ui/public/staticwebapp.config.json` is copied into the build.

```
az login
az group create -n matchvoice-rg -l westeurope
az staticwebapp create -n matchvoice-demo -g matchvoice-rg -l westeurope --sku Free
TOKEN=$(az staticwebapp secrets list -n matchvoice-demo -g matchvoice-rg --query properties.apiKey -o tsv)
cd ui && npm ci && npm run build:static
npx @azure/static-web-apps-cli deploy dist-static --deployment-token "$TOKEN" --env production
az staticwebapp show -n matchvoice-demo -g matchvoice-rg --query defaultHostname -o tsv
```

## B. Container Apps: the public live server ("Generate run", docs/live/PLAN.md)

Deployed 2026-10-27 as `encara-live`. One container serves the API for the page on Static Web Apps: `/api/session`, `/api/scene`, `/ws`,
`/api/tts`, `/api/health`. The page stays on Static Web Apps and calls the API by absolute URL (CORS and the WebSocket Origin
check allow only `MATCHVOICE_ALLOWED_ORIGINS`). Decisions: region **centralus** (known good for this subscription), **ACR Basic**
with the image built locally by **`docker buildx`** and pushed (ACR Tasks, so `az acr build`, are not allowed on this subscription), **min = max = 1 replica** (every cap is counted in memory: one
replica keeps them true, a second one would split them and `/api/tts` would not find runs of the other), 0.5 vCPU, 1 GiB, probes on
`/api/health`, keys as Container Apps secrets referenced with `secretref:`, never printed.

What the image holds (`.dockerignore` keeps `video/`, `data/corpus`, `docs`, the stray root `*.json` and every `.env` out of the
build context, so the build context is a few MB, not 1.6 GB): the server, `data/matches` (comeback-135 is on disk), `data/replays`,
`data/cache/analyst` (not read when `MATCHVOICE_LIVE_FRESH=1`), and `ui/dist` without the design mocks. Python packages are installed
with `-c constraints.txt`, the versions of the tested `.venv` (`backend/scripts/constraints.py` regenerates it). `MATCHVOICE_TRUSTED_HOPS=1`
is set in the image: behind the ingress the per-IP caps count the rightmost `X-Forwarded-For` entry, the address Envoy appends. Envoy
keeps whatever the client sent to the left of it, so `FORWARDED_ALLOW_IPS=*` (uvicorn then takes the leftmost entry) would let any client
pick its own address and dodge the per-IP caps; the image no longer sets it. An app created with it as an env var drops it with
`az containerapp update -n $APP -g $RG --remove-env-vars FORWARDED_ALLOW_IPS -o none`.

```
cd /Users/vmt/MicroSaaS/match-voice
RG=encara-rg; LOC=centralus
ACR=encaramv$(openssl rand -hex 3); APP=encara-live; ENV=encara-env
az provider register -n Microsoft.App --wait
az provider register -n Microsoft.ContainerRegistry --wait
az provider register -n Microsoft.OperationalInsights --wait
az acr create -n $ACR -g $RG -l $LOC --sku Basic --admin-enabled false -o none   # about 5 USD per month
az acr login -n $ACR
TAG=$(date +%Y%m%d-%H%M); docker buildx build --platform linux/amd64 -t $ACR.azurecr.io/match-voice:$TAG --push .
# where ACR Tasks are allowed: az acr build -r $ACR -t match-voice:$TAG .
az containerapp env create -n $ENV -g $RG -l $LOC --logs-destination none -o none
az containerapp create -n $APP -g $RG --environment $ENV \
  --image $ACR.azurecr.io/match-voice:$TAG --registry-server $ACR.azurecr.io --registry-identity system \
  --ingress external --target-port 8000 --transport auto \
  --min-replicas 1 --max-replicas 1 --cpu 0.5 --memory 1.0Gi --revisions-mode single \
  --env-vars MATCHVOICE_NO_DOTENV=1 MATCHVOICE_LIVE_CALLS=0 -o none
# secrets: the values are read through matchvoice.config (which never prints them), go straight into az, and are unset after
ANTH=$(.venv/bin/python -c "from matchvoice.config import anthropic_api_key as k; print(k() or '')")
EL=$(.venv/bin/python -c "from matchvoice.config import elevenlabs_api_key as k; print(k() or '')")
SESS=$(openssl rand -hex 32)
az containerapp secret set -n $APP -g $RG --secrets anthropic-key="$ANTH" elevenlabs-key="$EL" session-secret="$SESS" -o none
unset ANTH EL SESS
az containerapp update -n $APP -g $RG -o none --set-env-vars \
  ANTHROPIC_API_KEY=secretref:anthropic-key ELEVENLABS_API_KEY=secretref:elevenlabs-key \
  MATCHVOICE_SESSION_SECRET=secretref:session-secret \
  MATCHVOICE_PUBLIC=1 MATCHVOICE_LIVE_FRESH=1 \
  MATCHVOICE_ALLOWED_ORIGINS=https://happy-bush-012530710.5.azurestaticapps.net,http://localhost:5173 \
  MATCHVOICE_LIVE_CALLS=4000 MATCHVOICE_DAILY_CALLS=600 MATCHVOICE_LIVE_RUNS_PER_DAY=150 MATCHVOICE_LIVE_MAX_SECONDS=75 \
  MATCHVOICE_SESSION_RUNS=1 MATCHVOICE_IP_RUNS=10 MATCHVOICE_LIVE_CONCURRENT=3 \
  MATCHVOICE_TTS_CREDITS=45000 MATCHVOICE_TTS_DAILY_CREDITS=3000 MATCHVOICE_SESSION_CREDITS=900 \
  MATCHVOICE_IP_CREDITS=1500 MATCHVOICE_RUN_VOICE_CHANNELS=2 MATCHVOICE_WORLD_CALLS=0
az containerapp show -n $APP -g $RG --query properties.configuration.ingress.fqdn -o tsv
```

The secret values briefly appear in the az process arguments (visible to `ps` on this Mac); Key Vault references are the stricter
option. `az containerapp show` output carries no secret values.

**Environment** (all read by `python -m matchvoice.server`; defaults in brackets):

| Variable | Value here | Meaning |
| --- | --- | --- |
| `MATCHVOICE_NO_DOTENV` | `1` | never look for a `.env` in the container |
| `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `MATCHVOICE_SESSION_SECRET` | `secretref:` | the model key, the voice key, the HMAC key of the session tokens (without it a public server refuses live) |
| `MATCHVOICE_PUBLIC` | `1` | live only for the whitelisted scenes (`pipeline/scenes.py`), at speed 1, paced, for a valid session; replay stays open |
| `MATCHVOICE_LIVE_FRESH` | `1` | every live run makes its own model calls, no answer cache read |
| `MATCHVOICE_ALLOWED_ORIGINS` | the SWA URL, localhost dev | CORS and the WebSocket Origin check; unset means any origin. The server's own origin (a page it serves itself, Origin host equal to the request's Host) is always allowed. Leave CORS in the Container Apps ingress off, so it is not handled twice |
| `MATCHVOICE_LIVE_CALLS` | [0] | lifetime model call budget of the process; 0 turns live off. The daily cap below is the real limit |
| `MATCHVOICE_DAILY_CALLS` | [600] | model calls per UTC day, core and world booth together |
| `MATCHVOICE_LIVE_RUNS_PER_DAY` | [150] | live runs per UTC day, all visitors |
| `MATCHVOICE_LIVE_MAX_SECONDS` | [75] | longest live run in match seconds |
| `MATCHVOICE_SESSION_RUNS` | `1` [3] | live runs per browser session (public server: 1) |
| `MATCHVOICE_IP_RUNS` | [10] | live runs per client address per UTC day |
| `MATCHVOICE_LIVE_CONCURRENT` | [3] | live runs at once |
| `MATCHVOICE_TTS_CREDITS` | [300] | lifetime ElevenLabs credits, counted from the ledger in `data/cache/tts` (ephemeral in the container: a restart refills it) |
| `MATCHVOICE_TTS_DAILY_CREDITS` | [3000] | ElevenLabs credits per UTC day (the ledger rows of the day) |
| `MATCHVOICE_SESSION_CREDITS` | [900] | ElevenLabs credits per browser session; past it the page uses the browser voice |
| `MATCHVOICE_IP_CREDITS` | [1500] | ElevenLabs credits per client address per UTC day, so new sessions do not refill the voice |
| `MATCHVOICE_RUN_VOICE_CHANNELS` | [2] | channels one live run may voice (the one watched plus one switch); the first lines asked for fix them |
| `MATCHVOICE_WORLD_CALLS` | [0] | a separate budget for the world booth; at 0 a public server still offers the world channels on request (`world=1`), paid from the daily cap |
| `MATCHVOICE_TRUSTED_HOPS` | `1` (image) [0] | proxies in front that append to `X-Forwarded-For`; the per-IP caps count the entry this many places from the right (never a client-written one). 0 counts the socket peer. A container with no proxy in front must set 0 |
| `FORWARDED_ALLOW_IPS` | unset [127.0.0.1] | uvicorn's trusted proxies; never `*` (uvicorn then trusts the leftmost, client-written entry). The caps do not read it |

**Probes.** Container Apps ignores the Dockerfile `HEALTHCHECK`. `az containerapp show -n $APP -g $RG -o yaml > app.yaml`, add under
`properties.template.containers[0]`:

```
probes:
- {type: Startup, httpGet: {path: /api/health, port: 8000}, periodSeconds: 2, failureThreshold: 30}
- {type: Readiness, httpGet: {path: /api/health, port: 8000}, periodSeconds: 10}
- {type: Liveness, httpGet: {path: /api/health, port: 8000}, periodSeconds: 30, timeoutSeconds: 3}
```

then `az containerapp update -n $APP -g $RG --yaml app.yaml -o none`. `/api/health` is cheap (no model call, no file other than the voice ledger).

**WebSocket.** The HTTP ingress (`--transport auto`) carries WebSockets; its idle timeout (240 s) is far above a 60 s run with
heartbeats every 0.25 s. The page must connect with `wss://`.

**Smoke test** (no model call, no credit): `curl -s https://<fqdn>/api/health`, `curl -s https://<fqdn>/api/scene`,
`curl -s https://<fqdn>/api/session`.

**Redeploy:**
```
TAG=$(date +%Y%m%d-%H%M); docker buildx build --platform linux/amd64 -t $ACR.azurecr.io/match-voice:$TAG --push . && az containerapp update -n $APP -g $RG --image $ACR.azurecr.io/match-voice:$TAG -o none
```

Where ACR Tasks are allowed, `az acr build -r $ACR -t match-voice:$TAG .` replaces the buildx step. The live app uses
`ACR=encaramv630916`.

**Counters reset on every restart and every new revision** (the daily calls, runs, sessions, IP counts and the voice ledger), and old
and new revisions overlap for a moment. That is the price of keeping them in memory; Azure Files on `data/cache` would keep the voice
ledger. Cost: about 10 USD a month for the always-on replica plus about 5 USD for ACR Basic, plus model and voice spend, which the
daily caps bound (600 Haiku calls and 3,000 ElevenLabs credits a day at most).

To go back to replay only, set `MATCHVOICE_LIVE_CALLS=0`.
