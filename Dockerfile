# Stage 1: build the UI. The recorded demo insert in ui/public/insert is bundled into the build.
FROM node:22-slim AS ui
WORKDIR /app/ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

# Stage 2: the server. Replay mode is the default; live mode needs a key and a call budget at run time.
FROM python:3.12-slim AS run
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    MATCHVOICE_HOST=0.0.0.0 PORT=8000 MATCHVOICE_LIVE_CALLS=0
WORKDIR /app
COPY pyproject.toml ./
# dependencies first, so a code edit does not reinstall them
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/req.txt \
    && pip install -r /tmp/req.txt && rm /tmp/req.txt
COPY backend/matchvoice backend/matchvoice
# editable, so matchvoice.config.ROOT resolves to /app (data and ui/dist live there)
RUN pip install --no-deps -e .
COPY data/matches data/matches
COPY data/replays data/replays
COPY data/cache data/cache
COPY --from=ui /app/ui/dist ui/dist
RUN useradd --system --no-create-home app && chown -R app /app/data
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/api/health')"
CMD ["python", "-m", "matchvoice.server"]
