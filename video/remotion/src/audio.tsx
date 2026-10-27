import React from 'react';
import {Audio, Sequence, interpolate, staticFile} from 'remotion';
import {EASE, s2f} from './motion';
import {PAGE_MIX} from './tokens';

/**
 * Audio layer API.
 *  role 'voice'  founder speech (on camera or voice-over). Never ducked. Defines the duck windows.
 *  role 'app'    demo page sound (commentator lines, crowd). Ducked under 'voice'.
 *  role 'goal'   a goal call or its roar. NEVER ducked (rule: never duck under a goal call).
 *  role 'bed'    crowd bed (pre-filtered, see BED). Ducked under 'voice'.
 * Times in a segment are relative to the segment start; the Main composition makes them absolute.
 */
export type Role = 'voice' | 'app' | 'goal' | 'bed';

export type AudioCue = {
  src: string; // under public/, mp3/wav/mp4
  atS: number; // where it starts on the timeline (segment-relative in timeline.ts, absolute after resolve)
  inS?: number; // in point inside the file
  durS?: number; // play length (default: to the end of the file or of the segment)
  volume?: number; // linear gain
  role: Role;
  fadeInS?: number;
  fadeOutS?: number;
  /** volume keyframes in seconds relative to the cue start, e.g. [[0, .09], [2, .15]] (overrides volume) */
  env?: Array<[number, number]>;
};

/** Low-passed crowd bed: ffmpeg lowpass 900 Hz, Q 1.122 (WebAudio BiquadFilter Q 1 dB, as mock4.html line 1725), starting at 40 s of stadium-bed.mp3 like the page. */
export const BED = 'audio/stadium-bed-lp900.wav';
export const ROAR = 'audio/stadium-roar.mp3';
export const storyVoice = (ch: number, m: number): string => `audio/story-audio/${ch}-${m}.mp3`;

/**
 * Commentator lines of one page take, placed where the page spoke them.
 * lines: from the page, `__mock.D.LINES.map(l => ({m: l.m, w: l.ws[ch], kind: l.kind}))` for the channel captured.
 * shotStartW: the page time w at the first frame of the captured shot. inShotS: the in point used on the shot.
 */
export const pageVoiceCues = (
  ch: number,
  lines: Array<{m: number; w: number | null; kind?: string}>,
  shotStartW: number,
  inShotS = 0,
): AudioCue[] =>
  lines
    .filter((l) => l.w != null)
    .map((l) => ({
      src: storyVoice(ch, l.m),
      atS: (l.w as number) - shotStartW - inShotS,
      role: l.kind === 'goal' ? ('goal' as const) : ('app' as const),
      volume: PAGE_MIX.voice,
    }))
    .filter((c) => c.atS > -0.05);

export const DUCK = {
  gain: 0.1, // -20 dB under the founder
  attackF: 6, // inside the voice window, so a shot that ends at the cut is never ducked
  releaseF: 12,
} as const;

/** Founder voice windows in frames (absolute) from resolved cues. */
export const voiceWindows = (cues: AudioCue[], fallbackDurS = 0): Array<[number, number]> =>
  cues
    .filter((c) => c.role === 'voice')
    .map((c) => [s2f(c.atS), s2f(c.atS + (c.durS ?? fallbackDurS))] as [number, number]);

/** Duck multiplier at absolute frame f. */
export const duckAt = (f: number, wins: Array<[number, number]>): number => {
  let g = 1;
  for (const [a, b] of wins) {
    if (f < a) continue;
    const down = interpolate(f, [a, a + DUCK.attackF], [1, DUCK.gain], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: EASE});
    const up = interpolate(f, [b, b + DUCK.releaseF], [DUCK.gain, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: EASE});
    const v = f <= b ? down : up;
    g = Math.min(g, v);
  }
  return g;
};

const envAt = (t: number, env: Array<[number, number]>): number => {
  if (env.length === 1) return env[0][1];
  return interpolate(t, env.map((e) => e[0]), env.map((e) => e[1]), {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
};

/** Renders absolute cues. Every cue is its own Sequence; volume is a per-frame function (envelope x fades x duck). */
export const AudioLayer: React.FC<{cues: AudioCue[]; totalF: number; gainDb?: number}> = ({cues, totalF, gainDb = 0}) => {
  const wins = voiceWindows(cues);
  const master = Math.pow(10, gainDb / 20);
  return (
    <>
      {cues.map((c, i) => {
        const from = s2f(c.atS);
        const dur = c.durS != null ? s2f(c.durS) : totalF - from;
        if (dur <= 0) return null;
        const base = (c.volume ?? 1) * master;
        const fi = s2f(c.fadeInS ?? 0);
        const fo = s2f(c.fadeOutS ?? 0);
        const vol = (lf: number) => {
          let v = c.env ? envAt(lf / 30, c.env) * master : base;
          if (fi > 0) v *= interpolate(lf, [0, fi], [0, 1], {extrapolateRight: 'clamp', easing: EASE});
          if (fo > 0) v *= interpolate(lf, [dur - fo, dur], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: EASE});
          if (c.role === 'app' || c.role === 'bed') v *= duckAt(from + lf, wins);
          return v;
        };
        return (
          <Sequence key={i} from={from} durationInFrames={dur} name={`${c.role} ${c.src}`} layout="none">
            <Audio src={staticFile(c.src)} startFrom={s2f(c.inS ?? 0)} volume={vol} />
          </Sequence>
        );
      })}
    </>
  );
};
