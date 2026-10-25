// The stadium: a recorded crowd bed (ui/public/audio, from a freesound community recording, compressed and looped seamlessly
// with ffmpeg) played through Web Audio, always on once the page has had a click. It is heard from the commentary box: far
// off and dull (a low-pass takes the words out of the chants, a dip in the voice band keeps them from fighting the caller),
// it leans in when the ball nears a goal, swells on a shot, erupts on a goal (a recorded roar), and dips under a voice.

const PITCH_L = 105;
const BED = "audio/stadium-bed.mp3";
const ROAR = "audio/stadium-roar.mp3";
const LEVEL = 0.12; // the bed, quiet: it is a feeling, not a soundtrack
const DUCKED = 0.05; // while a commentator speaks
const DULL_HZ = 900; // the bed through the booth glass; opens toward OPEN_HZ on a chance
const OPEN_HZ = 2600;
const ROAR_LEVEL = 0.32;

let ctx: AudioContext | null = null;
let master: GainNode | null = null; // mute and the voice duck
let swell: GainNode | null = null; // tension, shots and goals push the bed up
let bright: BiquadFilterNode | null = null; // a low-pass that opens up with the swell
let roarBuf: AudioBuffer | null = null;
let level = 0;
let lastGoal = 0;
let lastShot = 0;

async function load(c: AudioContext, path: string): Promise<AudioBuffer> {
  const res = await fetch(new URL(path, document.baseURI));
  return c.decodeAudioData(await res.arrayBuffer());
}

/** Build the stadium once, from a click (browsers allow audio only after one). Safe to call again. */
export function startCrowd(): void {
  if (ctx) { void ctx.resume(); return; }
  const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AC) return;
  ctx = new AC();
  const c = ctx;
  master = c.createGain(); master.gain.value = 0;
  master.connect(c.destination);
  swell = c.createGain(); swell.gain.value = 1;
  bright = c.createBiquadFilter(); bright.type = "lowpass"; bright.frequency.value = DULL_HZ; bright.Q.value = 0.5;
  const voice = c.createBiquadFilter(); voice.type = "peaking"; voice.frequency.value = 1200; voice.Q.value = 0.7; voice.gain.value = -6;
  bright.connect(voice).connect(swell).connect(master);

  void load(c, BED).then((buf) => {
    const src = c.createBufferSource();
    src.buffer = buf; src.loop = true;
    src.connect(bright!);
    src.start(0, Math.random() * buf.duration); // a different stretch of the afternoon each time
    master!.gain.setTargetAtTime(LEVEL, c.currentTime, 1.5); // fade in
  }).catch(() => undefined);
  void load(c, ROAR).then((buf) => { roarBuf = buf; }).catch(() => undefined);
}

/** Called every frame with what the board shows. `shotAt`/`goalAt`: performance.now() of the latest, 0 for none. */
export function updateCrowd(o: { muted: boolean; speaking: boolean; playing: boolean; ballX: number | null; shotAt: number; goalAt: number }): void {
  if (!ctx || !master || !swell || !bright) return;
  const c = ctx;
  const t = c.currentTime;
  const now = performance.now();
  const sinceGoal = o.goalAt ? now - o.goalAt : Infinity;
  const ducked = o.speaking && sinceGoal > 2500; // the first seconds of a goal belong to the crowd and the caller together
  master.gain.setTargetAtTime(o.muted ? 0 : ducked ? DUCKED : LEVEL, t, 0.4);

  const d = o.ballX === null ? PITCH_L / 2 : Math.min(o.ballX, PITCH_L - o.ballX); // metres to the nearer goal line
  let want = o.playing ? Math.max(0, Math.min(1, (30 - d) / 20)) * 0.5 : 0;
  if (now - o.shotAt < 2200) want = 1;
  level += (want - level) * 0.03;
  const goal = sinceGoal < 6000 ? 1 : 0;
  swell.gain.setTargetAtTime(1 + level * 0.6 + goal * 0.6, t, 0.3);
  bright.frequency.setTargetAtTime(DULL_HZ + (OPEN_HZ - DULL_HZ) * Math.max(level, goal), t, 0.3);

  if (o.shotAt && o.shotAt !== lastShot) lastShot = o.shotAt;
  if (o.goalAt && o.goalAt !== lastGoal && roarBuf) {
    lastGoal = o.goalAt;
    const src = c.createBufferSource(); src.buffer = roarBuf;
    const g = c.createGain(); g.gain.value = o.muted ? 0 : ROAR_LEVEL;
    src.connect(g).connect(c.destination);
    src.start();
  }
}
