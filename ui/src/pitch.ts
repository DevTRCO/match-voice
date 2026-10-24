// Canvas pitch. Reads the Sim every animation frame; nothing here touches React.
// Broadcast graphics on light turf, not a dashboard: soft mown stripes, white lines, the ball with a dark outline and a short trail, the players in play as dots with white name tags, one restrained goal moment. No history on the pitch.
import { EV, O, T } from "./protocol";
import type { Sim } from "./sim";

const W_DM = 1050;
const H_DM = 680;
const PAD = 16;
const TAG_MS = 3400; // a player's name tag
const MARK_MS = 5200; // tackles, fouls and cards
const COMET_MS = 650;
const GOAL_MS = 3600;
const GOAL_Y0 = 340 - 36.6;
const GOAL_Y1 = 340 + 36.6;

interface Layout { s: number; ox: number; oy: number; w: number; h: number }
interface Spark { x: number; y: number; at: number }

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const easeOut = (p: number): number => 1 - Math.pow(1 - clamp01(p), 3);
const easeInOut = (p: number): number => { const q = clamp01(p); return q < 0.5 ? 4 * q * q * q : 1 - Math.pow(-2 * q + 2, 3) / 2; };

const INK = "#14201a"; // dark ink for the ball outline, the goal pill and the text on white tags
const tuned = new Map<string, string>();
/** A team colour deepened toward black so violet and amber both hold their own on light turf. Amber cannot reach 3:1 against the turf
 * without turning brown (1.0 to 1.4:1 at 22 percent), so a marker never relies on its fill alone: a white ring (3:1 against the fill) and a
 * thin dark outer ring (5:1 against the turf) carry it; the trail and the off-ball marks get a white halo under the colour. */
function tune(hex: string, amt = 0.22): string {
  const key = hex + amt;
  const hit = tuned.get(key);
  if (hit) return hit;
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  let out = INK;
  if (m) {
    const n = parseInt(m[1], 16);
    const mix = (c: number) => Math.round(c * (1 - amt)).toString(16).padStart(2, "0");
    out = `#${mix((n >> 16) & 255)}${mix((n >> 8) & 255)}${mix(n & 255)}`;
  }
  tuned.set(key, out);
  return out;
}

export class PitchView {
  private ctx: CanvasRenderingContext2D;
  private bg = document.createElement("canvas");
  private lay: Layout = { s: 1, ox: 0, oy: 0, w: 0, h: 0 };
  private dpr = 1;
  private ball: { x: number; y: number } | null = null;
  private sparks: Spark[] = [];
  private ballEv: unknown = null;
  private last = performance.now();
  private ro: ResizeObserver;
  private reduce = false;
  private mq: MediaQueryList | null = null;
  private onMq = (): void => { this.reduce = !!this.mq?.matches; };

  constructor(private canvas: HTMLCanvasElement, private sim: Sim) {
    this.ctx = canvas.getContext("2d")!;
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(canvas);
    this.mq = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null;
    this.onMq();
    this.mq?.addEventListener("change", this.onMq);
    this.resize();
  }

  destroy(): void { this.ro.disconnect(); this.mq?.removeEventListener("change", this.onMq); }

  private resize(): void {
    const r = this.canvas.getBoundingClientRect();
    this.dpr = Math.min(2, window.devicePixelRatio || 1);
    this.canvas.width = Math.max(1, Math.round(r.width * this.dpr));
    this.canvas.height = Math.max(1, Math.round(r.height * this.dpr));
    const w = r.width;
    const h = r.height;
    const s = Math.min((w - PAD * 2) / W_DM, (h - PAD * 2) / H_DM);
    if (!(s > 0.05)) return; // collapsed or not laid out yet
    this.lay = { s, ox: (w - W_DM * s) / 2, oy: (h - H_DM * s) / 2, w, h };
    this.paintBackground();
  }

  private px(x: number): number { return this.lay.ox + x * this.lay.s; }
  private py(y: number): number { return this.lay.oy + y * this.lay.s; }

