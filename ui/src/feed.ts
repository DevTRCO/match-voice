// Where messages come from. Step 1 is always the recording of the demo insert (one file, no server needed). Step 2 is a
// live run of a fresh random match from the server (docs/PROTOCOL.md). Both go through the same handlers, so the rest of
// the page cannot tell the two apart.
import type { ErrorMsg, Guided, Health, Hello, Insert, Msg } from "./protocol";

export type Backend =
  | { kind: "server"; health: Health }
  | { kind: "static" };

/** Why a live run did not start or stopped: the server's code (`no_runs_today`, `bad_request`, `no_key` ...) and a sentence. */
export interface Failure { code: string; message: string }

const here = (path: string): string => new URL(path, document.baseURI).toString();

async function getJson<T>(url: string, ms = 4000): Promise<T> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    const res = await fetch(url, { signal: ctl.signal });
    if (!res.ok) throw new Error(`${res.status} ${url}`);
    return (await res.json()) as T; // a static host answering with index.html fails here, which is the signal
  } finally {
    clearTimeout(timer);
  }
}

export const fetchHealth = (ms = 1500): Promise<Health> => getJson<Health>(here("api/health"), ms);

export async function detectBackend(forceStatic: boolean): Promise<Backend> {
  if (forceStatic) return { kind: "static" };
  try {
    const health = await fetchHealth();
    if (health.ok) return { kind: "server", health };
  } catch { /* no server, play the recording */ }
  return { kind: "static" };
}

/** The baked ElevenLabs mp3 of one line of the recorded insert (ui/public/insert/audio, made by backend/scripts/bake_insert_audio.py). */
export const insertAudioUrl = (ch: number, m: number): string => here(`insert/audio/${ch}-${m}.mp3`);

export const fetchInsert = (): Promise<Insert> => getJson<Insert>(here("insert/replay.json"), 15000);

/** A fresh random match and its 60 second window. Asking does not count as a live run. Throws a Failure when the server refuses. */
export async function fetchGuided(): Promise<Guided> {
  let res: Response;
  try { res = await fetch(here("api/guided-live")); } catch { throw { code: "offline", message: "The server did not answer." } satisfies Failure; }
  if (!res.ok) {
    let detail: { code?: string; message?: string } | undefined;
    try { detail = ((await res.json()) as { detail?: { code?: string; message?: string } }).detail; } catch { /* not json */ }
    throw { code: detail?.code ?? `http_${res.status}`, message: detail?.message ?? "Live is not available on this server." } satisfies Failure;
  }
  return (await res.json()) as Guided;
}

export interface StreamHandlers {
  onMessage: (m: Msg | Hello) => void;
  onClose: (failure: Failure | null) => void;
}

// WebSocket close codes the server uses: 4000 bad_request, 4001 no_runs_today (an `error` message comes first with the sentence).
const CLOSE_CODES: Record<number, string> = { 4000: "bad_request", 4001: "no_runs_today" };

/** A live WebSocket run at 1x of the window `g`. Returns a close function. */
export function openStream(g: Pick<Guided, "match" | "start" | "until">, h: StreamHandlers): () => void {
  const url = new URL("ws", document.baseURI);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("match", g.match);
  url.searchParams.set("mode", "live");
  url.searchParams.set("speed", "1");
  url.searchParams.set("start", String(g.start));
  url.searchParams.set("until", String(g.until));
  const ws = new WebSocket(url);
  let failed: Failure | null = null;
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data as string) as Msg | Hello | ErrorMsg;
    if (msg.k === "error") failed = { code: msg.code, message: msg.message };
    else h.onMessage(msg);
  };
  ws.onerror = () => { failed ??= { code: "offline", message: "The connection to the server failed." }; };
  ws.onclose = (ev) => {
    if (!failed && CLOSE_CODES[ev.code]) failed = { code: CLOSE_CODES[ev.code], message: "The server refused this live run." };
    h.onClose(failed);
  };
  return () => { ws.onmessage = null; ws.onclose = null; ws.close(); };
}

/** The recording at the pace it was streamed: a message is due at its wall time `w`, catch-up frames at once. */
export function openRecording(rec: Insert, h: StreamHandlers): () => void {
  let timer = 0;
  let i = 0;
  let due = 0;
  const t0 = performance.now();
  h.onMessage(rec.hello);
  const step = (): void => {
    while (i < rec.messages.length) {
      const m = rec.messages[i];
      due = Math.max(due, "w" in m && m.w !== undefined ? m.w : 0);
      const wait = t0 + due * 1000 - performance.now();
      if (wait > 4) { timer = window.setTimeout(step, wait); return; }
      i++;
      h.onMessage(m);
    }
    h.onClose(null);
  };
  step();
  return () => clearTimeout(timer);
}
