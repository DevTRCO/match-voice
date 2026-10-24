// Everything the logs, the lanes and the evidence box show is derived here from what the stream really sent: log messages
// with their wall times `w`, captions, voice messages, the frames' event rows. Nothing is estimated and nothing is invented;
// where the data has no time or no source, there is no row, no bar and no evidence line.
// Results are cached per run version (`sim.version.feed`) and channel, so the frame loop calls these for free.
import { EV } from "./protocol";
import type { Log, Say } from "./protocol";
import type { Sim } from "./sim";

export type AgentId = "det" | "ana" | "ver" | "pub" | "dir" | "voc";
export const AGENT_NAMES: Record<AgentId, string> = { det: "Detector", ana: "Analyst", ver: "Verifier", pub: "Publisher", dir: "Director", voc: "Voice" };
const OF_LOG: Record<string, AgentId> = { detector: "det", analyst: "ana", verifier: "ver", publisher: "pub", director: "dir" };

/** A row of the agent log. `w` is wall seconds since the run started, `ref` what a click selects. */
export interface AgentRow { key: string; ref: string | null; w: number; id: AgentId; who: string; text: string; dur: string }
/** A busy interval in wall seconds since the run started. `e` is null while the step is still running. */
export interface Interval { s: number; e: number | null }
export interface LaneData { det: number[]; ana: Interval[]; ver: Interval[]; pub: Interval[]; voc: Interval[]; span: number }
export interface Evidence { label: string; text: string }

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
export const fmtDur = (s: number): string => (s < 1 ? `${Math.max(1, Math.round(s * 1000))} ms` : `${s.toFixed(1)} s`);
export const fmtSince = (w: number): string => `+${w.toFixed(1)}s`;
const wOf = (l: { w?: number; at?: number }, start: number): number => l.w ?? Math.max(0, (l.at ?? start) - start);
const startOf = (sim: Sim): number => sim.hello?.start ?? 0;

interface Slot { m: number; s: number; e: number; state: "spoken" | "cut" | "skipped"; say: Say }
interface Built { rows: AgentRow[]; lanes: LaneData }
const cache = new WeakMap<Sim, { key: string; built: Built }>();

/** The voice lane and its rows. A line is a slot from the moment the voice was told to start it (`say` with s < e, or a
 * `voice` message) for as long as the server gave it (e - s); a cut ends the slot at the cut message's time. Lines the
 * server skipped, the browser dropped as stale and lines said while muted have no slot: they were not spoken. */
function voiceSlots(sim: Sim, ch: number): Slot[] {
  type Item = { w: number; say?: Say; voice?: (typeof sim.voices)[number] };
  const items: Item[] = [];
  for (const say of sim.says) if (say.ch === ch) items.push({ w: say.w ?? 0, say });
  for (const v of sim.voices) if (v.ch === ch) items.push({ w: v.w ?? 0, voice: v });
  items.sort((a, b) => a.w - b.w);
  const slots = new Map<number, Slot>();
  const caption = new Map<number, Say>();
  for (const it of items) {
    if (it.say) {
      const say = it.say;
      if (say.cut) {
        const slot = slots.get(say.m);
        if (slot && slot.state === "spoken") { slot.e = Math.min(slot.e, it.w); slot.state = "cut"; }
        continue;
      }
      caption.set(say.m, say);
      if (say.e > say.s) slots.set(say.m, { m: say.m, s: it.w, e: it.w + (say.e - say.s), state: "spoken", say });
    } else if (it.voice) {
      const v = it.voice;
      const say = caption.get(v.m);
      if (!say) continue;
      if (v.skip) slots.set(v.m, { m: v.m, s: it.w, e: it.w, state: "skipped", say });
      else if (v.cut) { const slot = slots.get(v.m); if (slot && slot.state === "spoken") { slot.e = Math.min(slot.e, it.w); slot.state = "cut"; } }
      else slots.set(v.m, { m: v.m, s: it.w, e: it.w + (v.e - v.s), state: "spoken", say });
    }
  }
  for (const slot of slots.values()) if (sim.skipped.has(`${ch}:${slot.m}`)) slot.state = "skipped";
  return [...slots.values()];
}

