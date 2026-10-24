import { useRef } from "react";
import { evidence, selectedRef } from "../derive";
import { useFrame, usePlayer } from "../hooks";

const MAX_ITEMS = 6;

/** "Why this line": the real data behind the caption on screen, or behind the log row the viewer clicked. Built only from
 * the stream (event rows, log steps, insights); with nothing real to show the box is empty. Written from the frame loop,
 * and only when the selection or the data changed. */
export function EvidenceBox({ reserve = false }: { reserve?: boolean }) {
  const player = usePlayer();
  const { sim } = player;
  const box = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const last = useRef("");
  useFrame(() => {
    const ul = list.current;
    if (!ul || !box.current) return;
    const ref = selectedRef(sim);
    const key = `${ref}|${sim.version.feed}|${sim.version.meta}|${player.ch}`;
    if (key === last.current) return;
    last.current = key;
    const items = evidence(sim, ref, player.ch).slice(0, MAX_ITEMS);
    ul.replaceChildren(...items.map((it) => {
      const li = document.createElement("li");
      const b = document.createElement("b"); b.textContent = it.label;
      const s = document.createElement("span"); s.textContent = it.text; s.title = it.text;
      li.append(b, s);
      return li;
    }));
    box.current.dataset.empty = items.length ? "" : "1";
    if (!reserve) box.current.hidden = items.length === 0;
  });
  return (
    <div className="why" ref={box} data-empty="1" hidden={!reserve} aria-label="Why this line">
      <h3>Why this line</h3>
      <ul ref={list} />
    </div>
  );
}
