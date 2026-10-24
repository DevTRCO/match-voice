import { useEffect, useMemo, useRef, useState } from "react";
import { LogModal, LogsColumn } from "./components/Logs";
import type { LogKind } from "./components/Logs";
import { Stage } from "./components/Stage";
import { TopBar } from "./components/TopBar";
import { PlayerContext } from "./hooks";
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
  const modalOpen = useRef(false);
  modalOpen.current = modal !== null;

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

  const open = (kind: LogKind, from: HTMLElement): void => setModal({ kind, from });

  return (
    <div className="app">
      <TopBar onMute={toggleMute} onOpen={open} />
      <main className="main"><Stage /><LogsColumn onOpen={open} /></main>
      {modal && <LogModal kind={modal.kind} returnTo={modal.from} onClose={() => setModal(null)} />}
    </div>
  );
}