function build(sim: Sim, ch: number): Built {
  const start = startOf(sim);
  const rows: AgentRow[] = [];
  const lanes: LaneData = { det: [], ana: [], ver: [], pub: [], voc: [], span: 0 };
  const wrote = new Map<number, number[]>(); // moment -> wall times of analyst_wrote
  const verified = new Map<number, number[]>(); // moment -> wall times of verified
  const open = new Map<number, number>(); // moment -> wall time its model call or lookup started, until analyst_wrote
  const mine = sim.logs.filter((l) => l.agent !== "facts" && (l.ch === undefined || l.ch === ch));
  const push = (map: Map<number, number[]>, m: number | null, w: number): void => { if (m !== null) { const a = map.get(m); if (a) a.push(w); else map.set(m, [w]); } };
  const before = (map: Map<number, number[]>, m: number | null, w: number): number | null => {
    const a = m === null ? undefined : map.get(m);
    return a ? Math.max(-1, ...a.filter((x) => x <= w + 1e-6)) : null;
  };
  for (const l of mine) {
    const w = wOf(l, start);
    if (l.step === "analyst_wrote") push(wrote, l.m, w);
    else if (l.step === "verified") push(verified, l.m, w);
  }
  const ivSeen = new Set<string>();
  const interval = (lane: Interval[], s: number, e: number | null): void => {
    const id = `${lane === lanes.ana ? "a" : lane === lanes.ver ? "v" : "p"}${s.toFixed(3)}${e === null ? "" : e.toFixed(3)}`;
    if (ivSeen.has(id)) return; // one `rejected` per channel is one verifier pass
    ivSeen.add(id);
    lane.push({ s: Math.max(0, s), e });
  };
  for (const l of mine) {
    const w = wOf(l, start);
    let dur = "";
    // Detector: dots, one per `queued` (a moment sent to the analyst).
    if (l.step === "queued") lanes.det.push(w);
    // Analyst: from the call (or cache lookup) start to analyst_wrote. analyst_wrote carries its own duration: latency_s of
    // a model call, or wall_s (what this run waited) for a cache hit. A moment still waiting for its answer is an open bar.
    else if (l.step === "writing" || l.step === "lookup") open.set(l.m ?? -1, w);
    else if (l.step === "analyst_wrote") {
      const d = num(l.d?.cached ? l.d?.wall_s : l.d?.latency_s);
      if (d !== null) { dur = l.d?.cached ? "cache" : fmtDur(d); interval(lanes.ana, w - d, w); }
      open.delete(l.m ?? -1);
    } else if (l.step === "analyst_error" || l.step === "timeout") open.delete(l.m ?? -1);
    // Verifier: from the analyst_wrote it checked to its verified / rejected message (both carry the real step time).
    else if (l.step === "verified" || l.step === "rejected") {
      const s = before(wrote, l.m, w);
      if (s !== null && s >= 0) { dur = fmtDur(Math.max(0, w - s)); interval(lanes.ver, s, w); }
    }
    // Publisher: from the last verified of the moment to its ready message.
    else if (l.step === "ready") {
      const s = before(verified, l.m, w);
      if (s !== null && s >= 0) interval(lanes.pub, s, w);
    }
    rows.push({ key: `l:${rows.length}`, ref: l.m === null ? null : `m:${l.m}`, w, id: OF_LOG[l.agent] ?? "ana", who: AGENT_NAMES[OF_LOG[l.agent] ?? "ana"], text: l.msg, dur });
  }
  for (const [m, w] of open) if (m >= 0) lanes.ana.push({ s: w, e: null });
  // Detector, play-by-play: a template line published at the moment the event reached the server (lat = event to caption).
  for (const say of sim.says) {
    if (say.ch !== ch || say.cut || say.src !== "template") continue;
    const w = say.w ?? 0;
    lanes.det.push(w);
    rows.push({ key: `s:${say.m}`, ref: `m:${say.m}`, w, id: "det", who: "Detector", text: `Template line: ${say.text}`, dur: say.lat === undefined ? "" : fmtDur(say.lat) });
  }
  for (const slot of voiceSlots(sim, ch)) {
    if (slot.state !== "skipped") interval(lanes.voc, slot.s, slot.e);
    rows.push({ key: `v:${slot.m}`, ref: `m:${slot.m}`, w: slot.s, id: "voc", who: "Voice",
      text: `${slot.state === "skipped" ? "Not spoken, caption only" : slot.state === "cut" ? "Cut off by a bigger moment" : "Reads"}: ${slot.say.text}`,
      dur: slot.state === "skipped" ? "" : fmtDur(Math.max(0, slot.e - slot.s)) });
  }
  rows.sort((a, b) => a.w - b.w);
  const window = sim.hello?.until !== undefined ? sim.hello.until - start : 0;
  let end = window;
  for (const a of [lanes.ana, lanes.ver, lanes.pub, lanes.voc]) for (const iv of a) end = Math.max(end, iv.e ?? iv.s);
  for (const d of lanes.det) end = Math.max(end, d);
  lanes.span = Math.max(1, end);
  return { rows, lanes };
}

