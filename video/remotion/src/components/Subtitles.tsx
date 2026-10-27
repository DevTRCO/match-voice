import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {C, FONT} from '../tokens';
import {DUR, enter, exit, s2f} from '../motion';

export type Cue = {
  startS: number;
  endS: number;
  /** what is said, in its own language */
  text: string;
  /** English line under non-English text */
  translation?: string;
  /** japanese etc.: set lang so the system CJK font is picked */
  lang?: string;
  /**
   * A line spoken on a captured page shot. The page draws its own subtitle at y 930 to 982; a page cue is an opaque,
   * fixed-width band (bottom edge y 1002, above the page's progress bar and name plate) that covers it, with no fade, so the
   * page's own line never shows next to ours.
   */
  page?: boolean;
  /** custom placement (voice-over over a busy page): band bottom from the frame bottom, centre x of the band, max width */
  bottom?: number;
  centerX?: number;
  maxWidth?: number;
};

const PAGE_BAND_BOTTOM = 78;
const PAGE_BAND_W = 1640;
const PAGE_BAND_BG = '#12001a';

export type SubtitlesProps = {
  cues: Cue[];
  /** distance of the band's bottom edge from the frame bottom */
  bottom?: number;
  maxWidth?: number;
};

/**
 * Burned-in subtitles. One cue at a time (cues must not overlap; checkCues() throws if they do).
 * A translucent dark band with a small radius (no pill), Schibsted Grotesk 600, the English translation under it in 400.
 * Each element is clamped to two lines. Cue fades in 6 f and out 6 f, never overlapping the next cue.
 */
export const Subtitles: React.FC<SubtitlesProps> = ({cues, bottom = 64, maxWidth = 1500}) => {
  const frame = useCurrentFrame();
  const cue = cues.find((c) => frame >= s2f(c.startS) && frame < s2f(c.endS));
  if (!cue) return null;
  const a = s2f(cue.startS);
  const b = s2f(cue.endS);
  const o = cue.page ? 1 : Math.min(enter(frame, a, DUR.micro), exit(frame, b - DUR.micro, DUR.micro));
  const bot = cue.page ? PAGE_BAND_BOTTOM : cue.bottom ?? bottom;
  const cx = cue.centerX ?? 960;
  const mw = cue.page ? PAGE_BAND_W : cue.maxWidth ?? maxWidth;
  const half = Math.min(cx, 1920 - cx);
  const clamp2 = {display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', textWrap: 'balance'} as React.CSSProperties;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: cx - half, width: 2 * half, bottom: bot, display: 'flex', justifyContent: 'center', opacity: o}}>
        <div
          lang={cue.lang}
          style={{
            maxWidth: mw,
            width: cue.page ? PAGE_BAND_W : undefined,
            boxSizing: 'border-box',
            background: cue.page ? PAGE_BAND_BG : 'rgba(14, 0, 19, 0.78)',
            borderRadius: 4,
            padding: '14px 28px 16px',
            textAlign: 'center',
            fontFamily: FONT.ui,
            boxShadow: '0 0 0 1px #ffffff10',
          }}
        >
          <div style={{...clamp2, fontSize: 44, fontWeight: 600, lineHeight: 1.25, color: C.text}}>{cue.text}</div>
          {cue.translation ? (
            <div style={{...clamp2, fontSize: 32, fontWeight: 400, lineHeight: 1.3, color: C.goldHi, marginTop: 6}}>{cue.translation}</div>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Validate a cue list: ordered, no overlap, no forbidden punctuation, each shown >= 9 f per word. Returns problems. */
export const checkCues = (cues: Cue[]): string[] => {
  const p: string[] = [];
  cues.forEach((c, i) => {
    if (c.endS <= c.startS) p.push(`cue ${i} ends before it starts`);
    if (i > 0 && c.startS < cues[i - 1].endS) p.push(`cue ${i} overlaps cue ${i - 1}`);
    for (const t of [c.text, c.translation ?? '']) if (/[—·・]/.test(t)) p.push(`cue ${i} has an em dash or a middle dot`);
    const words = (c.translation ?? c.text).split(/\s+/).filter(Boolean).length;
    const f = s2f(c.endS) - s2f(c.startS);
    if (f < words * 9) p.push(`cue ${i} on screen ${f} f, needs ${words * 9} f for ${words} words`);
  });
  return p;
};
