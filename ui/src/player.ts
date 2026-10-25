// Playback controller for the guided run. Step 1 is the recorded demo insert (a 21 second moment of a football match, always
// available, with or without a server). Step 2 is a live run: a fresh random match from /api/guided-live, 60 seconds at 1x,
// commentary made while it runs. Both go through the same handlers. Live uses the browser voice only.
import { detectBackend, fetchGuided, fetchHealth, fetchInsert, insertAudioUrl, openRecording, openStream } from "./feed";
import type { Backend, Failure } from "./feed";
import type { DemoInsert, Guided, Hello, Insert, Msg, Say, Voice } from "./protocol";
import { Sim } from "./sim";
import { configureTts, isSpeaking, primeAudio, speak, stopSpeaking } from "./speech";

export type Lang = "en" | "de" | "fr";
export type Style = "beginner" | "expert";
export type Step = 1 | 2;
export type Phase = "loading" | "ready" | "playing" | "over" | "error";

// Spoken lines older than this (wall seconds from the event to the line) are shown but not spoken.
const PBP_MAX_AGE_S = 3;
const ANALYST_MAX_AGE_S = 20;
// The voice may start a captioned line at most this long after its caption (wall seconds). The server holds the same
// limits in viewer seconds; the extra half second absorbs frame and network jitter.
const VOICE_MAX_BEHIND_S = { pbp: 3.5, analyst: 6.5 };
// The picture is this far behind the server schedule (wall seconds): a throttled tab or a slow link. Do not talk over it.
const MAX_LAG_S = 1.5;
// These cut in on a line that is still talking (priority 90 and up on the server); every other line waits its turn.
export const URGENT_KINDS = new Set(["shot_goal", "red", "full_time"]);

/** The one sentence for a refused or unavailable live, whichever way it was found (the first look at boot or a refused run): same code, same words. */
const noteOf = (f: Failure): string => (f.code === "no_runs_today" ? "Today's live runs are used up. They come back at midnight UTC." : f.message);

export class Player {
  sim = new Sim();
  backend: Backend = { kind: "static" };
  step: Step = 1; // the step on the pitch now: 1 recorded, 2 live
  phase: Phase = "loading";
  busy = "Loading"; // what the loading note says
  error: string | null = null;
  lang: Lang = "en";
  style: Style = "expert";
  muted = false;
  demo: DemoInsert | null = null; // the recorded insert's facts: start screen, true length
  guided: Guided | null = null; // the live window asked for last (its length labels step 2)
  liveNote: string | null = null; // why live did not start, in the server's words; replaces the Go live button
  checking = false; // the server is being asked whether live can start: the Go live button waits for the answer
  private recording: Insert | null = null;
  private skipped = this.sim.skipped; // "ch:m" of captioned lines the voice did not speak
  private voiceKey = ""; // "ch:m" of the line the voice is reading
  private closeStream: (() => void) | null = null;
  private token = 0;
  private wall0 = 0; // performance.now() when the stream said hello
  private wallEnd = 0; // wall seconds of the run when it ended

  constructor() {
    this.sim.onSay = (say, wasCut) => this.onSay(say, wasCut);
    this.sim.onVoice = (voice, caption) => this.onVoice(voice, caption);
  }

  private set(phase: Phase): void { this.phase = phase; this.sim.notify("transport"); }

  /** Load the recording (always), look at the server, and show the pitch ready for step 1. */
  async boot(forceStatic: boolean): Promise<void> {
    try {
      this.backend = await detectBackend(forceStatic);
      configureTts(false); // both steps use the browser voice
      await this.useRecording();
      this.set("ready");
      void this.checkLive(); // the window length for the step rail; asking does not count as a run
    } catch (err) { this.fail(err, "The recorded moment could not be loaded."); }
  }

  private async useRecording(): Promise<void> {
    this.recording ??= await fetchInsert();
    this.demo = this.recording.demo;
    this.sim.reset(this.recording.hello);
  }

