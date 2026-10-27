import React from 'react';
import {Img, staticFile, useCurrentFrame} from 'remotion';
import {C, FONT, TYPE} from '../tokens';
import {DUR, rise} from '../motion';
import {Stage} from './Stage';

export const DEMO_URL = 'https://happy-bush-012530710.5.azurestaticapps.net';
/** Repository link for the end card (public since 2026-10-27). null = no Code row. */
export const REPO_URL: string | null = 'https://github.com/DevTRCO/match-voice';
export const DISCLAIMER = 'All clubs, players and match data are synthetic. Recorded from a live run.';

const strip = (u: string) => u.replace(/^https?:\/\//, '');

// An invitation, not a sign-off (founder 2026-10-28): what to do next, the link, and the page itself next to it.
export const EndCard: React.FC<{startF?: number}> = ({startF = 0}) => {
  const f = useCurrentFrame();
  return (
    <Stage>
      <div style={{position: 'absolute', left: 120, width: 900, top: 0, bottom: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
        <div style={{fontSize: 40, fontWeight: 700, letterSpacing: '-0.02em', color: C.gold, ...rise(f, startF, DUR.large, 24)}}>encara</div>
        <div style={{fontSize: 96, fontWeight: 700, letterSpacing: '-0.035em', lineHeight: 1.04, color: C.text, marginTop: 18, ...rise(f, startF + 6, DUR.large, 24)}}>
          Experience the whole demo
        </div>
        <div style={{fontSize: 36, fontWeight: 500, lineHeight: 1.3, color: C.mute, marginTop: 26, ...rise(f, startF + 12, DUR.large, 16)}}>
          Pick any of nine languages, see how it works, and generate a new run live.
        </div>
        <div style={{marginTop: 56, display: 'flex', flexDirection: 'column', gap: 16, ...rise(f, startF + 18, DUR.large, 16)}}>
          <Row k="Demo" v={strip(DEMO_URL)} hi />
          {REPO_URL ? <Row k="Code" v={strip(REPO_URL)} /> : null}
        </div>
      </div>
      <div style={{position: 'absolute', left: 1110, top: 300, width: 730, borderRadius: 10, overflow: 'hidden', boxShadow: '0 0 0 1px #ffffff1f, 0 40px 90px -24px #000', ...rise(f, startF + 10, DUR.large, 24)}}>
        <Img src={staticFile('img/demo.jpg')} style={{width: '100%', display: 'block'}} />
      </div>
      <div style={{position: 'absolute', left: 120, right: 120, bottom: 72, fontSize: TYPE.label, color: C.mute, ...rise(f, startF + 18, DUR.large, 0)}}>{DISCLAIMER}</div>
    </Stage>
  );
};

const Row: React.FC<{k: string; v: string; hi?: boolean}> = ({k, v, hi}) => (
  <div style={{display: 'flex', alignItems: 'baseline', gap: 28}}>
    <div style={{width: 90, flex: 'none', fontFamily: FONT.bc, fontWeight: 700, fontSize: TYPE.label, letterSpacing: '0.06em', textTransform: 'uppercase', color: C.dim}}>{k}</div>
    <div style={{fontSize: hi ? 34 : 30, fontWeight: 600, color: hi ? C.gold : C.text, whiteSpace: 'nowrap'}}>{v}</div>
  </div>
);
