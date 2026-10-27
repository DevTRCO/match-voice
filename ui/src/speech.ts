// The voice. Two engines behind one queue: ElevenLabs audio from the server (an HTMLAudioElement, only when the server
// offers it) and the browser's SpeechSynthesis (free, no key, offline-capable, always the fallback).
// Captions are always shown, voice is optional. Both engines follow the same rules: a line waits for the one talking
// unless it is urgent, is dropped when it waits too long, never outlives its slot by more than a moment, and a
// goal or red card cuts the current line off.

const BCP47: Record<string, string> = { en: "en-GB", de: "de-DE", fr: "fr-FR" };

let voices: SpeechSynthesisVoice[] = [];
const synth: SpeechSynthesis | null = typeof window !== "undefined" && "speechSynthesis" in window ? window.speechSynthesis : null;

function refresh(): void { voices = synth?.getVoices() ?? []; }
if (synth) {
  refresh();
  synth.addEventListener("voiceschanged", refresh);
}

function pick(lang: string): SpeechSynthesisVoice | undefined {
  const pool = voices.filter((v) => v.lang.toLowerCase().startsWith(lang));
  return pool.find((v) => v.localService) ?? pool[0];
}

const GRACE_S = 1.5; // a line may run this long past its slot before it is cut
const MAX_RATE = 1.5; // faster than this stops being intelligible; a line that still does not fit is cut at its slot
// Measured with Chrome's local voices: about 12 to 13 characters per second at rate 1 (the server plans with the same
// figure, commentary/lang.py). Each uninterrupted line refines the figure for its language.
const DEFAULT_CPS: Record<string, number> = { en: 12.5, de: 12, fr: 13 };
const measuredCps: Record<string, number> = { ...DEFAULT_CPS };

const MAX_AUDIO_RATE = 1.25; // ElevenLabs audio is sped up at most this much to fit its slot; beyond that it is cut at the slot
const AUDIO_START_WATCHDOG_S = 1.5; // audio that has not started playing this long after its source is set counts as failed
const AUDIO_ERRORS_BEFORE_OFF = 2; // consecutive failed requests before the page stops asking and uses the browser voice

interface Pending { text: string; lang: string; slotEnd: number; deadline: number; url?: string; baked?: boolean; onStart?: () => void; onDrop?: () => void }
interface Options {
  baked?: boolean; // the mp3 is a file shipped with the page (the recorded run): played without the server, a failure never switches the live voice off
  tts?: string; // server URL of this line's mp3. Set only for a line the server published in a live run; fetched when the voice starts it, never before
  urgent?: boolean; // goals, red cards and the final whistle cut in; everything else waits for the line that is talking
  maxWaitS?: number; // how long a waiting line may wait before it is dropped (it stays on screen as a caption)
  onStart?: () => void; // called when the line is handed to the browser
  onDrop?: () => void; // called when the line is dropped instead of spoken
}

let session = 0; // every line that starts gets the next number; a handler of an older line sees it was replaced and does nothing
let stopCurrent: (() => void) | null = null;
let active = false; // a voice really is reading the current line (browser onstart, audio playing)
let busy = false; // the current line was handed to a voice and has not ended
let cutTimer = 0;
const waiting: Pending[] = [];

// ---- ElevenLabs path ----
export type VoiceEngine = "elevenlabs" | "browser";
let tts = { available: false };
let ttsErrors = 0;
const ttsListeners = new Set<() => void>();
export const onVoiceChange = (fn: () => void): (() => void) => { ttsListeners.add(fn); return () => { ttsListeners.delete(fn); }; };
const changed = (): void => ttsListeners.forEach((fn) => fn());
/** The engine that will speak the next line. */
export const engine = (): VoiceEngine => (tts.available ? "elevenlabs" : "browser");
/** The server's health says what is possible; a failed request switches ElevenLabs off until the next health check. */
export function configureTts(available: boolean): void {
  ttsErrors = 0;
  tts = { available };
  changed();
}
function ttsFailed(status: number): void {
  if (status === 404) return; // this one line is unknown to the server; the browser reads it, the next may be fine
  if (status === 402 || status === 503) {
    // over budget or not configured: stop asking, the browser voice takes over
    tts = { available: false };
  } else if (++ttsErrors >= AUDIO_ERRORS_BEFORE_OFF) {
    tts = { available: false };
  }
  changed();
}

