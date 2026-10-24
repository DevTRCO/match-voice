import { useEffect, useRef } from "react";
import { AGENT_NAMES, agentRows, fmtSince, laneData, related, selectedRef } from "../derive";
import type { Interval, LaneData } from "../derive";
import { useFrame, usePlayer, useTopic } from "../hooks";
import { EvidenceBox } from "./Evidence";
import { CloseIcon, ExpandIcon } from "./Icons";

export type LogKind = "game" | "agent";
const SHOWN = 24; // rows kept in the page: the panel is only as tall as a handful of them, older ones are hidden from the top (fit)
const FRAME_EPS = 0.25; // a lamp stays lit this long after a very short step, so a 2 ms verifier pass is still seen

interface Item { key: string; ref: string | null; sig: string; build: () => HTMLElement }

/** Keep `ol` equal to `items`, creating, moving and removing only what changed (focus stays on a row that did not move). */
function reconcile(ol: HTMLOListElement, items: Item[], cache: Map<string, HTMLElement>): void {
  const keep = new Set<string>();
  items.forEach((it, i) => {
    keep.add(it.key);
    let el = cache.get(it.key);
    if (!el || el.dataset.sig !== it.sig) { el = it.build(); el.dataset.sig = it.sig; cache.set(it.key, el); }
    if (ol.children[i] !== el) ol.insertBefore(el, ol.children[i] ?? null);
  });
  while (ol.children.length > items.length) ol.lastElementChild!.remove();
  for (const k of cache.keys()) if (!keep.has(k)) cache.delete(k);
}

/** Show only whole rows. All rows are in the list; from the newest backwards as many as fit stay visible and the older ones are
 * hidden, so the top edge never cuts a row in half. One layout read for the heights, then the writes. */
function fit(ol: HTMLOListElement): void {
  const rows = Array.from(ol.children) as HTMLElement[];
  for (const li of rows) if (li.hidden) li.hidden = false;
  if (!rows.length) return;
  const cs = getComputedStyle(ol);
  const room = ol.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
  if (!(room > 0)) { rows.forEach((li) => { li.hidden = true; }); return; }
  const heights = rows.map((li) => li.offsetHeight);
  let used = 0, first = rows.length;
  while (first > 0 && used + heights[first - 1] <= room + 0.5) { first--; used += heights[first]; }
  for (let i = 0; i < first; i++) rows[i].hidden = true;
  if (rows[first]) rows[first].toggleAttribute("data-first", true);
  for (let i = 0; i < rows.length; i++) if (i !== first) rows[i].removeAttribute("data-first");
}

const row = (ref: string | null, time: string, who: string | null, whoClass: string, text: string, dur: string, strong: boolean): HTMLElement => {
  const li = document.createElement("li");
  if (strong) li.dataset.strong = "";
  const body = ref ? document.createElement("button") : document.createElement("div");
  body.className = "r";
  if (ref) { (body as HTMLButtonElement).type = "button"; body.dataset.ref = ref; }
  const t = document.createElement("time"); t.textContent = time;
  const d = document.createElement("div");
  if (who) { const w = document.createElement("span"); w.className = `who ${whoClass}`; w.textContent = who; d.append(w); }
  d.append(document.createTextNode(text));
  if (dur) { const u = document.createElement("span"); u.className = "dur"; u.textContent = dur; d.append(u); }
  body.append(t, d);
  li.append(body);
  return li;
};

/** A log as a list that is written from the frame loop, only when its data or the selection changed. `limit` rows are kept
 * (the panel); without a limit it is the full log (the modal), which scrolls and sticks to the newest row. */
