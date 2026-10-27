# Voice cast: one voice per commentator

Proposal only. Nothing in the code was changed, no voice was added or removed, no text-to-speech call was made.
Sources, collected 2026-10-25 with zero credits: `GET /v1/voices` (the account's 53 voices: 21 premade, 22 copied from the
library, 10 generated), `GET /v1/shared-voices` (the public library, for the "add a voice" option) and `GET /v1/user/subscription`
(read only: starter tier, 10 of 10 voice slots used, 11,300 of 33,800 characters used this period, so about 22,500 credits left).

The people come from `ui/public/mock3.html`; ages are read from the placeholder faces in `ui/public/faces`.
Previews are the `preview_url` the API returns: free samples the service made, not our text. Links on `api.us.elevenlabs.io`
carry a timestamp and may stop working after a few days; the `storage.googleapis.com` links are stable. Listen before deciding.

## Summary

| Person | Seat | Recommended voice (in the account today) | Native? | Alternative |
|---|---|---|---|---|
| Charlie Hale | en/expert, lead | Charlie `IKne3meq5aSn9XLyUdCD` (premade) | Australian English | Brian `nPczCjzI2devNBz1zQrb` (premade) |
| Owen Carter | en/beginner, lead | Liam `TX3LPaxmHKxFdv7VOQHJ` (premade) | American English | Derek `Q0Et7LOU7VpeoeCRQAVS` (library copy, already added) |
| Jonas Weber | de/expert, lead | Marcus `vGWWh1bodhwwi4yHd6qZ` (library copy, already added) | **native German** | Jonas Berger `K8bIZwDsGMHreGKTIVHN` (already added) |
| Felix Brandt | de/beginner, lead | Leo `iQ5dS7juUUF7zgIVf8ET` (library copy, already added) | **native German** | Hannes `GZckiELWRyqX481UWTDl` (already added) |
| Hugo Martin | fr/expert, lead | George `JBFqnCBsd6RMkjVDRZzb` (premade) | **no**: British voice, verified for French | Eric `cjVigY5qzO86Huf0OWal` (premade) |
| Théo Laurent | fr/beginner, lead | Will `bIHbv24MWmeRgasZH58o` (premade) | **no**: American voice, verified for French | Mark `UgBBYS2sOqTuMpoF3BR0` (already added) |
| Daniel Price | co-commentator, all six booths | Daniel `onwK4e9ZLuTAKqWW03F9` (premade) | British English, verified for German, **not** for French | Bill `pqHfZKP75CvOlQylNhV4` (premade) |

Seven different voices, all male, all usable today without a free slot. English and German are covered well;
French has **no native male voice in the account** (see "French gap" below).

"Verified for French" means the service lists the voice under `verified_languages` with a French preview (made with
`eleven_multilingual_v2`). It still sounds like an English speaker who speaks very good French, not like a French broadcaster.

## Per person

### Charlie Hale (en/expert, about 40, tactical, calm in the build-up)

**Recommended: Charlie - Deep, Confident, Energetic**, `IKne3meq5aSn9XLyUdCD`, premade
- Labels: male, young, australian, conversational, hyped. Verified: en, es, fil, pt, zh. Flash v2.5: high quality.
- Why: it is the voice already baked for en/expert in `ui/public/insert/story-audio`, so keeping it costs nothing and the
  name matches. Deep enough for a 40-year-old; the build-up lines run on calm settings, the goal on peak. The mismatch is
  "hyped" against "calm expert", which the energy settings handle.