// Every ElevenLabs line gets its own audio element, kept in the document while it plays (`<audio id="voice-audio">`) so it
// can be inspected. A page that has had a click may play audio; `primeAudio` (called from the kick-off click) makes sure.
const SILENCE = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";
export function primeAudio(): void {
  if (typeof Audio === "undefined") return;
  const el = new Audio(SILENCE);
  el.play().catch(() => undefined);
}

/** True while a voice is reading a line aloud. */
export const isSpeaking = (): boolean => active;

/** Say `text`; `wallSeconds` is the time the director gave this line, so a long line is read a bit faster.
 * A line never interrupts another one unless it is urgent: it waits for the end of the line that is talking, and is
 * dropped if that takes longer than `maxWaitS`. The voice never outlives its slot by more than a moment. */
export function speak(text: string, lang: string, wallSeconds: number, opts: Options = {}): void {
  if (!synth && !(opts.tts && (opts.baked || tts.available))) return;
  const now = performance.now();
  const line: Pending = {
    text, lang, slotEnd: now + wallSeconds * 1000, deadline: now + (opts.maxWaitS ?? 0) * 1000, url: opts.tts, baked: opts.baked, onStart: opts.onStart, onDrop: opts.onDrop,
  };
  if (opts.urgent) {
    for (const w of waiting.splice(0)) w.onDrop?.();
    start(line);
  } else if (busy) {
    waiting.push(line);
  } else {
    start(line);
  }
}

function startNext(): void {
  while (waiting.length) {
    const line = waiting.shift()!;
    if (performance.now() > line.deadline) { line.onDrop?.(); continue; }
    start(line);
    return;
  }
}

function start(line: Pending): void {
  line.onStart?.();
  clearTimeout(cutTimer);
  if (busy) { stopCurrent?.(); stopCurrent = null; } // only an urgent line gets here while another is talking
  // a hidden tab defers media, so the credits would buy a line nobody hears: the browser voice reads it instead
  if (line.url && (line.baked || tts.available) && typeof Audio !== "undefined" && document.visibilityState !== "hidden") startAudio(line);
  else startBrowser(line);
}

const DE_NUM = ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn"];

/** The spoken form of a caption for the browser voice: German writes a score 1:1 and says "eins zu eins" (the server's
 * shape_for_tts does the same for ElevenLabs); a system voice would read "1:1" as a ratio or a time of day. */
export function spokenForm(text: string, lang: string): string {
  if (lang !== "de") return text;
  return text.replace(/\b(\d{1,2}):(\d{1,2})\b/g, (all, a: string, b: string) =>
    +a <= 10 && +b <= 10 ? `${DE_NUM[+a]} zu ${DE_NUM[+b]}` : all);
}

function startBrowser(line: Pending): void {
  if (!synth) { finish(session); return; }
  const { lang } = line;
  const text = spokenForm(line.text, lang);
  const cps = measuredCps[lang] ?? 12.5;
  const natural = text.length / cps;
  // The slot may be half gone if the line had to wait; never squeeze it beyond MAX_RATE.
  const wall = Math.max((line.slotEnd - performance.now()) / 1000, natural / MAX_RATE, 0.5);
  const u = new SpeechSynthesisUtterance(text);
  u.lang = BCP47[lang] ?? lang;
  const v = pick(lang);
  if (v) u.voice = v;
  u.rate = Math.min(MAX_RATE, Math.max(1, natural / wall));
  const mine = ++session;
  stopCurrent = () => synth.cancel();
  active = false;
  busy = true;
  let startedAt = 0;
  let cut = false;
  u.onstart = () => { startedAt = performance.now(); if (session === mine) active = true; };
  u.onend = () => {
    if (!cut && startedAt && text.length >= 20) {
      const seen = text.length / ((performance.now() - startedAt) / 1000) / u.rate;
      if (seen > 6 && seen < 25) measuredCps[lang] = 0.7 * (measuredCps[lang] ?? 12.5) + 0.3 * seen;
    }
    finish(mine);
  };
  u.onerror = () => finish(mine);
  clearTimeout(cutTimer);
  cutTimer = window.setTimeout(() => { if (session === mine) { cut = true; synth.cancel(); } }, (wall + GRACE_S) * 1000);
  synth.speak(u);
}

