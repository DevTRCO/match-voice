import { URGENT_KINDS } from "./player";
import type { Say } from "./protocol";

/** Which line the caption shows. Normally the newest. A line that is being voiced is not pushed off the screen by a newer
 * one that has not started speaking (the analyst's answer can land a moment after the goal call): it waits for the voice. */
export function choose(shown: Say | null, newest: Say | undefined, t: number, ch: number): Say | null {
  if (!newest || t < newest.s) return shown?.ch === ch ? shown : null;
  if (!shown || shown.ch !== ch || newest.m === shown.m) return newest;
  const voicing = shown.e > shown.s && t < shown.e && !shown.cut;
  const waiting = newest.e === newest.s && !URGENT_KINDS.has(newest.kind);
  return voicing && waiting ? shown : newest;
}
