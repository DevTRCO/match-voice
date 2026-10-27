import React from 'react';
import {AbsoluteFill} from 'remotion';
import {C, FONT, STAGE_BG} from '../tokens';
import {loadFonts} from '../fonts';

loadFonts();

/** Full-frame royal purple stage every card sits on. No grain, no radial light (H.264 bands those). */
export const Stage: React.FC<{children?: React.ReactNode; flat?: boolean}> = ({children, flat}) => (
  <AbsoluteFill style={{background: flat ? C.bg : STAGE_BG, color: C.text, fontFamily: FONT.ui}}>{children}</AbsoluteFill>
);
