import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {C, TYPE} from '../tokens';
import {DUR, exit, readFrames, rise} from '../motion';
import {Stage} from './Stage';

export type TextCardProps = {
  /** one or two lines; each line rises on its own */
  lines: string[];
  /** frame the first line starts to rise */
  startF?: number;
  /** frames between line 1 landing and line 2 starting (0 = right after the hold) */
  gapF?: number;
  /** fade the card text out at the end of the sequence */
  fadeOut?: boolean;
  size?: number;
};

/**
 * Full-frame purple card. Line k rises (18 f, 24 px) after line k-1 has landed and held 8 f.
 * readyAt() tells the caller the earliest frame the card may end (>= 9 f per word after the last line lands).
 */
export const TextCard: React.FC<TextCardProps> = ({lines, startF = 6, gapF = 0, fadeOut = true, size = TYPE.title}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const starts = cardStarts(lines, startF, gapF);
  const out = fadeOut ? exit(frame, durationInFrames - DUR.small, DUR.small) : 1;
  return (
    <Stage>
      <div
        style={{
          position: 'absolute',
          left: 200,
          right: 200,
          top: 0,
          bottom: 0,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          gap: 28,
          opacity: out,
        }}
      >
        {lines.map((l, k) => {
          const r = rise(frame, starts[k], DUR.standard, 24);
          return (
            <div
              key={k}
              style={{
                ...r,
                fontSize: k === 0 ? size : Math.round(size * 0.8),
                fontWeight: k === 0 ? 700 : 600,
                color: k === 0 ? C.text : C.mute,
                lineHeight: 1.18,
                letterSpacing: '-0.015em',
                maxWidth: 1400,
              }}
            >
              {l}
            </div>
          );
        })}
      </div>
    </Stage>
  );
};

export const cardStarts = (lines: string[], startF = 6, gapF = 0): number[] => {
  const s: number[] = [];
  let f = startF;
  for (let k = 0; k < lines.length; k++) {
    s.push(f);
    f += DUR.standard + Math.max(8, gapF);
  }
  return s;
};

/** Earliest end frame for a TextCard: last line landed + reading time of all words + exit. */
export const textCardMinFrames = (lines: string[], startF = 6, gapF = 0): number => {
  const st = cardStarts(lines, startF, gapF);
  const landed = st[st.length - 1] + DUR.standard;
  return landed + readFrames(lines.join(' ')) + DUR.small;
};
