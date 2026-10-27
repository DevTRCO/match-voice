# Stage 1: build the UI. The recorded demo insert in ui/public/insert is bundled into the build.
FROM node:22-slim AS ui
WORKDIR /app/ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
# the server build; the design mocks in public/ (mock*.html) are working files for the dev server and are not shipped
RUN npm run build && rm -f dist/mock*.html

# Stage 2: the server. Replay mode is the default; live mode needs a key and a call budget at run time.
# Python 3.13, the version the test suite runs on locally.
FROM python:3.13-slim AS run
# MATCHVOICE_TRUSTED_HOPS=1: the per-IP caps count the RIGHTMOST X-Forwarded-For entry, the one Container Apps' ingress (Envoy, the only
# way in) appends; entries to its left are written by the client and never counted (server/app.py client_ip). Do not set
# FORWARDED_ALLOW_IPS=*: uvicorn then takes the leftmost, client-written entry. A container published directly on a host, with no
# proxy in front, must set MATCHVOICE_TRUSTED_HOPS=0, or the client writes the counted entry itself.
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    MATCHVOICE_HOST=0.0.0.0 PORT=8000 MATCHVOICE_LIVE_CALLS=0 MATCHVOICE_TRUSTED_HOPS=1
WORKDIR /app
COPY pyproject.toml constraints.txt ./
# dependencies first, so a code edit does not reinstall them; pinned to the tested versions (constraints.txt, backend/scripts/constraints.py)
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/req.txt \
    && pip install -r /tmp/req.txt -c constraints.txt && rm /tmp/req.txt
COPY backend/matchvoice backend/matchvoice
# editable, so matchvoice.config.ROOT resolves to /app (data and ui/dist live there)
RUN pip install --no-deps -e .
COPY data/matches data/matches
COPY data/replays data/replays
# the answer cache: a public server runs fresh (MATCHVOICE_LIVE_FRESH=1) and never reads it, other live runs reuse it
COPY data/cache data/cache
COPY --from=ui /app/ui/dist ui/dist
RUN useradd --system --no-create-home app && chown -R app /app/data
USER app
EXPOSE 8000
# Container Apps ignores HEALTHCHECK: its probes on /api/health are set on the app (docs/DEPLOY.md)
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/api/health')"
CMD ["python", "-m", "matchvoice.server"]
