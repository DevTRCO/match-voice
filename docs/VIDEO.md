# Demo video script

Target 1:55, hard limit 2:00. Judges may not run the project, so this video carries the whole demo.
Three short pieces to camera (the founder), everything else is the real demo page with its own sound. Cut and edited in
Remotion, English subtitles burnt in for everything said, in any language. No music, no real logos, clubs, people or
broadcaster marks. Every team, player and commentator is fictional, the faces are generated, the match data is synthetic.

## What the founder records

Four clips, saved to `video/founder/` as A, B, C, D (.mov or .mp4), landscape 1920x1080, eye level, look into the lens,
window light from the front. One sentence per take, two or three takes each. Lower third on clip A: "Vu Minh Tran, building encara".
About 130 words in total. Page with stress and pause marks and the independent review: https://claude.ai/artifact/TTsY5Numv3xYoCQKYtF5DE

| Clip | Length | Say |
| --- | --- | --- |
| A | about 20 s | "I'm Vu, and I'm building encara. Most football matches get commentary in one language, or none. encara is a real-time engine that writes and speaks commentary from match data. Nine languages run today, and it grows with the voice engine underneath, which already speaks more than ninety." (ElevenLabs Eleven v4 and v4 Turbo: 90+ languages, docs checked 2026-10-26) |
| B | about 10 s | "Wexmoor are a goal down, it's the 68th minute, and the game has gone quiet. That's when a good commentator points something out." |
| C | about 22 s, first sentence on camera, rest voice-over | "Those two lines came from five agents on the Microsoft Agent Framework. One spots the pattern, one writes the line. Then plain code checks the names and numbers against the match data. A wrong line gets one retry. If it fails again, it is not spoken." |
| D | about 18 s | "Each new language needs a prompt and word lists for the checker. Clubs, leagues and streaming services can plug the engine into their own apps. I want every fan to have a commentator who goes mad for their team, in their language." |

No third-party footage (the "Ankara Messi" idea was dropped: no rights; our own goal call is the hook).
Copy rules: no slogan triplets, no "not X but Y" reveals, no one-word punchlines, no "deserves", no claim the code cannot back.

## Timeline

| # | Time | Picture | Sound | On-screen text (besides subtitles) |
| --- | --- | --- | --- | --- |
| 1 | 0:00 to 0:05 | Crowd from frame 1, the 71' goal in Japanese: Yuki Tanaka's plate, 1-1, her whole pay-off line. | "ゴール！フォンテーヌ！同点！" then "言った通りです！イブセンが奪って、今度はすぐ反対側のラスムッセンへ！" | Subtitles: "GOAL! Fontaine! Level!" / "Just as I said! Ibsen wins it, and this time straight across to Rasmussen!" |
| 2 | 0:05 to 0:10 | One text card. | Crowd tail. | "Yuki Tanaka is an AI commentator. In the 68th minute she spotted a habit in Wexmoor's game." |
| 3 | 0:10 to 0:30 | Clip A. | Founder. | "Vu Minh Tran, building encara", bottom left, 3 s |
| 4 | 0:30 to 0:40 | Clip B. | Founder. | none |
| 5 | 0:40 to 0:52 | Scene 1 "Analysis", English expert: the 11 ball wins, the counter, "Pattern spotted". | Daniel Price's set-up line. | none |
| 6 | 0:52 to 1:05 | Scene 2 "The goal": the win, the 50 m switch, the goal, "Pattern broken, flagged 2:41 ago". | Goal call, pay-off, crowd. | none |
| 7 | 1:05 to 1:25 | Clip C: first sentence on camera, then voice-over over How mode and the real verifier catch from `story.json`: es/expert "ha ganado tres veces" rejected (`comeback_win`, the record counts points, not wins), then the accepted line. | Founder. | none |
| 8 | 1:25 to 1:30 | Expert and beginner side by side, same moment. | App sound low. | "Expert" / "Beginner" |
| 9 | 1:30 to 1:36 | The same goal call, 2 s each: de, es, tr, face and name. | Each goal call. | none (clip A already names the languages) |
| 10 | 1:36 to 1:54 | Clip D. | Founder. | none |
| 11 | 1:54 to 1:58 | End card on royal purple. | Crowd fades. | "encara, real-time commentary engine", demo URL, repo URL, "All clubs, players and match data are synthetic. Recorded from a live run." |

## How it is made (Claude does this)

1. Picture: the demo page recorded headless at 1920x1080, 30 fps (Playwright `recordVideo`), one take per channel needed.
2. Sound: rebuilt in Remotion from the baked files (`ui/public/insert/story-audio/<ch>-<m>.mp3`) at the clip times in
   `story.json`, plus the crowd bed and roar, so audio and picture are frame-exact.
3. Subtitles: from the `say` texts; non-English lines get an English translation underneath.
4. Founder clips: trimmed, light grade, loudness matched to -16 LUFS, the app sound ducked under the voice, never under a goal call.
5. Export MP4 1920x1080, under 2:00.

## Claims, and where each is true

| Claim | Where |
| --- | --- |
| Five agents, distinct jobs | Spotter (`patterns.py`, `moments.py`), Analyst (Claude Haiku via `agent-framework-anthropic`), Verifier (`verifier.py`), Publisher (`newsroom.py`), Directors (`director.py`) |
| The set-up was found by the system, no lookahead | `test_patterns.py` (later events thrown away, same set-up); facts checked 2026-10-26 |
| Plain code checks every name and number | `verifier.py`, docs/EVAL.md (injected errors caught 99.8 to 100 percent) |
| Nine languages, twelve commentators | `lang.py` `BOOTH`, `story.json` `hello.channels` |
| "Flagged 2:41 ago" | match seconds between the set-up and the pay-off as the channel spoke them |

Do not say "live" about what is on screen: it is a recorded live run, and the page says so. Do not say the languages
were checked by native speakers. Do not show the Japanese or Turkish build-up lines (two known fact errors there: Tavares
"on the left", the first-time pass "to Tavares"); the Japanese in shot 1 starts at the goal call, which is correct.

## Do not show

- The `.env` file or any key, a terminal with one in the environment.
- Any real club, player, league logo, broadcaster mark or music; no browser chrome.