/** ElevenLabs: ask the server for the mp3 now (the voice is starting this line, so it is worth the credits), play it
 * through its own audio element, speed it up a little if it is longer than the slot, end the slot when it really ends. */
function startAudio(line: Pending): void {
  const el = new Audio();
  el.id = "voice-audio";
  el.preload = "auto";
  el.hidden = true;
  document.body.appendChild(el);
  const mine = ++session;
  const ctl = new AbortController();
  let objectUrl = "";
  let playing = false;
  let watchdog = 0;
  const teardown = (): void => {
    clearTimeout(watchdog);
    ctl.abort();
    el.onplaying = el.onended = el.onerror = el.onloadedmetadata = null;
    el.pause();
    if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = ""; }
    el.removeAttribute("src");
    el.remove();
  };
  stopCurrent = teardown;
  active = false;
  busy = true;
  const fallback = (): void => {
    if (session !== mine) return;
    teardown();
    // the line keeps its slot: the browser voice reads it for what is left of it
    if (performance.now() < line.slotEnd - 300) startBrowser(line); else finish(mine);
  };
  clearTimeout(cutTimer);
  cutTimer = window.setTimeout(() => { if (session === mine) { teardown(); finish(mine); } }, Math.max(line.slotEnd - performance.now(), 500) + GRACE_S * 1000);
  void (async () => {
    try {
      const res = await fetch(line.url!, { signal: ctl.signal });
      if (session !== mine) return;
      if (!res.ok) { if (!line.baked) ttsFailed(res.status); return fallback(); }
      const blob = await res.blob();
      if (session !== mine) return;
      objectUrl = URL.createObjectURL(blob);
      el.onloadedmetadata = () => {
        if (session !== mine) return;
        const available = Math.max((line.slotEnd - performance.now()) / 1000 + 0.3, 0.5);
        el.playbackRate = Math.min(MAX_AUDIO_RATE, Math.max(1, el.duration / available));
      };
      el.onplaying = () => { if (session === mine) { playing = true; active = true; if (!line.baked) ttsErrors = 0; clearTimeout(watchdog); } };
      el.onended = () => { if (session === mine) { teardown(); finish(mine); } }; // the real end of the audio ends the slot
      el.onerror = () => { if (session === mine && !playing) { if (!line.baked) ttsFailed(0); fallback(); } else if (session === mine) { teardown(); finish(mine); } };
      el.src = objectUrl;
      // a page that cannot play media (deferred or blocked) never reaches `playing`: count it and let the browser voice read the line
      watchdog = window.setTimeout(() => { if (session === mine && !playing) { if (!line.baked) ttsFailed(0); fallback(); } }, AUDIO_START_WATCHDOG_S * 1000);
      await el.play();
    } catch (err) {
      if (session !== mine || (err instanceof DOMException && err.name === "AbortError")) return;
      if (!line.baked) ttsFailed(0);
      fallback();
    }
  })();
}

function finish(id: number): void {
  if (session !== id) return; // a newer line replaced this one; its own handlers run the queue
  active = false;
  busy = false;
  stopCurrent = null;
  clearTimeout(cutTimer);
  startNext();
}

export function stopSpeaking(): void {
  clearTimeout(cutTimer);
  session++;
  stopCurrent?.();
  stopCurrent = null;
  active = false;
  busy = false;
  for (const w of waiting.splice(0)) w.onDrop?.();
  synth?.cancel();
}
