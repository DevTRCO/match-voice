import React from 'react';
import {AbsoluteFill, Composition} from 'remotion';
import {Main, resolve} from './Main';
import {timeline} from './timeline';
import {FPS, H, W} from './tokens';
import {FounderClip} from './components/FounderClip';
import {TextCard} from './components/TextCard';
import {VerifierCatch} from './components/VerifierCatch';
import {SplitScreen} from './components/SplitScreen';
import {Subtitles} from './components/Subtitles';
import {EndCard} from './components/EndCard';
import {LOWER_THIRD} from './timeline';

const T = 300; // 10 s test compositions

const SubsTest: React.FC = () => (
  <AbsoluteFill>
    <FounderClip src="founder/B_blur.mp4" volume={0} />
    <Subtitles
      cues={[
        {startS: 0.2, endS: 4.8, text: "Wexmoor are a goal down, and it's the 68th minute, and the game has gone quiet."},
        {startS: 5.0, endS: 9.8, text: '言った通りです！イブセンが奪って、今度はすぐ反対側のラスムッセンへ！', translation: 'Just as I said! Ibsen wins it, and this time straight across to Rasmussen!', lang: 'ja'},
      ]}
    />
  </AbsoluteFill>
);

export const Root: React.FC = () => {
  const total = resolve(timeline).totalF;
  return (
    <>
      <Composition id="Main" component={Main} durationInFrames={total} fps={FPS} width={W} height={H} defaultProps={{timeline}} />
      <Composition
        id="Test-Founder"
        component={FounderClip}
        durationInFrames={T}
        fps={FPS}
        width={W}
        height={H}
        defaultProps={{src: 'founder/A_blur.mp4', inS: 0, lowerThird: {text: LOWER_THIRD, fromS: 0.4, durS: 3.2}}}
      />
      <Composition
        id="Test-TextCard"
        component={TextCard}
        durationInFrames={T}
        fps={FPS}
        width={W}
        height={H}
        defaultProps={{lines: ['Yuki Tanaka is an AI commentator.', "In the 68th minute she spotted a habit in Wexmoor's game."]}}
      />
      <Composition id="Test-Verifier" component={VerifierCatch} durationInFrames={T} fps={FPS} width={W} height={H} defaultProps={{atS: [0.2, 3.4, 6.2] as [number, number, number]}} />
      <Composition
        id="Test-Split"
        component={SplitScreen}
        durationInFrames={T}
        fps={FPS}
        width={W}
        height={H}
        defaultProps={{left: {src: 'founder/A_blur.mp4', label: 'Expert'}, right: {src: 'founder/C_blur.mp4', label: 'Beginner'}}}
      />
      <Composition id="Test-Subtitles" component={SubsTest} durationInFrames={T} fps={FPS} width={W} height={H} />
      <Composition id="Test-End" component={EndCard} durationInFrames={T} fps={FPS} width={W} height={H} />
    </>
  );
};