  /** Ask the server again whether live can start: health first, then (when it says yes) the next window. Runs at boot and when the recorded run
   * ends, always the same way, so the note and the Go live button at the end say what the start would say now. `askWindow` is off after a live run:
   * the board still shows that match and its numbers, only the runs left are read again. */
  private async checkLive(askWindow = true): Promise<void> {
    this.checking = true;
    this.sim.notify("transport");
    try {
      if (this.backend.kind === "server") {
        try { const health = await fetchHealth(); if (health.ok) this.backend = { kind: "server", health }; } catch { /* keep what we know */ }
      }
      if (askWindow) {
        this.liveNote = null;
        if (this.liveBlock === null) await this.askGuided();
      }
    } finally {
      this.checking = false;
      this.sim.notify("transport");
    }
  }

  private async askGuided(): Promise<void> {
    try { this.guided = await fetchGuided(); } catch (f) { this.liveNote = noteOf(f as Failure); }
    this.sim.notify("transport");
  }

  private fail(err: unknown, what = "Something went wrong."): void {
    this.error = `${what} ${err instanceof Error ? err.message : String(err)}`;
    this.set("error");
  }

  /** Channel id of the current language and style, from the hello table. */
  get ch(): number {
    return this.sim.hello?.channels.find((x) => x.lang === this.lang && x.style === this.style)?.id ?? 0;
  }

  /** Seconds of the recorded moment, from the data. */
  get recordedLen(): number | null { return this.demo ? Math.round(this.demo.length ?? this.demo.until - this.demo.start) : null; }
  /** Seconds of the live window, from the server's last answer. */
  get liveLen(): number | null { return this.guided ? Math.round(this.guided.window_s) : null; }

  /** One honest line when a live run cannot start, else null. Recorded keeps working either way. */
  get liveBlock(): string | null {
    if (this.liveNote) return this.liveNote;
    if (this.backend.kind !== "server") return "Live needs the server. This build plays the recording only.";
    const live = this.backend.health.live;
    if (live.available) return null;
    switch (live.code) {
      case "no_runs_today": return "Today's live runs are used up. They come back at midnight UTC.";
      case "no_budget": return "Live is paused: this server has used up its model budget.";
      case "no_key": return "Live is off on this server: no model key is set.";
      default: return live.reason ?? "Live is not available on this server.";
    }
  }

  /** Wall seconds since the run started: the playhead of the lanes. Frozen when the run is over, 0 before it starts. */
  elapsed(): number {
    if (this.phase === "playing") return (performance.now() - this.wall0) / 1000;
    return this.phase === "over" ? this.wallEnd : 0;
  }

  /** Space bar and the main button before step 1. */
  play(): void { if (this.phase === "ready" || this.phase === "over") void this.playRecorded(); }

  /** Step 1: the recorded moment. */
  async playRecorded(): Promise<void> {
    if (!this.recording || this.phase === "loading" || this.phase === "playing") return;
    primeAudio(); // runs from a click, which is what lets the page play audio later
    const token = this.begin();
    try {
      await this.useRecording();
      if (token !== this.token) return;
      this.step = 1;
      this.wall0 = performance.now();
      this.set("playing");
      this.closeStream = openRecording(this.recording!, this.handlers(token, 1));
    } catch (err) { this.fail(err); }
  }

  /** Step 2: a fresh live match. The board keeps showing the finished recording until the server's hello arrives. */
  async goLive(): Promise<void> {
    if (this.phase === "loading" || this.phase === "playing" || this.liveBlock !== null) return;
    primeAudio();
    const token = this.begin();
    this.busy = "Finding a live match";
    this.set("loading");
    try {
      const g = await fetchGuided();
      if (token !== this.token) return;
      this.guided = g;
      this.closeStream = openStream(g, this.handlers(token, 2));
    } catch (f) { this.liveFailed(f as Failure, token); }
  }

  private begin(): number {
    const token = ++this.token;
    this.closeStream?.(); stopSpeaking();
    this.voiceKey = ""; // the skip set belongs to the run on the board: sim.reset clears it when the new run's hello arrives
    this.error = null;
    return token;
  }

  /** The server refused or is gone before the run began: say why, keep the recording available. */
  private liveFailed(f: Failure, token: number): void {
    if (token !== this.token) return;
    this.liveNote = noteOf(f);
    this.error = null;
    this.step = 1;
    this.set("over");
  }