  /** The turf is painted once per size: mowing stripes, floodlight falloff, vignette and crisp lines. */
  private paintBackground(): void {
    const { s, ox, oy, w, h } = this.lay;
    const bg = this.bg;
    bg.width = this.canvas.width; bg.height = this.canvas.height;
    const c = bg.getContext("2d")!;
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    c.clearRect(0, 0, w, h);
    const X = (x: number) => ox + x * s;
    const Y = (y: number) => oy + y * s;
    const pw = W_DM * s, ph = H_DM * s;

    // turf and soft mown stripes
    const turf = c.createLinearGradient(0, oy, 0, oy + ph);
    turf.addColorStop(0, "#52b27d"); turf.addColorStop(1, "#47a572");
    c.fillStyle = turf; c.fillRect(ox, oy, pw, ph);
    const stripes = 14;
    for (let i = 0; i < stripes; i++) {
      c.fillStyle = i % 2 === 0 ? "rgba(255,255,255,0.06)" : "rgba(10,60,35,0.035)";
      c.fillRect(ox + (i * W_DM / stripes) * s, oy, (W_DM / stripes) * s + 0.5, ph);
    }

    // line work: plain white paint
    c.save();
    c.strokeStyle = "rgba(255,255,255,0.92)";
    c.lineWidth = Math.max(1.4, s * 2);
    c.lineJoin = "round";
    c.strokeRect(X(0), Y(0), pw, ph);
    c.beginPath(); c.moveTo(X(525), Y(0)); c.lineTo(X(525), Y(H_DM)); c.stroke();
    c.beginPath(); c.arc(X(525), Y(340), 91.5 * s, 0, Math.PI * 2); c.stroke();
    const dot = Math.max(1.8, s * 3.2);
    c.fillStyle = "rgba(255,255,255,0.92)";
    c.beginPath(); c.arc(X(525), Y(340), dot, 0, Math.PI * 2); c.fill();
    for (const [x0, dir] of [[0, 1], [W_DM, -1]] as const) {
      c.strokeRect(dir > 0 ? X(0) : X(W_DM - 165), Y(340 - 201.6), 165 * s, 403.2 * s);
      c.strokeRect(dir > 0 ? X(0) : X(W_DM - 55), Y(340 - 91.6), 55 * s, 183.2 * s);
      const spot = x0 + dir * 110;
      c.beginPath(); c.arc(X(spot), Y(340), dot, 0, Math.PI * 2); c.fill();
      c.beginPath(); c.arc(X(spot), Y(340), 91.5 * s, dir > 0 ? -0.93 : Math.PI - 0.93, dir > 0 ? 0.93 : Math.PI + 0.93); c.stroke();
    }
    c.restore();
    // the goals: frame and a faint net
    for (const dir of [1, -1]) this.net(c, dir, 0, 0, 0.3);
  }

  /** One goal's frame and net. With `amp` above 0 the net is displaced around the impact point `ey`, which is the ripple. */
  private net(c: CanvasRenderingContext2D, dir: number, amp: number, phase: number, alpha: number, impactY = 340): void {
    const { s } = this.lay;
    const x0 = dir > 0 ? 0 : W_DM; // goal line
    const back = dir > 0 ? -20 : 20; // the net hangs behind the line
    const bulge = (y: number, depth: number) => amp * Math.exp(-Math.pow((y - impactY) / 22, 2)) * Math.sin(phase - depth * 3.2) * (0.35 + depth);
    c.save();
    c.lineWidth = Math.max(0.8, s * 0.9);
    c.strokeStyle = `rgba(255,255,255,${alpha})`;
    c.beginPath();
    for (let yi = 0; yi <= 8; yi++) {
      const y = GOAL_Y0 + (yi / 8) * (GOAL_Y1 - GOAL_Y0);
      for (let xi = 0; xi <= 5; xi++) {
        const d = xi / 5;
        const px = this.px(x0 + back * d + dir * -bulge(y, d) * 0.55), py = this.py(y);
        if (xi === 0) c.moveTo(px, py); else c.lineTo(px, py);
      }
    }
    for (let xi = 1; xi <= 5; xi++) {
      const d = xi / 5;
      for (let yi = 0; yi <= 16; yi++) {
        const y = GOAL_Y0 + (yi / 16) * (GOAL_Y1 - GOAL_Y0);
        const px = this.px(x0 + back * d + dir * -bulge(y, d) * 0.55), py = this.py(y);
        if (yi === 0) c.moveTo(px, py); else c.lineTo(px, py);
      }
    }
    c.stroke();
    c.strokeStyle = "rgba(255,255,255,0.92)";
    c.lineWidth = Math.max(1.4, s * 2);
    c.strokeRect(dir > 0 ? this.px(-20) : this.px(W_DM), this.py(GOAL_Y0), 20 * s, (GOAL_Y1 - GOAL_Y0) * s);
    c.restore();
  }

