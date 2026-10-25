import { useEffect, useMemo, useRef, useState } from "react";
import { LogModal, LogsColumn } from "./components/Logs";
import type { LogKind } from "./components/Logs";
import { ProofModal } from "./components/Proof";
import { Stage } from "./components/Stage";
import { TopBar } from "./components/TopBar";
import { startCrowd, updateCrowd } from "./crowd";
import { PlayerContext, useFrame } from "./hooks";
import { EV, T } from "./protocol";
import { isSpeaking } from "./speech";
import { Player } from "./player";
import type { Lang, Style } from "./player";

function pref<T extends string>(key: string, fallback: T, ok: readonly T[]): T {
  try {
    const v = localStorage.getItem(key) as T | null;
    return v && ok.includes(v) ? v : fallback;
  } catch { return fallback; }
}
function save(key: string, value: string): void {
  try { localStorage.setItem(key, value); } catch { /* private window, fine */ }
}

export default function App() {
  const player = useMemo(() => {
    const p = new Player();
    if (import.meta.env.DEV) (window as unknown as { __player: Player }).__player = p; // dev server only: a handle for measurements
    return p;
  }, []);
  return <PlayerContext.Provider value={player}><Shell player={player} /></PlayerContext.Provider>;
}

function Shell({ player }: { player: Player }) {
  const [modal, setModal] = useState<{ kind: LogKind; from: HTMLElement | null } | null>(null);
  const [proof, setProof] = useState(false);
  const modalOpen = useRef(false);
  modalOpen.current = modal !== null || proof;

  useEffect(() => {
    const q = new URLSearchParams(location.search);
    const lang = q.get("lang") as Lang | null;
    const style = q.get("style") as Style | null;
    player.lang = lang && ["en", "de", "fr"].includes(lang) ? lang : pref<Lang>("mv.lang", "en", ["en", "de", "fr"]);
    player.style = style && ["beginner", "expert"].includes(style) ? style : pref<Style>("mv.style", "expert", ["beginner", "expert"]);
    player.muted = q.has("mute") || pref("mv.voice", "on", ["on", "off"]) === "off";
    let gone = false;
    void player.boot(q.has("static") || import.meta.env.MODE === "static").then(() => { if (!gone && q.has("autoplay")) player.play(); });
    return () => { gone = true; player.dispose(); };
  }, [player]);

  const toggleMute = (): void => { player.setMuted(!player.muted); save("mv.voice", player.muted ? "off" : "on"); };
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.metaKey || e.ctrlKey || e.altKey || modalOpen.current) return;
      if (e.key === "m") toggleMute();
      if (e.key === " " && (e.target as HTMLElement).tagName !== "BUTTON") { e.preventDefault(); player.play(); }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  });

  // the stadium: on from the first click, then fed every frame with what the board shows
  useEffect(() => {
    const go = (): void => startCrowd();
    addEventListener("pointerdown", go);
    addEventListener("keydown", go);
    return () => { removeEventListener("pointerdown", go); removeEventListener("keydown", go); };
  }, []);
  const shot = useRef({ at: 0, seen: 0 });
  useFrame(() => {
    const { sim } = player;
    const last = sim.recent[sim.recent.length - 1];
    for (let i = sim.recent.length - 1; i >= 0; i--) {
      const r = sim.recent[i];
      if (r.at <= shot.current.seen) break;
      if (r.row[EV.type] === T.shot) { shot.current.at = r.at; break; }
    }
    if (last) shot.current.seen = last.at;
    updateCrowd({ muted: player.muted, speaking: isSpeaking(), playing: player.phase === "playing", ballX: last ? last.row[EV.ex] ?? last.row[EV.x] : null,
      shotAt: shot.current.at, goalAt: sim.flash?.kind === "goal" ? sim.flash.at : 0 });
  });

  const open = (kind: LogKind, from: HTMLElement): void => setModal({ kind, from });

  return (
    <div className="app">
      <TopBar onMute={toggleMute} onOpen={open} />
      <main className="main"><Stage onProof={() => setProof(true)} /><LogsColumn onOpen={open} /></main>
      {proof && <ProofModal onClose={() => setProof(false)} />}
      {modal && <LogModal kind={modal.kind} returnTo={modal.from} onClose={() => setModal(null)} />}
    </div>
  );
}
