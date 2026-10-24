# Deploy

Nothing here has been run against a cloud account. Two targets, both free tier. Pick A for the public demo,
B only if you want the live mode on the same URL.

## Check locally first

```
docker build -t match-voice .
docker run --rm -p 8000:8000 match-voice          # replay mode, no key, http://localhost:8000
cd ui && npm ci && npm run build:static           # writes ui/dist-static
npx serve dist-static                             # any static server works, no backend needed
```

The image holds no secrets. Without a key and with `MATCHVOICE_LIVE_CALLS=0` (the default) the Live toggle is
disabled and the UI shows a **Recorded run** (earlier analyst lines, tape-delayed), labelled as such. Real-time
commentary exists only with a key and a call budget.

## A. Static Web Apps (recommended, replay only, free plan)

The static build bundles `insert/replay.json`, the recorded 30 second demo insert, so no server is needed. It is labelled
"Recorded" in the status line under the caption, says in one line that live needs the server, and uses the browser voice. It is not real-time commentary. `ui/public/staticwebapp.config.json`
is copied into the build.

```
az login
az group create -n matchvoice-rg -l westeurope
az staticwebapp create -n matchvoice-demo -g matchvoice-rg -l westeurope --sku Free
TOKEN=$(az staticwebapp secrets list -n matchvoice-demo -g matchvoice-rg --query properties.apiKey -o tsv)
cd ui && npm ci && npm run build:static
npx @azure/static-web-apps-cli deploy dist-static --deployment-token "$TOKEN" --env production
az staticwebapp show -n matchvoice-demo -g matchvoice-rg --query defaultHostname -o tsv
```

## B. Container Apps (server, live optional)

Container Apps has a monthly free grant of vCPU seconds and requests, and scales to zero. The image listens on
`$PORT` (default 8000) on `0.0.0.0`.

```
az login
az group create -n matchvoice-rg -l westeurope
az acr create -n <uniqueacrname> -g matchvoice-rg --sku Basic        # Basic is billed, about 5 USD per month
az acr build -r <uniqueacrname> -t match-voice:1 .
az containerapp env create -n matchvoice-env -g matchvoice-rg -l westeurope
az containerapp create -n matchvoice -g matchvoice-rg --environment matchvoice-env \
  --image <uniqueacrname>.azurecr.io/match-voice:1 --registry-server <uniqueacrname>.azurecr.io \
  --target-port 8000 --ingress external --min-replicas 0 --max-replicas 1 --cpu 0.5 --memory 1.0Gi
az containerapp show -n matchvoice -g matchvoice-rg --query properties.configuration.ingress.fqdn -o tsv
```

To avoid the registry cost, push the image to a public Docker Hub or GHCR repository and pass `--image` for it
instead (the image contains no secrets).

### Live mode

Two settings turn it on. Both are needed, otherwise the server reports why live is off.

```
az containerapp secret set -n matchvoice -g matchvoice-rg --secrets anthropic-key=<key>
az containerapp update -n matchvoice -g matchvoice-rg \
  --set-env-vars ANTHROPIC_API_KEY=secretref:anthropic-key MATCHVOICE_LIVE_CALLS=12
```

`MATCHVOICE_LIVE_CALLS` is the model call budget per process start, held in memory. With `--min-replicas 0` every
scale-from-zero starts a fresh budget, and answers written at runtime are lost with the ephemeral filesystem, so
the real cap is N calls per cold start. Use `--min-replicas 1` or keep it low if a hard total cap matters. Prompts already in `data/cache/analyst`
(baked into the image) cost nothing, so the three demo matches run live for free, but their analyst lines are then cached answers from earlier calls, marked "Cached" in the UI. Set `MATCHVOICE_LIVE_FRESH=1` to ignore the cache: every analyst moment is then a real call (about 8 per match) and counts against the budget. To go back to replay only,
set `MATCHVOICE_LIVE_CALLS=0`.