  private color(side: number): string {
    return tune(this.sim.hello?.match.teams[side]?.color ?? INK);
  }

  draw(now: number): void {
    const { ctx, sim, lay } = this;
    const dt = Math.min(0.1, (now - this.last) / 1000);
    this.last = now;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, lay.w, lay.h);
    if (!sim.hello) { ctx.drawImage(this.bg, 0, 0, lay.w, lay.h); return; }

    const f = sim.flash;
    const gp = f && f.kind === "goal" ? (now - f.at) / GOAL_MS : 2; // goal moment progress, 0 to 1
    // slow push-in toward the goal mouth: ease in over the first 0.6 s, ease back out
    if (!this.reduce && gp >= 0 && gp < 1) {
      const push = gp < 0.17 ? easeInOut(gp / 0.17) : 1 - easeInOut((gp - 0.17) / 0.83);
      const k = 1 + 0.05 * push;
      const cx = this.px(f!.ex), cy = this.py(f!.ey);
      ctx.translate(cx, cy); ctx.scale(k, k); ctx.translate(-cx, -cy);
    }
    ctx.drawImage(this.bg, 0, 0, lay.w, lay.h);

    const ev = sim.recent;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    // net ripple on the goal mouth
    if (f && f.kind === "goal" && gp >= 0 && gp < 1) {
      const dir = f.ex < W_DM / 2 ? 1 : -1;
      const env = Math.pow(1 - gp, 2);
      if (!this.reduce) this.net(ctx, dir, 26 * env, gp * 26, 0.3 + 0.5 * env, f.ey);
      this.pulse(f.ex, f.ey, gp);
    }

    // off-ball events: quiet rings, a cross for a foul, a flag for a card
    for (const e of ev) {
      const r = e.row, type = r[EV.type];
      if (type < T.tackle || type > T.card) continue;
      const age = now - e.at;
      if (age > MARK_MS) continue;
      const a = Math.pow(1 - age / MARK_MS, 1.3);
      const x = this.px(r[EV.x]), y = this.py(r[EV.y]);
      if (type === T.card) { this.flag(x, y, r[EV.outcome] === O.red ? "#e5484d" : "#f5c542", a, now); continue; }
      ctx.globalAlpha = a * 0.9;
      ctx.beginPath();
      if (type === T.foul) { ctx.moveTo(x - 4, y - 4); ctx.lineTo(x + 4, y + 4); ctx.moveTo(x + 4, y - 4); ctx.lineTo(x - 4, y + 4); }
      else {
        const ring = this.reduce ? 4.5 : 4.5 + 7 * easeOut(age / 700) * (age < 700 ? 1 : 0);
        ctx.arc(x, y, ring, 0, Math.PI * 2);
      }
      ctx.strokeStyle = "rgba(255,255,255,0.85)"; ctx.lineWidth = 4; ctx.stroke(); // white halo, then the team colour on top
      ctx.strokeStyle = this.color(r[EV.side]); ctx.lineWidth = 2; ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // the standing goal marker, so the end state still shows where the goal came from
    if (f && f.kind === "goal") this.goalMark(f, now);

    // players involved in the newest events: a clean marker and a quiet name tag
    const tags: { x: number; y: number; w: number }[] = [];
    const tagged = new Set<number>(); // one marker per player: the newest event wins
    for (let i = ev.length - 1, n = 0; i >= 0 && n < 3; i--) {
      const e = ev[i], r = e.row;
      const age = now - e.at;
      if (age > TAG_MS || r[EV.player] < 0 || r[EV.type] === T.card || tagged.has(r[EV.player])) continue;
      tagged.add(r[EV.player]);
      n++;
      this.player(r, age, tags);
    }

    // the ball glides to the newest position
    const lastEv = ev[ev.length - 1];
    if (lastEv) {
      const r = lastEv.row;
      const tx = r[EV.ex] >= 0 ? r[EV.ex] : r[EV.x];
      const ty = r[EV.ey] >= 0 ? r[EV.ey] : r[EV.y];
      if (!this.ball) this.ball = { x: tx, y: ty };
      if (lastEv !== this.ballEv) {
        // a new event with its own origin: the ball starts at the origin, so the comet only follows this event's line
        this.ballEv = lastEv;
        if (r[EV.ex] >= 0 && r[EV.x] >= 0 && Math.hypot(this.ball.x - r[EV.x], this.ball.y - r[EV.y]) > 0.5) {
          this.ball.x = r[EV.x]; this.ball.y = r[EV.y];
          this.sparks.length = 0;
        }
      }
      const rate = this.reduce ? 60 : r[EV.type] === T.shot ? 13 : 7;
      const k = 1 - Math.exp(-dt * rate);
      const ox = this.ball.x, oy = this.ball.y;
      this.ball.x += (tx - this.ball.x) * k;
      this.ball.y += (ty - this.ball.y) * k;
      if (!this.reduce && Math.hypot(this.ball.x - ox, this.ball.y - oy) > 0.05) this.sparks.push({ x: this.ball.x, y: this.ball.y, at: now });
      this.comet(now, this.color(r[EV.side]));
      this.drawBall(this.px(this.ball.x), this.py(this.ball.y));
    } else { this.ball = null; this.ballEv = null; this.sparks.length = 0; }
  }

