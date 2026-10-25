import { useEffect, useRef, useState } from "react";
import { fetchProof } from "../feed";
import type { Proof } from "../feed";
import { CloseIcon } from "./Icons";

const CH = ["EN beginner", "EN expert", "DE beginner", "DE expert", "FR beginner", "FR expert"];

/** The verifier at work: the real analyst lines it passed, then mistakes injected on purpose and what it said to each. */
export function ProofModal({ onClose }: { onClose: () => void }) {
  const dlg = useRef<HTMLDialogElement>(null);
  const [proof, setProof] = useState<Proof | null>(null);
  const [failed, setFailed] = useState(false);
  const [run, setRun] = useState(0);
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => { fetchProof().then(setProof).catch(() => setFailed(true)); }, []);
  useEffect(() => {
    const d = dlg.current;
    if (d && !d.open) d.showModal();
    return () => { if (d?.open) d.close(); };
  }, []);
  useEffect(() => { body.current?.scrollTo(0, 0); }, [proof]);
  const passed = proof?.checked.filter((c) => c.ok).length ?? 0;
  return (
    <dialog ref={dlg} className="modal proof" aria-labelledby="proof-title" onCancel={(e) => { e.preventDefault(); onClose(); }}
      onClick={(e) => { if (e.target === dlg.current) onClose(); }}>
      <div className="mh">
        <h2 id="proof-title">Nothing is spoken unchecked</h2>
        <span>plain code, not a second model: the same check runs on every line</span>
        <button className="iconbtn" onClick={onClose} aria-label="Close" autoFocus><CloseIcon /></button>
      </div>
      <div className="pbody" ref={body}>
        {failed && <p className="note">The proof file could not be loaded.</p>}
        {proof && (
          <>
            <section key={run} className="attacks">
              <h3>
                <span className="big">{proof.attacks.length}/{proof.attacks.length}</span> mistakes injected on purpose were caught
                <button className="again" onClick={() => setRun(run + 1)}>Run again</button>
              </h3>
              <ol className="plist">
                {proof.attacks.map((a, i) => (
                  <li key={a.code} style={{ ["--d" as string]: `${i * 0.9 + 0.2}s` }} data-ok="false">
                    <div className="atk"><em>{a.label} · {CH[a.ch]}</em><del>{a.text}</del></div>
                    <div className="why2"><i aria-hidden="true">✕</i><code>{a.violations[0].code}</code><span>{a.violations[0].detail}</span></div>
                    <div className="fb"><b>Template takes over</b><span>{a.fallback}</span></div>
                  </li>
                ))}
              </ol>
            </section>
            <section>
              <h3><span className="big">{passed}/{proof.checked.length}</span> lines the analyst wrote for this goal passed</h3>
              <ul className="plist">
                {proof.checked.map((c) => (
                  <li key={c.ch} data-ok={c.ok}><i aria-hidden="true">{c.ok ? "✓" : "✕"}</i><em>{CH[c.ch]}</em><span>{c.text}</span></li>
                ))}
              </ul>
            </section>
            <p className="fine2">The mistakes are written for this demo. The verdicts are the real verifier's, run on match {proof.match} at {proof.t.toFixed(0)} s. No model call.</p>
          </>
        )}
      </div>
    </dialog>
  );
}
