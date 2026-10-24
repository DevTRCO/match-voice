# Voice candidates for a sports-commentator sound

Collected on 2026-10-20 from two free ElevenLabs endpoints, with zero credits spent and no voice added to the account:
`GET /v1/voices` (the account's own list, 53 voices: 21 premade, 22 professional copies from the library, 10 generated) and
`GET /v1/shared-voices` (the public Voice Library, searched with `search`, `language`, `use_cases`, `descriptives`; about 270 distinct
voices came back across the queries). Every preview below is the `preview_url` the API returns, a short sample the service made
itself. Nothing here was synthesised with our text. The ranking is from labels and descriptions only; **listen first**, then decide.

How to read it
- **Premade** voices need no slot and work today. Voices marked "already added" are in the account's list now.
- **Voice Library** voices cost nothing to preview, but using one in text-to-speech means adding it to the account, and all 10 slots are used.
  Adding one means removing another, which is the account owner's call. Nothing was added or removed.
- Flash v2.5 (the model this build uses) speaks German and French with any multilingual voice, but a voice whose own language is the target
  sounds more native. Premade voices are English voices that borrow the language.
- None of the French candidates is described as a sports commentator; the library returned no football or sports voice for French or German
  beyond the ones listed. French is the weakest language of the three.

A booth of two (what the text is written for): the build text has a play-by-play caller (templates, short, urgent) and a colour
analyst (the model's lines). With one voice per language both seats sound the same, so the energy settings in
`commentary/delivery.py` (`VOICE_SETTINGS`) do the work. With two voices per language the booth is real. That needs a role field in
`tts/voices.py` and the lines already know their `voice` (`pbp` or `analyst`); it is not built.

## English

**Recommendation: 1) Charlie for the caller, 2) keep Daniel for the colour analyst, both premade, no slot.** If one voice only: Daniel with the energy settings, or Charlie if the listening test says the Australian accent is fine. For a British booth in full, the Library's Blue is the one to add for the analyst seat.