  /** The acting player: a clean disc at the event position and a name tag that fades. */
  private player(r: number[], age: number, tags: { x: number; y: number; w: number }[]): void {
    const ctx = this.ctx;
    const pl = this.sim.hello!.players[r[EV.player]];
    if (!pl) return;
    const a = age < 220 ? age / 220 : age > TAG_MS - 900 ? clamp01((TAG_MS - age) / 900) : 1;
    const x = this.px(r[EV.x]), y = this.py(r[EV.y]);
    const col = this.color(r[EV.side]);
    ctx.globalAlpha = a;
    ctx.fillStyle = "rgba(20,32,26,0.22)";
    ctx.beginPath(); ctx.arc(x, y + 1.5, 9, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = col;
    ctx.beginPath(); ctx.arc(x, y, 6.5, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2.4;
    ctx.stroke();
    ctx.strokeStyle = "rgba(20,32,26,0.6)"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(x, y, 8.4, 0, Math.PI * 2); ctx.stroke();

    const text = `${pl.n}  ${pl.name.split(" ").slice(-1)[0]}`;
    ctx.font = "600 12px 'Schibsted Grotesk Variable', sans-serif";
    ctx.textBaseline = "middle";
    const w = ctx.measureText(text).width + 18;
    const tx = Math.min(this.lay.w - w - 4, Math.max(4, x - w / 2));
    let ty = y - 34;
    if (ty < 4) ty = y + 16;
    for (const t of tags) if (Math.abs(t.x - tx) < (t.w + w) / 2 && Math.abs(t.y - ty) < 24) ty = t.y + (ty < y ? -25 : 25);
    ty = Math.min(this.lay.h - 26, Math.max(4, ty));
    tags.push({ x: tx, y: ty, w });
    ctx.fillStyle = "rgba(255,255,255,0.97)";
    ctx.beginPath(); ctx.roundRect(tx, ty, w, 22, 11); ctx.fill();
    ctx.strokeStyle = "rgba(20,32,26,0.16)"; ctx.lineWidth = 1; ctx.stroke();
    ctx.fillStyle = INK;
    ctx.fillText(text, tx + 9, ty + 11.5);
    ctx.globalAlpha = 1;
  }

  /** A card is a tiny flag on a pole, with a slow wave along its free edge. */
  private flag(x: number, y: number, col: string, a: number, now: number): void {
    const ctx = this.ctx;
    const wave = this.reduce ? 0 : Math.sin(now / 260) * 1.6;
    ctx.globalAlpha = a;
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 1.8;
    ctx.beginPath(); ctx.moveTo(x, y + 4); ctx.lineTo(x, y - 16); ctx.stroke();
    ctx.fillStyle = col;
    ctx.beginPath();
    ctx.moveTo(x, y - 16);
    ctx.lineTo(x + 11, y - 16 + wave * 0.5);
    ctx.lineTo(x + 10, y - 10 + wave);
    ctx.lineTo(x, y - 9);
    ctx.closePath(); ctx.fill();
    ctx.globalAlpha = 1;
  }

  /** A light pulse on the goal mouth. */
  private pulse(ex: number, ey: number, p: number): void {
    const ctx = this.ctx;
    const x = this.px(ex), y = this.py(ey);
    const r = (this.lay.s * 150) * (0.35 + 0.65 * easeOut(p * 1.6));
    const a = 0.5 * Math.pow(1 - clamp01(p * 1.25), 2);
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, `rgba(255,255,255,${a})`); g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
  }

  /** A ring at the spot of the last goal or red card with its minute, kept after the moment so the end state still points at it. */
  private goalMark(f: NonNullable<Sim["flash"]>, now: number): void {
    const ctx = this.ctx;
    const x = this.px(f.x), y = this.py(f.y);
    const age = now - f.at;
    const a = clamp01(age / 500);
    const breathe = this.reduce ? 0 : Math.sin(now / 700) * 0.5;
    ctx.globalAlpha = a;
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2.4;
    ctx.beginPath(); ctx.arc(x, y, 10 + breathe, 0, Math.PI * 2); ctx.stroke();
    ctx.font = "700 12px 'Schibsted Grotesk Variable', sans-serif";
    ctx.textBaseline = "middle"; ctx.textAlign = "center";
    const text = `Goal ${f.clock}'`;
    const w = ctx.measureText(text).width + 20;
    const tx = Math.min(this.lay.w - w / 2 - 4, Math.max(w / 2 + 4, x)), ty = Math.min(this.lay.h - 14, y + 30); // below the ring: the player's name tag sits above it
    ctx.fillStyle = INK; // a dark pill with white text
    ctx.beginPath(); ctx.roundRect(tx - w / 2, ty - 11, w, 22, 11); ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.fillText(text, tx, ty + 0.5);
    ctx.textAlign = "start";
    ctx.globalAlpha = 1;
  }

  /** Comet tail: the ball's recent positions, tapering and fading. */
  private comet(now: number, col: string): void {
    const ctx = this.ctx;
    while (this.sparks.length && now - this.sparks[0].at > COMET_MS) this.sparks.shift();
    const p = this.sparks;
    if (p.length < 2) return;
    ctx.lineCap = "round";
    for (let i = 1; i < p.length; i++) {
      const age = clamp01((now - p[i].at) / COMET_MS);
      const a = Math.pow(1 - age, 1.5), w = 1 + 5 * (1 - age);
      ctx.beginPath(); ctx.moveTo(this.px(p[i - 1].x), this.py(p[i - 1].y)); ctx.lineTo(this.px(p[i].x), this.py(p[i].y));
      ctx.globalAlpha = 0.6 * a; ctx.strokeStyle = "#ffffff"; ctx.lineWidth = w + 3; ctx.stroke(); // white halo
      ctx.globalAlpha = 0.85 * a; ctx.strokeStyle = col; ctx.lineWidth = w; ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  private drawBall(bx: number, by: number): void {
    const ctx = this.ctx;
    const r = 3.8 + this.lay.s * 2.4;
    const sh = ctx.createRadialGradient(bx + 2, by + 3.5, 0, bx + 2, by + 3.5, r * 1.9);
    sh.addColorStop(0, "rgba(10,40,25,0.32)"); sh.addColorStop(1, "rgba(10,40,25,0)");
    ctx.fillStyle = sh;
    ctx.beginPath(); ctx.ellipse(bx + 2, by + 3.5, r * 1.9, r * 1.2, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.beginPath(); ctx.arc(bx, by, r, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = INK; ctx.lineWidth = 1.8; // the dark outline is what keeps a white ball visible on white lines
    ctx.stroke();
  }
}
