// Types for overlay protocol v1, see docs/PROTOCOL.md. The hello message carries every code table.

export interface Team { side: "H" | "A"; name: string; short: string; color: string; formation: string }
export interface Player { id: string; side: "H" | "A"; n: number; name: string; pos: string; grp: "GK" | "DEF" | "MID" | "FWD" }
export interface Channel { id: number; key: string; lang: "en" | "de" | "fr"; style: "beginner" | "expert" }

export interface Hello {
  k: "hello"; v: number; t: number; mode: "replay" | "live"; speed: number; dt: number; duration: number; start?: number;
  until?: number; // live insert: the stream ends at this match second
  run?: string; // live run id, the key of /api/tts
  match: { id: string; title: string; competition: string; venue: string; arc: string; pitch: [number, number]; teams: [Team, Team] };
  players: Player[]; scale: number;
  types: string[]; outcomes: string[]; setPieces: string[]; stats: string[]; eventFields: string[];
  channels: Channel[];
}

/** [i, type, side, player, x, y, end_x, end_y, outcome, set_piece, xg*100] */
export type EventRow = number[];
export interface Frame {
  k: "f"; t: number; c: string; p: number; s: [number, number]; wp: [number, number, number]; mo: number;
  e: EventRow[]; st?: [Record<string, number>, Record<string, number>];
}
export interface Say {
  k: "say"; t: number; ch: number; m: number; kind: string; voice: "pbp" | "analyst"; text: string;
  s: number; e: number; cut: 0 | 1; src: "analyst" | "template"; cached?: 1; // cached: the analyst line came from the answer cache, not from a call in this run. Live: s == e while the voice is busy, a `voice` message may follow
  w?: number; // live only: wall seconds since the stream started
  lat?: number; // live only: wall seconds from the event to this line
}
/** Live only: the voice side of a line a `say` already captioned. It starts at s to e, was cut at e, or is never spoken. */
export interface Voice { k: "voice"; t: number; ch: number; m: number; s: number; e: number; cut?: 1; skip?: 1; w?: number; lat?: number }
export interface Log {
  k: "log"; t: number; at: number; agent: string; step: string; m: number | null; msg: string; ch?: number; d?: Record<string, unknown>;
  w?: number; // live only: wall seconds since the stream started
}
export interface End { k: "end"; t: number; score: [number, number]; events: number; says: number; calls: number | null }
export interface ErrorMsg { k: "error"; code: string; message: string }
/** Live only: keeps the match clock moving while nothing else is sent. */
export interface Heartbeat { k: "hb"; t: number; w: number }
export type Msg = Frame | Say | Voice | Log | End | Heartbeat;

/** The recorded demo insert (`python -m matchvoice.pipeline export-insert`): the stream of a live run at 1x, as it was sent. */
export interface Insert { v: number; demo: DemoInsert; hello: Hello; messages: Msg[] }
export interface TtsHealth { available: boolean; reason: string | null }
/** `code`: ok, no_key, no_budget or no_runs_today. The caps are null when that cap is off. */
export interface LiveHealth {
  available: boolean; code?: string; reason: string | null; calls_left?: number | null; fresh?: boolean;
  runs_left?: number | null; runs_per_day?: number | null; max_seconds?: number | null;
}
export interface Health { ok: boolean; live: LiveHealth; tts?: TtsHealth }
/** GET /api/guided-live: a fresh random match and the window of it with the most going on. `goal_t` is null without a goal. */
export interface Guided { match: string; arc: string; seed: number; start: number; until: number; window_s: number; goal_t: number | null; fresh: boolean; runs_left: number | null }
export interface DemoInsert { match: string; arc: string; seed: number; start: number; until: number; goal_t: number; goal_clock: string;
  score?: [number, number]; clock?: string } // score and clock before the first frame

// Event row positions and the codes this UI reasons about. Names come from hello, these are the v1 indexes.
export const EV = { i: 0, type: 1, side: 2, player: 3, x: 4, y: 5, ex: 6, ey: 7, outcome: 8, xg: 10 } as const;
export const T = { pass: 1, carry: 2, shot: 3, tackle: 4, foul: 7, card: 8 } as const;
export const O = { incomplete: 2, goal: 4, red: 14 } as const;
