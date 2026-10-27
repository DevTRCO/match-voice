import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C, FONT, TYPE} from '../tokens';
import {DUR, enter, rise, s2f} from '../motion';
import {Stage} from './Stage';

/**
 * The five agents, as README "How it works" and docs/VIDEO.md Claims name them. Only Analyst, Verifier and Publisher run as
 * the Microsoft Agent Framework workflow (newsroom.py WorkflowBuilder); the bracket says exactly that.
 * Boxes: radius 6, 1 px line, no accent bars. The active agent's name turns gold and its border brightens.
 */
export const AGENTS = [
  {name: 'Spotter', role: 'finds the pattern in the match data'},
  {name: 'Analyst', role: 'writes the line'},
  {name: 'Verifier', role: 'checks every name and number'},
  {name: 'Publisher', role: 'releases the line, or drops it'},
  {name: 'Directors', role: 'one per channel, decide what to say'},
] as const;

export type AgentCardProps = {
  /** seconds: boxes start rising (staggered 4 f), bracket rises, then the highlight times per agent index */
  boxesAtS?: number;
  bracketAtS?: number;
  highlights?: Array<[number, number]>; // [agent index, atS]
};

const BOX_W = 296;
const GAP = 22;
const LEFT = (1920 - (5 * BOX_W + 4 * GAP)) / 2;

export const AgentCard: React.FC<AgentCardProps> = ({boxesAtS = 0.1, bracketAtS = 1.3, highlights = []}) => {
  const f = useCurrentFrame();
  const active = (i: number) => {
    // an agent stays lit until the next highlight starts
    let on = 0;
    highlights.forEach(([k, t], j) => {
      const next = highlights[j + 1]?.[1] ?? Infinity;
      if (k === i && f >= s2f(t) && f < s2f(next)) on = enter(f, s2f(t), DUR.small);
    });
    return on;
  };
  const br = rise(f, s2f(bracketAtS), DUR.standard, 12);
  const top = 330;
  const boxH = 252;
  return (
    <Stage>
      <div
        style={{
          position: 'absolute',
          left: LEFT,
          top: top - 96,
          fontFamily: FONT.bc,
          fontWeight: 700,
          fontSize: TYPE.label + 6,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          color: C.dim,
          ...rise(f, s2f(boxesAtS), DUR.standard, 0),
        }}
      >
        Five agents, one line of commentary
      </div>
      {AGENTS.map((a, i) => {
        const r = rise(f, s2f(boxesAtS) + i * 4, DUR.standard, 20);
        const on = active(i);
        return (
          <div
            key={a.name}
            style={{
              position: 'absolute',
              left: LEFT + i * (BOX_W + GAP),
              top,
              width: BOX_W,
              height: boxH,
              boxSizing: 'border-box',
              padding: '26px 24px',
              borderRadius: 6,
              background: C.panel,
              boxShadow: `0 0 0 ${1 + on}px rgba(227, 179, 80, ${0.12 + 0.68 * on}), 0 24px 60px -24px #000`,
              ...r,
            }}
          >
            <div style={{fontFamily: FONT.bc, fontWeight: 700, fontSize: 30, color: C.dim, letterSpacing: '0.04em'}}>{i + 1}</div>
            <div
              style={{
                fontFamily: FONT.bc,
                fontWeight: 700,
                fontSize: 54,
                lineHeight: 1,
                marginTop: 8,
                color: on > 0.5 ? C.gold : C.text,
              }}
            >
              {a.name}
            </div>
            <div style={{fontSize: 28, fontWeight: 500, lineHeight: 1.28, color: C.mute, marginTop: 16}}>{a.role}</div>
          </div>
        );
      })}
      {/* bracket under Analyst, Verifier, Publisher */}
      <div
        style={{
          position: 'absolute',
          left: LEFT + (BOX_W + GAP),
          width: 3 * BOX_W + 2 * GAP,
          top: top + boxH + 28,
          ...br,
        }}
      >
        <div style={{height: 14, borderLeft: `2px solid ${C.gold}`, borderRight: `2px solid ${C.gold}`, borderBottom: `2px solid ${C.gold}`, borderRadius: '0 0 4px 4px'}} />
        <div style={{textAlign: 'center', marginTop: 18, fontFamily: FONT.bc, fontWeight: 700, fontSize: 40, letterSpacing: '0.02em', color: C.gold}}>
          One Microsoft Agent Framework workflow
        </div>
        <div style={{textAlign: 'center', marginTop: 8, fontSize: 28, color: C.mute}}>with one retry edge from the Verifier back to the Analyst</div>
      </div>
    </Stage>
  );
};
