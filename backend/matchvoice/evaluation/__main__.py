"""python -m matchvoice.evaluation  [--speed 30] [--out data/eval/results.json] [--report docs/EVAL.md]

Runs the replay pipeline unpaced over every match and channel. No model call, no key.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from ..config import ROOT
from . import metrics
from .report import render
from .run import DEFAULT_SPEED, evaluate_all


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=DEFAULT_SPEED, help="main run; a real-time run (x1) always follows")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "eval" / "results.json")
    ap.add_argument("--report", type=Path, default=ROOT / "docs" / "EVAL.md")
    a = ap.parse_args()
    res = evaluate_all(speeds=(a.speed, 1.0))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(metrics.dumps(res))
    a.report.write_text(render(res))
    o = res["runs"]["%g" % a.speed]["overall"]
    print(f"{a.out}\n{a.report}")
    print(f"x{a.speed:g}: {o['lines']} lines, grounding {o['grounding_rate']:.1%}, analyst-written {o['said_by_analyst_share']:.1%}, "
          f"key moments found {o['keymoment_detection_coverage']:.1%}, voiced {o['keymoment_spoken_coverage']:.1%}, "
          f"ready delay median {o['ready_delay_viewer_s']['median']} s")


if __name__ == "__main__":
    main()
