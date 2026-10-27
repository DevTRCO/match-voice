import React from 'react';
import {Img, staticFile, useCurrentFrame} from 'remotion';
import {C, FONT} from '../tokens';
import {DUR, exit, rise, s2f} from '../motion';

/**
 * Commentator name plate over a page shot: face, name, role. Barlow 700 on a dark plate (radius 4, no pill, no accent bar).
 * Sits bottom left between the pitch (bottom edge y 772) and the subtitle band (top y 869 with a translation), x clear of the
 * page's insight labels. `cut` = appears on the cut with no motion (2 s montage shots); otherwise rises 12 f and fades 12 f.
 */
export type PlateSpec = {fromS: number; durS: number; name: string; role: string; face: string; cut?: boolean};

export const Plate: React.FC<{p: PlateSpec}> = ({p}) => {
  const f = useCurrentFrame();
  const a = s2f(p.fromS);
  const b = a + s2f(p.durS);
  if (f < a || f >= b) return null;
  const r = p.cut ? {opacity: 1, transform: 'none'} : rise(f, a, DUR.small, 12);
  const o = p.cut ? 1 : r.opacity * exit(f, b - DUR.small, DUR.small);
  return (
    <div
      style={{
        position: 'absolute',
        left: 96,
        top: 784,
        height: 68,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '0 22px 0 6px',
        background: 'rgba(14, 0, 19, 0.9)',
        boxShadow: '0 0 0 1px #ffffff18',
        borderRadius: 4,
        opacity: o,
        transform: r.transform,
        fontFamily: FONT.bc,
        fontWeight: 700,
        whiteSpace: 'nowrap',
      }}
    >
      <Img src={staticFile(`faces/${p.face}.jpg`)} style={{width: 56, height: 56, borderRadius: 3, objectFit: 'cover'}} />
      <div style={{fontSize: 40, color: C.text, letterSpacing: '0.01em', lineHeight: 1}}>{p.name}</div>
      <div style={{fontSize: 30, color: C.gold, letterSpacing: '0.04em', textTransform: 'uppercase', lineHeight: 1, paddingTop: 4}}>{p.role}</div>
    </div>
  );
};
