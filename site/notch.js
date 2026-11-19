// The notch island on the front page: a live, looping demo of the desktop dock. It runs the same
// three states as the apps (closed pill → ears with a read-out → open panel) with made-up numbers,
// so nothing real is shown. Hover or focus pins it open; Reduce Motion gets the open panel, still.
import { GLYPHS } from './glyphs.js?v=25';

const notch = document.querySelector('[data-notch]');
if (notch) {
  const ears = notch.querySelector('[data-ears]');
  const open = notch.querySelector('[data-open]');
  const still = matchMedia('(prefers-reduced-motion: reduce)');

  /** 5x7 pixel text as one SVG path, drawn in currentColor. */
  const px = (text, dot = 1.5, cls = '') => {
    const t = String(text).toUpperCase();
    const w = Math.max(t.length * 6 - 1, 1) * dot;
    let d = '';
    for (let i = 0; i < t.length; i++) {
      const rows = GLYPHS[t[i]];
      if (!rows) continue;
      for (let r = 0; r < 7; r++) for (let c = 0; c < 5; c++)
        if (rows[r] & (0x10 >> c)) d += `M${(i * 6 + c) * dot} ${r * dot}h${dot}v${dot}h-${dot}z`;
    }
    return `<svg class="pxt ${cls}" viewBox="0 0 ${w} ${7 * dot}" width="${w}" height="${7 * dot}" shape-rendering="crispEdges" aria-hidden="true"><path fill="currentColor" d="${d}"/></svg>`;
  };
  const bar = (frac, n, cls = '') => {
    const lit = Math.round(Math.min(Math.max(frac, 0), 1) * n);
    let h = '';
    for (let i = 0; i < n; i++) h += `<i${i < lit ? ' class="on"' : ''}></i>`;
    return `<span class="nseg n${n} ${cls}">${h}</span>`;
  };
  const pct = (v) => Math.round(v * 100) + '%';
  const rate = (b) => (b >= 1e6 ? (b / 1e6).toFixed(1) + 'M' : (b / 1e3).toFixed(0) + 'K');

  const t0 = performance.now();
  const sample = () => {
    const t = (performance.now() - t0) / 1000;
    return {
      cpu: 0.34 + 0.12 * Math.sin(t / 2.1) + 0.05 * Math.sin(t * 1.7),
      mem: 0.65 + 0.012 * Math.sin(t / 5),
      tmp: 49 + 4 * Math.sin(t / 3),
      net: 1.8e6 * (1 + 0.5 * Math.sin(t / 1.3)),
      dsk: 0.58,
      gpu: 0.12 + 0.08 * Math.sin(t / 1.9),
      up: 2.1e5 * (1 + 0.6 * Math.sin(t / 1.1)),
      swap: 0.57,
      load: 2.4 + 0.5 * Math.sin(t / 2.6),
      five: 0.34 + Math.min(t * 0.0004, 0.04),
    };
  };

  const render = () => {
    const s = sample();
    ears.innerHTML =
      `<span class="ear l"><b class="live"></b>${px(Math.round(s.cpu * 100), 1)}</span>` +
      `<span class="ear r">${px(pct(s.five), 1)}</span>`;
    if (notch.dataset.state !== 'open' && !still.matches) return;     // closed: only the ears are visible
    const col = (l, v, f, hot) => `<div class="stat ${hot ? 'hot' : ''}"><span class="c-dim">${px(l, 1)}</span>${px(v, 1.5)}${bar(f, 10)}</div>`;
    const lg = (b) => Math.log10(Math.max(b, 1)) / 8;
    open.innerHTML =
      `<div class="row head">${px('PULSE', 2, 'c-on')}<span class="c-dim">${px('HOVER OFF TO CLOSE', 1)}</span></div>` +
      `<hr>` +
      `<div class="stats">${col('CPU', pct(s.cpu), s.cpu)}${col('MEM', pct(s.mem), s.mem)}${col('GPU', pct(s.gpu), s.gpu)}` +
      `${col('TEMP', Math.round(s.tmp) + '°', (s.tmp - 30) / 70)}${col('DISK', pct(s.dsk), s.dsk)}</div>` +
      `<div class="stats">${col('DOWN', rate(s.net), lg(s.net))}${col('UP', rate(s.up), lg(s.up))}${col('SWAP', pct(s.swap), s.swap)}` +
      `${col('LOAD', s.load.toFixed(1), s.load / 12)}${col('BATT', '86%', 0.86)}</div>` +
      `<hr>` +
      `<div class="row claude"><div><span class="c-dim">${px('CLAUDE · 5H LIMIT', 1)}</span>` +
      `<div class="line">${bar(s.five, 14, 'wide')}${px(pct(s.five), 1, 'c-mid')}</div></div>` +
      `<div class="r c-mid">${px('VELOCITY 204K/H', 1)}<span class="c-dim">${px('EST. OUT 1H 48M · 62% CONF', 1)}</span></div></div>` +
      `<div class="row c-mid">${px('TODAY 3.2M', 1)}${px('WEEK 104.7M', 1)}${px('EST. $41.20', 1)}${px('1 LIVE', 1, 'c-on')}</div>` +
      `<div class="row foot"><span class="c-dim">${px('2 ACCOUNTS · 1 LIVE', 1)}</span><span class="c-mid">${px('OPEN DASHBOARD', 1)}</span></div>`;
  };

  const set = (state) => { notch.dataset.state = state; render(); };

  // the loop: closed → ears → open → closed; hover or focus pins it open
  let pinned = false, timer;
  const script = [['closed', 2200], ['peek', 2200], ['open', 6200]];
  let step = 0;
  const run = () => {
    if (pinned || still.matches) return;
    const [state, ms] = script[step % script.length];
    set(state);
    step++;
    timer = setTimeout(run, ms);
  };
  const pin = () => { pinned = true; clearTimeout(timer); set('open'); };
  const unpin = () => { pinned = false; clearTimeout(timer); timer = setTimeout(() => { step = 0; run(); }, 900); };
  notch.addEventListener('pointerenter', pin);
  notch.addEventListener('pointerleave', unpin);
  notch.addEventListener('focus', pin);
  notch.addEventListener('blur', unpin);
  addEventListener('keydown', (e) => { if (e.key === 'Escape' && pinned) { notch.blur(); } });

  setInterval(() => { if (notch.dataset.state !== 'closed' || still.matches) render(); }, 1000);

  if (still.matches) set('open');
  else { set('closed'); timer = setTimeout(() => { step = 1; run(); }, 900); }
}
