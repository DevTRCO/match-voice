"""Gate measurements for phase 2 (docs/PLAN-DATA.md): every number comes from the rows, none is estimated."""
from __future__ import annotations

from collections import Counter
from typing import Any

from ...schema import Event, EventType
from .enrich import Enriched

KICK_FORBIDDEN = ("outcome", "assist", "assist_eid", "receiver", "touch", "facing", "hold_s")
TOUCH_TYPES = ("pass", "carry", "shot", "receipt")
INSERT_WINDOW = (4381.0, 4402.0)  # comeback-135, the demo insert
RANGES = {"short": (60, 78), "long": (8, 16), "back": (10, 20), "lofted": (12, 25)}  # percent of a team's passes
COUNT_RANGES = {"cross": (8, 25), "switch": (3, 12), "through": (1, 8)}  # per team and match


def arrival_bounds(events: list[Event], rows: list[dict[str, Any]]) -> tuple[int, int]:
    """(rows checked, rows outside [t + T, t_next - 0.25]) over every skeleton pass annotation."""
    by_i = {e.i: e for e in events}
    bad = n = 0
    for r in rows:
        if r["type"] != "pass" or r["k"] != 0:
            continue
        e = by_i[r["i"]]
        t_next = events[e.i + 1].t
        lo = e.t + e.length / (e.ball_speed / 3.6)
        n += 1
        if not (lo - 1e-9 <= r["t_arr"] <= t_next - 0.25 + 1e-9):
            bad += 1
    return n, bad


def measure(events: list[Event], res: Enriched) -> dict[str, Any]:
    rows = res.rows
    eids = [r["eid"] for r in rows]
    minutes = events[-1].t / 60
    skeleton_touches = sum(e.type in (EventType.PASS, EventType.CARRY, EventType.SHOT) for e in events)
    receipts = sum(r["type"] == "receipt" for r in rows)
    implicit = sum(1 for r in rows if r.get("implicit"))
    passes = [r for r in rows if r["type"] == "pass"]
    ft = sum(r["first_time"] for r in passes)
    n_checked, n_bad = arrival_bounds(events, rows)
    pressure_bad = sum(1 for e in events if e.under_pressure and e.type in (EventType.PASS, EventType.CARRY, EventType.SHOT)
                       and not next(r for r in rows if r["eid"] == 16 * e.i)["pressure"]["under"])
    window = [r for r in rows if r["type"] in TOUCH_TYPES and INSERT_WINDOW[0] <= r["t"] <= INSERT_WINDOW[1]]
    # time order along eid
    out_of_order = sum(1 for a, b in zip(rows, rows[1:]) if b["t"] < a["t"] - 1e-9)
    mix: dict[str, dict[str, Any]] = {}
    by_team = {s: [r for r in passes if r["team"] == s] for s in ("H", "A")}
    for s, ps in by_team.items():
        n = len(ps) or 1
        c = Counter(r["pass_type"] for r in ps)
        mix[s] = {"passes": len(ps), "short_pct": 100 * c["short"] / n, "long_pct": 100 * c["long"] / n,
                  "back_pct": 100 * c["back"] / n, "lofted_pct": 100 * sum(r["height"] == "lofted" for r in ps) / n,
                  "cross": c["cross"], "switch": c["switch"], "through": c["through"], "cut_back": c["cut_back"],
                  "lay_off": c["lay_off"], "clearance": c["clearance"], "types": dict(c)}
    return {
        "rows": len(rows), "unique_increasing": eids == sorted(set(eids)), "out_of_order_t": out_of_order,
        "overflow": res.stats.overflow, "squeezed": res.stats.squeezed, "unrepaired": len(res.stats.unrepaired),
        "arrival_checked": n_checked, "arrival_outside": n_bad,
        "passes": len(passes), "first_time_passes": ft, "first_time_pct": 100 * ft / max(1, len(passes)),
        "receipts": receipts, "implicit_passes": res.stats.implicit_passes, "implicit_carries": res.stats.implicit_carries,
        "touches_per_min": (skeleton_touches + receipts + implicit) / minutes,
        "touches_per_min_before": skeleton_touches / minutes,
        "insert_touches": len(window), "under_pressure_missing": pressure_bad,
        "kick_rows_with_outcome": sum(1 for r in rows if r["type"] == "pass" and (r["k"] == 0 or r.get("implicit"))
                                      and any(k in r for k in KICK_FORBIDDEN)),
        "mix": mix,
        "take_on_lost": sum(r["type"] == "take_on" for r in rows),
        "first_time_shots": sum(r["type"] == "shot" and r["first_time"] for r in rows),
        "shots": sum(r["type"] == "shot" for r in rows),
        "assisted_shots": sum(r["type"] == "shot" and r["assist_eid"] is not None for r in rows),
    }


def mix_table(m: dict[str, Any]) -> list[str]:
    """Lines of the pass-mix table for one match (percent of a team's passes, counts per team), with the 4.2 ranges."""
    lines = ["team  passes  short%  long%  back%  lofted%  cross  switch  through"]
    for s, x in m["mix"].items():
        lines.append(f"{s:<4}  {x['passes']:>6}  {x['short_pct']:>6.1f}  {x['long_pct']:>5.1f}  {x['back_pct']:>5.1f}  "
                     f"{x['lofted_pct']:>7.1f}  {x['cross']:>5}  {x['switch']:>6}  {x['through']:>7}")
    lines.append("range  "
                 f"{'':>6}  {RANGES['short'][0]}-{RANGES['short'][1]:<3}  {RANGES['long'][0]}-{RANGES['long'][1]:<3}  "
                 f"{RANGES['back'][0]}-{RANGES['back'][1]:<2}  {RANGES['lofted'][0]}-{RANGES['lofted'][1]:<3}  "
                 f"{COUNT_RANGES['cross'][0]}-{COUNT_RANGES['cross'][1]:<2}  {COUNT_RANGES['switch'][0]}-{COUNT_RANGES['switch'][1]:<2}  "
                 f"{COUNT_RANGES['through'][0]}-{COUNT_RANGES['through'][1]}")
    return lines


def summary(match_id: str, m: dict[str, Any]) -> str:
    out = [f"{match_id}: {m['rows']} rows, eids unique and increasing {m['unique_increasing']}, time out of order {m['out_of_order_t']}, "
           f"overflow {m['overflow']}, unrepaired jumps {m['unrepaired']}",
           f"  t_arr outside [t+T, t_next-0.25]: {m['arrival_outside']} of {m['arrival_checked']}; "
           f"first_time passes {m['first_time_passes']} of {m['passes']} ({m['first_time_pct']:.2f}%), first_time shots "
           f"{m['first_time_shots']} of {m['shots']}",
           f"  touches per minute {m['touches_per_min']:.2f} (skeleton alone {m['touches_per_min_before']:.2f}); "
           f"receipts {m['receipts']}, implicit passes {m['implicit_passes']}, implicit carries {m['implicit_carries']}, "
           f"lost take-ons {m['take_on_lost']}",
           f"  under_pressure skeleton events without pressure.under: {m['under_pressure_missing']}; kick rows with an outcome field: "
           f"{m['kick_rows_with_outcome']}; touches in the insert window {m['insert_touches']}",
           *("  " + ln for ln in mix_table(m))]
    return "\n".join(out)
