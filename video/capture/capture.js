// Deterministic 30 fps capture of ui/public/mock4.html (served on 127.0.0.1:8812).
// Usage: node capture.js <takeId> [<takeId> ...]   (see TAKES below)
// Each take: fresh page, virtual clock (virt.js), one screenshot per 1/30 s of page time, piped to ffmpeg.
// Output: video/shots/<id>.mp4 and <id>.json
const fs = require('fs'), path = require('path'), { spawn } = require('child_process');
const { chromium } = require('/Users/vmt/.npm-global/lib/node_modules/@playwright/mcp/node_modules/playwright-core');
const EXE = '/Users/vmt/Library/Caches/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell';
const URL0 = 'http://127.0.0.1:8812/mock4.html';
const OUT = '/Users/vmt/MicroSaaS/match-voice/video/shots';
const FPS = 30, DT = 1000 / FPS;
const DURS = JSON.parse(fs.readFileSync(path.join(__dirname, 'durations.json'), 'utf8'));
const VIRT = fs.readFileSync(path.join(__dirname, 'virt.js'), 'utf8');
// build-up lines (interception, switch, chest, long ball, first time) that carry known fact errors in ja and tr: never shown
const BUILDUP = [1189316, 1189569, 1189576, 1189697, 1189713];
const W = (w) => ({ w });   // an action at a page clip time instead of a frame

// frames: total frames; actions: [frame or {w}, js]; strip: [[channel, [moment ids]]] lines removed from the runtime data
const TAKES = {
  // en/expert from the idle start screen (2 s) through the end of the clip: S2 and S3 are cut from it
  M_enx: { com: 1, idle: 60, untilW: 47.5, actions: [] },
  // en/beginner, the same run: S5
  S5_en_beginner: { com: 0, idle: 60, untilW: 47.5, actions: [] },
  // S1 Japanese cold open: build-up lines removed, starts 4 s before the goal (30.37), through the score line start (38.97) plus 2.5 s
  S1_ja_goal: { com: 11, strip: [[11, BUILDUP]], startW: 26.4, untilW: 41.6, actions: [] },
  // S4 How mode on the goal, en/expert
  S4_how_goal_enx: { com: 1, how: true, startW: 26.4, untilW: 44.5, actions: [] },
  // S4b How mode, scene 1, es/expert (the story line has the real verifier catch: 1 rejected and rewritten)
  S4b_how_scene1_es: { com: 6, how: true, idle: 30, untilW: 16.6, actions: [] },
  // S6 goal call in three more languages, 1.2 s handle before (start just after the first-time fragment so no build-up subtitle shows)
  S6_de_goal: { com: 3, startW: 27.4, untilW: 35.4, actions: [] },
  S6_es_goal: { com: 6, startW: 27.4, untilW: 35.4, actions: [] },
  S6_tr_goal: { com: 10, strip: [[10, BUILDUP]], startW: 27.4, untilW: 35.4, actions: [] },
  // S7 start screen with the picker, untouched (ja default, as a judge sees it)
  S7a_start_screen: { com: 11, idleOnly: 8 * FPS, actions: [] },
  // S7b the picker in use on the start screen: one face after another
  S7b_picker_cycle: { com: 11, idleOnly: 10 * FPS, actions: [[45, 'm.setCom(1)'], [90, 'm.setCom(3)'], [135, 'm.setCom(6)'], [180, 'm.setCom(5)'], [225, 'm.setCom(11)']] },
  // S7c switching commentator during the goal: en/expert, the strip opens, Kim Berger (de) takes the pay-off, then Lucía Romero (es)
  S7c_switch_midgoal: { com: 1, startW: 29.6, untilW: 41.5, actions: [[W(32.6), 'm.openStrip()'], [W(34.2), 'm.setCom(3); m.closeStrip()'], [W(36.6), 'm.openStrip()'], [W(37.6), 'm.setCom(6); m.closeStrip()']] },
};

