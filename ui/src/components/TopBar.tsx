import { usePlayer, useTopic } from "../hooks";
import type { Lang, Style } from "../player";
import { ExpandIcon, SoundIcon } from "./Icons";

const LANGS: { id: Lang; label: string; name: string }[] = [
  { id: "en", label: "EN", name: "English" }, { id: "de", label: "DE", name: "Deutsch" }, { id: "fr", label: "FR", name: "Français" },
];
const STYLES: { id: Style; label: string; hint: string }[] = [
  { id: "beginner", label: "Beginner", hint: "Plain words, every term explained" },
  { id: "expert", label: "Expert", hint: "Tactics and expected goals, no hand holding" },
];

function Seg<T extends string>({ label, value, options, onChange }: {
  label: string; value: T; options: { id: T; label: string; title: string }[]; onChange: (v: T) => void;
}) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.id} role="radio" aria-checked={value === o.id} title={o.title} onClick={() => onChange(o.id)}>{o.label}</button>
      ))}
    </div>
  );
}

/** The guided run: step 1 recorded, step 2 live. The lengths are the data's: the insert's window and the server's last answer. */
function Rail() {
  const player = usePlayer();
  useTopic("transport");
  useTopic("meta");
  const { step, phase } = player;
  const connecting = phase === "loading" && player.busy !== "Loading";
  const on2 = step === 2 || connecting;
  const done1 = on2 || (step === 1 && phase === "over");
  const blocked = player.liveBlock;
  const len = (n: number | null): string => (n === null ? "" : `${n} s`);
  return (
    <ol className="rail" aria-label="Guided run">
      <li className="step" data-on={!done1 || undefined} data-done={done1 || undefined} aria-current={!done1 ? "step" : undefined}>
        <i aria-hidden="true">{done1 ? "✓" : "1"}</i>Recorded <small>{len(player.recordedLen)}</small>
      </li>
      <li className="sep" aria-hidden="true" />
      <li className="step" data-on={(on2 && !blocked) || undefined} data-next={(done1 && !on2 && !blocked) || undefined} data-off={blocked ? "" : undefined}
        aria-current={on2 ? "step" : undefined} title={blocked ?? undefined}>
        <i aria-hidden="true">2</i>Live <small>{blocked ? "off" : len(player.liveLen)}</small>
      </li>
    </ol>
  );
}

/** Wordmark, the step rail, the voice label and the two log buttons that stand in for the logs on a narrow screen. */
export function TopBar({ onMute, onOpen }: { onMute: () => void; onOpen: (kind: "game" | "agent", el: HTMLElement) => void }) {
  const player = usePlayer();
  useTopic("transport");
  return (
    <header className="bar">
      <div className="brand" aria-label="match-voice">
        <span>match<b>voice</b></span>
      </div>
      <Rail />
      <div className="tools">
        <span className="logbtns">
          <button className="iconbtn" onClick={(e) => onOpen("game", e.currentTarget)} aria-haspopup="dialog" title="Open the full game log"><ExpandIcon /><span>Game</span></button>
          <button className="iconbtn" onClick={(e) => onOpen("agent", e.currentTarget)} aria-haspopup="dialog" title="Open the full agent log"><ExpandIcon /><span>Agents</span></button>
        </span>
        {player.step === 1 && player.lang === "en" && player.style === "expert"
          ? <span className="fine" title="The recorded run has a baked ElevenLabs voice for English expert; the other commentators and the live step use the browser's own voice">ElevenLabs voice</span>
          : <span className="fine" title="Read by the browser's own voice; only English expert in the recorded run has a baked ElevenLabs voice">Browser voice</span>}
        <button className="mute" aria-pressed={player.muted} onClick={onMute} title="Spoken commentary on or off. Captions stay. Shortcut: m">
          <SoundIcon off={player.muted} />
          <span>{player.muted ? "Sound off" : "Sound on"}</span>
        </button>
      </div>
    </header>
  );
}

/** The settings of a run, chosen before it starts. `compact` is the one-row form on the end screen. */
export function Settings({ compact = false }: { compact?: boolean }) {
  const player = usePlayer();
  useTopic("transport");
  const lang = <Seg label="Language" value={player.lang} onChange={(v) => player.setChannel(v, player.style)} options={LANGS.map((l) => ({ id: l.id, label: l.label, title: l.name }))} />;
  const style = <Seg label="Commentary style" value={player.style} onChange={(v) => player.setChannel(player.lang, v)} options={STYLES.map((s) => ({ id: s.id, label: s.label, title: s.hint }))} />;
  if (compact) return <div className="settings compact">{lang}{style}</div>;
  return (
    <div className="settings">
      <div className="row"><span className="lab">Language</span>{lang}</div>
      <div className="row"><span className="lab">Commentary</span>{style}</div>
    </div>
  );
}
