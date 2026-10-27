import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C, FONT, TYPE} from '../tokens';
import {DUR, rise, s2f} from '../motion';
import {Stage} from './Stage';
import {verifierCatch} from '../data/story';

// The real catch from the recorded run: es/expert, moment 3339167 (68').
// The Spanish lines and the reason code come from story.json; the glosses and the plain reason are ours.
const LOG = verifierCatch('es/expert', 'ganado');

export const VERIFIER_COPY = {
  flagged: 'ganado',
  rejectedGloss: 'Wexmoor claw points back: they have won three times after going behind this season.',
  rejectedGlossMark: 'won',
  reason: 'The record counts points after being behind, not wins',
  acceptedGloss: 'Third time this season that Wexmoor take points after going behind.',
  acceptedMark: 'suma puntos',
  acceptedGlossMark: 'take points',
} as const;

export type VerifierCatchProps = {
  /** seconds (inside the sequence) when each block rises: rejected line, reason, accepted line */
  atS?: [number, number, number];
};

/** Mark one phrase of a line with a colour (no underline, no box). */
const Mark: React.FC<{text: string; mark: string; color: string}> = ({text, mark, color}) => {
  const i = text.indexOf(mark);
  if (i < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, i)}
      <span style={{color}}>{mark}</span>
      {text.slice(i + mark.length)}
    </>
  );
};

const Label: React.FC<{children: React.ReactNode; color: string}> = ({children, color}) => (
  <div style={{fontFamily: FONT.bc, fontWeight: 700, fontSize: TYPE.label, letterSpacing: '0.06em', textTransform: 'uppercase', color, marginBottom: 14}}>
    {children}
  </div>
);

export const VerifierCatch: React.FC<VerifierCatchProps> = ({atS = [0.2, 3.4, 6.2]}) => {
  const frame = useCurrentFrame();
  const [a, b, c] = atS.map(s2f);
  const V = VERIFIER_COPY;
  const line: React.CSSProperties = {fontSize: 50, fontWeight: 600, lineHeight: 1.22, letterSpacing: '-0.01em', color: C.text};
  const gloss: React.CSSProperties = {fontSize: 32, fontWeight: 400, lineHeight: 1.3, color: C.mute, marginTop: 10};
  return (
    <Stage>
      <div style={{position: 'absolute', left: 200, right: 200, top: 120, display: 'flex', flexDirection: 'column'}}>
        <div style={{fontFamily: FONT.bc, fontWeight: 700, fontSize: TYPE.label, letterSpacing: '0.06em', color: C.dim, textTransform: 'uppercase', marginBottom: 56, ...rise(frame, a, DUR.standard, 0)}}>
          Verifier log, Spanish expert channel, {LOG.minute}&apos;
        </div>

        <div style={rise(frame, a, DUR.standard)}>
          <Label color={C.crimson}>Rejected, not spoken</Label>
          <div style={line}>
            <Mark text={LOG.rejected} mark={V.flagged} color={C.crimson} />
          </div>
          <div style={gloss}>
            <Mark text={V.rejectedGloss} mark={V.rejectedGlossMark} color={C.crimson} />
          </div>
        </div>

        <div style={{marginTop: 44, fontSize: 40, fontWeight: 600, color: C.gold, ...rise(frame, b, DUR.standard)}}>{V.reason}</div>

        <div style={{marginTop: 64, ...rise(frame, c, DUR.standard)}}>
          <Label color={C.gold}>Retry, accepted</Label>
          <div style={line}>
            <Mark text={LOG.accepted} mark={V.acceptedMark} color={C.gold} />
          </div>
          <div style={gloss}>
            <Mark text={V.acceptedGloss} mark={V.acceptedGlossMark} color={C.gold} />
          </div>
        </div>
      </div>
    </Stage>
  );
};

export const VERIFIER_LOG = LOG;
