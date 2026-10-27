
## 2026-10-26 Remotion scaffold (video/remotion)

- Remotion 4.0.535, react 18.3.1, typescript 5.6.3, pinned exact. `npm run studio`, `npm run typecheck`, `npm run assets`, `npm run render`, `npm run loudness`.
- Assets: Remotion copies public/ into its bundle and does NOT follow symlinks (404 on founder/A_blur.mp4). `scripts/link-assets.sh` hard-links founder *_blur.mp4 (never the unblurred takes), story-audio mp3s, roar and any video/shots/*.mp4 into public/. Re-run after a source file is re-made (new inode).
- Crowd bed: public/audio/stadium-bed-lp900.wav = stadium-bed.mp3 from 40 s, 160 s long, ffmpeg lowpass 900 Hz Q 1.122 (WebAudio BiquadFilter Q 1 dB, mock4.html line 1725). Measured -24 LUFS integrated, TP -8.6 dBFS. At the page gain 0.09 it sits about -45 LUFS.
- Page mix constants (tokens.ts PAGE_MIX, from mock4.html): voice 1.0, bed 0.09, bed under a scene card 0.02, bed on the goal 0.15 then 0.08, roar 0.3.
- Fonts local in public/fonts (Schibsted Grotesk variable latin + latin-ext, Barlow Condensed 700); Japanese falls back to Hiragino Sans (renders correctly in stills).
- Components: FounderClip (4:5 window 734x918, crop cx 680 top 128 h 592 of the 1280x720 take, left 200; the lamp is out of frame; upscale 1.55x), TextCard, VerifierCatch (reads story.json: es/expert moment 3339167, 68'), SplitScreen, Subtitles (+ checkCues), EndCard (REPO_URL placeholder), AudioLayer (roles voice/app/goal/bed, duck 0.22 with 12 f attack and 18 f release, goal never ducked), pageVoiceCues helper.
- timeline.ts is a DRAFT: 113.9 s. Shots missing, so Main shows "SHOT PENDING" frames. Founder subtitle times are spread by character share (silencedetect found almost no pauses: A 12.37 to 12.62 s, C 11.30 to 11.67 s); refine against the waveform. C on camera 0 to 4.4 s is an estimate.
- Test renders in video/shots/test: stills of each component read and checked; Main frames 380 to 679 (card end, founder A with lower third and subtitles) rendered as h264 crf 16 + aac 192k: -15.9 LUFS integrated, true peak -4.5 dBFS on that clip.
- Fixed after the first look: lower third collided with the subtitle band (moved up 168 px); Japanese subtitle orphaned a glyph (text-wrap balance).

## Demo shot capture (2026-10-26)

Method: deterministic virtual clock, not a real-time screencast. `video/capture/virt.js` is an init script: `performance.now`, `requestAnimationFrame` and `setTimeout` run on a virtual clock, CSS animations and transitions are paused and stepped by hand, `HTMLAudioElement` is a silent stand-in that keeps time on the same clock (durations from ffprobe, `capture/durations.json`) and logs create/play/seek/pause/ended, the crowd bed's gain targets and buffer start are logged, `speechSynthesis` is stubbed (0 calls in every take). `capture/capture.js` steps 1/30 s per frame, takes one PNG screenshot per step (CDP), pipes to ffmpeg (h264 crf 16, yuv420p, 30 fps CFR). mock4.html is unchanged.
Measured: every file is exactly 30 fps CFR, frame count = duration x 30, 300 of 300 frames differ from the previous one in the goal sections (no duplicates, no drops). Capture throughput 12 frames per real second. A real-time CDP screencast of the same page delivered 58 fps (150 frames in 2.56 s), as a cross-check: the start overlay transition looks the same in both.
Logs: each `shots/<id>.json` has fps, frames, durationS, frame0Epoch, audioEvents (tS in shot seconds, src, ev, offsetS, volume, dur; bed: gain target + time constant, bedstart offset 40 s, 900 Hz low-pass), wSamples (page clip time w per frame), subtitleCues (sampled from #fsay per frame, speaker from the name plate, moment id, en/expert text of the same moment), frameState (score, clock, scene card, insight card, How mode per frame). Event tS = frame index / 30 of the frame on which it happened.
Takes (`node capture/capture.js <id>`; S2, S3, S5 cut frame-exact by `capture/slice.py` from the masters M_enx / M_enb, which run idle 2 s, Play at frame 60, then w = frame/30 - 2):
- S1_ja_goal: Yuki Tanaka, start(26.4), goal call at 4.00 s, pay-off 7.20 s, score line 12.60 s, ends 15.23 s. The Japanese build-up lines (moments 1189316..1189713) were removed from the runtime data (`D.LINES`) before Play, so no Japanese subtitle or voice before the goal call.
- S2_scene1_analysis_enx: idle 2 s, Play, Scene 1 card, 11 ball wins montage, Pattern spotted, Daniel's set-up (w 1.80 to 7.38), Charlie's story line, ends before the cut (18.0 s).
- S3_scene2_goal_enx: w 14.0 to the end card + 2 s (34.0 s): Scene 2 card, build-up, switch, goal (w 30.37), Pattern broken, flagged at 68', Daniel's pay-off, score line.
- S4_how_goal_enx: How mode, start(26.4) to w 44.5; flow band Data in, Understood, Written, Checked, Spoken.
- S4b_how_scene1_es: How mode, Lucía Romero, scene 1 (Checked step shows "1 rejected and rewritten" on the story line).
- S5_en_beginner: Owen Carter, same frame clock as M_enx (50 s).
- S6_de_goal / S6_es_goal / S6_tr_goal: start(27.4), goal at 2.97 s, 8.03 s each; tr build-up lines removed as for ja.
- S7a_start_screen (8 s idle, ja), S7b_picker_cycle (10 s, setCom ja -> en/x -> de/x -> es -> fr/x -> ja every 1.5 s), S7c_switch_midgoal (en/x goal, strip opens, Kim Berger takes the pay-off, then Lucía Romero).
Seen in the contact sheets (page behaviour, also in the real-time screencast): the start overlay ghosts back for about 0.35 s at w 1.45 to 1.8 (S2 frames ~103 to 114) as the board tilts into scene 1; the shot label after the goal ("Fontaine shoots, 25 m, nobody closing") jumps position 3 to 4 times in about a second; board labels stay English in the ja and tr takes. No console errors, no failed requests, no browser chrome, no cursor.

## Assembly and render (2026-10-26)

Output: `video/out/encara-demo.mp4` (h264 High crf 16 yuv420p, 1920x1080, 30 fps CFR, 3474 frames, 115.82 s; aac 192k 48 kHz stereo). `video/out/encara-demo_raw.mp4` is the Remotion render before the master gain.
Rebuild: `cd video/remotion && npm run assets && python3 scripts/level-voices.py 11-162 11-163 1-800004 1-1189697 1-1189713 1-162 1-163 1-3339167 3-162 6-162 10-162 && npm run render`, then
`ffmpeg -i ../out/encara-demo_raw.mp4 -map 0 -c:v copy -af volume=1.5dB -c:a aac -b:a 192k -ar 48000 -movflags +faststart ../out/encara-demo.mp4`.

What changed in the Remotion project:
- `src/timeline.ts` is the cut. Page shots take their sound and subtitles from the capture logs (`src/data/shots.ts` reading `src/data/shotlogs.json`, a compact copy of the play/pause/ended events and page subtitle cues of the shots used): every voice file starts on the frame the page started it and stops where the page stopped it.
- Page subtitles: the page draws its own line at y 930 to 982. A page cue is an opaque fixed-width band (1640 px, bottom edge y 1002) that covers it, with no fade, and shows the same text (plus the English under a non-English line). The page's line never shows next to ours; the name plate and progress bar stay visible.
- Voice-over subtitles have their own placement (How mode: under the pitch in the left column; picker: between the Play button and the page footer), so they never sit on page text.
- SplitScreen crops each pane to the board (score bug, insight card, pitch; the page subtitle and controls are cropped away) and puts each pane's line under it.
- Commentary files are levelled for the film (`scripts/level-voices.py`, `public/audio/story-lv/*.wav`): they ranged -15.8 to -28.6 LUFS (1-3339167 is -28.6); now -18 LUFS, goal calls -17, limiter at 0.79.
- Duck: -20 dB (gain 0.1) on the bed and app sound under founder speech, 6 f attack inside the voice window, 12 f release; goal calls and the roar are never ducked. In this cut no commentary line plays under the founder at all (the How and picker shots carry no page voice).
- Founder first cues start at the measured speech onset (whisper.cpp ggml-small puts the first word about 0.35 s early; onsets measured by RMS on the takes: A 0.46, B 0.35, C 0.36, D1 0.77, D2 0.36, D3 0.35 s). C_blur.mp4 frame 0 is black (luma 16): the take starts one frame in.
- EndCard REPO_URL = github.com/DevTRCO/match-voice (git remote origin).

Shot list (film time, frames, source in point -> out point):
| # | Film | Frames | Picture | Source |
| --- | --- | --- | --- | --- |
| 1 | 0:00.00 to 0:09.30 | 0 to 278 | Japanese goal call and pay-off, Yuki Tanaka | S1_ja_goal 3.20 to 12.50 (goal call at 0.80, pay-off at 4.00) |
| 2 | 0:09.30 to 0:14.80 | 279 to 443 | Text card "Yuki Tanaka is an AI commentator." / "In the 68th minute she spotted a habit in Wexmoor's game." | TextCard |
| 3 | 0:14.80 to 0:33.93 | 444 to 1017 | Founder A, lower third 0:17.90 to 0:21.30 | A_blur 0 to 19.13 |
| 4 | 0:33.93 to 0:44.43 | 1018 to 1332 | Founder B | B_blur 0 to 10.50 |
| 5a | 0:44.43 to 0:45.83 | 1333 to 1374 | Scene 1 card | S2 2.00 to 3.40 (cut before the start overlay ghost) |
| 5b | 0:45.83 to 0:51.80 | 1375 to 1553 | Pattern spotted, ball wins montage, Daniel's set-up | S2 3.8333 to 9.80 |
| 6a | 0:51.80 to 0:53.10 | 1554 to 1592 | Scene 2 card, "Two minutes later" | S3 2.40 to 3.70 |
| 6b | 0:53.10 to 1:08.80 | 1593 to 2063 | Long ball, first time, goal (0:57.20), Pattern broken, Daniel's pay-off | S3 12.30 to 28.00 |
| 7a | 1:08.80 to 1:14.00 | 2064 to 2219 | Founder C on camera (sound runs on as voice-over to 1:24.37) | C_blur 0.033 to 5.233 |
| 7b | 1:14.00 to 1:17.00 | 2220 to 2309 | How mode, flow band to Spoken | S4 7.00 to 10.00 |
| 7c | 1:17.00 to 1:24.40 | 2310 to 2531 | Verifier catch: rejected at +0.35 s ("plain code checks"), reason +1.85 s, accepted +4.45 s ("one retry") | VerifierCatch |
| 8 | 1:24.40 to 1:29.80 | 2532 to 2693 | Expert / Beginner split, story note, expert line heard | S2 and S5 9.60 to 15.00 |
| 9a | 1:29.80 to 1:31.63 | 2694 to 2748 | German goal call, Jonas Weber | S6_de 3.00 to 4.83 (cut in the breath after "Fontaine!") |
| 9b | 1:31.63 to 1:33.63 | 2749 to 2808 | Spanish goal call, Lucía Romero | S6_es 3.00 to 5.00 |
| 9c | 1:33.63 to 1:35.67 | 2809 to 2869 | Turkish goal call, Emre Aydın | S6_tr 3.00 to 5.03 |
| 10a | 1:35.67 to 1:39.97 | 2870 to 2998 | Founder D1 | D1_blur 0 to 4.30 |
| 10b | 1:39.97 to 1:45.10 | 2999 to 3152 | Picker cycling (Charlie Hale, Jonas Weber, Lucía Romero, Hugo Martin), D2 voice-over | S7b 1.40 to 6.53 |
| 10c | 1:45.10 to 1:51.30 | 3153 to 3338 | Founder D3 | D3_blur 0 to 6.20 |
| 11 | 1:51.30 to 1:55.82 | 3339 to 3473 | End card | EndCard |

Measured on the final file:
- Duration 115.818 s, 3474 frames, 30/1 fps, 1920x1080, yuv420p.
- Loudness (ffmpeg ebur128): -15.2 LUFS integrated, true peak -2.9 dBFS, LRA 5.7 LU (before the +1.5 dB master gain: -16.7 LUFS, -4.3 dBTP). Mean momentary by part: shot 1 -17.2, founder A -15.4, B -16.3, scene 1 -18.8, scene 2 -17.3, C -15.4, split -19.7, montage -14.6, D -14.5 (gaps included).
- Subtitle sync: page lines start on the logged play frame; the levelled voice files have 0.03 to 0.12 s leading silence, so onset is 0.03 to 0.12 s after the subtitle. Founder first cues within 0.03 s of the RMS onset; cue boundaries inside a take within 0.16 s (A "encara is" cue starts 0.16 s after the filler "So", on "encara"); C 5.2 and 8.2 boundaries 0.09 to 0.10 s after the word starts.
- checkCues: no overlap, no em dash or middle dot; one cue under the 9 f per word reading rule: "A wrong line gets one retry, and if it fails, it's not spoken." 106 f for 13 words (bound by the speech). mock4.html and story.json contain no "·" or em dash (grep 0).
- Frame checks: contact sheet every 2 s and frames on both sides of every cut read. Founder background is blurred plain wall in all six takes, no banner. No browser chrome, no cursor. blackdetect (pix_th 0.06) flags only the purple card stages (text card start 9.30 to 10.43 while line 1 rises, its fade 14.57 to 14.80, verifier 77.00 to 77.43 before the first block rises, end card 111.30 to 111.90 while the title rises): text is on screen in those, it covers under 2 percent of the pixels. freezedetect (0.0005, 1 s): text card hold 10.87 to 14.47, scene 1 montage 46.6 to 49.9 (the page's slow montage), scene 2 card 51.8 to 53.1, verifier holds 77.9 to 84.2, split 85.57 to 89.63 (both boards are static at that moment, only the lines change), picker holds 100.2 to 104.6 (1.5 s per face), end card.
- Not done: nobody has listened to the film. Duck depth is from the code (gain 0.1), not measured on a stem.

## Review fixes (2026-10-27)

Four reviews (visual, story, sound, truth) checked against the film, the shots, the takes and the code. Each finding was checked first.

What changed:
- End card: no Code row (`REPO_URL = null` in EndCard.tsx). `gh api repos/DevTRCO/match-voice` returns visibility private, and an anonymous request gets HTTP 404. Set it back once the repo is public. The disclaimer is now 30 px in --mute, so it reads.
- 7b is now an agent card (`components/AgentCard.tsx`), not How mode: Spotter, Analyst, Verifier, Publisher and Directors, with one role each. A gold bracket under Analyst, Verifier and Publisher says "One Microsoft Agent Framework workflow, with one retry edge from the Verifier back to the Analyst" (newsroom.py WorkflowBuilder, README:54). The boxes come in on "five", the bracket on "Microsoft", Spotter lights on "spots" and Analyst on "writes". Clip C is on camera only up to C 2.27 s ("Those two lines came from"), the card runs to C 8.10, and the verifier starts on "Then" (C 8.10, RMS). That takes care of the How mode "What you hear" contradiction, the rounded chip and the 0.15 s late C cues. All four C cues now sit on 7a and are timed from the RMS envelope: 0.36, 5.08, 8.10 and 11.98, ending 15.52.
- Founder layout: centred 16:9 window, 1600x900 (crop 1052x592 from top 128, so the lamp stays out). Subtitles sit inside the window, with the band bottom 24 px above its edge. The lower third is one line, "Vu Minh Tran, building encara", on a dark plate at the bottom left of the video.
- Commentator plates (`components/Plate.tsx`, face, name and role in Barlow 700) above the subtitle band: Yuki Tanaka (shot 1), Daniel Price as co-commentator (5b and on the pay-off in 6b), Charlie Hale as play-by-play (6b), and Jonas Weber, Lucía Romero and Emre Aydın on the cut in the montage.
- Shot 1 has a line in the page's top strip: "Recorded from a live run. Synthetic match data, fictional clubs and players."
- Text card: "she pointed out a habit" (not "spotted": the detector found it).
- Split: a different moment, Rasmussen chests it down at 70:07 (S3 8.9 to 12.3 against S5 24.9 to 28.3, the same frame clock). The lines are "Chests it down." and "Takes it on the chest.", both exact, and the boards move. The labels read "Expert, Charlie Hale" and "Newcomer, Owen Carter". Panes are cropped to the pitch, lines are set at 48 px, and the split is 3.4 s instead of 5.4 s. The beginner line "come from behind three times" is gone.
- 5a in on S2 frame 67 (2.2333). Frames 60 to 65 still show the start overlay, and frame 66 is the first clean one.
- Picker (10b): in on S7b frame 49 (1.6333). The name switches on 45, but the ring is still leaving Yuki on 45 to 48. The shot is now a panel of the avatar row, name line and Play button (`panel` on ShotSeg), so "Welcome to the demo" and the footer typo are not in it. D2 subtitle at the default place below.
- B: cue 2 starts at 6.90 (speech resumes at 6.92 by RMS, whisper said 6.32). Cue 1 ends at 6.00.
- Montage gloss is "GOAL! Fontaine!" in all three.
- Sound: goal calls levelled to -13 LUFS with a ceiling of 0.71. They land at -13.9 to -14.6 after the limiter. Roar is 0.45 in the film (PAGE_MIX.filmRoar). Founder voice is at 0.8 (-1.9 dB). The split line is at 1.4. The bed is 0.25 under the text card and the end card, and fades over 1.5 s. The master gain moved inside the AudioLayer (`gainDb`, +1.3 dB), so AAC is encoded once. The final file is the raw render remuxed with faststart (`ffmpeg -i encara-demo_raw.mp4 -map 0 -c copy -movflags +faststart encara-demo.mp4`).

Rebuild: `npm run assets && python3 scripts/level-voices.py 11-162 11-163 1-800004 1-1189576 1-1189697 1-1189713 1-162 1-163 1-3339167 3-162 6-162 10-162 && npm run render`, then the remux above.

Measured on the final file:
- 113.536 s, 3406 frames, 30 fps, 1920x1080 h264 crf 16, aac 192k 48 kHz.
- -15.8 LUFS integrated, true peak -1.2 dBTP, LRA 7.8 LU.
- Mean and max momentary by part (at master +1.5 dB, one render before; the final is 0.2 dB lower): ja goal -15.6/-9.5, card -33.0, A -17.4/-12.6, B -18.3/-12.9, scene 1 -18.6, scene 2 -15.9/-10.1, agents -19.2, verifier -16.5/-10.8, split -18.4, montage -11.7/-8.2, D -16.3 to -16.6, end -38.6. The founder's loudest momentary is -10.8. The goal calls peak at ja -9.5, en -10.1, de -9.5, es -8.2 and tr -8.7. So de, es and tr are 1.3 to 2.6 LU above the founder's peak, but ja and en are only 0.7 to 1.3 LU above (target was 2). On average, every goal section is louder than every founder section.
- silencedetect -50 dB/0.4 s: only the last 0.64 s (the fade).
- Contact sheets every 2 s and frame tiles on the 5a and picker cuts checked: clean first frames, no text on text, no em dash or middle dot in src.

Still open:
- Clip C says "five agents on the Microsoft Agent Framework", but only three run on it. The agent card shows the exact split, but the sentence itself needs a re-record to be fully true, for example "five agents, three of them on the Microsoft Agent Framework".
- Repo visibility: make it public (after a secret scan), then set REPO_URL and re-render the end card.
- ja and en goal calls are under the +2 LU target over the founder's loudest moment.
- Nobody has listened to the film yet.
