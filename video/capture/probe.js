// Probe: load mock4, dump line timings per channel (clip time w), cuts, LEN, teaseEnd.
const { chromium } = require('/Users/vmt/.npm-global/lib/node_modules/@playwright/mcp/node_modules/playwright-core');
const EXE = '/Users/vmt/Library/Caches/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell';
(async () => {
  const b = await chromium.launch({ executablePath: EXE, args: ['--autoplay-policy=no-user-gesture-required'] });
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  const errs = []; p.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') errs.push(m.text()); }); p.on('pageerror', e => errs.push('PAGEERR ' + e.message));
  await p.goto('http://127.0.0.1:8812/mock4.html');
  await p.waitForFunction(() => window.__mock && window.__mock.D && window.__mock.D.LINES);
  const out = await p.evaluate(() => {
    const D = window.__mock.D, coms = window.__mock.coms;
    return { LEN: D.LEN, cuts: D.cuts, off: D.off, parts: D.parts, GOAL_FROM: D.GOAL_FROM, ATTACK_FROM: D.ATTACK_FROM, coms,
      lines: D.LINES.map(l => ({ m: l.m, kind: l.kind, gk: l.g.kind, w: +l.w.toFixed(3), ins: l.ins ? l.ins.kind : null,
        ch: Object.fromEntries(Object.keys(l.l).filter(k => l.l[k]).map(k => [k, [+(l.ws[k] ?? 0).toFixed(3), +(l.dur[k] || 0).toFixed(2), l.l[k], l.who[k] ? (l.who[k].name || l.who[k]) : null]])) })) };
  });
  console.log(JSON.stringify(out, null, 1));
  console.error('ERRS', errs);
  await b.close();
})();
