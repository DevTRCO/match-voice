// The mutable match store. Messages are folded into plain fields; the canvas and the DOM read them every animation
// frame. React only hears about rare changes (match loaded, play state) through the `version` counters.
import { describeRow, writeEvent } from "./gamelog";
import { EV, O, T } from "./protocol";
import type { EventRow, Frame, Hello, Log, Msg, Say, Voice } from "./protocol";

// feed: a message added rows to a log or a lane (the modals and the frame loop re-read), sel: another row or caption was picked
export type Topic = "meta" | "transport" | "feed" | "sel";
export interface RecentEvent { t: number; at: number; row: EventRow } // at: performance.now() when the event reached the board
/** One line of the game log: an event written out, or an insight from the facts agent. `ref` is what clicking it selects. */
export interface GameRow { key: string; ref: string; kind: "event" | "insight"; t: number; clock: string; side: 0 | 1 | null; text: string; strong: boolean; log: Log | null }
/** An event as the frame carried it, kept for the evidence box. `before` and `after` are the score around its frame. */
export interface EventRec { row: EventRow; t: number; clock: string; before: [number, number]; after: [number, number] }
export interface Flash { kind: "goal" | "red"; x: number; y: number; ex: number; ey: number; at: number; clock: string }

const RING = 48;
const SAID_KEPT = 200; // captions remembered for the voice messages that refer to them
const KEPT_MAX = 4000; // a guided run is 60 seconds; this only bounds a run that never ends

const logKey = (l: Log): string => `${l.agent}|${l.step}|${l.m}|${l.ch ?? ""}|${l.d?.attempt ?? ""}|${l.d?.key ?? ""}`;

export class Sim {
  hello: Hello | null = null;
  t = 0; // newest match second seen
  ended = false;
  clock = "";
  period = 1;
  score: [number, number] = [0, 0];
  framed = false; // a frame has arrived, so score and clock are real
  lastSay = new Map<number, Say>(); // per channel, the newest line (a cut replaces it)
  said = new Map<string, Say>(); // "ch:m" -> caption: a `voice` message names its line this way
  logs: Log[] = [];
  game: GameRow[] = []; // the game log: events written from the frames, plus the facts agent's insights
  events = new Map<number, EventRec>(); // event id -> the event, from the frames that were watched (not the catch-up)
  eventsAt = new Map<number, number[]>(); // frame time -> event ids
  says: Say[] = []; // every caption of every channel, in arrival order (the agent log and the voice lane pick their channel)
  voices: Voice[] = [];
  skipped = new Set<string>(); // "ch:m" of captioned lines the voice did not speak (skipped, stale or muted); the player fills it
  shown: Say | null = null; // the caption on screen, set by the stage each frame; what the evidence follows
  calls: number | null = null; // model calls of the run, from `end`
  sel: string | null = null; // a log row or the caption the viewer picked; null follows the caption
  recent: RecentEvent[] = [];
  flash: Flash | null = null;
  version: Record<Topic, number> = { meta: 0, transport: 0, feed: 0, sel: 0 };
  private listeners: Record<Topic, Set<() => void>> = { meta: new Set(), transport: new Set(), feed: new Set(), sel: new Set() };
  onSay: ((say: Say, cut: boolean) => void) | null = null;
  onVoice: ((voice: Voice, caption: Say) => void) | null = null;
  private seenLogs = new Set<string>();

  subscribe(topic: Topic, fn: () => void): () => void {
    this.listeners[topic].add(fn);
    return () => { this.listeners[topic].delete(fn); };
  }
  notify(topic: Topic): void {
    this.version[topic]++;
    this.listeners[topic].forEach((fn) => fn());
  }

  /** Start from nothing: a new run, or the same insert again. */
  reset(hello: Hello): void {
    this.hello = hello;
    this.t = hello.start ?? 0;
    this.ended = false; this.framed = false;
    this.clock = ""; this.period = 1; this.score = [0, 0];
    this.lastSay.clear(); this.said.clear(); this.logs = []; this.seenLogs.clear(); this.recent = []; this.flash = null;
    this.game = []; this.events.clear(); this.eventsAt.clear(); this.says = []; this.voices = []; this.skipped.clear(); this.sel = null; this.shown = null; this.calls = null;
    this.notify("meta");
    this.notify("feed");
  }

