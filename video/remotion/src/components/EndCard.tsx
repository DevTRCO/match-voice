import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C, FONT, TYPE} from '../tokens';
import {DUR, rise} from '../motion';
import {Stage} from './Stage';

export const DEMO_URL = 'https://happy-bush-012530710.5.azurestaticapps.net';
/**
 * Repository link for the end card. null = no Code row. DevTRCO/match-voice is private (gh api: visibility private,
 * anonymous HTTP 404), so the row is off; set it back to 'github.com/DevTRCO/match-voice' once the repo is public.
 */
export const REPO_URL: string | null = null;
export const DISCLAIMER = 'All clubs, players and match data are synthetic. Recorded from a live run.';

const strip = (u: string) => u.replace(/^https?:\/\//, '');

export const EndCard: React.FC<{startF?: number}> = ({startF = 0}) => {
  const f = useCurrentFrame();
  return (
    <Stage>
      <div style={{position: 'absolute', left: 200, right: 200, top: 0, bottom: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
        <div style={{fontSize: 150, fontWeight: 700, letterSpacing: '-0.04em', lineHeight: 1, color: C.text, ...rise(f, startF, DUR.large, 24)}}>encara</div>
        <div style={{fontSize: TYPE.title - 12, fontWeight: 600, color: C.gold, marginTop: 18, ...rise(f, startF + 8, DUR.large, 24)}}>real-time commentary engine</div>
        <div style={{marginTop: 72, display: 'flex', flexDirection: 'column', gap: 14, ...rise(f, startF + 16, DUR.large, 16)}}>
          <Row k="Demo" v={strip(DEMO_URL)} />
          {REPO_URL ? <Row k="Code" v={strip(REPO_URL)} /> : null}
        </div>
      </div>
      <div style={{position: 'absolute', left: 200, right: 200, bottom: 88, fontSize: TYPE.label, color: C.mute, ...rise(f, startF + 16, DUR.large, 0)}}>{DISCLAIMER}</div>
    </Stage>
  );
};

const Row: React.FC<{k: string; v: string}> = ({k, v}) => (
  <div style={{display: 'flex', alignItems: 'baseline', gap: 28}}>
    <div style={{width: 110, fontFamily: FONT.bc, fontWeight: 700, fontSize: TYPE.label, letterSpacing: '0.06em', textTransform: 'uppercase', color: C.dim}}>{k}</div>
    <div style={{fontSize: TYPE.body, fontWeight: 600, color: C.text}}>{v}</div>
  </div>
);
