// Sound and subtitles of a captured page shot, rebuilt from its capture log (video/shots/<id>.json, compacted into
// shotlogs.json: play/pause/ended events and the page's own subtitle cues). Every time is a frame of the shot.
import logs from './shotlogs.json';
import {ROAR, type AudioCue} from '../audio';
import type {Cue} from '../components/Subtitles';
import {PAGE_MIX} from '../tokens';

type Ev = {tS: number; src: string; ev: string; offsetS?: number | null; volume?: number; dur?: number; synthetic?: boolean};
type PCue = {startS: number; endS: number; text: string; lang: string; moment: number; speaker: string};
type Log = {frames: number; audioEvents: Ev[]; subtitleCues: PCue[]};

export type ShotId = keyof typeof logs;
export const shotLog = (id: ShotId): Log => (logs as unknown as Record<string, Log>)[id];

const f = (s: number) => Math.round(s * 30);
const voiceSrc = (src: string) => src.replace(/^insert\/story-audio\/(.*)\.mp3$/, 'audio/story-lv/$1.wav'); // levelled copies, scripts/level-voices.py
const isVoice = (src: string) => src.startsWith('insert/story-audio/');
const isRoar = (src: string) => src.endsWith('stadium-roar.mp3');
/** moment id of a story voice file, e.g. insert/story-audio/11-162.mp3 -> 162 */
const momentOf = (src: string) => Number(src.match(/-(\d+)\.mp3$/)?.[1] ?? -1);

/**
 * Audio cues of a shot window [inS, outS) in segment seconds. A voice or roar runs from its play event to the
 * next ended/pause/play of the same file (or the window end, then it gets a 6-frame fade-out). Goal calls (moment 162)
 * and the roar are 'goal' (never ducked), everything else 'app'.
 */
export const shotAudio = (id: ShotId, inS: number, outS: number, opts: {skip?: number[]; roar?: boolean} = {}): AudioCue[] => {
  const ev = shotLog(id).audioEvents;
  const a = f(inS);
  const b = f(outS);
  const out: AudioCue[] = [];
  ev.forEach((e, i) => {
    if (e.ev !== 'play' || !(isVoice(e.src) || isRoar(e.src))) return;
    if (isRoar(e.src) && opts.roar === false) return;
    if (isVoice(e.src) && opts.skip?.includes(momentOf(e.src))) return;
    const start = f(e.tS);
    const stopEv = ev.slice(i + 1).find((x) => x.src === e.src && ['ended', 'pause', 'play'].includes(x.ev));
    const natural = start + f(e.dur ?? 0);
    const stop = Math.min(stopEv ? f(stopEv.tS) : natural, natural || Infinity);
    if (stop <= a || start >= b) return;
    const from = Math.max(start, a);
    const to = Math.min(stop, b);
    const goal = isRoar(e.src) || momentOf(e.src) === 162;
    out.push({
      src: isRoar(e.src) ? ROAR : voiceSrc(e.src),
      atS: (from - a) / 30,
      inS: (e.offsetS ?? 0) + (from - start) / 30,
      durS: (to - from) / 30,
      role: goal ? 'goal' : 'app',
      volume: isRoar(e.src) ? PAGE_MIX.filmRoar : PAGE_MIX.voice,
      fadeInS: from > start ? 0.2 : 0,
      fadeOutS: to < stop ? 0.2 : 0,
    });
  });
  return out;
};

/**
 * Subtitle cues of a shot window from the page's own subtitle log, as page cues (they cover the page's line).
 * translations: English under a non-English line, by moment id. Throws if a cue would flash for under 0.4 s.
 */
export const shotCues = (id: ShotId, inS: number, outS: number, translations: Record<number, string> = {}, moments?: number[]): Cue[] => {
  const a = f(inS);
  const b = f(outS);
  return shotLog(id)
    .subtitleCues.filter((c) => f(c.endS) > a && f(c.startS) < b && (!moments || moments.includes(c.moment)))
    .map((c) => {
      const s = Math.max(f(c.startS), a);
      const e = Math.min(f(c.endS), b);
      if (e - s < 12) throw new Error(`${id}: cue '${c.text}' only ${e - s} frames inside ${inS}..${outS}`);
      const tr = c.lang === 'en' ? undefined : translations[c.moment];
      if (c.lang !== 'en' && !tr) throw new Error(`${id}: no English for moment ${c.moment} (${c.lang})`);
      return {startS: (s - a) / 30, endS: (e - a) / 30, text: c.text, translation: tr, lang: c.lang, page: true};
    });
};

/** Cues for one pane of the split screen (plain text, segment seconds). */
export const paneCues = (id: ShotId, inS: number, outS: number, moments?: number[]) =>
  shotCues(id, inS, outS, {}, moments).map((c) => ({startS: c.startS, endS: c.endS, text: c.text}));