function built(sim: Sim, ch: number): Built {
  const key = `${sim.hello ? 1 : 0}:${sim.version.feed}:${sim.version.meta}:${ch}:${sim.skipped.size}`;
  const hit = cache.get(sim);
  if (hit && hit.key === key) return hit.built;
  const b = build(sim, ch);
  cache.set(sim, { key, built: b });
  return b;
}

export const agentRows = (sim: Sim, ch: number): AgentRow[] => built(sim, ch).rows;
export const laneData = (sim: Sim, ch: number): LaneData => built(sim, ch).lanes;

// ---- evidence ----

/** Which event row a template wording came from: the events of the frame it was captioned in, narrowed by what the
 * wording is about, and by the surname in the text when a frame holds more than one such event. Null when not certain. */
export function eventOf(sim: Sim, say: Say): number | null {
  const h = sim.hello;
  const ids = sim.eventsAt.get(say.t);
  if (!h || !ids) return null;
  const type = (id: number): string => h.types[sim.events.get(id)!.row[EV.type]];
  const outcome = (id: number): string => h.outcomes[sim.events.get(id)!.row[EV.outcome]];
  const piece = (id: number): string => h.setPieces[sim.events.get(id)!.row[9]];
  const k = say.kind;
  const want = (id: number): boolean => {
    if (k === "shot_goal") return type(id) === "shot" && outcome(id) === "goal";
    if (k === "shot_saved" || k === "shot_post" || k === "shot_blocked") return type(id) === "shot" && outcome(id) === k.slice(5);
    if (k === "shot_off") return type(id) === "shot" && !["goal", "saved", "post", "blocked"].includes(outcome(id));
    if (k === "corner") return type(id) === "pass" && piece(id) === "corner";
    if (k === "long_ball" || k === "pass_final_third") return type(id) === "pass" && outcome(id) === "complete" && !piece(id);
    if (k === "tackle_won") return type(id) === "tackle" && outcome(id) === "won";
    if (k === "foul") return type(id) === "foul";
    if (k === "yellow") return type(id) === "card" && outcome(id) === "yellow";
    if (k === "red") return type(id) === "card" && outcome(id) === "red";
    if (k === "half_time" || k === "full_time") return type(id) === "period_end";
    if (k === "kickoff_start") return type(id) === "kickoff";
    return false;
  };
  const cands = ids.filter(want);
  if (cands.length === 1) return cands[0];
  const text = say.text.toLowerCase();
  const named = cands.filter((id) => {
    const p = h.players[sim.events.get(id)!.row[EV.player]];
    return !!p && text.includes((p.name.split(" ").pop() ?? "").toLowerCase());
  });
  return named.length === 1 ? named[0] : null;
}

const insightsOf = (sim: Sim, ids: number[]): Log[] =>
  sim.game.filter((g) => g.log && ids.some((id) => Array.isArray(g.log!.d?.ev) && (g.log!.d!.ev as number[]).includes(id))).map((g) => g.log!);

/** One agent step in a short clause, from the log's own detail fields; the message itself when there is nothing shorter. */
function brief(l: Log): string {
  const d = l.d ?? {};
  const lat = num(d.latency_s);
  switch (l.step) {
    case "lookup": return "answer cache lookup, no model call";
    case "writing": return "model call started";
    case "analyst_wrote":
      return d.cached ? `reused ${d.lines} cached lines (first call took ${lat === null ? "?" : fmtDur(lat)})`
        : `wrote ${d.lines} lines${lat === null ? "" : ` in ${fmtDur(lat)}`}${(num(d.attempt) ?? 0) > 0 ? ` (attempt ${(num(d.attempt) ?? 0) + 1})` : ""}`;
    case "rejected": return `sent ${d.key} back, ${String(d.why ?? "").replace(/\s+/g, " ")}`;
    case "verified": return `accepted ${d.accepted} lines, ${d.failing} failing`;
    default: return l.msg;
  }
}