export function LogList({ kind, full = false, label }: { kind: LogKind; full?: boolean; label: string }) {
  const player = usePlayer();
  const { sim } = player;
  const ol = useRef<HTMLOListElement>(null);
  const cache = useRef(new Map<string, HTMLElement>());
  const last = useRef("");
  const sel = useRef("");
  const stick = useRef(true);

  useFrame(() => {
    const el = ol.current;
    if (!el) return;
    const ch = player.ch;
    const key = `${kind}|${sim.version.feed}|${sim.version.meta}|${ch}|${sim.skipped.size}`;
    if (key !== last.current) {
      last.current = key;
      let items: Item[];
      if (kind === "game") {
        const rows = full ? sim.game : sim.game.slice(-SHOWN);
        items = rows.map((g) => ({
          key: g.key, ref: g.ref, sig: g.text,
          build: () => row(g.ref, g.clock ? `${g.clock}'` : "", g.kind === "insight" ? "Insight" : null, "ins", g.text, "", g.strong),
        }));
      } else {
        const all = agentRows(sim, ch);
        const rows = full ? all : all.slice(-SHOWN);
        items = rows.map((a) => ({
          key: a.key, ref: a.ref, sig: a.text + a.dur,
          build: () => row(a.ref, fmtSince(a.w), a.who, a.id, a.text, a.dur, false),
        }));
      }
      const wasAtEnd = full ? el.scrollTop + el.clientHeight >= el.scrollHeight - 8 : true;
      reconcile(el, items, cache.current);
      sel.current = "";
      if (full) { if (wasAtEnd || stick.current) el.scrollTop = el.scrollHeight; } else fit(el);
    }
    const ref = selectedRef(sim);
    const skey = `${ref}|${last.current}`;
    if (skey !== sel.current) {
      sel.current = skey;
      const set = related(sim, ref, ch);
      for (const li of el.children) {
        const b = li.firstElementChild as HTMLElement | null;
        const on = !!b?.dataset.ref && set.has(b.dataset.ref);
        if (li.hasAttribute("data-sel") !== on) li.toggleAttribute("data-sel", on);
      }
    }
  });

  // the panel is as tall as the screen allows: when it resizes (or the font arrives), fit the whole rows again
  useEffect(() => {
    const el = ol.current;
    if (!el) return;
    // the modal list: the lanes and the evidence box fill in after the first frame and shrink it, so keep the newest row in view
    const ro = new ResizeObserver(() => { if (full) { if (stick.current) el.scrollTop = el.scrollHeight; } else fit(el); });
    ro.observe(el);
    void document.fonts?.ready.then(() => { if (full) { if (stick.current) el.scrollTop = el.scrollHeight; } else fit(el); });
    return () => ro.disconnect();
  }, [full]);

  return (
    <ol ref={ol} className={full ? "list full" : "list"} aria-label={label} data-empty={kind === "game" ? "Events show up here as the moment plays." : "Every step of every agent shows up here."}
      onClick={(e) => { const r = (e.target as HTMLElement).closest<HTMLElement>("[data-ref]")?.dataset.ref; if (r) sim.select(r); }}
      onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 8; }} />
  );
}

const LANES: (keyof Omit<LaneData, "span">)[] = ["det", "ana", "ver", "pub", "voc"];

/** Who works when. One row per agent: a lamp that is lit while the agent is busy, a track with its busy intervals and the playhead
 * (wall seconds since the run started). Where each lane comes from (derive.ts, all from log times `w`):
 *  Detector   dots at each `queued` log and at each template caption of the watched channel
 *  Analyst    [analyst_wrote.w - duration, analyst_wrote.w]; duration is latency_s (model call) or wall_s (cache hit); an open
 *             bar from `writing` / `lookup` while the answer is still pending
 *  Verifier   [the analyst_wrote it checked, its verified / rejected]
 *  Publisher  [the last verified, ready]
 *  Voice      the speech slot of each spoken line (the `say` or `voice` start, for e - s seconds, shorter when cut); lines
 *             that were skipped or said while muted have none */
export function Lanes() {
  const player = usePlayer();
  const { sim } = player;
  useTopic("transport");
  const root = useRef<HTMLDivElement>(null);
  const built = useRef<{ data: unknown; open: { el: HTMLElement; s: number }[]; span: number; segs: { el: HTMLElement; s: number; e: number | null }[] }>({ data: null, open: [], span: 0, segs: [] });
  const heads = useRef(new Map<string, number>());

  useFrame(() => {
    const el = root.current;
    if (!el) return;
    const data = laneData(sim, player.ch);
    const b = built.current;
    const running = player.phase === "playing" || player.phase === "over";
    const t = running ? player.elapsed() : -1;
    if (b.data !== data) {
      b.data = data; b.span = data.span; b.open = []; b.segs = [];
      const pct = (x: number): string => `${Math.min(100, (x / data.span) * 100).toFixed(2)}%`;
      for (const id of LANES) {
        const track = el.querySelector<HTMLElement>(`[data-lane="${id}"] .track`)!;
        for (const old of track.querySelectorAll(".seg2, .dot")) old.remove();
        const head = track.querySelector(".head");
        if (id === "det") for (const w of data.det) { const d = document.createElement("i"); d.className = "dot"; d.style.left = pct(w); b.segs.push({ el: d, s: w, e: w + 0.4 }); track.insertBefore(d, head); }
        else for (const iv of data[id] as Interval[]) {
          const s = document.createElement("i"); s.className = "seg2";
          s.style.left = pct(iv.s);
          s.style.width = iv.e === null ? "0" : `${Math.max(0, ((iv.e - iv.s) / data.span) * 100).toFixed(2)}%`;
          b.segs.push({ el: s, s: iv.s, e: iv.e === null ? null : iv.e + FRAME_EPS });
          if (iv.e === null) b.open.push({ el: s, s: iv.s });
          track.insertBefore(s, head);
        }
      }
      const ticks = el.querySelectorAll<HTMLElement>(".axis span");
      ticks.forEach((tick, i) => { tick.textContent = sim.hello ? `${Math.round((data.span * i) / (ticks.length - 1))} s` : ""; });
    }
    for (const g of b.segs) { // only the bar that is working right now is green
      const act = t >= 0 && t >= g.s && t <= (g.e ?? Infinity);
      if (g.el.hasAttribute("data-act") !== act) g.el.toggleAttribute("data-act", act);
    }
    for (const o of b.open) { const w = `${Math.max(0, ((Math.max(t, o.s) - o.s) / b.span) * 100).toFixed(2)}%`; if (o.el.style.width !== w) o.el.style.width = w; }
    for (const id of LANES) {
      const lane = el.querySelector<HTMLElement>(`[data-lane="${id}"]`)!;
      const on = t >= 0 && (id === "det" ? data.det.some((w) => t >= w && t <= w + 0.4)
        : (data[id] as Interval[]).some((iv) => t >= iv.s && t <= (iv.e ?? Infinity) + FRAME_EPS));
      if (lane.hasAttribute("data-on") !== on) lane.toggleAttribute("data-on", on);
      const head = lane.querySelector<HTMLElement>(".head")!;
      const x = t < 0 ? -1 : Math.round(Math.min(1, t / b.span) * 1000);
      if (heads.current.get(id) !== x) { heads.current.set(id, x); head.style.left = `${x / 10}%`; head.hidden = x < 0; }
    }
  });

  return (
    <div className="lanes" ref={root} role="group" aria-label="Who is working when, in seconds since the run started">
      {LANES.map((id) => (
        <div className={`lane ${id}`} data-lane={id} key={id}>
          <div className="nm"><i className="bulb" />{AGENT_NAMES[id]}{id === "voc" && player.muted ? <small>off</small> : null}</div>
          <div className="track"><i className="head" hidden /></div>
        </div>
      ))}
      <div className="axis"><span /><div><span /><span /><span /><span /><span /></div></div>
    </div>
  );
}

