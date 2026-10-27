import type {AudioCue} from './audio';
import type {Cue} from './components/Subtitles';
import type {Crop} from './components/FounderClip';
import type {Side, PaneCrop} from './components/SplitScreen';
import type {PlateSpec} from './components/Plate';
import type {AgentCardProps} from './components/AgentCard';

type Base = {
  /** short id for logs and NOTES.md */
  id: string;
  /** subtitle cues, seconds relative to the segment start */
  subs?: Cue[];
  /** extra audio, atS relative to the segment start */
  audio?: AudioCue[];
  /** commentator name plates, seconds relative to the segment start */
  plates?: PlateSpec[];
  /** small caption in the page's top strip (e.g. the recorded-run note), whole segment */
  note?: string;
};

/** Founder on camera. Length = outS - inS. Its own sound is added as a 'voice' cue automatically. */
export type FounderSeg = Base & {
  type: 'founder';
  src: string;
  inS: number;
  outS: number;
  crop?: Crop;
  lowerThird?: {text: string; fromS: number; durS: number};
  context?: string;
  volume?: number;
  /** length of the founder's sound when it runs on as voice-over over the next segments (default outS - inS) */
  voiceDurS?: number;
};

/** A captured page shot (video/shots, served as public/shots). Silent: its sound is rebuilt in `audio`. */
export type ShotSeg = Base & {
  type: 'shot';
  src: string;
  inS: number;
  outS: number;
  /** show only this source window, scaled to `width` px and centred at `centerY`, as a framed panel on the stage */
  panel?: PaneCrop & {width: number; centerY: number};
};

export type TextSeg = Base & {type: 'text'; lines: string[]; durS: number};
export type VerifierSeg = Base & {type: 'verifier'; durS: number; atS?: [number, number, number]};
export type SplitSeg = Base & {
  type: 'split';
  durS: number;
  left: Side;
  right: Side;
};
export type AgentSeg = Base & {type: 'agents'; durS: number} & AgentCardProps;
export type EndSeg = Base & {type: 'end'; durS: number};

export type Segment = FounderSeg | ShotSeg | TextSeg | VerifierSeg | SplitSeg | AgentSeg | EndSeg;

export type Timeline = {
  segments: Segment[];
  /** cues on the whole film, absolute seconds (crowd bed, roars that run across cuts) */
  global: AudioCue[];
  /** master gain on every audio cue inside the AudioLayer (dB), so the audio is AAC-encoded once; measured, not guessed */
  masterGainDb: number;
};
