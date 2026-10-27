// THE CUT. Source of truth for content: docs/VIDEO.md and the task brief (founder transcripts as spoken).
// Page shots: video/shots/*.mp4 (silent), their sound and subtitles are rebuilt from the capture logs (data/shots.ts),
// so every voice file starts on the frame the page started it and every subtitle is the page's own line.
// Founder subtitle times: whisper.cpp (ggml-small) word times on the *_blur takes; the first cue of each take starts at the
// measured speech onset (RMS, whisper puts the first word about 0.35 s early); texts from the brief.
// masterGainDb is applied inside the AudioLayer (every cue's volume), so the audio is AAC-encoded once (review 2026-10-27).
import {BED, ROAR} from './audio';
import {paneCues, shotAudio, shotCues} from './data/shots';
import {PAGE_MIX} from './tokens';
import type {Segment, Timeline} from './types';
import {segFrames} from './Main';

export const LOWER_THIRD = 'Vu Minh Tran, building encara';

// Founder takes are at -16 LUFS; in the film they sit 2 dB lower so every goal call peaks above the founder's loudest word.
const FOUNDER = 0.8;

export const RECORDED_NOTE = 'Recorded from a live run. Synthetic match data, fictional clubs and players.';

// Clip C runs as one sound cue over 7a (on camera), 7b (agents) and 7c (verifier). Cut points in C file time, from the
// 20 ms RMS envelope of C_blur.mp4: "five" starts 2.30 (dip 2.20 to 2.28), "One spots" 5.10, "Then plain code" 8.10,
// "A wrong line" 12.00, speech ends 15.52.
const C_IN = 0.0333;
const C_TO_AGENTS = 2.2667;
const C_TO_VERIFIER = 8.1;
const c = (t: number) => t - C_IN; // C file time -> 7a segment time

