// Game log wording: one plain sentence per event row, written from the frame and the hello tables (players, outcomes,
// set pieces). Nothing here is invented: every word is a type, an outcome or a name that came with the data.
import { EV, O, T } from "./protocol";
import type { EventRow, Hello } from "./protocol";

export const surname = (full: string): string => full.split(" ").pop() ?? full;

export interface Written { text: string; strong: boolean; side: 0 | 1 }

/** `after` is the score of the frame the event came in. Returns null for events too small to read out (possession changes). */
export function writeEvent(h: Hello, row: EventRow, after: [number, number]): Written | null {
  const type = h.types[row[EV.type]];
  const outcome = h.outcomes[row[EV.outcome]];
  const setPiece = h.setPieces[row[9]];
  const p = h.players[row[EV.player]];
  const who = p ? surname(p.name) : "A player";
  const side = (row[EV.side] === 1 ? 1 : 0) as 0 | 1;
  const team = h.match.teams[side]?.name ?? "";
  const plain = (text: string, strong = false): Written => ({ text, strong, side });
  switch (type) {
    case "kickoff": return plain("Kick-off.");
    case "period_end": return plain(outcome === "half_time" ? "Half time." : "Full time.", true);
    case "possession_change": return null;
    case "pass":
      if (setPiece) return plain(`${who} takes a ${setPiece.replace("_", " ")}.`);
      return plain(outcome === "complete" ? `${who} completes a pass.` : outcome === "out" ? `${who}'s pass goes out.` : `${who}'s pass is not completed.`);
    case "carry": return plain(`${who} carries the ball.`);
    case "shot": {
      const xg = row[EV.xg] > 0 ? ` (xG ${(row[EV.xg] / 100).toFixed(2)})` : "";
      if (row[EV.outcome] === O.goal) return plain(`Goal. ${who} scores for ${team}, it is ${after[0]}-${after[1]}.${xg}`, true);
      const what = outcome === "saved" ? "saved" : outcome === "blocked" ? "blocked" : outcome === "post" ? "hits the post" : "off target";
      return plain(`${who} shoots, ${what}.${xg}`, true);
    }
    case "tackle": return plain(outcome === "won" ? `${who} wins a tackle.` : `${who} tackles.`);
    case "interception": return plain(`${who} intercepts.`);
    case "pressure": return plain(`${who} presses the ball.`);
    case "foul": return plain(`Foul by ${who}.`);
    case "card": return plain(row[EV.outcome] === O.red ? `Red card for ${who}.` : `Yellow card for ${who}.`, true);
    default: return null;
  }
}

/** The facts of one event row for the evidence box: what it was, who, where in the match. */
export function describeRow(h: Hello, row: EventRow, clock: string): string {
  const p = h.players[row[EV.player]];
  const type = h.types[row[EV.type]];
  const outcome = h.outcomes[row[EV.outcome]];
  const bits = [`#${row[EV.i]}`, outcome ? `${type}, ${outcome.replace("_", " ")}` : type];
  if (p) bits.push(`${surname(p.name)} (${p.n})`);
  if (row[EV.type] === T.shot && row[EV.xg] > 0) bits.push(`xG ${(row[EV.xg] / 100).toFixed(2)}`);
  bits.push(`${clock}'`);
  return bits.join(", ");
}
