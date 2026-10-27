import React from 'react';
import {Audio, OffthreadVideo, staticFile, useCurrentFrame} from 'remotion';
import {C, FONT, H, TYPE} from '../tokens';
import {DUR, exit, rise, s2f} from '../motion';
import {Stage} from './Stage';

/** Source window in the 1280x720 founder take. Defaults hide the ceiling lamp (bottom edge about y 95) and most of the low angle. */
export type Crop = {
  /** centre x of the window in source pixels (face is about x 680) */
  cx: number;
  /** top edge in source pixels */
  top: number;
  /** height in source pixels (bottom is clamped to 720) */
  h: number;
};

export const DEFAULT_CROP: Crop = {cx: 680, top: 128, h: 592};

export type FounderClipProps = {
  /** file under public/, e.g. founder/A_blur.mp4. Never the unblurred take. */
  src: string;
  /** in point in the source, seconds */
  inS?: number;
  /** linear gain for the voice (clips are already at -16 LUFS) */
  volume?: number;
  /** audio only: the parent supplies the picture */
  voiceOver?: boolean;
  crop?: Crop;
  /** window aspect, width / height (4:5 default) */
  aspect?: number;
  /** window height as a share of frame height */
  heightShare?: number;
  /** left edge of the window in frame pixels */
  left?: number;
  lowerThird?: {text: string; fromS: number; durS: number};
  /** one quiet line of context to the right of the window */
  context?: string;
};

const even = (v: number) => Math.round(v / 2) * 2;

export const FounderClip: React.FC<FounderClipProps> = ({
  src,
  inS = 0,
  volume = 1,
  voiceOver = false,
  crop = DEFAULT_CROP,
  aspect = 16 / 9,
  heightShare = 900 / 1080,
  left,
  lowerThird,
  context,
}) => {
  const frame = useCurrentFrame();
  const startFrom = s2f(inS);
  if (voiceOver) return <Audio src={staticFile(src)} startFrom={startFrom} volume={volume} />;

  const boxH = even(H * heightShare);
  const boxW = even(boxH * aspect);
  const top = Math.round((H - boxH) / 2);
  // centred on the same axis as the subtitles (review: a left window left half the frame empty)
  const x = left ?? Math.round((1920 - boxW) / 2);
  const srcH = Math.min(crop.h, 720 - crop.top);
  const scale = boxH / srcH;
  const srcW = boxW / scale;
  const x0 = Math.max(0, Math.min(1280 - srcW, crop.cx - srcW / 2));

  // lower third: one line on a dark plate, bottom left on the video, above the subtitle band (2-line band top is about y 876).
  // Rise 18 f, hold, fade 12 f.
  let lt: React.ReactNode = null;
  if (lowerThird) {
    const a = s2f(lowerThird.fromS);
    const b = a + s2f(lowerThird.durS);
    const r = rise(frame, a, DUR.standard, 16);
    const o = r.opacity * exit(frame, b - DUR.small, DUR.small);
    if (frame >= a && frame < b) {
      const i = lowerThird.text.indexOf(', ');
      const name = i < 0 ? lowerThird.text : lowerThird.text.slice(0, i);
      const rest = i < 0 ? '' : lowerThird.text.slice(i);
      lt = (
        <div
          style={{
            position: 'absolute',
            left: x + 40,
            top: 772,
            opacity: o,
            transform: r.transform,
            fontFamily: FONT.bc,
            fontWeight: 700,
            fontSize: 52,
            lineHeight: 1,
            letterSpacing: '0.01em',
            background: 'rgba(14, 0, 19, 0.86)',
            boxShadow: '0 0 0 1px #ffffff14',
            borderRadius: 4,
            padding: '14px 24px 16px',
            whiteSpace: 'nowrap',
          }}
        >
          <span style={{color: C.text}}>{name}</span>
          <span style={{color: C.gold}}>{rest}</span>
        </div>
      );
    }
  }

  return (
    <Stage>
      <div
        style={{
          position: 'absolute',
          left: x,
          top,
          width: boxW,
          height: boxH,
          overflow: 'hidden',
          borderRadius: 8,
          background: C.deep,
          boxShadow: '0 0 0 1px #ffffff14, 0 40px 90px -20px #000, 0 18px 40px #0008',
        }}
      >
        <OffthreadVideo
          src={staticFile(src)}
          startFrom={startFrom}
          volume={volume}
          style={{
            position: 'absolute',
            width: 1280 * scale,
            height: 720 * scale,
            left: -x0 * scale,
            top: -crop.top * scale,
            maxWidth: 'none',
          }}
        />
      </div>
      {context ? (
        <div
          style={{
            position: 'absolute',
            left: x + 40,
            top: top + 32,
            width: boxW - 80,
            fontSize: TYPE.body,
            fontWeight: 600,
            color: C.mute,
            lineHeight: 1.3,
          }}
        >
          {context}
        </div>
      ) : null}
      {lt}
    </Stage>
  );
};
