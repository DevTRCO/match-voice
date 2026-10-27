# Live "New run" demo: plan (2026-10-27, night)

Founder brief (2026-10-27 00:10): the public demo gets a "New run". The server simulates ANOTHER scene from the same match
(comeback-135, Wexmoor Athletic vs Tamsworth Wanderers, same players) live, and the page shows directly what happens: the
generated match data as it arrives, the agents at work with real times, the commentary spoken. Limits per browser session.
Founder approved planning and building overnight ("planen + machen"). Not approved: push, making the repo public.

Input: docs/live/UNDERSTAND.md (three read-only reports: backend, page, deploy).

## Decisions
- Scene: comeback-135 window 5415 to 5490 (75 s, the production run cap). Superseded 2026-10-27 (founder: "massively optimise only the LIVE
  mode: better, more logical match flows"): the plain match's window stuck the ball at the corner flag (13 of 17 actions on the clamp
  edge, 0 m passes) and every New run streamed the same rows. Now the play is generated per run (`sim/scene.py`, `Library.scene_bundle`):
  the plain match up to Tamsworth's goal kick at 5408.6 (1-1, 88'), then a new 45 to 55 s phase from that goal kick (build-up under
  Wexmoor's press, a turnover, an attack with one of five finishes) and the 2-1 for Wexmoor inside 5462 to 5471.5 (89'); the seed is
  new per run (`hello.scene_seed`), the scorer is one of Wexmoor's attackers or central midfielders (Tavares about 30 percent). Receivers stand where the page
  already draws them (`sim/sceneshape.py` ports the page's shape model), passes are 6 to 50 m with flight times from their length, no
  ball on a line. `seed=` only on a server that is not public. Whitelisted on the public server; no other match or window can be started
  there. Scene list in code so a second scene can be added.
- Every public run is fresh: real model calls, no answer cache reads (`live_fresh`), so lines differ run to run and latencies are real.
- Runner on the server runs like the recorded insert: `fast=True`, pattern detector on, booth state per run, world booth on every run (page sends `world=1` whenever `today.world`, since 2026-10-27 night, about 12 extra calls a run, so all nine languages can be switched to; before: only when the
  viewer's commentator is a world channel (`world=1`), so an English viewer does not pay for six world languages.
- Enriched rows (the board's motion source, today insert/micro.json) are streamed as a new additive message `row` at the time each row
  becomes known (no lookahead). Documented in docs/PROTOCOL.md.
- Voice: ElevenLabs `eleven_flash_v2_5`, one voice per person (cast from backend/scripts/bake_story_audio.py CAST), all 9 languages;
  only lines of the viewer's channel are synthesised; browser voice fallback; the page says which voice is in use.
- Limits (env, defaults):
  - session token: HMAC-signed, issued by `GET /api/session`, kept in sessionStorage, sent on /ws and /api/tts; 1 run per session (env MATCHVOICE_SESSION_RUNS=1 since 2026-10-27 night, was 3).
  - per client IP: 10 runs per UTC day. The address is the rightmost X-Forwarded-For entry (MATCHVOICE_TRUSTED_HOPS=1, the one Envoy
    appends); FORWARDED_ALLOW_IPS=* was dropped after review (2026-10-27): uvicorn then trusts the leftmost, client-written entry.
  - concurrency: 3 live runs at once.
  - global per UTC day: 150 runs, 600 model calls (core plus world), 3,000 ElevenLabs credits; when voice credits are out the
    browser voice takes over, when calls are out the run is refused with an honest note and the recorded run stays.
  - counters in memory; one replica (min = max = 1) so they hold; a restart resets them (documented).
- Origins: CORS and a WebSocket Origin check from `MATCHVOICE_ALLOWED_ORIGINS` (SWA URL plus localhost dev).
- Page (ui/public/mock4.html): live branch that collects the stream into the same {demo, hello, messages} shape and rebuilds
  D/P/RUNS/INTEL about 4 times a second; board plays 1 s behind the generator (stated on the page; was 3 s until the `run` cues of
  2026-10-27 gave the board the receivers' runs 2.5 s before each kick); a live run opens in How mode so
  data, agents and voice are visible; after `end` the run behaves like a recording (seek, replay, other commentator).
  "New run" as a button in the top bar next to "How does it work" (only while a run can start; runs left beside it, hidden on a phone,
  in its tooltip and aria-label) and on the end screen (the top bar button hides there, so the count is shown once). The start screen
  shows only the reason after a refused click. Fallback to the recorded run on any refusal.
- Recorded run label: "Recorded from a real run of the engine. The agents wrote and checked every line; this page replays it at match pace."
- Hosting: Azure Container Apps in centralus (known good region), ACR Basic with `az acr build` (local Docker is broken),
  min = max = 1 replica, 0.5 vCPU, 1 GiB, probes on /api/health; .dockerignore excludes video/, data/corpus, docs, stray root JSON.
  Keys as Container Apps secrets, never printed. Static page stays on Static Web Apps and calls the API by absolute URL.

## Spend for testing (self-imposed, report in the morning)
At most 40 Haiku calls and 3,000 ElevenLabs credits for end-to-end tests. Unit tests use fakes only.

## Order
1. Backend (now, parallel to the video job): server changes, tests, docs/PROTOCOL.md.
2. Page (after the video job finishes, because the video captures mock4.html).
3. Deploy to Container Apps, wire the page, redeploy the static site.
4. End-to-end test with real calls in a headless browser against the deployed server; independent review; fixes.