export const timeline: Timeline = {
  masterGainDb: 1.3,
  global: [],
  segments: [
    {
      // 1. cold open: the same goal in four languages, hard cuts, each in the breath after the scorer's name.
      // Japanese first: the goal call starts at S1 4.00 s, "フォンテーヌ！" ends at about 5.55 (RMS of 11-162.mp3)
      id: '1-ja-goal',
      type: 'shot',
      src: 'shots/S1_ja_goal.mp4',
      inS: 2.8,
      outS: 5.6,
      audio: shotAudio('S1_ja_goal', 2.8, 5.6),
      subs: [{startS: 1.2, endS: 2.8, text: 'ゴール！フォンテーヌ！', translation: 'GOAL! Fontaine!', lang: 'ja', page: true}],
      plates: [{fromS: 0, durS: 2.8, name: 'Yuki Tanaka', role: 'Japanese', face: 'yuki-tanaka', cut: true}],
      note: RECORDED_NOTE,
    },
    // then German, Spanish, Turkish
    {
      id: '9a-de-goal',
      type: 'shot',
      src: 'shots/S6_de_goal.mp4',
      inS: 3.0,
      outS: 4.8333,
      audio: shotAudio('S6_de_goal', 3.0, 4.8333),
      subs: [{startS: 0, endS: 1.8333, text: 'Tooor! Fontaine!', translation: 'GOAL! Fontaine!', lang: 'de', page: true}],
      plates: [{fromS: 0, durS: 1.8333, name: 'Jonas Weber', role: 'German', face: 'jonas-weber', cut: true}],
    },
    {
      id: '9b-es-goal',
      type: 'shot',
      src: 'shots/S6_es_goal.mp4',
      inS: 3.0,
      outS: 5.0,
      audio: shotAudio('S6_es_goal', 3.0, 5.0),
      subs: [{startS: 0, endS: 2.0, text: '¡GOOOL! ¡Fontaine!', translation: 'GOAL! Fontaine!', lang: 'es', page: true}],
      plates: [{fromS: 0, durS: 2.0, name: 'Lucía Romero', role: 'Spanish', face: 'lucia-romero', cut: true}],
    },
    {
      id: '9c-tr-goal',
      type: 'shot',
      src: 'shots/S6_tr_goal.mp4',
      inS: 3.0,
      outS: 5.0333,
      audio: shotAudio('S6_tr_goal', 3.0, 5.0333),
      subs: [{startS: 0, endS: 2.0333, text: 'GOOOL! Fontaine!', translation: 'GOAL! Fontaine!', lang: 'tr', page: true}],
      plates: [{fromS: 0, durS: 2.0333, name: 'Emre Aydın', role: 'Turkish', face: 'emre-aydin', cut: true}],
    },
    {
      id: '3-founder-A',
      type: 'founder',
      volume: FOUNDER,
      src: 'founder/A_blur.mp4',
      inS: 0,
      outS: 19.1333,
      // starts after "I'm Vu, and I'm building encara." so the same words are not on screen twice
      lowerThird: {text: LOWER_THIRD, fromS: 3.1, durS: 3.4},
      subs: [
        {startS: 0.44, endS: 3.0, text: "I'm Vu, and I'm building encara."},
        {startS: 3.04, endS: 7.55, text: 'Most football matches get commentary in one language, or none.'},
        {startS: 7.6, endS: 12.88, text: 'encara is a real-time engine that writes and speaks commentary from match data.'},
        {
          startS: 12.92,
          endS: 19.1,
          text: 'We have nine languages today, but it grows with the voice engine underneath, which already speaks more than ninety.',
        },
      ],
    },
    {
      id: '4-founder-B',
      type: 'founder',
      volume: FOUNDER,
      src: 'founder/B_blur.mp4',
      inS: 0,
      outS: 10.5,
      subs: [
        {startS: 0.33, endS: 6.0, text: "Wexmoor are a goal down, and it's the 68th minute, and the game has gone quiet."},
        // speech resumes at 6.92 (RMS); whisper put it at 6.32
        {startS: 6.9, endS: 10.45, text: "That's when a good commentator points something out."},
      ],
    },
    // 5. Scene 1: the scene card (in on S2 frame 67, the first frame with no start overlay; out before it ghosts back at w 1.45)
    {id: '5a-scene1-card', type: 'shot', src: 'shots/S2_scene1_analysis_enx.mp4', inS: 2.2333, outS: 3.4},
    {
      id: '5b-scene1-setup',
      type: 'shot',
      src: 'shots/S2_scene1_analysis_enx.mp4',
      inS: 3.8333,
      outS: 9.8,
      audio: shotAudio('S2_scene1_analysis_enx', 3.8333, 9.8),
      subs: shotCues('S2_scene1_analysis_enx', 3.8333, 9.8),
      plates: [{fromS: 0.2, durS: 2.8, name: 'Daniel Price', role: 'Co-commentator, English', face: 'daniel-price'}],
    },
    // 6. Scene 2: the card, then the long ball, first time, goal, "Pattern broken", the pay-off
    // the jump from 68' to 71' needs saying (founder 2026-10-28); the page's scene card right after says how long, so this card does not
    {id: '5c-bridge', type: 'text', durS: 3.6, lines: ['Then Wexmoor win the ball again. Watch where it goes.']},
    {id: '6a-scene2-card', type: 'shot', src: 'shots/S3_scene2_goal_enx.mp4', inS: 2.4, outS: 3.7},
    {
      id: '6b-scene2-goal',
      type: 'shot',
      src: 'shots/S3_scene2_goal_enx.mp4',
      inS: 12.3,
      outS: 28.0,
      audio: shotAudio('S3_scene2_goal_enx', 12.3, 28.0),
      subs: shotCues('S3_scene2_goal_enx', 12.3, 28.0),
      plates: [
        {fromS: 0.2, durS: 2.6, name: 'Charlie Hale', role: 'Play-by-play, English', face: 'charlie-hale'},
        {fromS: 9.6, durS: 2.6, name: 'Daniel Price', role: 'Co-commentator, English', face: 'daniel-price'},
      ],
    },
    // 7. Clip C: "Those two lines came from" on camera, then the five agents (on "five agents ... one writes the line"),
    // then the verifier catch. One continuous sound cue of 15.5667 s; all of C's subtitles live on 7a.
    {
      id: '7a-founder-C',
      type: 'founder',
      volume: FOUNDER,
      src: 'founder/C_blur.mp4',
      // frame 0 of C_blur.mp4 is black (luma 16), so the take starts one frame in
      inS: C_IN,
      outS: C_TO_AGENTS,
      voiceDurS: 15.5667,
      subs: [
        {startS: c(0.36), endS: c(5.02), text: 'Those two lines came from five agents on the Microsoft Agent Framework.'},
        {startS: c(5.08), endS: c(8.05), text: 'One spots the pattern, one writes the line.'},
        {startS: c(8.1), endS: c(11.92), text: 'Then plain code checks the names and numbers against the match data.'},
        {startS: c(11.98), endS: c(15.52), text: "A wrong line gets one retry, and if it fails, it's not spoken."},
      ],
    },
    {
      id: '7b-agents',
      type: 'agents',
      durS: C_TO_VERIFIER - C_TO_AGENTS,
      // card time = C time - 2.2667: boxes on "five", bracket on "Microsoft", Spotter on "spots", Analyst on "writes"
      boxesAtS: 0.03,
      bracketAtS: 1.13,
      highlights: [
        [0, 3.13],
        [1, 4.5],
      ],
    },
    {
      id: '7c-verifier',
      type: 'verifier',
      durS: 7.5,
      // rejected line on "plain code checks", the reason on "numbers", the accepted line on "one retry" (C 8.58, 10.08, 12.68)
      atS: [0.4833, 1.9833, 4.5833],
    },
    // the split needs its premise first (founder 2026-10-28)
    {id: '8-intro', type: 'text', durS: 3.4, lines: ['Same moment, two styles: expert or newcomer.']},
    {
      // 8. same moment, two levels (Rasmussen chests it down, 70:07): both lines exact, boards moving. The expert line is heard.
      id: '8-split',
      type: 'split',
      durS: 3.4,
      left: {src: 'shots/S3_scene2_goal_enx.mp4', inS: 8.9, label: 'Expert, Charlie Hale', cues: paneCues('S3_scene2_goal_enx', 8.9, 12.3, [1189576])},
      right: {src: 'shots/S5_en_beginner.mp4', inS: 24.9, label: 'Newcomer, Owen Carter', cues: paneCues('S5_en_beginner', 24.9, 28.3, [1189576])},
      // the line is short and the boards carry no crowd: lifted 3 dB so the split does not dip under the film
      audio: shotAudio('S3_scene2_goal_enx', 8.9, 12.3, {skip: [1189569]}).map((x) => ({...x, volume: 1.4})),
    },
    {
      id: '10a-founder-D1',
      type: 'founder',
      volume: FOUNDER,
      src: 'founder/D1_blur.mp4',
      inS: 0,
      outS: 4.3,
      subs: [{startS: 0.75, endS: 4.27, text: 'Each new language needs a prompt and word lists for the checker.'}],
    },
    {
      // D2 as voice-over over the commentator picker (Charlie Hale, Jonas Weber, Lucía Romero, Hugo Martin)
      id: '10b-picker-D2',
      type: 'shot',
      src: 'shots/S7b_picker_cycle.mp4',
      // in on frame 49: the name switches to Charlie Hale on 45, the selection ring finishes moving off Yuki Tanaka on 48
      inS: 1.6333,
      outS: 6.7667,
      // the avatar row, name line and Play button only: "Welcome to the demo" and the footer stay out
      panel: {x: 400, y: 505, w: 1120, h: 310, width: 1736, centerY: 480},
      audio: [{src: 'founder/D2_blur.mp4', atS: 0, inS: 0, durS: 5.1333, role: 'voice', volume: FOUNDER, fadeInS: 0.1, fadeOutS: 0.2}],
      subs: [{startS: 0.34, endS: 5.08, text: 'Clubs, leagues and streaming services can plug the engine into their own apps.'}],
    },
    {
      id: '10c-founder-D3',
      type: 'founder',
      volume: FOUNDER,
      src: 'founder/D3_blur.mp4',
      inS: 0,
      outS: 6.2,
      subs: [{startS: 0.33, endS: 6.12, text: 'So I want every fan to have a commentator who goes mad for their team, in their language.'}],
    },
    {id: '11-end', type: 'end', durS: 6.0},
  ],
};

// Crowd bed under the whole film at the page level, ducked -20 dB under the founder. Lifted to 0.25 under the end card so it
// does not play as silence; fades over the last 1.5 s.
const startOf = (id: string): number => {
  let f = 0;
  for (const s of timeline.segments as Segment[]) {
    if (s.id === id) return f / 30;
    f += segFrames(s);
  }
  throw new Error(`no segment ${id}`);
};
const END = startOf('11-end');
const lift = (id: string, durS: number): [number, number][] => {
  const a = startOf(id);
  return [[a, PAGE_MIX.bed], [a + 0.6, 0.25], [a + durS - 0.4, 0.25], [a + durS, PAGE_MIX.bed]];
};
timeline.global.push({
  src: BED,
  atS: 0,
  role: 'bed',
  fadeInS: 0.2,
  fadeOutS: 1.5,
  env: [
    [0, PAGE_MIX.bed],
    ...lift('5c-bridge', 3.6),
    ...lift('8-intro', 3.4),
    [END - 0.3, PAGE_MIX.bed],
    [END + 0.3, 0.25],
  ],
});