function Panel({ kind, onOpen }: { kind: LogKind; onOpen: (kind: LogKind, el: HTMLElement) => void }) {
  const title = kind === "game" ? "Game log" : "Agent log";
  return (
    <section className="panel" data-kind={kind} aria-label={title}>
      <div className="ph">
        <h2>{title}</h2><span>{kind === "game" ? "what the data says" : "what the agents do"}</span>
        <button className="iconbtn" onClick={(e) => onOpen(kind, e.currentTarget)} aria-haspopup="dialog" title={`Open the full ${title.toLowerCase()}`} aria-label={`Open the full ${title.toLowerCase()}`}><ExpandIcon /></button>
      </div>
      {kind === "agent" && <Lanes />}
      <LogList kind={kind} label={title} />
    </section>
  );
}

/** The right column: both logs, compact. On a narrow screen only the buttons in the top bar remain. */
export function LogsColumn({ onOpen }: { onOpen: (kind: LogKind, el: HTMLElement) => void }) {
  return (
    <aside className="logs" aria-label="What happens behind the commentary">
      <Panel kind="game" onOpen={onOpen} />
      <Panel kind="agent" onOpen={onOpen} />
    </aside>
  );
}

/** One log in full, in a modal dialog: scrolls inside, Esc or the button closes it, focus is trapped by the dialog and goes back to the button that opened it. */
export function LogModal({ kind, returnTo, onClose }: { kind: LogKind; returnTo: HTMLElement | null; onClose: () => void }) {
  const dlg = useRef<HTMLDialogElement>(null);
  const title = kind === "game" ? "Game log" : "Agent log";
  useEffect(() => {
    const d = dlg.current;
    if (!d) return;
    if (!d.open) d.showModal();
    return () => { if (d.open) d.close(); returnTo?.focus(); };
  }, [returnTo]);
  // The dialog makes the page behind it inert; Tab also wraps inside it instead of leaving for the browser's own controls.
  const trap = (e: React.KeyboardEvent<HTMLDialogElement>): void => {
    if (e.key !== "Tab") return;
    const ok = [...e.currentTarget.querySelectorAll<HTMLElement>("button, [href], [tabindex]:not([tabindex='-1'])")].filter((x) => !x.hidden && x.offsetParent !== null);
    if (!ok.length) return;
    const first = ok[0], lastEl = ok[ok.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); lastEl.focus(); }
    else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); first.focus(); }
  };
  return (
    <dialog ref={dlg} className="modal" data-kind={kind} aria-labelledby="modal-title" onCancel={(e) => { e.preventDefault(); onClose(); }} onKeyDown={trap}
      onClick={(e) => { if (e.target === dlg.current) onClose(); }}>
      <div className="mh">
        <h2 id="modal-title">{title}</h2>
        <span>{kind === "game" ? "every event of the run and every insight, oldest first" : "every step of every agent, in seconds since the run started"}</span>
        <button className="iconbtn" onClick={onClose} aria-label={`Close the ${title.toLowerCase()}`} autoFocus><CloseIcon /></button>
      </div>
      {kind === "agent" && <Lanes />}
      <LogList kind={kind} full label={`${title}, full`} />
      <EvidenceBox />
    </dialog>
  );
}