| # | Voice | Source | Labels | Previews |
|---|---|---|---|---|
| 1 | **Charlie - Deep, Confident, Energetic**<br>`IKne3meq5aSn9XLyUdCD` | account, premade (no slot) | male, young, australian, conversational, hyped<br>verified/primary: en,es,fil,pt,zh | [free preview](https://api.us.elevenlabs.io/v1/voices/IKne3meq5aSn9XLyUdCD/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiIxMDJkZTZmMi0yMmVkLTQzZTAtYTFmMS0xMTFmYTc1YzU0ODEubXAzIiwidGltZXN0YW1wIjoxNzkyNTMwMDAwMDAwMDAwfQ%3D%3D) |
| 2 | **Daniel - Steady Broadcaster**<br>`onwK4e9ZLuTAKqWW03F9` | account, premade (no slot) | male, middle_aged, british, informative_educational, formal<br>verified/primary: de,en,tr | [free preview](https://api.us.elevenlabs.io/v1/voices/onwK4e9ZLuTAKqWW03F9/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiI3ZWVlMDIzNi0xYTcyLTRiODYtYjMwMy01ZGNhZGMwMDdiYTkubXAzIiwidGltZXN0YW1wIjoxNzkyNTMwMDAwMDAwMDAwfQ%3D%3D) |
| 3 | **Liam - Energetic, Social Media Creator**<br>`TX3LPaxmHKxFdv7VOQHJ` | account, premade (no slot) | male, young, american, social_media, confident<br>verified/primary: cs,de,en,hi,pl,pt,tr | [free preview](https://storage.googleapis.com/eleven-public-prod/premade/voices/TX3LPaxmHKxFdv7VOQHJ/63148076-6363-42db-aea8-31424308b92c.mp3) |
| 4 | **George - Warm, Captivating Storyteller**<br>`JBFqnCBsd6RMkjVDRZzb` | account, premade (no slot) | male, middle_aged, british, narrative_story, mature<br>verified/primary: ar,cs,en,es,fil,fr,hi,ja | [free preview](https://api.us.elevenlabs.io/v1/voices/JBFqnCBsd6RMkjVDRZzb/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiJlNjIwNmQxYS0wNzIxLTQ3ODctYWFmYi0wNmE2ZTcwNWNhYzUubXAzIiwidGltZXN0YW1wIjoxNzkyNTMwMDAwMDAwMDAwfQ%3D%3D) |
| 5 | **Blue - Neutral, Vocal Fry, Commentator**<br>`kfU9VUUMjY4PWNoUfZ45` | Voice Library (needs a free slot to use) | female, young, british, entertainment_tv, upbeat, en-GB<br>verified/primary: en | [free preview](https://storage.googleapis.com/eleven-public-prod/database/workspace/127e66ad503d436f89ad8e5031a5cf08/voices/kfU9VUUMjY4PWNoUfZ45/4zk2lR13UeyCbj2L26sj.mp3) |
| 6 | **Connor - Sports, Advertisements & Social Media**<br>`xtw8E1CXDMtNKx4sgP7u` | Voice Library (needs a free slot to use) | male, middle_aged, british, advertisement, upbeat, en-GB<br>verified/primary: en | [free preview](https://api.us.elevenlabs.io/v1/voices/xtw8E1CXDMtNKx4sgP7u/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJjdXN0b20iLCJ3b3Jrc3BhY2VfaWQiOiJmZTYzNzU2NzA5MmE0ZTk4YmIxYmU0NjVlNGRjZGU0YyIsImZpbGVuYW1lIjoiYVNBWVVhM3dmRzJnRWsyWjVZeG0ubXAzIiwidGltZXN0YW1wIjoxNzkyNTMwMDAwMDAwMDAwfQ%3D%3D) |
| 7 | **Andrew Griffin - Football Commentator**<br>`SF9uvIlY93SJRMdV5jeP` | Voice Library (needs a free slot to use) | male, middle_aged, american, conversational, calm, en-US<br>verified/primary: en | [free preview](https://storage.googleapis.com/eleven-public-prod/database/workspace/4567cb2d224245f8b853c0d5e2fd8728/voices/SF9uvIlY93SJRMdV5jeP/242a626d-6d37-4f88-956f-e9c8abcbec5f.mp3) |
| 8 | **Sam - Engaging Game Narrator**<br>`gnPxliFHTp6OK6tcoA6i` | Voice Library (needs a free slot to use) | male, middle_aged, american, entertainment_tv, hyped, en-US<br>verified/primary: en | [free preview](https://storage.googleapis.com/eleven-public-prod/database/user/kdqoco0jNZTkJjkkkkb3mUIkFiy1/voices/gnPxliFHTp6OK6tcoA6i/aUx0lzSdMNYqWlVupXHB.mp3) |
| 9 | **Shaurya - Dynamic Football Commentator**<br>`PgrxtC09o2q2Q7YXfVHy` | Voice Library (needs a free slot to use) | male, young, indian, entertainment_tv, excited, en-IN<br>verified/primary: en | [free preview](https://api.us.elevenlabs.io/v1/voices/PgrxtC09o2q2Q7YXfVHy/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJjdXN0b20iLCJ3b3Jrc3BhY2VfaWQiOiJlZDliMDVlNjMyNGM0NTc2ODU0OTAzNTJlOWExZWM5MCIsImZpbGVuYW1lIjoiYktvT0ZFaWtGYzk2WnIwRFZxSjIubXAzIiwidGltZXN0YW1wIjoxNzkyNTMwMDAwMDAwMDAwfQ%3D%3D) |

1. **Charlie - Deep, Confident, Energetic**: Best premade fit for a caller: the only premade labelled `hyped`. Australian, not British. Service text: "A young Australian male with a confident and energetic voice."
2. **Daniel - Steady Broadcaster**: Current default. Steady, British, formal: right for the colour analyst, flat for goals unless the energy settings lift it. Service text: "A strong voice perfect for delivering a professional broadcast or news story."
3. **Liam - Energetic, Social Media Creator**: Young and energetic; social-media register, may sound more creator than broadcaster. Service text: "A young adult with energy and warmth - suitable for reels and shorts."
4. **George - Warm, Captivating Storyteller**: British, warm storyteller: good for calm analysis, too soft for a goal call. Service text: "Warm resonance that instantly captivates listeners."
5. **Blue - Neutral, Vocal Fry, Commentator**: Library. British, neutral, written for a play-by-play commentator or sports analyst. Best library fit for the analyst seat. Service text: "Designed for a neutral sports commentator, a dry, Gen Z voice, a play-by-play commentator, or a sports analyst. Also great for a disengaged, unbothered neutral character. British/English voice."
6. **Connor - Sports, Advertisements & Social Media**: Library. British, punchy and rhythmic, sports and ads. Service text: "This honest, energetic and youthful voice features a bright resonance and rhythmic, punchy delivery. Built for fast-paced narration and sports broadcasting, it maintains exceptional clarity and crisp articulation even at a rapid tempo. The vibrant mid-to-high ..."
7. **Andrew Griffin - Football Commentator**: Library. Named Football Commentator, but calm American; most used voice of the search by a wide margin. Service text: "Middle-aged American male with a calm tone. Works well for casual conversations."
8. **Sam - Engaging Game Narrator**: Library. American armchair play-by-play. Wrong accent for a British booth. Service text: "Middle-aged American sports guy doing his armchair play-by-play calls."
9. **Shaurya - Dynamic Football Commentator**: Library. Football commentary, strong and energetic, Indian English. Service text: "Shaurya - Football Commentary, Strong, Powerful & Energetic  - Shaurya’s voice is the perfect match for adrenaline-fueled football commentary. With a commanding tone, dynamic energy, and bold modulations, he brings alive every moment on the field,from goals to..."

## German

**Recommendation: 1) John (Library) for the caller, 2) Chris (Library) as the alternative, 3) Anna (already in the account) as the voice usable today.** John is described as a stadium voice and is the closest thing to a German match commentator that came back. If no slot can be freed, use Anna Broadcast Excited & Journalistic for the caller and Daniel for the analyst.

| # | Voice | Source | Labels | Previews |
|---|---|---|---|---|
| 1 | **John - Nice and Emotional**<br>`iQgleKwj2ZKxy6MvS4xe` | Voice Library (needs a free slot to use) | male, middle_aged, standard, entertainment_tv, professional, de-DE<br>verified/primary: de | [free preview](https://api.us.elevenlabs.io/v1/voices/iQgleKwj2ZKxy6MvS4xe/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJjdXN0b20iLCJ1c2VyX2lkIjoienZLT3FMb2JMc2NhVXNNQVlZaEhJV3RvcXdNMiIsImZpbGVuYW1lIjoia01MZ0RicjcyTTlFcmxnR1VydTcubXAzIiwidGltZXN0YW1wIjoxNzkyNTMwMDAwMDAwMDAwfQ%3D%3D) |
| 2 | **Chris - Natural and Clear**<br>`Qvd9mju8GJ7MsKzX6FFA` | Voice Library (needs a free slot to use) | male, middle_aged, standard, entertainment_tv, excited, de-DE<br>verified/primary: de | [free preview](https://storage.googleapis.com/eleven-public-prod/database/user/W7sJ2qojntcz2f53hdpbbYMyqFX2/voices/Qvd9mju8GJ7MsKzX6FFA/mbjCy0RNn1SYjfmVwQUA.mp3) |
| 3 | **Anna Broadcast Excited & Journalistic **<br>`DEZHhPbmb8LVZmWufkCh` | account, already added (copied from the library) | female, young, standard, social_media, hyped<br>verified/primary: ar,de,en,ko,ms,nl,no,ro,ru,tr,uk,vi | [free preview](https://storage.googleapis.com/eleven-public-prod/database/workspace/5d3e22ddcd5645b69969709ff0765f9d/voices/DEZHhPbmb8LVZmWufkCh/mCxbcrKM8a6s2sm0xyIb.mp3) |
| 4 | **Dan - Radio Host & Moderator**<br>`utkd5fchbspYG3Ld0zt0` | Voice Library (needs a free slot to use) | male, middle_aged, standard, conversational, excited, de-DE<br>verified/primary: de | [free preview](https://api.us.elevenlabs.io/v1/voices/utkd5fchbspYG3Ld0zt0/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJjdXN0b20iLCJ1c2VyX2lkIjoiSmlKYjl1dG1NMFBEcWZBWVJiYUdHZmd2dlRqMiIsImZpbGVuYW1lIjoiTldTSmNqbVhNbFcyNUZNaDJlckkubXAzIiwidGltZXN0YW1wIjoxNzkyNTMwMDAwMDAwMDAwfQ%3D%3D) |
| 5 | **Robby - Dynamic and Professional**<br>`vl67BWhZHh0QyG35TvXt` | Voice Library (needs a free slot to use) | male, middle_aged, standard, entertainment_tv, formal, de-DE<br>verified/primary: de | [free preview](https://storage.googleapis.com/eleven-public-prod/database/user/EwLe5tD9P6et7MxPWpFxgpx7OTX2/voices/vl67BWhZHh0QyG35TvXt/5a3e3700-ceb8-47a9-a94b-f3cea8883b29.mp3) |
| 6 | **Leo - Uplifting Advertisement Voice**<br>`iQ5dS7juUUF7zgIVf8ET` | account, already added (copied from the library) | male, young, standard, advertisement, crisp<br>verified/primary: ar,da,de,es,hi,hr,it,ko,nl,no,pt,ro,uk,zh | [free preview](https://storage.googleapis.com/eleven-public-prod/database/workspace/fb4a273526394da1b409cb2ecb65e2d6/voices/iQ5dS7juUUF7zgIVf8ET/dZH8Hlae7NTgyp85ywjT.mp3) |
| 7 | **Marcus - for ads, Spotify, commercials, promo, brands, radio**<br>`vGWWh1bodhwwi4yHd6qZ` | account, already added (copied from the library) | male, middle_aged, standard, advertisement, professional<br>verified/primary: ar,de,hi,hr,it,ms,nl,no,pl,pt,ro,ru,tr,uk,vi,zh | [free preview](https://storage.googleapis.com/eleven-public-prod/database/workspace/9d5daecd4210450281f8157fe899598f/voices/vGWWh1bodhwwi4yHd6qZ/AYWXonxIZlUhcxjlSp1l.mp3) |
| 8 | **Charlie - Deep, Confident, Energetic**<br>`IKne3meq5aSn9XLyUdCD` | account, premade (no slot) | male, young, australian, conversational, hyped<br>verified/primary: en,es,fil,pt,zh | [free preview](https://api.us.elevenlabs.io/v1/voices/IKne3meq5aSn9XLyUdCD/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiIxMDJkZTZmMi0yMmVkLTQzZTAtYTFmMS0xMTFmYTc1YzU0ODEubXAzIiwidGltZXN0YW1wIjoxNzkyNTMwMDAwMDAwMDAwfQ%3D%3D) |
| 9 | **Daniel - Steady Broadcaster**<br>`onwK4e9ZLuTAKqWW03F9` | account, premade (no slot) | male, middle_aged, british, informative_educational, formal<br>verified/primary: de,en,tr | [free preview](https://api.us.elevenlabs.io/v1/voices/onwK4e9ZLuTAKqWW03F9/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiI3ZWVlMDIzNi0xYTcyLTRiODYtYjMwMy01ZGNhZGMwMDdiYTkubXAzIiwidGltZXN0YW1wIjoxNzkyNTMwMDAwMDAwMDAwfQ%3D%3D) |

1. **John - Nice and Emotional**: Library. Described as the sound of a German football stadium, energetic and powerful: the closest match to a German caller. Service text: "Christian Plasa delivers the authentic sound of a German football stadium with an energetic, powerful voice ideal for live commentary, sports games, and immersive media. Capturing the intensity of Bundesliga action, his voice brings every moment to life,from t..."
2. **Chris - Natural and Clear**: Library. Described as 'your slightly excited commentator'. Service text: "Your slightly excited commentator."
3. **Anna Broadcast Excited & Journalistic **: Already in the account, usable now. Female, young, labelled hyped and journalistic: a reporter voice, fits a caller if a female booth is fine. Service text: "Cool young voice, serious yet open and dynamic. Perfectly made for broadcasting."
4. **Dan - Radio Host & Moderator**: Library. Radio host, mentions live commentary, labelled excited. Service text: "RadioHost is a dynamic, energetic, and friendly voice designed for radio-style presentations, podcasts, and live commentary. Clear, engaging, and natural, it delivers content with a warm tone, professional clarity, and a playful personality. Perfect for announ..."
5. **Robby - Dynamic and Professional**: Library. Reporter register: good for the analyst seat. Service text: "Reporter Robby offers a dynamic and lively voice that is perfect for news, reports and moderation. With his professional yet accessible tone, he gets to the heart of every message in a concise and appealing way. Ideal for documentaries, live reporting and ente..."
6. **Leo - Uplifting Advertisement Voice**: Already in the account. Young, crisp advertising voice. Service text: "Friendly, uplifting announcer voice, perfect for advertising, commercials, podcasts, Spotify ads, promotional content, brand storytelling, motivational spots, online campaigns, radio, and social media. Warm, clear, engaging, energetic, trustworthy, and versati..."
7. **Marcus - for ads, Spotify, commercials, promo, brands, radio**: Already in the account. Promo and radio announcer. Service text: "I'm Marcus - the iconic German voice from TV and radio. Now as AI: strong, clear, trusted. Perfect for ads, brand voice, promos & stations. This is how professional sounds."
8. **Charlie - Deep, Confident, Energetic**: Premade Charlie speaks German only through the multilingual model (not listed as verified for de), expect an accent. Service text: "A young Australian male with a confident and energetic voice."
9. **Daniel - Steady Broadcaster**: Premade Daniel, verified for German on the multilingual model. What the build uses today. Service text: "A strong voice perfect for delivering a professional broadcast or news story."

## French

**Recommendation: 1) Simon (Library) for the caller, 2) Nicolas Petit Radio Host (Library) for the analyst, 3) George or Sarah (premade, verified for French) if no slot is available.** Without a slot the honest answer is that no premade voice is a French caller; George with the peak settings is the nearest.

| # | Voice | Source | Labels | Previews |
|---|---|---|---|---|
| 1 | **Simon - Cheerful, Energetic and Rapid**<br>`mvhJVdVoTWVUtL4keT7W` | Voice Library (needs a free slot to use) | male, young, parisian, advertisement, excited, fr-FR<br>verified/primary: fr | [free preview](https://api.us.elevenlabs.io/v1/voices/mvhJVdVoTWVUtL4keT7W/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJjdXN0b20iLCJ1c2VyX2lkIjoiSTdoV3lYYUNZMmdnODlkN0hBTDZGVFk1WkdwMSIsImZpbGVuYW1lIjoid0xpcUNzbnJtYnhrQjMyVDNqcjUubXAzIiwidGltZXN0YW1wIjoxNzkyNTMwMDAwMDAwMDAwfQ%3D%3D) |
| 2 | **Corentin - Enthusiastic and Bright**<br>`IHngRooVccHyPqB4uQkG` | Voice Library (needs a free slot to use) | male, young, standard, social_media, confident, fr-FR<br>verified/primary: fr | [free preview](https://storage.googleapis.com/eleven-public-prod/custom/voices/IHngRooVccHyPqB4uQkG/yQPlGmXFNsSO01HV7Qsk.mp3) |
| 3 | **Nicolas Petit - Radio Host**<br>`WUAdt1wuIPYQ1XruI5dW` | Voice Library (needs a free slot to use) | male, middle_aged, parisian, narrative_story, professional, fr-FR<br>verified/primary: fr | [free preview](https://storage.googleapis.com/eleven-public-prod/database/workspace/7593eab373974d1db7d45255c5986d46/voices/WUAdt1wuIPYQ1XruI5dW/Y9TxSmJ1rLXBCHMvc6Cz.mp3) |
| 4 | **Paul French - Podcaster**<br>`cTNP6ZM2mLTKj2BFhxEh` | Voice Library (needs a free slot to use) | male, middle_aged, standard, entertainment_tv, modulated, fr-FR<br>verified/primary: fr | [free preview](https://api.us.elevenlabs.io/v1/voices/cTNP6ZM2mLTKj2BFhxEh/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJjdXN0b20iLCJ3b3Jrc3BhY2VfaWQiOiIzMGY0ZTZlZWEzNjA0YWFmYWFiYmI4MWQxNmExNWQ0OSIsImZpbGVuYW1lIjoiTE9xVVRkTjRkSGtodm9sUUhkM0UubXAzIiwidGltZXN0YW1wIjoxNzkyNTMwMDAwMDAwMDAwfQ%3D%3D) |
| 5 | **Sarah - Mature, Reassuring, Confident**<br>`EXAVITQu4vr4xnSDxMaL` | account, premade (no slot) | female, young, american, entertainment_tv, professional<br>verified/primary: ar,en,es,fr,hi,zh | [free preview](https://storage.googleapis.com/eleven-public-prod/premade/voices/EXAVITQu4vr4xnSDxMaL/01a3e33c-6e99-4ee7-8543-ff2216a32186.mp3) |
| 6 | **George - Warm, Captivating Storyteller**<br>`JBFqnCBsd6RMkjVDRZzb` | account, premade (no slot) | male, middle_aged, british, narrative_story, mature<br>verified/primary: ar,cs,en,es,fil,fr,hi,ja | [free preview](https://api.us.elevenlabs.io/v1/voices/JBFqnCBsd6RMkjVDRZzb/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiJlNjIwNmQxYS0wNzIxLTQ3ODctYWFmYi0wNmE2ZTcwNWNhYzUubXAzIiwidGltZXN0YW1wIjoxNzkyNTMwMDAwMDAwMDAwfQ%3D%3D) |
| 7 | **Daniel - Steady Broadcaster**<br>`onwK4e9ZLuTAKqWW03F9` | account, premade (no slot) | male, middle_aged, british, informative_educational, formal<br>verified/primary: de,en,tr | [free preview](https://api.us.elevenlabs.io/v1/voices/onwK4e9ZLuTAKqWW03F9/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiI3ZWVlMDIzNi0xYTcyLTRiODYtYjMwMy01ZGNhZGMwMDdiYTkubXAzIiwidGltZXN0YW1wIjoxNzkyNTMwMDAwMDAwMDAwfQ%3D%3D) |

1. **Simon - Cheerful, Energetic and Rapid**: Library. Young Parisian, cheerful, energetic and rapid, labelled excited: closest to a French caller. Service text: "A young male voice, brimming with energy and warmth. It is clear and well-articulated, with an intonation that immediately captures attention. The tone is both engaging and professional, ideal for hosting radio shows or podcasts. The voice exudes a natural vit..."
2. **Corentin - Enthusiastic and Bright**: Library. Young, enthusiastic and bright. Service text: "A dynamic young French male voice. Perfect for short-form videos and social media."
3. **Nicolas Petit - Radio Host**: Library. Parisian radio-host tone, dynamic and smiling: fits the analyst seat. Service text: "French voice of Nicolas Petit with a radio animation tone. Ideal for projects with a dynamic and smiling tone."
4. **Paul French - Podcaster**: Library. Modulated podcaster, poised. Service text: "Credible and captivating for podcasts, but not only that!  A poised and authoritative voice, perfect for podcasts, documentaries, and journalistic content. Designed for this use but adaptable to other professional formats. Adjust settings to fine-tune tone and..."
5. **Sarah - Mature, Reassuring, Confident**: Premade, verified for French. Mature and reassuring female: calm analyst only. Service text: "Young adult woman with a confident and warm, mature quality and a reassuring, professional tone."
6. **George - Warm, Captivating Storyteller**: Premade George, verified for French. Warm British storyteller; no French sports energy. Service text: "Warm resonance that instantly captivates listeners."
7. **Daniel - Steady Broadcaster**: Premade Daniel is NOT verified for French; what the build uses today. Service text: "A strong voice perfect for delivering a professional broadcast or news story."

## Settings to try with any of them

`VOICE_SETTINGS` in `commentary/delivery.py` (sent only when the server runs with `--tts-delivery`, which is off):

| Energy | stability | similarity_boost | speed | style |
|---|---|---|---|---|
| calm | 0.62 | 0.80 | 0.97 | 0.00 |
| rising | 0.45 | 0.80 | 1.04 | 0.25 |
| peak | 0.30 | 0.75 | 1.12 | 0.55 |

`style` is left out for Flash (it raises latency); the table is a starting point to tune by ear, not a measured result.