/** The "why this line" box for a caption (`m:<moment>`), a game log event (`e:<id>`) or an insight (`i:<n>`). */
export function evidence(sim: Sim, ref: string | null, ch: number): Evidence[] {
  const h = sim.hello;
  if (!h || !ref) return [];
  const out: Evidence[] = [];
  const key = h.channels.find((c) => c.id === ch)?.key ?? "";
  const event = (id: number): void => { const f = sim.eventFacts(id); if (f) out.push({ label: "event", text: f }); };
  const scoreOf = (id: number): void => {
    const r = sim.events.get(id);
    if (r && (r.before[0] !== r.after[0] || r.before[1] !== r.after[1])) out.push({ label: "state", text: `score ${r.before[0]}-${r.before[1]} became ${r.after[0]}-${r.after[1]}` });
  };
  const insight = (l: Log): void => { out.push({ label: "insight", text: l.msg }); };
  const [kind, rest] = [ref.slice(0, 1), ref.slice(2)];

  if (kind === "e") {
    const id = Number(rest);
    event(id); scoreOf(id);
    const rec = sim.events.get(id);
    if (rec) {
      const line = sim.says.find((s) => s.ch === ch && !s.cut && s.src === "template" && s.t === rec.t && eventOf(sim, s) === id);
      if (line) out.push({ label: "wording", text: `template ${line.kind} line${line.lat === undefined ? "" : `, on screen in ${fmtDur(line.lat)}`}` });
      for (const l of sim.logs) if (l.step === "queued" && l.at === rec.t && (l.ch === undefined || l.ch === ch)) out.push({ label: "detector", text: l.msg });
    }
    for (const l of insightsOf(sim, [id])) insight(l);
  } else if (kind === "i") {
    const g = sim.game.find((x) => x.ref === ref);
    const d = g?.log?.d;
    if (!g?.log || !d) return out;
    insight(g.log);
    const ev = Array.isArray(d.ev) ? (d.ev as number[]) : [];
    for (const id of ev) event(id);
    if (d.kind === "wp_swing") { const sc = d.score as number[] | undefined; if (sc) out.push({ label: "state", text: `score ${sc[0]}-${sc[1]} after the event` }); }
    else if (d.kind === "momentum") out.push({ label: "fact", text: `${d.share}% of the attacking threat, ${d.shots} shots, ${d.possession}% possession in ${d.minutes} minutes` });
    else if (d.kind === "shots") out.push({ label: "fact", text: `${d.player}: ${d.shots} shots. ${d.team}: ${d.team_shots} shots, ${d.on_target} on target` });
  } else if (kind === "m") {
    const m = Number(rest);
    const say = sim.said.get(`${ch}:${m}`) ?? [...sim.says].reverse().find((s) => s.ch === ch && s.m === m && !s.cut);
    const logs = sim.logs.filter((l) => l.m === m && l.agent !== "facts" && (l.ch === undefined || l.ch === ch) && !(l.step === "rejected" && l.d?.key !== key));
    let ids: number[] = [];
    if (say?.src === "template") {
      const id = eventOf(sim, say);
      if (id !== null) { ids = [id]; event(id); scoreOf(id); }
      out.push({ label: "wording", text: `template ${say.kind} line, ${key}${say.lat === undefined ? "" : `, on screen in ${fmtDur(say.lat)}`}` });
    } else {
      const q = logs.find((l) => l.step === "queued");
      ids = q ? (sim.eventsAt.get(q.at) ?? []) : [];
      if (ids.length === 1) { event(ids[0]); scoreOf(ids[0]); }
    }
    for (const l of logs) {
      if (l.step === "ready" && say?.src === "template") continue;
      out.push({ label: AGENT_NAMES[OF_LOG[l.agent] ?? "ana"].toLowerCase(), text: brief(l) });
    }
    if (ids.length) for (const l of insightsOf(sim, ids)) insight(l);
  }
  return out;
}

/** The row that is selected: what the viewer picked, else the caption on screen. */
export const selectedRef = (sim: Sim): string | null => sim.sel ?? (sim.shown ? `m:${sim.shown.m}` : null);

/** Every row that belongs to the selected one (the caption's event, its insights, its agent steps), so they light up together. */
export function related(sim: Sim, ref: string | null, ch: number): Set<string> {
  const out = new Set<string>();
  if (!ref || !sim.hello) return out;
  out.add(ref);
  const ids: number[] = [];
  const [kind, rest] = [ref.slice(0, 1), ref.slice(2)];
  if (kind === "e") ids.push(Number(rest));
  else if (kind === "i") { const d = sim.game.find((g) => g.ref === ref)?.log?.d; if (Array.isArray(d?.ev)) ids.push(...(d!.ev as number[])); }
  else if (kind === "m") {
    const m = Number(rest);
    const say = sim.said.get(`${ch}:${m}`);
    if (say?.src === "template") { const id = eventOf(sim, say); if (id !== null) ids.push(id); }
    else { const q = sim.logs.find((l) => l.m === m && l.step === "queued"); const at = q ? (sim.eventsAt.get(q.at) ?? []) : []; if (at.length === 1) ids.push(at[0]); }
  }
  for (const id of ids) { out.add(`e:${id}`); for (const g of sim.game) if (g.log && Array.isArray(g.log.d?.ev) && (g.log.d!.ev as number[]).includes(id)) out.add(g.ref); }
  return out;
}
