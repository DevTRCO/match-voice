// encara look, taken from ui/public/mock4.html :root tokens. Purple and gold broadcast graphics.
// Rules for this film: no em dashes, no middle dots, no accent bars, no pills, no green, no serif.

export const FPS = 30;
export const W = 1920;
export const H = 1080;

export const C = {
  bg: '#12001a', // --bg
  panel: '#22002a', // --panel
  panel2: '#2c0536', // --panel2
  deep: '#0e0013', // --deep
  royal: '#37003c', // --royal
  royalHi: '#5a0f66', // --royal-hi
  violet: '#7b2a8c', // --violet
  text: '#fbf7fc', // --text
  mute: '#c3afcb', // --mute
  dim: '#8c7596', // --dim
  gold: '#e3b350', // --signal
  goldHi: '#f6dc9a', // --gold-hi
  goldLo: '#a9792a', // --gold-lo
  crimson: '#e8424e', // --home (Wexmoor)
  line: '#ffffff12',
  line2: '#ffffff26',
} as const;

/** Stage behind every card: the page's base gradient (#1d0021 -> #0f0014), kept linear and narrow so H.264 does not band. */
export const STAGE_BG = 'linear-gradient(180deg, #24002a 0%, #1a0020 55%, #12001a 100%)';

export const FONT = {
  // Schibsted Grotesk for every word people read; Hiragino as the system fallback for Japanese subtitles.
  ui: '"Schibsted Grotesk", "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Noto Sans JP", system-ui, sans-serif',
  // Barlow Condensed 700 only for broadcast titles, labels, numbers.
  bc: '"Barlow Condensed", "Schibsted Grotesk", sans-serif',
} as const;

/** Type scale for 1920x1080 (broadcast sizes, all even). */
export const TYPE = {
  caption: 26,
  label: 30,
  body: 40,
  sub: 44,
  title: 60,
  hero: 96,
} as const;

/** Mix levels the demo page uses (mock4.html start(), goal(), cuts). Gains, not dB. */
export const PAGE_MIX = {
  voice: 1.0,
  bed: 0.09, // normal crowd bed, after the 900 Hz low-pass
  bedUnderCut: 0.02, // while a scene card is up
  bedGoal: 0.15, // jumps here on the goal, then settles to bedAfterGoal
  bedAfterGoal: 0.08,
  roar: 0.3, // stadium-roar.mp3 on the goal (page)
  filmRoar: 0.45, // the film lifts the roar so the goal sits above the founder's voice (review 2026-10-27)
} as const;
