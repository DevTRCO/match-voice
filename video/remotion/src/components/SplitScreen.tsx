import React from 'react';
import {OffthreadVideo, staticFile, useCurrentFrame} from 'remotion';
import {C, FONT, TYPE} from '../tokens';
import {DUR, enter, exit, rise, s2f} from '../motion';
import {Stage} from './Stage';

/** A caption under one pane, seconds relative to the split's start. */
export type SideCue = {startS: number; endS: number; text: string};

export type Side = {src: string; inS?: number; label: string; volume?: number; cues?: SideCue[]};

/** Source window of the 1920x1080 page shot shown in a pane: score bug, insight card and pitch; the page's own subtitle and controls stay out. */
export type PaneCrop = {x: number; y: number; w: number; h: number};
export const DEFAULT_PANE_CROP: PaneCrop = {x: 80, y: 200, w: 1760, h: 590}; // the pitch only (header strip and score bug out)

export type SplitScreenProps = {left: Side; right: Side; labelAtS?: number; crop?: PaneCrop};

const GUTTER = 48;
const GAP = 32;
const BOX_W = (1920 - 2 * GUTTER - GAP) / 2; // 896

/**
 * Two page shots side by side, cropped to the board, each with a small Barlow label above it and its own line under it
 * (the page's subtitle is cropped away, so nothing is shown twice). Sound comes from the parent's audio layer.
 */
export const SplitScreen: React.FC<SplitScreenProps> = ({left, right, labelAtS = 0, crop = DEFAULT_PANE_CROP}) => {
  const frame = useCurrentFrame();
  const scale = BOX_W / crop.w;
  const boxH = Math.round((crop.h * scale) / 2) * 2;
  const capH = 150;
  const top = Math.round((1080 - (58 + boxH + 28 + capH)) / 2) + 58;
  const r = rise(frame, s2f(labelAtS), DUR.standard, 12);
  const box = (s: Side, x: number) => {
    const cue = (s.cues ?? []).find((c) => frame >= s2f(c.startS) && frame < s2f(c.endS));
    const co = cue ? Math.min(enter(frame, s2f(cue.startS), DUR.micro), exit(frame, s2f(cue.endS) - DUR.micro, DUR.micro)) : 0;
    return (
      <React.Fragment key={s.label}>
        <div
          style={{
            position: 'absolute',
            left: x,
            top: top - 58,
            fontFamily: FONT.bc,
            fontWeight: 700,
            fontSize: TYPE.label + 4,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: C.gold,
            ...r,
          }}
        >
          {s.label}
        </div>
        <div
          style={{
            position: 'absolute',
            left: x,
            top,
            width: BOX_W,
            height: boxH,
            overflow: 'hidden',
            borderRadius: 8,
            background: C.deep,
            boxShadow: '0 0 0 1px #ffffff14, 0 30px 70px -20px #000',
          }}
        >
          <OffthreadVideo
            src={staticFile(s.src)}
            startFrom={s2f(s.inS ?? 0)}
            muted
            style={{position: 'absolute', width: 1920 * scale, height: 1080 * scale, left: -crop.x * scale, top: -crop.y * scale, maxWidth: 'none'}}
          />
        </div>
        {cue ? (
          <div
            style={{
              position: 'absolute',
              left: x,
              width: BOX_W,
              top: top + boxH + 28,
              opacity: co,
              fontFamily: FONT.ui,
              fontSize: 48,
              fontWeight: 600,
              lineHeight: 1.3,
              color: C.text,
              textWrap: 'balance',
            } as React.CSSProperties}
          >
            {cue.text}
          </div>
        ) : null}
      </React.Fragment>
    );
  };
  return (
    <Stage>
      {box(left, GUTTER)}
      {box(right, GUTTER + BOX_W + GAP)}
    </Stage>
  );
};