  private handlers(token: number, step: Step) {
    let got = false;
    return {
      onMessage: (m: Msg | Hello): void => {
        if (token !== this.token) return;
        if (m.k === "hello") {
          got = true;
          this.wall0 = performance.now();
          this.step = step;
          if (step === 2) this.liveNote = null; // only a live run that really started clears the note, the recorded hello must not
          this.sim.reset(m);
          this.set("playing");
        } else this.sim.ingest(m);
      },
      onClose: (f: Failure | null): void => {
        if (token !== this.token) return;
        if (!got) { this.liveFailed(f ?? { code: "offline", message: "The live run did not start." }, token); return; }
        if (!this.sim.ended && f) { this.error = f.message; this.set("error"); return; }
        this.sim.ended = true;
        this.wallEnd = (performance.now() - this.wall0) / 1000;
        this.checking = true; // no Go live button until the server has answered again
        this.set("over");
        void this.checkLive(this.step === 1);
      },
    };
  }

  setChannel(lang: Lang, style: Style): void {
    this.lang = lang; this.style = style;
    stopSpeaking(); // the next line is spoken in the new language and style
    this.sim.notify("transport");
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    if (muted) stopSpeaking();
    this.sim.notify("transport");
  }

  private onSay(say: Say, wasCut: boolean): void {
    if (this.phase !== "playing" || say.ch !== this.ch) return;
    if (this.muted) { if (say.e > say.s) this.skip(say); return; }
    if (wasCut || say.cut) { if (this.voiceKey === `${say.ch}:${say.m}`) stopSpeaking(); return; } // a goal interrupted this line
    if (say.e <= say.s) return; // a live caption waits for its `voice` message
    if (!this.fresh(say, say.lat, say.w, say.w)) { this.skip(say); return; }
    this.say(say, VOICE_MAX_BEHIND_S[say.voice]);
  }

  private onVoice(v: Voice, cap: Say): void {
    if (this.phase !== "playing" || v.ch !== this.ch) return;
    if (this.muted) { if (!v.cut) this.skip(cap); return; }
    if (v.skip) { this.skip(cap); return; }
    if (v.cut) { if (this.voiceKey === `${v.ch}:${v.m}`) stopSpeaking(); return; }
    if (!this.fresh(cap, v.lat, v.w, cap.w)) { this.skip(cap); return; }
    this.say({ ...cap, s: v.s, e: v.e }, VOICE_MAX_BEHIND_S[cap.voice] - Math.max(0, (v.w ?? 0) - (cap.w ?? v.w ?? 0)));
  }

  /** Never queue stale speech: a late line stays on screen as a caption, the voice stays on the picture and close to its caption. */
  private fresh(line: Say, lat: number | undefined, w: number | undefined, captionW: number | undefined): boolean {
    const behindPicture = w === undefined ? 0 : (performance.now() - this.wall0) / 1000 - w;
    const behindCaption = w === undefined || captionW === undefined ? 0 : w - captionW;
    const tooOld = (lat ?? 0) > (line.voice === "pbp" ? PBP_MAX_AGE_S : ANALYST_MAX_AGE_S);
    return !(tooOld || behindPicture > MAX_LAG_S || behindCaption > VOICE_MAX_BEHIND_S[line.voice]);
  }

  private skip(line: Say): void { this.skipped.add(`${line.ch}:${line.m}`); this.sim.notify("feed"); }

  /** What the voice is doing about a caption: reading it, or leaving it as text. */
  talking(cap: Say | null): boolean {
    return !!cap && this.phase === "playing" && !this.muted && this.voiceKey === `${cap.ch}:${cap.m}` && isSpeaking();
  }

  private say(say: Say, maxWaitS: number): void {
    const wall = Math.max(0.5, say.e - Math.max(say.s, this.sim.t)); // 1x: a match second is a wall second
    const key = `${say.ch}:${say.m}`;
    // A line that has to wait for the one still talking is dropped (caption only) once it would run too far behind its caption.
    speak(say.text, this.lang, wall, {
      urgent: URGENT_KINDS.has(say.kind), maxWaitS: Math.max(0, maxWaitS),
      tts: this.step === 1 ? insertAudioUrl(say.ch, say.m) : undefined, baked: this.step === 1,
      onStart: () => { this.voiceKey = key; }, onDrop: () => { this.skip(say); },
    });
  }

  dispose(): void { this.token++; this.closeStream?.(); stopSpeaking(); }
}
