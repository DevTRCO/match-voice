import { useEffect, useRef } from "react";
import { fmtDur } from "../derive";
import { setAttr, setText, useFrame, usePlayer, useTopic } from "../hooks";
import { PitchView } from "../pitch";
import { choose } from "../caption";
import type { DemoInsert, Say, Team } from "../protocol";
import { Trace } from "./Trace";
import { LiveIcon, PlayIcon, ReplayIcon } from "./Icons";
import { Settings } from "./TopBar";
import { Voices } from "./Voices";

const LONG_CAPTION = 96; // characters: past this the caption is set smaller so three lines fit the block that holds two
const FADE_MIN_S = 4; // a finished line recedes this long after its speech slot, longer for a long sentence (reading time)

/** The honest line under the caption: which run this is and what it costs, from the data. */
function statusOf(player: ReturnType<typeof usePlayer>): string {
  const { sim, guided } = player;
  const runs = (player.backend.kind === "server" ? player.backend.health.live.runs_left : null) ?? guided?.runs_left ?? null; // the health is re-read after every run, the guided answer is older
  const left = player.liveBlock === null && runs !== null && player.phase !== "playing" ? ` ${runs} live ${runs === 1 ? "run" : "runs"} left today.` : "";
  if (player.step === 1) return `Recorded${player.recordedLen === null ? "" : `, ${player.recordedLen} s`}. No model calls, free.${left}`;
  if (!guided) return "Live";
  const win = Math.round(guided.window_s);
  const id = `${guided.arc.replace("_", " ")} match, seed ${guided.seed}`;
  if (player.phase === "playing") {
    const left = Math.max(0, Math.ceil(guided.window_s - player.elapsed()));
    return `Live, new ${id}. ${left} s left of ${win} s.`;
  }
  if (player.phase === "over") return `Live, ${id}, ${Math.round(player.elapsed())} s.${sim.calls === null ? "" : ` ${sim.calls} model ${sim.calls === 1 ? "call" : "calls"}.`}${left}`;
  return "Live";
}