- Preview: [en](https://api.us.elevenlabs.io/v1/voices/IKne3meq5aSn9XLyUdCD/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiIxMDJkZTZmMi0yMmVkLTQzZTAtYTFmMS0xMTFmYTc1YzU0ODEubXAzIiwidGltZXN0YW1wIjoxNzkyOTUxMjAwMDAwMDAwfQ%3D%3D)

Alternative: **Brian - Deep, Resonant and Comforting**, `nPczCjzI2devNBz1zQrb`, premade. Male, middle_aged, american,
classy, social_media. A calmer, older expert sound. Costs a re-bake of channel 1 (about 232 credits).
[preview](https://api.us.elevenlabs.io/v1/voices/nPczCjzI2devNBz1zQrb/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiIyZGQzZTcyYy00ZmQzLTQyZjEtOTNlYS1hYmM1ZDRlNWFhMWQubXAzIiwidGltZXN0YW1wIjoxNzkyOTUxMjAwMDAwMDAwfQ%3D%3D)

### Owen Carter (en/beginner, about 30, explains what just happened)

**Recommended: Liam - Energetic, Social Media Creator**, `TX3LPaxmHKxFdv7VOQHJ`, premade
- Labels: male, young, american, confident, social_media. Verified: cs, de, en, hi, pl, pt, tr. Flash v2.5: listed as a
  high-quality model.
- Why: young, warm and energetic, easy to tell apart from Charlie's deeper voice. The creator register suits a newcomer
  channel that explains. Downside: American, while the rest of the English booth is British or Australian.
- Preview: [en](https://storage.googleapis.com/eleven-public-prod/premade/voices/TX3LPaxmHKxFdv7VOQHJ/63148076-6363-42db-aea8-31424308b92c.mp3)

Alternative: **Derek - Fun & Energetic Capture Attention**, `Q0Et7LOU7VpeoeCRQAVS`, already added. Male, young, american,
casual, advertisement. Radio and podcast host. English only.
[preview](https://storage.googleapis.com/eleven-public-prod/database/workspace/89ae3edb17064b4f91c1ae8609b5572f/voices/Q0Et7LOU7VpeoeCRQAVS/8b6573b8-1f6c-4819-8a4c-7a3b03e5c814.mp3)

### Jonas Weber (de/expert, about 40, glasses, tactics and numbers, clear language)

**Recommended: Marcus - for ads, Spotify, commercials, promo, brands, radio**, `vGWWh1bodhwwi4yHd6qZ`, already added
- Labels: male, middle_aged, standard German (de-DE), professional, advertisement. Flash v2.5: fine-tuned.
- Why: native German, TV and radio announcer, "strong, clear, trusted". Fits a precise expert with authority, and has
  the presence for a goal call.
- Preview: [de](https://storage.googleapis.com/eleven-public-prod/database/workspace/9d5daecd4210450281f8157fe899598f/voices/vGWWh1bodhwwi4yHd6qZ/AYWXonxIZlUhcxjlSp1l.mp3)

Alternative: **Jonas Berger - Gentle and Steady**, `K8bIZwDsGMHreGKTIVHN`, already added. Male, middle_aged, standard German,
neutral, informative_educational. Native, measured and clear; likely too soft for the goal call.
[preview](https://api.us.elevenlabs.io/v1/voices/K8bIZwDsGMHreGKTIVHN/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJjdXN0b20iLCJ3b3Jrc3BhY2VfaWQiOiI4NDk4MGY0NGQ5MjY0NjBmYjYyMDZmNmQwMzUxODBjNiIsImZpbGVuYW1lIjoiam5uR3gxSEtBVDJtRkNPbjVDWkMubXAzIiwidGltZXN0YW1wIjoxNzkyOTUxMjAwMDAwMDAwfQ%3D%3D)

### Felix Brandt (de/beginner, about 30, explains every scene)

**Recommended: Leo - Uplifting Advertisement Voice**, `iQ5dS7juUUF7zgIVf8ET`, already added
- Labels: male, young, standard German (de-DE), crisp, advertisement. Flash v2.5: fine-tuned.
- Why: the only young native German male in the account. Friendly, uplifting, clear: right for a newcomer channel, and
  clearly younger than Marcus.
- Preview: [de](https://storage.googleapis.com/eleven-public-prod/database/workspace/fb4a273526394da1b409cb2ecb65e2d6/voices/iQ5dS7juUUF7zgIVf8ET/dZH8Hlae7NTgyp85ywjT.mp3),
  [de, Flash v2.5 sample](https://api.us.elevenlabs.io/v1/voices/iQ5dS7juUUF7zgIVf8ET/previews/audio?payload=eyJraW5kIjoidmVyaWZpZWRfbGFuZ3VhZ2UiLCJsYW5ndWFnZSI6ImRlIiwibW9kZWxfaWQiOiJlbGV2ZW5fZmxhc2hfdjJfNSJ9)

Alternative: **Hannes - Grounded & Intimate**, `GZckiELWRyqX481UWTDl`, already added. Male, middle_aged, standard German,
calm, conversational. Native and natural, but low energy and older than Felix looks.
[preview](https://storage.googleapis.com/eleven-public-prod/database/workspace/b28cc4a9d0384cf9857840644b429281/voices/GZckiELWRyqX481UWTDl/PLsRUQWVWjiKeeM2xSuC.mp3)

### Hugo Martin (fr/expert, about 40, tactics and precision)

**Recommended: George - Warm, Captivating Storyteller**, `JBFqnCBsd6RMkjVDRZzb`, premade. **Not native.**
- Labels: male, middle_aged, british, mature, narrative_story. Verified: ar, cs, en, es, fil, fr (fr-FR), hi, ja.
  Flash v2.5: listed as a high-quality model.
- Why: right age and a mature, warm sound for a precise expert; verified for French with a French sample. Weak on the goal call.
- Preview: [fr](https://api.us.elevenlabs.io/v1/voices/JBFqnCBsd6RMkjVDRZzb/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiI2MDk2YWNjZS1lMThmLTRlOTUtYThlMy1iYjFjMGEyNzYyNGUubXAzIiwidGltZXN0YW1wIjoxNzkyOTUxMjAwMDAwMDAwfQ%3D%3D),
  [en](https://api.us.elevenlabs.io/v1/voices/JBFqnCBsd6RMkjVDRZzb/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiJlNjIwNmQxYS0wNzIxLTQ3ODctYWFmYi0wNmE2ZTcwNWNhYzUubXAzIiwidGltZXN0YW1wIjoxNzkyOTUxMjAwMDAwMDAwfQ%3D%3D)

Alternative: **Eric - Smooth, Trustworthy**, `cjVigY5qzO86Huf0OWal`, premade. Male, middle_aged ("a man in his 40s"), american,
classy. Verified for fr and de.
[fr preview](https://storage.googleapis.com/eleven-public-prod/premade/voices/cjVigY5qzO86Huf0OWal/4c076868-22c6-42a6-9edd-b836f6a33f9f.mp3)

### Théo Laurent (fr/beginner, late 20s, explains every action)

**Recommended: Will - Relaxed Optimist**, `bIHbv24MWmeRgasZH58o`, premade. **Not native.**
- Labels: male, young, american, chill, conversational. Verified for fr (fr-FR) and de. Flash v2.5: fine-tuned.
- Why: the only young male premade verified for French. Relaxed and friendly suits a channel that explains; clearly
  younger than George.
- Preview: [fr](https://storage.googleapis.com/eleven-public-prod/premade/voices/bIHbv24MWmeRgasZH58o/a46e8450-1b81-4370-adbc-f6b504a409ad.mp3)

Alternative: **Mark - Natural Conversations**, `UgBBYS2sOqTuMpoF3BR0`, already added. Male, young, american, casual.
Verified for fr on multilingual v2, but **Flash v2.5 is not among its high-quality models**, so live lines may sound worse.
[fr preview](https://storage.googleapis.com/eleven-public-prod/database/user/y7Wmp2r8nCeGkLiXiwMOVWktro13/voices/UgBBYS2sOqTuMpoF3BR0/a9e71ad8-57c9-426d-91a4-9bc80eee2a3f.mp3)

### Daniel Price (co-commentator in all six booths, about 55, grey hair)

**Recommended: Daniel - Steady Broadcaster**, `onwK4e9ZLuTAKqWW03F9`, premade
- Labels: male, middle_aged, british, formal, informative_educational. Verified: de, en, tr. Flash v2.5: fine-tuned.
- Why: what the build uses today, the name matches, and his en/expert lines are already baked. A steady British pundit
  reads as the oldest voice in every booth. He is verified for German; **in French he has no verified sample**, so the
  French booth's analysis will carry an English accent. In the story a British guest pundit speaking French is
  plausible, but listen first.
- Previews: [en](https://api.us.elevenlabs.io/v1/voices/onwK4e9ZLuTAKqWW03F9/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiI3ZWVlMDIzNi0xYTcyLTRiODYtYjMwMy01ZGNhZGMwMDdiYTkubXAzIiwidGltZXN0YW1wIjoxNzkyOTUxMjAwMDAwMDAwfQ%3D%3D),
  [de](https://api.us.elevenlabs.io/v1/voices/onwK4e9ZLuTAKqWW03F9/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiI3YzMwYzY2MS04NDQ4LTRhMWUtYjdiNy1iNWI2MjllYzY0MWIubXAzIiwidGltZXN0YW1wIjoxNzkyOTUxMjAwMDAwMDAwfQ%3D%3D)

Alternative: **Bill - Wise, Mature, Balanced**, `pqHfZKP75CvOlQylNhV4`, premade. Male, **old**, american, crisp. The only
older male premade verified for **both** de and fr, so the co-commentator would sound equally good in all three booths.
American rather than British, and the en/expert analyst lines would need a re-bake (2 lines, about 138 credits; 1-163 is stale and re-baked anyway).
[fr preview](https://storage.googleapis.com/eleven-public-prod/premade/voices/pqHfZKP75CvOlQylNhV4/ef978e66-26c2-446e-94fc-81b4362d71b1.mp3),
[de preview](https://storage.googleapis.com/eleven-public-prod/premade/voices/pqHfZKP75CvOlQylNhV4/a1eee806-7c72-46c4-9270-dc9256ddffe6.mp3)

## French gap and what a library voice would mean

The account has no male voice whose own language is French. All 22 library copies are German or English; the French
recommendations above are English premade voices that are verified for French.

Native French options from the library (free to preview, current previews from `GET /v1/shared-voices`):

| Voice | Labels | Fits | Preview |
|---|---|---|---|
| Simon - Cheerful, Energetic and Rapid `mvhJVdVoTWVUtL4keT7W` | male, young, parisian, fr-FR, excited | Théo (fr/beginner) | [fr](https://api.us.elevenlabs.io/v1/voices/mvhJVdVoTWVUtL4keT7W/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJjdXN0b20iLCJ1c2VyX2lkIjoiSTdoV3lYYUNZMmdnODlkN0hBTDZGVFk1WkdwMSIsImZpbGVuYW1lIjoid0xpcUNzbnJtYnhrQjMyVDNqcjUubXAzIiwidGltZXN0YW1wIjoxNzkyOTUxMjAwMDAwMDAwfQ%3D%3D) |
| Nicolas Petit - Radio Host `WUAdt1wuIPYQ1XruI5dW` | male, middle_aged, parisian, fr-FR, professional | Hugo (fr/expert) | [fr](https://storage.googleapis.com/eleven-public-prod/database/workspace/7593eab373974d1db7d45255c5986d46/voices/WUAdt1wuIPYQ1XruI5dW/Y9TxSmJ1rLXBCHMvc6Cz.mp3) |

German library voices described as football commentators (John `iQgleKwj2ZKxy6MvS4xe`, "the sound of a German football
stadium"; Chris `Qvd9mju8GJ7MsKzX6FFA`, "your slightly excited commentator") are listed in docs/VOICES.md. Marcus and Leo
are good enough that German does not need them.

Slots: the account is on the starter tier with **10 of 10 voice slots used** (`voice_slots_used` = `voice_limit` = 10).
Adding Simon and Nicolas Petit means removing two voices first. Candidates that this project does not use: the German
female library copies (Ela, Irene, Miranda, Susi and others) and the generated `idol-voice-*` voices, which belong to another
project of the user. Removing a voice is the account owner's call. Adding costs no credits; synthesis with a library voice
is billed like any other voice. Not done.

## Ready to apply (not applied)

Shaped like `backend/matchvoice/tts/voices.py`. Today `voice_for(lang)` picks by language only and
`bake_insert_audio.voice_of` hardcodes Charlie for every `pbp` line, so applying this needs both to look up by channel
(`"<lang>/<level>"`) and role (`pbp` = lead, `analyst` = co-commentator). The bake script passes a voice id string to
`client.synth`, so it would call `voice_of(...).id`. `GuardedTTS` (`tts/guarded.py`, lines 94 and 110) also calls `voice_for(lang)`
for the live `/api/tts` path and its cache key; the UI no longer uses that path, but it would need the channel too if it stays.

```python
# Lead commentator per channel (lang/level); the co-commentator speaks the analysis in every booth.
LEADS: dict[str, Voice] = {
    "en/expert":   Voice("IKne3meq5aSn9XLyUdCD", "Charlie"),       # Charlie Hale, premade, already baked
    "en/beginner": Voice("TX3LPaxmHKxFdv7VOQHJ", "Liam"),          # Owen Carter, premade
    "de/expert":   Voice("vGWWh1bodhwwi4yHd6qZ", "Marcus"),        # Jonas Weber, native German, already added
    "de/beginner": Voice("iQ5dS7juUUF7zgIVf8ET", "Leo"),           # Felix Brandt, native German, already added
    "fr/expert":   Voice("JBFqnCBsd6RMkjVDRZzb", "George"),        # Hugo Martin, premade, verified fr (not native)
    "fr/beginner": Voice("bIHbv24MWmeRgasZH58o", "Will"),          # Théo Laurent, premade, verified fr (not native)
}
CO_COMMENTATOR = Voice("onwK4e9ZLuTAKqWW03F9", "Daniel")          # Daniel Price, premade; not verified for fr


def voice_of(channel: str, role: str) -> Voice:
    """channel is "<lang>/<level>"; role is the say line's voice field: "pbp" (lead) or "analyst" (co-commentator)."""
    return CO_COMMENTATOR if role == "analyst" else LEADS[channel]
```

## Credits to bake the recorded insert with this cast

The UI loads `ui/public/insert/story.json` (with `insert/story-audio`); `replay.json` is only the fallback.
Counted with the bake script's own functions (`lines`, `text_of`, `energy_of`, `model_of`) and `CREDITS_PER_CHAR`
(Flash v2.5 0.5 per character, eleven_v3 1.0 per character, the latter marked in the code as an assumption). Characters are
the text actually sent (after `shape_for_tts` and `hype_for_tts`). Per channel: 8 lines, 6 lead (5 calm on Flash, the goal
call on v3) and 2 co-commentator (1 calm on Flash, 1 lifted on v3).

Counted on `story.json` as of 2026-10-25 19:34 (the file was re-exported during this task; an earlier count at 19:2x gave
1,408 in total, so recount with the dry run right before baking).

| Channel | Lead | Characters (Flash / v3) | Credits |
|---|---|---|---|
| 0 en/beginner | Owen (Liam) | 174 / 156 | 243 |
| 1 en/expert | Charlie (Charlie) | 155 / 155 | 232, **already baked except 1-163** |
| 2 de/beginner | Felix (Leo) | 186 / 163 | 256 |
| 3 de/expert | Jonas (Marcus) | 158 / 151 | 230 |
| 4 fr/beginner | Théo (Will) | 190 / 154 | 249 |
| 5 fr/expert | Hugo (George) | 173 / 142 | 228 |
| **All six** | | 1,036 / 921 | **about 1,439** |

- With the recommended cast, channel 1 is on disk with the same voices, so the script's dry run (`--insert story`) reports
  **40 lines, 1,647 characters, about 1,206 credits** for channels 0 and 2 to 5.
- Plus **about 99 credits** for `story-audio/1-163.mp3` (Daniel's goal analysis, eleven_v3, 99 characters): CLAUDE.md marks it
  STALE (it speaks the old template line), and the script skips it because the file exists. Delete it first.
  Total to bake with this cast: **about 1,305 credits**. That is over the script's default `--max-credits 900`, so it needs
  `--max-credits 1400` or two runs.
- Choosing Brian for Charlie Hale adds the rest of channel 1 (about 133 more, 232 in all); choosing Bill as co-commentator
  adds the other channel 1 analyst line (about 39; 1-163 is re-baked anyway). Existing files are skipped, so delete them first.
- Caveat on the estimate: en/expert cost 475 credits on the counter (CLAUDE.md), against 232 estimated for its current 8 lines.
  `story-audio` holds 17 files for channel 1, so earlier versions of the insert were baked too; the difference is most likely
  those, but eleven_v3 could also bill more than 1.0 per character. Read the subscription counter after the first channel
  (`--channel 0`) before baking the rest. About 22,500 credits are left in the current period.
