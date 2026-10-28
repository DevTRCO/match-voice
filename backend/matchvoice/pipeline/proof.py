"""Proof for the demo insert: the real verifier run on the recorded analyst lines, and on lines made wrong on purpose.

    python -m matchvoice.pipeline.proof

Writes ui/public/insert/proof.json. Nothing here calls a model. The "attacks" are injected errors and are labelled
as such in the file and in the UI: the verdicts are the real verifier's, the wrong sentences are ours.
"""
from __future__ import annotations

import json

from ..config import ROOT
from ..mcp_server import tools

INSERT = ROOT / "ui" / "public" / "insert"
CH_LANG = ["en", "en", "de", "de", "fr", "fr"]

# One wrong sentence per kind of error the verifier knows. `ch` is the channel the sentence is aimed at.
ATTACKS = [
    {"code": "score_mismatch", "ch": 1, "label": "Wrong scoreline",
     "text": "Fontaine's goal puts Wexmoor 2-1 in front."},
    {"code": "number_unsupported", "ch": 1, "label": "Invented statistic",
     "text": "Wexmoor's chance of a win jumps to 61 percent, and Tamsworth have to start all over again."},
    {"code": "player_unsupported", "ch": 3, "label": "Wrong player",
     "text": "Rourke steht plötzlich vor dem Tor und gleicht aus."},
    {"code": "language_mismatch", "ch": 5, "label": "Wrong language",
     "text": "Wexmoor have levelled it, and Tamsworth must respond now."},
]


def build() -> dict:
    ins = json.loads((INSERT / "replay.json").read_text(encoding="utf-8"))
    match, t = ins["demo"]["match"], ins["demo"]["goal_t"] + 0.2
    says = [m for m in ins["messages"] if m["k"] == "say"]
    analyst = {m["ch"]: m["text"] for m in says if m["voice"] == "analyst"}
    template = {m["ch"]: m["text"] for m in says if m["kind"] == "shot_goal"}

    def verdict(text: str, ch: int) -> dict:
        r = tools.verify_sentence(match, t, text, CH_LANG[ch])
        return {"ok": r["ok"], "violations": r["violations"]}

    checked = [{"ch": ch, "text": text, **verdict(text, ch)} for ch, text in sorted(analyst.items())]
    attacks = []
    for a in ATTACKS:
        v = verdict(a["text"], a["ch"])
        if v["ok"] or v["violations"][0]["code"] != a["code"]:
            raise SystemExit(f"attack {a['code']} was not caught as expected: {v}")
        attacks.append({**a, **v, "fallback": template[a["ch"]]})
    return {"v": 1, "match": match, "t": round(t, 1), "context": tools.verify_sentence(match, t, "x", "en")["context"],
            "checked": checked, "attacks": attacks,
            "note": "checked: the lines the analyst wrote, run through the real verifier. attacks: injected errors, written for this demo, "
                    "judged by the real verifier. fallback: the template line the pipeline publishes when a line fails twice."}


if __name__ == "__main__":
    out = build()
    (INSERT / "proof.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {INSERT / 'proof.json'}: {sum(c['ok'] for c in out['checked'])}/{len(out['checked'])} lines ok, "
          f"{len(out['attacks'])} attacks caught")