function enc(file) {
  const ff = spawn('/opt/homebrew/bin/ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', '-',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-r', String(FPS), '-movflags', '+faststart', file], { stdio: ['pipe', 'inherit', 'inherit'] });
  return ff;
}

async function runTake(browser, id, T) {
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errs = [];
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errs.push(m.type() + ': ' + m.text()); });
  page.on('pageerror', (e) => errs.push('pageerror: ' + e.message));
  page.on('requestfailed', (r) => errs.push('requestfailed: ' + r.url()));
  await page.addInitScript(`window.__CAP_DURS=${JSON.stringify(DURS)};\n${VIRT}`);
  await page.goto(URL0, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => window.__mock && window.__mock.D && window.__mock.D.LINES && !document.getElementById('play').disabled);
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => Promise.all([...document.images].map((i) => i.complete ? 0 : new Promise((r) => { i.onload = i.onerror = r; }))));
  await page.waitForTimeout(800);
  await page.evaluate(({ com, how, strip }) => {
    const m = window.__mock; m.setCom(com);
    if (how) m.setHow(true);
    (strip || []).forEach(([ch, ms]) => m.D.LINES.forEach((l) => { if (ms.includes(l.m)) delete l.l[ch]; }));
  }, { com: T.com, how: !!T.how, strip: T.strip || [] });
  await page.waitForTimeout(600);
  const cdp = await ctx.newCDPSession(page);
  await page.evaluate(() => window.__cap.enable());
  const file = path.join(OUT, id + '.mp4');
  const ff = enc(file);
  const samples = [];
  const acts = (T.actions || []).map(([a, js]) => ({ a, js, done: false }));
  const idle = T.idleOnly ? 0 : (T.idle || 0);
  let f = 0, lastW = null, settleNext = false;
  const t0 = Date.now();
  let frame0Epoch = null;
  while (true) {
    const pre = [];
    if (!T.idleOnly && f === idle) { pre.push(`m.start(${T.startW || 0})`); if (T.startW) settleNext = true; }
    for (const x of acts) {
      if (x.done) continue;
      if (typeof x.a === 'number' ? f === x.a : (lastW != null && lastW + DT / 1000 >= x.a.w - 1e-6)) { pre.push(x.js); x.done = true; }
    }
    const s = await page.evaluate(({ pre, dt, settle }) => {
      const m = window.__mock, C = window.__cap, $ = (i) => document.getElementById(i);
      C.advance(dt);
      for (const js of pre) (new Function('m', js))(m);
      C.step(dt);
      if (settle) C.settle();
      const cut = $('cut'), insc = $('insc'), bt = $('booth').title || '';
      return { w: m.w, sub: $('fsay').textContent, who: bt.split(',')[0], com: m.comId, sh: $('sh').textContent, sa: $('sa').textContent, clock: $('clock').textContent,
        how: document.body.classList.contains('how'), cut: cut.parentElement && cut.classList.contains('on') ? cut.textContent : '',
        ins: insc.classList.contains('on') ? insc.textContent : '', end: document.body.classList.contains('endon'), v: C.vnow, epoch: Date.now() };
    }, { pre, dt: DT, settle: settleNext && f === idle });
    if (f === 0) frame0Epoch = s.epoch;
    const shot = await cdp.send('Page.captureScreenshot', { format: 'png', optimizeForSpeed: true });
    const buf = Buffer.from(shot.data, 'base64');
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
    samples.push(Object.assign({ f }, s));
    lastW = s.w;
    f++;
    if (T.idleOnly ? f >= T.idleOnly : ((s.w != null && s.w >= T.untilW) || (s.end && samples.filter(x=>x.end).length >= 60))) break;
    if (f > 60 * FPS * 2) break;
  }
  ff.stdin.end();
  await new Promise((r) => ff.on('close', r));
  const realS = (Date.now() - t0) / 1000;
  const C = await page.evaluate(() => ({ log: window.__cap.log, v0: window.__cap.v0 }));
  const lines = await page.evaluate(() => window.__mock.D.LINES.map((l) => ({ m: l.m, kind: l.kind, gk: l.g.kind, l: l.l })));
  const coms = await page.evaluate(() => window.__mock.coms);
  await ctx.close();
  // audio: the virtual time of frame k's step is v0 + (k+1)*DT, so tS = (v - v0)/1000 - 1/FPS
  const audioEvents = C.log.filter((e) => e.virt).map((e) => ({ tS: +(((e.v - C.v0) / 1000) - 1 / FPS).toFixed(4), src: e.src, ev: e.ev, offsetS: e.offsetS != null ? +(+e.offsetS).toFixed(4) : null,
    volume: e.volume, target: e.target, tc: e.tc, dur: e.dur, text: e.text }));
  const preLog = C.log.filter((e) => !e.virt);
  const cues = cuesOf(samples, lines, coms);
  const meta = { id, fps: FPS, frames: samples.length, durationS: +(samples.length / FPS).toFixed(4), frame0Epoch, width: 1920, height: 1080,
    method: 'deterministic virtual clock (video/capture/virt.js), one PNG screenshot per 1/30 s of page time; audio stand-in logs on the same clock',
    capture: { realSeconds: +realS.toFixed(1), framesPerRealSecond: +(samples.length / realS).toFixed(2) },
    take: { com: T.com, how: !!T.how, startW: T.startW ?? 0, idleFrames: T.idleOnly || idle, untilW: T.untilW ?? null, removedLines: T.strip || [], actions: (T.actions || []).map(([a, js]) => ({ at: a, js })) },
    bed: { file: 'audio/stadium-bed.mp3', lowpassHz: 900, note: 'Web Audio: buffer starts at offset 40 s, loops, through a 900 Hz low-pass; gain events are setTargetAtTime(target, timeConstant tc)' },
    audioEvents, wSamples: samples.map((s) => ({ f: s.f, tS: +(s.f / FPS).toFixed(4), w: s.w == null ? null : +s.w.toFixed(4) })),
    subtitleCues: cues, frameState: samples.map((s) => ({ f: s.f, com: s.com, who: s.who, score: s.sh + '-' + s.sa, clock: s.clock, cut: s.cut, ins: s.ins, how: s.how, end: s.end })),
    preCaptureAudio: preLog, consoleErrors: errs };
  fs.writeFileSync(path.join(OUT, id + '.json'), JSON.stringify(meta, null, 1));
  console.log(`${id}: ${samples.length} frames, ${realS.toFixed(1)} s real, errors ${errs.length}`);
  return meta;
}