  /** Fold one message in, as it arrives. */
  ingest(m: Msg): void {
    if (m.t > this.t) this.t = m.t;
    if (m.k === "f") this.frame(m);
    else if (m.k === "say") {
      if (this.says.length < KEPT_MAX) this.says.push(m);
      this.notify("feed");
      const prev = this.lastSay.get(m.ch);
      this.lastSay.set(m.ch, m);
      if (!m.cut) {
        this.said.set(`${m.ch}:${m.m}`, m);
        if (this.said.size > SAID_KEPT) this.said.delete(this.said.keys().next().value!);
      }
      this.onSay?.(m, m.cut === 1 && prev?.m === m.m);
    } else if (m.k === "voice") { if (this.voices.length < KEPT_MAX) this.voices.push(m); this.voice(m); this.notify("feed"); }
    else if (m.k === "log") {
      const key = logKey(m);
      if (this.seenLogs.has(key)) return;
      this.seenLogs.add(key);
      this.logs.push(m);
      if (m.agent === "facts" && m.step === "insight") this.insight(m);
      this.notify("feed");
    } else if (m.k === "end") { this.ended = true; this.calls = m.calls; }
  }

  /** The voice took a captioned line (it becomes the caption again, in step with what is heard), was cut, or skipped it. */
  private voice(v: Voice): void {
    const cap = this.said.get(`${v.ch}:${v.m}`);
    if (!cap) return;
    const last = this.lastSay.get(v.ch);
    if (v.cut) { if (last?.m === v.m) this.lastSay.set(v.ch, { ...last, e: v.e, cut: 1 }); }
    else if (!v.skip) this.lastSay.set(v.ch, { ...cap, s: v.s, e: v.e });
    this.onVoice?.(v, cap);
  }

  /** Pick a log row or the caption for the evidence box; null goes back to following the caption. */
  select(ref: string | null): void {
    if (this.sel === ref) return;
    this.sel = ref;
    this.notify("sel");
  }

  private insight(l: Log): void {
    const ev = Array.isArray(l.d?.ev) ? (l.d.ev as number[]) : [];
    const clock = (ev.length ? this.events.get(ev[0])?.clock : undefined) ?? this.clock;
    const n = this.game.filter((g) => g.kind === "insight").length;
    this.game.push({ key: `i:${n}`, ref: `i:${n}`, kind: "insight", t: l.at, clock, side: l.d?.side === "A" ? 1 : l.d?.side === "H" ? 0 : null, text: l.msg, strong: false, log: l });
  }

  private frame(f: Frame): void {
    const before = this.score;
    this.clock = f.c; this.period = f.p; this.score = f.s; this.framed = true;
    if (f.t < (this.hello?.start ?? 0)) return; // catch-up: the state of the match so far, not something the viewer is watching happen
    const at = performance.now();
    for (const row of f.e) {
      this.record(f, row, before);
      this.recent.push({ t: f.t, at, row });
      if (this.recent.length > RING) this.recent.shift();
      const type = row[EV.type];
      if ((type === T.shot && row[EV.outcome] === O.goal) || (type === T.card && row[EV.outcome] === O.red)) {
        const shot = type === T.shot;
        this.flash = { kind: shot ? "goal" : "red", x: row[EV.x], y: row[EV.y], ex: shot ? row[EV.ex] : row[EV.x], ey: shot ? row[EV.ey] : row[EV.y], at, clock: f.c };
      }
    }
  }

  /** Write one event into the game log. A goal reads the score of its frame; the evidence box reads the stored event. */
  private record(f: Frame, row: EventRow, before: [number, number]): void {
    const rec: EventRec = { row, t: f.t, clock: f.c, before, after: f.s };
    this.events.set(row[EV.i], rec);
    const at = this.eventsAt.get(f.t);
    if (at) at.push(row[EV.i]); else this.eventsAt.set(f.t, [row[EV.i]]);
    const w = this.hello ? writeEvent(this.hello, row, f.s) : null;
    if (!w) return;
    const key = `e:${row[EV.i]}`;
    this.game.push({ key, ref: key, kind: "event", t: f.t, clock: f.c, side: w.side, text: w.text, strong: w.strong, log: null });
    this.notify("feed");
  }

  /** The facts of an event for the evidence box. */
  eventFacts(id: number): string | null {
    const rec = this.events.get(id);
    return rec && this.hello ? describeRow(this.hello, rec.row, rec.clock) : null;
  }
}
