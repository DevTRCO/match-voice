import { useRef } from "react";
import { fmtDur } from "../derive";
import { setAttr, setText, useFrame, usePlayer, useTopic } from "../hooks";
import type { Lang, Style } from "../player";

const LABEL: Record<Lang, string> = { en: "English", de: "Deutsch", fr: "Français" };
const STYLE: Record<Style, string> = { beginner: "Beginner", expert: "Expert" };
const POP_MS = 1400;

/** The six commentators of one match, side by side: three languages by two styles, all fed by the same events at the same moment.
 * The card of the picked channel is the one that is spoken. Written from the frame loop, like the rest of the stage. */
export function Voices({ onProof }: { onProof: () => void }) {
  const player = usePlayer();
  const { sim } = player;
  useTopic("meta");
  useTopic("transport");
  const cards = useRef<(HTMLElement | null)[]>([]);
  const seen = useRef<string[]>([]);
  const popAt = useRef<number[]>([]);

  useFrame((now) => {
    const hello = sim.hello;
    if (!hello) return;
    hello.channels.forEach((c) => {
      const el = cards.current[c.id];
      if (!el) return;
      const say = sim.lastSay.get(c.id);
      const live = !!say && sim.t >= say.s;
      const key = live && say ? `${say.m}:${say.text}` : "";
      if (key === (seen.current[c.id] ?? "")) {
        const pop = now - (popAt.current[c.id] ?? -1e9) < POP_MS;
        if ((el.dataset.pop === "1") !== pop) el.dataset.pop = pop ? "1" : "0";
        return;
      }
      seen.current[c.id] = key;
      setText(el.querySelector<HTMLElement>(".vt"), live && say ? say.text.replace(/(\d)-(\d)/g, "$1⁠-⁠$2") : "");
      if (live && say) {
        const analyst = say.src === "analyst";
        setAttr(el, "data-src", analyst ? "analyst" : "template");
        const lat = say.lat === undefined ? "" : fmtDur(say.lat);
        setText(el.querySelector<HTMLElement>(".vs"), analyst ? "Analyst, verified" : `Template${lat ? `, ${lat}` : ""}`);
        popAt.current[c.id] = now;
        el.dataset.pop = "1";
      } else {
        setAttr(el, "data-src", "");
        setText(el.querySelector<HTMLElement>(".vs"), "");
      }
    });
  });

  const channels = sim.hello?.channels ?? [];
  const order = [...channels].sort((a, b) => (a.style === b.style ? 0 : a.style === "beginner" ? -1 : 1) || a.id - b.id);
  const picked = player.ch;
  return (
    <div className="voices" aria-label="Six commentators">
      {order.map((c) => (
        <article key={c.id} className="voice" ref={(el) => { cards.current[c.id] = el; }} data-picked={c.id === picked || undefined} data-src="" data-pop="0">
          <header>
            <button className="pick" onClick={() => player.setChannel(c.lang, c.style)} aria-pressed={c.id === picked} title="Hear this commentator">
              <b>{c.lang.toUpperCase()}</b><span>{LABEL[c.lang]}, {STYLE[c.style]}</span>
            </button>
            <button className="vs" onClick={onProof} title="How every line is checked" />
          </header>
          <p className="vt" />
        </article>
      ))}
    </div>
  );
}