/** Scoreboard, pitch, the one caption line, why it was said, and the run's status. Everything that moves is written by the frame loop. */
export function Stage({ onProof }: { onProof: () => void }) {
  const player = usePlayer();
  const { sim } = player;
  useTopic("meta");
  useTopic("transport");
  const canvas = useRef<HTMLCanvasElement>(null);
  const view = useRef<PitchView | null>(null);
  const hud = useRef<Record<string, HTMLElement | null>>({});
  const reg = (name: string) => (el: HTMLElement | null) => { hud.current[name] = el; };
  const state = useRef<{ shown: Say | null; key: string; meta: number }>({ shown: null, key: "", meta: -1 });
  const lastScore = useRef("");
  const cut = useRef({ t: 0, at: -1e9, text: "" });

  useEffect(() => {
    if (!canvas.current) return;
    const v = new PitchView(canvas.current, sim);
    view.current = v;
    return () => { v.destroy(); view.current = null; };
  }, [sim]);

  useFrame((now) => {
    if (!sim.hello) return;
    const teams0 = sim.hello.match.teams;
    view.current?.draw(now);
    const h = hud.current;
    const st = state.current;
    const live = sim.framed;
    const intro = player.step === 1 ? player.demo : null; // before the first frame the board shows where the insert starts
    const score = live ? sim.score : intro?.score;
    const clock = live ? sim.clock : intro?.clock;
    setText(h.sh, score ? String(score[0]) : "");
    setText(h.sa, score ? String(score[1]) : "");
    setText(h.clock, clock ? `${clock}'` : "");
    const sc = `${sim.score[0]}-${sim.score[1]}`;
    if (live && lastScore.current && sc !== lastScore.current) { // the score changed in front of the viewer
      const el = h.board;
      el?.classList.remove("bump"); void el?.offsetWidth; el?.classList.add("bump");
    }
    lastScore.current = live ? sc : "";

    if (st.meta !== sim.version.meta) { // a new run: nothing of the last one stays on screen
      st.meta = sim.version.meta; st.shown = null; st.key = "\0";
      setText(h.text, ""); h.caption?.classList.remove("on");
    }
    const ch = player.ch;
    st.shown = choose(st.shown, sim.lastSay.get(ch), sim.t, ch);
    const cap = st.shown;
    if (sim.shown !== cap) { sim.shown = cap; sim.notify("sel"); } // the evidence and the log highlights follow the caption
    const key = cap ? `${cap.ch}:${cap.m}:${cap.text}` : "";
    if (key !== st.key) {
      st.key = key;
      if (sim.sel !== null) sim.select(null); // a new caption takes the evidence back
      setText(h.text, cap ? cap.text.replace(/(\d)-(\d)/g, "$1⁠-⁠$2") : ""); // keep scorelines on one line
      if (h.text) { if (cap && cap.text.length > LONG_CAPTION) h.text.setAttribute("data-long", ""); else h.text.removeAttribute("data-long"); } // a long sentence is set smaller
      if (cap) {
        const src = cap.src === "analyst" ? "analyst" : "template";
        setAttr(h.src, "data-src", src);
        const lat = cap.lat === undefined ? "" : fmtDur(cap.lat);
        setText(h.srcName, src === "analyst" ? (cap.cached ? "Analyst, answered from its cache" : `Analyst, on screen ${lat} after the event`) : `Template${lat ? `, on screen in ${lat}` : ""}`);
      }
      h.caption?.classList.toggle("on", !!cap);
    }
    const talking = player.talking(cap);
    const old = !!cap && player.phase === "playing" && sim.t > Math.max(cap.e, cap.s) + Math.max(FADE_MIN_S, cap.text.length / 12);
    const mode = talking ? "talking" : old ? "old" : "quiet";
    if (h.caption && h.caption.dataset.mode !== mode) h.caption.dataset.mode = mode;
    setText(h.status, statusOf(player));
    const wp = sim.wp; // the win probability: three segments that slide when a goal moves it
    if (h.wp) h.wp.dataset.on = wp ? "1" : "0";
    if (wp && teams0) {
      const [ph, pd, pa] = wp.map((x) => Math.round(x / 10));
      h.wbh?.style.setProperty("flex-grow", String(wp[0]));
      h.wbd?.style.setProperty("flex-grow", String(wp[1]));
      h.wba?.style.setProperty("flex-grow", String(wp[2]));
      setText(h.wph, `${teams0[0].short} ${ph}%`);
      setText(h.wpa, `${pa}% ${teams0[1].short}`);
      setText(h.wpd, `win probability, draw ${pd}%`);
    }
    const c = cut.current; // the story insert jumps ahead: say so, like a broadcast cut
    if (sim.framed && c.t && sim.t - c.t > 20 && player.phase === "playing") {
      const mins = Math.round((sim.t - c.t) / 60);
      c.at = now; c.text = `${mins <= 1 ? "A minute" : `${mins} minutes`} later, ${sim.clock}'`;
    }
    c.t = sim.framed ? sim.t : 0;
    const cutOn = now - c.at < 2600;
    if (h.cut && (h.cut.dataset.on === "1") !== cutOn) h.cut.dataset.on = cutOn ? "1" : "0";
    if (cutOn) setText(h.cutsub, c.text);
    const f = sim.flash;
    const on = !!f && f.kind === "goal" && now - f.at < 3400 && player.phase === "playing";
    if (h.goal && (h.goal.dataset.on === "1") !== on) h.goal.dataset.on = on ? "1" : "0";
    if (on && f) setText(h.goalsub, `${f.clock}', ${sim.score[0]}\u2013${sim.score[1]}`);
  });

  const teams = sim.hello?.match.teams;
  const phase = player.phase;
  const blocked = player.liveBlock;
  const canLive = blocked === null && !player.checking;

  return (
    <section className="stage" aria-label="Match">
      <div className="board" ref={reg("board")} style={teams ? undefined : { visibility: "hidden" }}>
        <div className="team home" style={{ ["--team" as string]: teams?.[0].color }}>
          <span>{teams?.[0].name}</span><i aria-hidden="true" />
        </div>
        <div className="score">
          <b className="digit" ref={reg("sh")} aria-label="Home goals" />
          <span className="dash" aria-hidden="true" />
          <b className="digit" ref={reg("sa")} aria-label="Away goals" />
          <span className="clock" ref={reg("clock")} />
        </div>
        <div className="team away" style={{ ["--team" as string]: teams?.[1].color }}>
          <span>{teams?.[1].name}</span><i aria-hidden="true" />
        </div>
      </div>

      <div className="wpbar" ref={reg("wp")} style={teams ? { ["--h" as string]: teams[0].color, ["--a" as string]: teams[1].color } : undefined} aria-label="Win probability">
        <span className="wl" ref={reg("wph")} />
        <div className="wtrack"><i className="wh" ref={reg("wbh")} /><i className="wd" ref={reg("wbd")} /><i className="wa" ref={reg("wba")} /></div>
        <span className="wl r" ref={reg("wpa")} />
        <small ref={reg("wpd")} />
      </div>

      <div className="pitchslot">
        <div className="pitchwrap" data-idle={phase === "ready" || phase === "over" || undefined} data-phase={phase}>
          <canvas ref={canvas} className="pitch" aria-hidden="true" />
          <div className="goalbanner" ref={reg("goal")} aria-hidden="true"><b>GOAL</b><span ref={reg("goalsub")} /></div>
          <div className="cutcard" ref={reg("cut")} aria-hidden="true"><span ref={reg("cutsub")} /></div>
          {phase === "ready" && (
            <div className="cta">
              <Settings />
              <button className="start" onClick={() => void player.playRecorded()} autoFocus>
                <PlayIcon /><span>Play the moment</span>
              </button>
            </div>
          )}
          {phase === "over" && (
            <div className="cta end">
              <Settings compact />
              <span />
              <div className="bottom">
                <div className="btns">
                  {canLive && <button className="start" onClick={() => void player.goLive()} autoFocus><LiveIcon /><span>{player.step === 2 ? "Go live again" : "Go live"}</span></button>}
                  <button className={canLive ? "start ghost" : "start"} onClick={() => void player.playRecorded()} autoFocus={!canLive}><ReplayIcon size={20} /><span>Replay recorded</span></button>
                  {player.step === 1 && <button className="start ghost" onClick={onProof}><span>Try to break it</span></button>}
                </div>
              </div>
            </div>
          )}
          {phase === "loading" && <div className="cta"><p className="note">{player.busy}</p></div>}
          {phase === "error" && (
            <div className="cta" role="alert">
              <p className="note">{player.error}</p>
              <button className="start small" onClick={() => location.reload()}>Reload</button>
            </div>
          )}
        </div>
      </div>

      <Voices onProof={onProof} />
      <Trace />
      <div className="foot">
        <p className="status" ref={reg("status")} />
        {phase === "ready" && <p className="status">{scene(teams, player.demo)}</p>}
        {blocked && <p className="status warn" role="status">{blocked}</p>}
      </div>
    </section>
  );
}

/** 1st, 2nd, 3rd, 4th ... 11th, 12th, 13th, 21st, 71st. */
export function ordinal(n: number): string {
  const r100 = n % 100;
  if (r100 >= 11 && r100 <= 13) return `${n}th`;
  return `${n}${({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
}

/** One quiet line of context for the start screen: who is behind, when, and how long the moment runs. */
function scene(teams: Team[] | undefined, d: DemoInsert | null): string {
  if (!teams || !d?.score || !d.clock) return "";
  const [h, a] = d.score;
  const added = d.clock.includes("+");
  const when = added ? `Added time, ${d.clock}'.` : `${ordinal(parseInt(d.clock, 10))} minute.`;
  const state = h === a ? `Level at ${h}-${a}.` : `${(h < a ? teams[0] : teams[1]).name} trail ${h}-${a}.`;
  const len = Math.round(d.length ?? d.until - d.start);
  return `${state} ${when} ${len} seconds of commentary.`;
}
