import { useRef } from "react";
import { evidence, selectedRef } from "../derive";
import { useFrame, usePlayer } from "../hooks";

/** The path of the line on screen, in four steps: the raw event, what the system understood from it, what it decided to do,
 * and the words this fan hears. Built from the stream only (derive.evidence); written from the frame loop when it changes. */
const STEPS = [
  { id: "raw", title: "Raw event", labels: ["event"] },
  { id: "intel", title: "Intelligence", labels: ["state", "insight", "fact"] },
  { id: "decide", title: "Decision", labels: ["detector", "director", "wording", "analyst", "verifier", "publisher"] },
  { id: "voice", title: "Your voice", labels: [] },
] as const;
const PER_STEP = 2;
const MOMENT_S = 12; // a line about a moment looks this far back for the event and the insight it is about
const NAMES: Record<string, string> = { en: "English", de: "Deutsch", fr: "Français" };

export function Trace() {
  const player = usePlayer();
  const { sim } = player;
  const cols = useRef<(HTMLUListElement | null)[]>([]);
  const box = useRef<HTMLDivElement>(null);
  const last = useRef("");

  useFrame(() => {
    if (!box.current) return;
    const ref = selectedRef(sim);
    const key = `${ref}|${sim.version.feed}|${sim.version.meta}|${player.ch}`;
    if (key === last.current) return;
    last.current = key;
    const items = evidence(sim, ref, player.ch);
    const cap = sim.shown;
    const ch = sim.hello?.channels.find((c) => c.id === player.ch);
    STEPS.forEach((step, k) => {
      const ul = cols.current[k];
      if (!ul) return;
      let rows: string[];
      if (step.id === "voice") {
        rows = cap && ch ? [`${NAMES[ch.lang]}, ${ch.style}`, cap.text] : [];
      } else {
        rows = items.filter((it) => (step.labels as readonly string[]).includes(it.label)).map((it) => it.text);
        // a line about a moment (the analysis of a goal) has no single event of its own: show the moment it is about
        const near = cap ? [...sim.game].reverse().filter((g) => g.t <= cap.t + 0.5 && cap.t - g.t <= MOMENT_S) : [];
        if (step.id === "raw" && !rows.length && cap) {
          const ev = near.find((g) => g.kind === "event" && g.strong);
          rows = ev ? [`${ev.clock}' ${ev.text}`] : [cap.kind === "story_note" ? "No event: a quiet spell" : "No single event"];
        }
        if (step.id === "intel" && !rows.length && cap) {
          const ins = near.filter((g) => g.kind === "insight").map((g) => g.text);
          rows = ins.length ? ins : cap.kind === "story_note"
            ? [`Score ${sim.score[0]}-${sim.score[1]} at ${sim.clock}'`, "Club file: a story that fits the score and the time"] : [];
        }
      }
      ul.replaceChildren(...rows.slice(0, PER_STEP).map((t) => {
        const li = document.createElement("li");
        li.textContent = t; li.title = t;
        return li;
      }));
    });
    box.current.dataset.empty = cap ? "" : "1";
  });

  return (
    <div className="trace" ref={box} data-empty="1" aria-label="From raw event to your voice">
      {STEPS.map((s, k) => (
        <section key={s.id} data-step={s.id}>
          <h3>{s.title}</h3>
          <ul ref={(el) => { cols.current[k] = el; }} />
        </section>
      ))}
    </div>
  );
}
