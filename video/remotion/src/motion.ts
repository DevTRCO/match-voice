import {Easing, interpolate} from 'remotion';
import {FPS} from './tokens';

/** The one easing curve (neo-motion 02). */
export const EASE = Easing.bezier(0.3, 0, 0.1, 1);

/** Duration tokens in frames @30 fps. No other lengths. */
export const DUR = {micro: 6, small: 12, standard: 18, large: 24, hero: 30} as const;

/** Minimum hold after any landing. */
export const HOLD = 8;

/** Reading time: frames per word on screen after landing. */
export const READ_F_PER_WORD = 9;

export const s2f = (s: number): number => Math.round(s * FPS);

/** Eased 0..1 over [start, start+dur]. */
export const enter = (frame: number, start: number, dur: number = DUR.standard): number =>
  interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: EASE,
  });

/** Eased 1..0 over [start, start+dur]. */
export const exit = (frame: number, start: number, dur: number = DUR.small): number => 1 - enter(frame, start, dur);

/** Rise: opacity 0 -> 1 and y +dy -> 0, whole pixels at rest. */
export const rise = (frame: number, start: number, dur: number = DUR.standard, dy = 24) => {
  const p = enter(frame, start, dur);
  const y = p >= 1 ? 0 : dy * (1 - p);
  return {opacity: p, transform: `translateY(${p >= 1 ? 0 : y.toFixed(2)}px)`};
};

export const words = (s: string): number => s.trim().split(/\s+/).filter(Boolean).length;

/** Frames a text must stay readable after it lands (>= 9 f per word, >= HOLD). */
export const readFrames = (s: string): number => Math.max(HOLD, words(s) * READ_F_PER_WORD);