function cuesOf(samples, lines, coms) {
  const cues = []; let cur = null;
  const langOf = (id) => (coms.find((c) => c.id === id) || {}).lang;
  for (const s of samples) {
    const text = (s.sub || '').trim();
    if (cur && (text !== cur.text || s.who !== cur.speaker && text)) { cur.endS = +(s.f / FPS).toFixed(4); cues.push(cur); cur = null; }
    if (!cur && text) {
      const ln = lines.find((l) => l.l[s.com] === text) || lines.find((l) => Object.values(l.l).includes(text));
      cur = { startS: +(s.f / FPS).toFixed(4), endS: null, speaker: s.who, lang: langOf(s.com), channel: s.com, text, moment: ln ? ln.m : null, kind: ln ? ln.gk : null,
        en_expert: ln && ln.l[1] && langOf(s.com) !== 'en' ? ln.l[1] : undefined };
    }
  }
  if (cur) { cur.endS = +(samples.length / FPS).toFixed(4); cues.push(cur); }
  return cues;
}

(async () => {
  const ids = process.argv.slice(2);
  const browser = await chromium.launch({ executablePath: EXE, args: ['--autoplay-policy=no-user-gesture-required', '--hide-scrollbars', '--force-color-profile=srgb', '--disable-renderer-backgrounding', '--disable-background-timer-throttling'] });
  for (const id of ids) { if (!TAKES[id]) { console.error('unknown take', id); continue; } await runTake(browser, id, TAKES[id]); }
  await browser.close();
})();
