import { createContext, useContext, useEffect, useRef, useSyncExternalStore } from "react";
import type { Player } from "./player";
import type { Topic } from "./sim";
import { onVoiceChange } from "./speech";

export const PlayerContext = createContext<Player>(null as unknown as Player);
export const usePlayer = (): Player => useContext(PlayerContext);

/** Re-render only when a rare topic changes (match loaded, play state). */
export function useTopic(topic: Topic): number {
  const { sim } = usePlayer();
  return useSyncExternalStore((fn) => sim.subscribe(topic, fn), () => sim.version[topic]);
}

const frames = new Set<(now: number) => void>();
let raf = 0;
function loop(now: number): void {
  raf = requestAnimationFrame(loop); // scheduled first: one throwing frame must not stop the loop
  frames.forEach((fn) => fn(now));
}

/** Run `fn` on every animation frame. The one place where playback state reaches the DOM and the canvas. */
export function useFrame(fn: (now: number) => void): void {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    const cb = (now: number) => ref.current(now);
    frames.add(cb);
    if (frames.size === 1) raf = requestAnimationFrame(loop);
    return () => {
      frames.delete(cb);
      if (frames.size === 0) cancelAnimationFrame(raf);
    };
  }, []);
}

/** Write a DOM property only when it changed, so a 60 Hz loop does not cause style recalculation. */
export function setText(el: HTMLElement | null, value: string): void {
  if (el && el.dataset.v !== value) { el.dataset.v = value; el.textContent = value; }
}
export function setAttr(el: HTMLElement | null, name: string, value: string): void {
  if (el && el.getAttribute(name) !== value) el.setAttribute(name, value);
}

let voiceVersion = 0;
/** Re-render when the voice engine changes (once per run at most: server voice to browser voice after errors). */
export function useVoice(): number {
  return useSyncExternalStore((fn) => onVoiceChange(() => { voiceVersion++; fn(); }), () => voiceVersion);
}
