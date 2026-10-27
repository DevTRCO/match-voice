import React from 'react';
import {AbsoluteFill, OffthreadVideo, Sequence, getStaticFiles, staticFile} from 'remotion';
import {AudioLayer, type AudioCue} from './audio';
import {AgentCard} from './components/AgentCard';
import {EndCard} from './components/EndCard';
import {Plate} from './components/Plate';
import {FounderClip} from './components/FounderClip';
import {SplitScreen} from './components/SplitScreen';
import {Stage} from './components/Stage';
import {Subtitles, type Cue} from './components/Subtitles';
import {TextCard} from './components/TextCard';
import {VerifierCatch} from './components/VerifierCatch';
import {s2f} from './motion';
import {C, FONT} from './tokens';
import type {Segment, Timeline} from './types';

export const segFrames = (s: Segment): number => (s.type === 'founder' || s.type === 'shot' ? s2f(s.outS - s.inS) : s2f(s.durS));

export type Resolved = {seg: Segment; from: number; frames: number};

/** Lays the segments end to end (hard cuts), makes subtitle and audio times absolute. */
export const resolve = (tl: Timeline) => {
  let f = 0;
  const parts: Resolved[] = [];
  const subs: Cue[] = [];
  const audio: AudioCue[] = [...tl.global];
  for (const seg of tl.segments) {
    const frames = segFrames(seg);
    parts.push({seg, from: f, frames});
    const t0 = f / 30;
    // founder cues sit inside the 16:9 window (bottom edge y 990): band bottom 24 px above it, on the same centre axis
    for (const c of seg.subs ?? []) subs.push({...(seg.type === 'founder' && !c.page ? {bottom: 114} : {}), ...c, startS: t0 + c.startS, endS: t0 + c.endS});
    for (const a of seg.audio ?? []) audio.push({...a, atS: t0 + a.atS});
    if (seg.type === 'founder') audio.push({src: seg.src, atS: t0, inS: seg.inS, durS: seg.voiceDurS ?? seg.outS - seg.inS, role: 'voice', volume: seg.volume ?? 1, fadeInS: 0.1, fadeOutS: 0.2});
    f += frames;
  }
  return {parts, subs, audio, totalF: f};
};

const has = (src: string): boolean => {
  try {
    return getStaticFiles().some((x) => x.name === src);
  } catch {
    return true;
  }
};

const Pending: React.FC<{src: string}> = ({src}) => (
  <Stage flat>
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', fontFamily: FONT.bc, fontWeight: 700, fontSize: 48, color: C.dim, letterSpacing: '0.04em'}}>
      SHOT PENDING: {src}
    </AbsoluteFill>
  </Stage>
);

const Picture: React.FC<{seg: Segment}> = ({seg}) => {
  switch (seg.type) {
    case 'founder':
      // founder sound is placed by the AudioLayer (so ducking sees it); the picture plays muted
      return <FounderClip src={seg.src} inS={seg.inS} volume={0} crop={seg.crop} lowerThird={seg.lowerThird} context={seg.context} />;
    case 'shot':
      if (seg.panel && has(seg.src)) {
        const p = seg.panel;
        const k = p.width / p.w;
        const h = Math.round(p.h * k);
        return (
          <Stage>
            <div style={{position: 'absolute', left: (1920 - p.width) / 2, top: Math.round(p.centerY - h / 2), width: p.width, height: h, overflow: 'hidden', borderRadius: 8, boxShadow: '0 0 0 1px #ffffff14, 0 30px 70px -20px #000'}}>
              <OffthreadVideo src={staticFile(seg.src)} startFrom={s2f(seg.inS)} muted style={{position: 'absolute', width: 1920 * k, height: 1080 * k, left: -p.x * k, top: -p.y * k, maxWidth: 'none'}} />
            </div>
          </Stage>
        );
      }
      return has(seg.src) ? (
        <AbsoluteFill style={{background: C.bg}}>
          <OffthreadVideo src={staticFile(seg.src)} startFrom={s2f(seg.inS)} muted style={{width: '100%', height: '100%'}} />
        </AbsoluteFill>
      ) : (
        <Pending src={seg.src} />
      );
    case 'text':
      return <TextCard lines={seg.lines} />;
    case 'verifier':
      return <VerifierCatch atS={seg.atS} />;
    case 'split':
      return has(seg.left.src) && has(seg.right.src) ? <SplitScreen left={seg.left} right={seg.right} /> : <Pending src={`${seg.left.src} + ${seg.right.src}`} />;
    case 'agents':
      return <AgentCard boxesAtS={seg.boxesAtS} bracketAtS={seg.bracketAtS} highlights={seg.highlights} />;
    case 'end':
      return <EndCard />;
  }
};

/** One quiet line in the page's top strip, between the page tagline (ends x 470) and the "How does it work?" button (starts x 1750). */
const Note: React.FC<{text: string}> = ({text}) => (
  <div style={{position: 'absolute', right: 200, top: 13, height: 34, display: 'flex', alignItems: 'center', fontFamily: FONT.ui, fontSize: 24, fontWeight: 500, color: C.mute, whiteSpace: 'nowrap'}}>
    {text}
  </div>
);

export const Main: React.FC<{timeline: Timeline}> = ({timeline}) => {
  const r = resolve(timeline);
  return (
    <AbsoluteFill style={{background: C.bg}}>
      {r.parts.map(({seg, from, frames}) => (
        <Sequence key={seg.id} name={seg.id} from={from} durationInFrames={frames}>
          <Picture seg={seg} />
          {(seg.plates ?? []).map((p, i) => (
            <Plate key={i} p={p} />
          ))}
          {seg.note ? <Note text={seg.note} /> : null}
        </Sequence>
      ))}
      <Subtitles cues={r.subs} />
      <AudioLayer cues={r.audio} totalF={r.totalF} gainDb={timeline.masterGainDb} />
    </AbsoluteFill>
  );
};
