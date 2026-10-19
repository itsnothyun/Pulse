// Pulse marketing site — the widget is re-drawn here from the app's own font and layout,
// fed by one synthetic feed so every copy on the page agrees.
import { GLYPHS } from './glyphs.js';

const INK = { bg: '#090909', on: '#F2F2ED', mid: '#B3B3AD', dim: '#757573', off: '#262626', line: '#303030' };
const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const alpha = (hex, a) => `rgba(${rgb(hex).join(',')},${Math.max(0, Math.min(1, a)).toFixed(3)})`;
const motionQuery = matchMedia('(prefers-reduced-motion: reduce)');
const still = () => motionQuery.matches;
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));

/* ---------------------------------------------------------------- pixel type */

const textWidth = (s, scale) => Math.max(s.length * 6 - 1, 0) * scale;

function drawText(ctx, text, x, y, scale, color) {
  const dot = scale >= 3 ? scale - 0.75 : scale;
  const t = text.toUpperCase();
  ctx.fillStyle = color;
  for (let i = 0; i < t.length; i++) {
    const rows = GLYPHS[t[i]];
    if (!rows) continue;
    for (let r = 0; r < 7; r++)
      for (let c = 0; c < 5; c++)
        if (rows[r] & (0x10 >> c)) ctx.fillRect(x + (i * 6 + c) * scale, y + r * scale, dot, dot);
  }
}
const drawTextR = (ctx, text, right, y, scale, color) => drawText(ctx, text, right - textWidth(text, scale), y, scale, color);

/** Pixel headings: <span data-pixel="LINE ONE|LINE TWO"> becomes crisp SVG; the real text stays for assistive tech. */
function pixelSVG(line, dot, gap, assemble) {
  const cols = Math.max(line.length * 6 - 1, 1);
  const w = cols * dot, h = 7 * dot, s = dot - gap;
  let body = '';
  const t = line.toUpperCase();
  for (let i = 0; i < t.length; i++) {
    const rows = GLYPHS[t[i]];
    if (!rows) continue;
    for (let r = 0; r < 7; r++)
      for (let c = 0; c < 5; c++)
        if (rows[r] & (0x10 >> c)) {
          const x = (i * 6 + c) * dot, y = r * dot;
          body += assemble
            ? `<rect x="${x}" y="${y}" width="${s}" height="${s}" style="animation-delay:${Math.round(Math.random() * 520 + c * 18 + i * 14)}ms"/>`
            : `M${x} ${y}h${s}v${s}h-${s}z`;
        }
  }
  const inner = assemble ? body : `<path d="${body}"/>`;
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" shape-rendering="crispEdges" fill="currentColor" aria-hidden="true" focusable="false">${inner}</svg>`;
}

function mountPixel(el) {
  const lines = el.dataset.pixel.split('|');
  const cs = getComputedStyle(el);
  const want = parseFloat(cs.getPropertyValue('--dot')) || 4;
  const box = el.parentElement.getBoundingClientRect().width || 320;
  const cols = Math.max(...lines.map((l) => l.length * 6 - 1));
  const dot = Math.max(1.5, Math.min(want, Math.floor((box / cols) * 4) / 4));
  const gap = dot >= 6 ? Math.round(dot * 0.12 * 4) / 4 : 0;
  const assemble = el.hasAttribute('data-assemble') && !el.dataset.done && !still();
  el.innerHTML = lines.map((l) => `<span class="px-line">${pixelSVG(l, dot, gap, assemble)}</span>`).join('');
  if (assemble) { el.classList.add('assembling'); el.dataset.done = '1'; }
}

/* ---------------------------------------------------------------- formatting */

const F = {
  pct: (v) => `${Math.round(v * 100)}%`,
  gib: (b) => (b / 1073741824).toFixed(1),
  size: (b) => (b >= 1e12 ? (b / 1e12).toFixed(1) + 'T' : b >= 1e9 ? (b / 1e9).toFixed(0) + 'G' : (b / 1e6).toFixed(0) + 'M'),
  rate: (b) => (b >= 1e9 ? (b / 1e9).toFixed(1) + 'G' : b >= 1e6 ? (b / 1e6).toFixed(1) + 'M' : b >= 1e3 ? (b / 1e3).toFixed(0) + 'K' : b.toFixed(0) + 'B'),
  tok: (v) => (v >= 1e9 ? (v / 1e9).toFixed(2) + 'B' : v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v >= 1e3 ? (v / 1e3).toFixed(0) + 'K' : v.toFixed(0)),
};

/* ---------------------------------------------------------------- synthetic feed */

class Feed {
  constructor() {
    this.todayIndex = 3;                            // synthetic: always Thursday 09:41, like the desktops
    this.s = {
      cpu: 0.3, cores: [0.5, 0.4, 0.35, 0.3, 0.2, 0.15, 0.1, 0.08], mem: 0.64, memTotal: 16 * 1073741824,
      diskUsed: 287e9, diskTotal: 494e9, temp: 47, peak: 55, gpu: 0.2, netIn: 1.2e6, netOut: 180e3,
      swapUsed: 1.2e9, swapTotal: 2.1e9, commitUsed: 14.2e9, commitTotal: 24e9, procs: 241, threads: 3120,
      battery: 82, load: 2.4, tick: false, clock: '09:41',
      claude: { week: 0, today: 0, five: 31.9e6, output: 2.41e6, input: 9.8e6, cached: 0, sessions: 9, live: 1, calls: 3184, days: [0, 0, 0, 0, 0, 0, 0] },
    };
    const base = [88e6, 102e6, 164e6, 121e6, 96e6, 41e6, 22e6];
    const c = this.s.claude;
    for (let i = 0; i < 7; i++) c.days[i] = i < this.todayIndex ? base[i] : i === this.todayIndex ? 58.3e6 : 0;
    this.recount();
    this.hist = { cpu: [], mem: [], dsk: [], tmp: [], gpu: [] };
    this.target = 0.3;
    // seed forty seconds of shaped history so every sparkline starts as a trend, not a flat line
    for (let i = 0; i < 40; i++) {
      const wave = (b, a, f = 4) => clamp(b + a * Math.sin(i / f) + (Math.random() - 0.5) * a * 0.8);
      this.push('cpu', wave(0.32, 0.2)); this.push('mem', wave(0.63, 0.035, 6)); this.push('dsk', this.s.diskUsed / this.s.diskTotal);
      this.push('tmp', wave(0.24, 0.08, 5)); this.push('gpu', wave(0.22, 0.15, 3));
    }
    this.subs = new Set();
    this.step();
    setInterval(() => { this.step(); this.subs.forEach((f) => f()); }, 1000);
  }
  recount() {
    const c = this.s.claude;
    c.week = c.days.reduce((a, b) => a + b, 0);
    c.today = c.days[this.todayIndex];
    c.cached = c.week - c.input - c.output;
  }
  push(k, v) { const h = this.hist[k]; h.push(clamp(v)); if (h.length > 40) h.shift(); }
  step(seed = false) {
    const s = this.s;
    if (Math.random() < 0.12) this.target = Math.random() < 0.25 ? 0.55 + Math.random() * 0.3 : 0.12 + Math.random() * 0.25;
    s.cpu = clamp(s.cpu + (this.target - s.cpu) * 0.35 + (Math.random() - 0.5) * 0.06, 0.03, 0.97);
    s.cores = s.cores.map((_, i) => clamp(s.cpu * (1.6 - i * 0.17) + (Math.random() - 0.5) * 0.18, 0.02, 1));
    s.mem = clamp(s.mem + (Math.random() - 0.5) * 0.008 + (s.cpu - 0.35) * 0.004, 0.55, 0.78);
    s.temp = s.temp + (36 + s.cpu * 38 - s.temp) * 0.18 + (Math.random() - 0.5) * 0.6;
    s.peak = Math.max(s.peak, s.temp);
    s.gpu = clamp(s.gpu + (Math.random() - 0.5) * 0.12, 0.04, 0.8);
    s.netIn = Math.random() < 0.2 ? 2e6 + Math.random() * 9e6 : Math.max(8e3, s.netIn * (0.3 + Math.random() * 0.5));
    s.netOut = s.netIn * (0.06 + Math.random() * 0.12);
    s.load = 0.8 + s.cpu * 6;
    s.procs = 236 + Math.round(Math.random() * 10);
    if (!seed) {
      s.tick = !s.tick;
      s.clock = '09:41';
      if (Math.random() < 0.35) {                    // a live session spends a little
        const spent = 40e3 + Math.random() * 260e3;
        s.claude.days[this.todayIndex] += spent; s.claude.five += spent; s.claude.output += spent * 0.012;
        s.claude.calls += 1; this.recount();
      }
      if (Math.random() < 0.02) s.battery = Math.min(100, s.battery + 1);
    }
    this.push('cpu', s.cpu); this.push('mem', s.mem); this.push('dsk', s.diskUsed / s.diskTotal);
    this.push('tmp', (s.temp - 30) / 70); this.push('gpu', s.gpu);
  }
  on(f) { this.subs.add(f); }
}

/* ---------------------------------------------------------------- widget */

const W = 320, PAD = 18, INNER = W - PAD * 2, MINI_H = 29, MINI_VAL = 4 * 6 * 1.5 - 1.5;
const MINI_W = 12 + 4 + 3 * 12 + 3 * (textWidth('CPU', 1) + 5 + MINI_VAL) + 12;
const SIZES = ['full', 'compact', 'mini'];
const widgets = new Set();

class Widget {
  constructor(canvas, feed, { platform = 'mac', size = 'full', scale = 1, interactive = false } = {}) {
    Object.assign(this, { canvas, feed, platform, size, scale, interactive });
    this.ctx = canvas.getContext('2d');
    this.tweens = new Map();
    this.regions = {};
    this.highlight = null;
    this.visible = true;
    this.lastLoop = 0;
    feed.on(() => this.draw());
    widgets.add(this);
    new IntersectionObserver(([e]) => { this.visible = e.isIntersecting; }).observe(canvas);
    this.draw();
  }

  get width() { return this.size === 'mini' ? MINI_W : W; }
  get radius() { return this.size === 'mini' ? 10 : 14; }
  get headerBottom() { return this.size === 'mini' ? MINI_H : PAD + 20; }
  get hot() { return this.feed.s.temp >= 85; }

  setSize(size) { this.size = size; this.draw(); this.canvas.dispatchEvent(new CustomEvent('pulse:size', { bubbles: true, detail: size })); }
  setScale(scale) { this.scale = scale; this.draw(); }

  /* -- tweened bars, only when a segment changes */
  tween(key, target, segments, now) {
    const seg = (v) => Math.floor(clamp(v) * segments * 2);
    let t = this.tweens.get(key);
    const ev = (t) => { const p = 1 - Math.pow(1 - clamp((now - t.start) / 450), 3); return t.from + (t.to - t.from) * p; };
    if (!t) { t = { from: target, to: target, start: -1e9 }; this.tweens.set(key, t); }
    if (target !== t.to) {
      const cur = ev(t);
      t = seg(cur) !== seg(target) && !still() ? { from: cur, to: target, start: now } : { from: target, to: target, start: -1e9 };
      this.tweens.set(key, t);
    }
    if (now - t.start < 450) this.animating = true;
    return ev(t);
  }

  /* -- primitives (dc null = measure only) */
  rect(dc, c, x, y, w, h) { if (dc && w > 0 && h > 0) { dc.fillStyle = c; dc.fillRect(x, y, w, h); } }
  text(dc, t, x, y, s, c) { if (dc) drawText(dc, t, x, y, s, c); }
  textR(dc, t, r, y, s, c) { if (dc) drawTextR(dc, t, r, y, s, c); }
  rule(dc, y, gap = 14) {
    y += gap;
    if (dc) { dc.fillStyle = INK.line; for (let i = 0; i < INNER; i += 4) dc.fillRect(PAD + i, y, 2, 1); }
    return y + 1 + gap;
  }
  bar(dc, key, x, y, w, h, value, segments = 28, blink = false, now = 0) {
    if (!dc) return;
    const v = this.tween(key, clamp(value), segments, now);
    const gap = 2, sw = Math.floor((w - gap * (segments - 1)) / segments);
    const exact = v * segments, lit = Math.floor(exact), partial = exact - lit;
    for (let i = 0; i < segments; i++) {
      let c = i < lit ? INK.on : INK.off;
      if (i === lit && partial > 0.15) c = INK.dim;
      if (blink && i === Math.max(lit - 1, 0)) c = INK.off;
      this.rect(dc, c, x + i * (sw + gap), y, sw, h);
    }
  }
  spark(dc, x, y, data, columns = 18, height = 18) {
    if (!dc) return;
    const cw = 2, gap = 1, px = 2, n = Math.min(columns, data.length), start = x + (columns - n) * (cw + gap), levels = height / px;
    for (let i = 0; i < columns; i++) this.rect(dc, INK.off, x + i * (cw + gap), y + height - 1, cw, 1);
    for (let i = 0; i < n; i++) {
      const v = data[data.length - n + i], hgt = Math.max(1, Math.round(clamp(v) * levels)), age = (i + 1) / n, cx = start + i * (cw + gap);
      for (let l = 0; l < hgt; l++)
        this.rect(dc, l === hgt - 1 ? alpha(INK.on, 0.35 + 0.65 * age) : alpha(INK.dim, 0.12 + 0.3 * age), cx, y + height - (l + 1) * px, cw, px - 0.5);
    }
  }
  cores(dc, x, y, w, cores) {
    if (!dc) return;
    const gap = 4, px = 2, lg = 1, levels = 5, cw = Math.floor((w - gap * (cores.length - 1)) / cores.length);
    cores.forEach((v, i) => {
      const lit = Math.ceil(clamp(v) * levels);
      for (let l = 0; l < levels; l++) this.rect(dc, l < lit ? INK.on : INK.off, x + i * (cw + gap), y + 15 - (l + 1) * (px + lg), cw, px);
    });
  }
  week(dc, x, y, w, days, today, chartH = 24, levels = 8, labelScale = 1) {
    if (!dc) return;
    const gap = Math.max(4, w * 0.035), px = (chartH / levels) * (2 / 3), lg = (chartH / levels) / 3;
    const cw = Math.floor((w - gap * 6) / 7), peak = Math.max(1, ...days);
    for (let i = 0; i < 7; i++) {
      const lit = days[i] > 0 ? Math.max(1, Math.ceil((days[i] / peak) * levels)) : 0;
      for (let l = 0; l < levels; l++) {
        const c = l < lit ? (i === today ? INK.on : alpha(INK.mid, 0.75)) : i > today ? alpha(INK.off, 0.5) : INK.off;
        this.rect(dc, c, x + i * (cw + gap), y + chartH - (l + 1) * (px + lg), cw, px);
      }
      this.text(dc, 'MTWTFSS'[i], x + i * (cw + gap) + (cw - 5 * labelScale) / 2, y + chartH + 4 * labelScale, labelScale, i === today ? INK.on : INK.dim);
    }
  }

  /* -- layout */
  header(dc, y) {
    this.text(dc, 'PULSE', PAD, y, 2, INK.on);
    this.scannerPos = [PAD + textWidth('PULSE', 2) + 8, y + 5.5];
    const toggle = this.size === 'full' ? '-' : '+';
    this.textR(dc, toggle, W - PAD, y + 1.75, 1.5, INK.dim);
    this.textR(dc, this.feed.s.clock, W - PAD - textWidth(toggle, 1.5) - 8, y + 1.75, 1.5, INK.mid);
    return y + 14;
  }
  heroRow(dc, y, label, detail, value, hist) {
    this.text(dc, label, PAD, y, 2, INK.on);
    this.text(dc, detail, PAD, y + 19, 1, INK.dim);
    this.textR(dc, value, W - PAD, y + 2.5, 3, INK.on);
    this.spark(dc, W - PAD - 70 - 10 - 53, y + 4, hist);
    return y + 34;
  }
  tile(dc, x, y, w, label, value, sub, bar, key, now) {
    if (dc) { dc.strokeStyle = INK.line; dc.lineWidth = 1; dc.strokeRect(x + 0.5, y + 0.5, w - 1, 61); }
    this.text(dc, label, x + 10, y + 10, 1, INK.dim);
    this.text(dc, value, x + 10, y + 24, 2, INK.on);
    if (bar != null) this.bar(dc, key, x + 10, y + 45, Math.min(w - 20, 112), 5, bar, 16, false, now);
    else if (sub) this.text(dc, sub, x + 10, y + 45, 1, INK.mid);
  }
  region(name, y0, y1) { this.regions[name] = { x: PAD - 7, y: y0 - 7, w: INNER + 14, h: y1 - y0 + 14 }; }

  full(dc, now) {
    const s = this.feed.s, h = this.feed.hist, mac = this.platform === 'mac';
    let y = this.header(dc, PAD);
    y = this.rule(dc, y);
    const t = s.temp, state = t < 50 ? 'COOL' : t < 70 ? 'WARM' : t < 85 ? 'HOT' : 'CRITICAL';
    let y0 = y;
    y = this.heroRow(dc, y, 'CPU', mac ? `8 CORES · LOAD ${s.load.toFixed(1)}` : `8 CORES · ${s.procs} PROCS`, F.pct(s.cpu), h.cpu);
    this.cores(dc, PAD, y, INNER, s.cores); y += 15; this.region('cpu', y0, y);
    y = this.rule(dc, y); y0 = y;
    y = this.heroRow(dc, y, 'MEM', `${F.gib(s.mem * s.memTotal)} / ${F.gib(s.memTotal)} GB`, F.pct(s.mem), h.mem);
    this.bar(dc, 'mem', PAD, y, INNER, 8, s.mem, 28, false, now); y += 8; this.region('mem', y0, y);
    y = this.rule(dc, y); y0 = y;
    y = this.heroRow(dc, y, 'TMP', `${state} · PEAK ${Math.round(s.peak)}°`, `${Math.round(t)}°`, h.tmp);
    this.bar(dc, 'tmp', PAD, y, INNER, 8, (t - 30) / 70, 28, this.hot && s.tick, now); y += 8; this.region('tmp', y0, y);
    y = this.rule(dc, y); y0 = y;
    const free = F.size(s.diskTotal - s.diskUsed), total = F.size(s.diskTotal);
    y = this.heroRow(dc, y, 'DSK', mac ? `${free} FREE OF ${total}` : `C: ${free} FREE OF ${total}`, F.pct(s.diskUsed / s.diskTotal), h.dsk);
    this.bar(dc, 'dsk', PAD, y, INNER, 8, s.diskUsed / s.diskTotal, 28, false, now); y += 8; this.region('dsk', y0, y);
    y += 22;
    const tw = (INNER - 8) / 2, x2 = PAD + tw + 8;
    this.tile(dc, PAD, y, tw, 'GPU', F.pct(s.gpu), null, s.gpu, 'gpu', now);
    this.tile(dc, x2, y, tw, 'NETWORK', `↓${F.rate(s.netIn)}/S`, `↑${F.rate(s.netOut)}/S`, null, 'net', now);
    this.regions.gpu = { x: PAD - 4, y: y - 4, w: tw + 8, h: 70 };
    this.regions.net = { x: x2 - 4, y: y - 4, w: tw + 8, h: 70 };
    y += 70;
    if (mac) this.tile(dc, PAD, y, tw, 'SWAP', F.size(s.swapUsed), `OF ${F.size(s.swapTotal)}`, null, 'swap', now);
    else this.tile(dc, PAD, y, tw, 'COMMIT', F.size(s.commitUsed), `OF ${F.size(s.commitTotal)}`, null, 'swap', now);
    this.tile(dc, x2, y, tw, 'POWER', `${s.battery}%`, s.battery < 100 ? '⚡ CHARGING' : 'AC POWER', null, 'pwr', now);
    this.regions.swap = { x: PAD - 4, y: y - 4, w: tw + 8, h: 70 };
    this.regions.pwr = { x: x2 - 4, y: y - 4, w: tw + 8, h: 70 };
    y += 62;
    y = this.rule(dc, y); y0 = y;
    y = this.claude(dc, y); this.region('claude', y0, y);
    y = this.rule(dc, y);
    this.text(dc, mac ? 'THERMAL NOMINAL' : `${s.threads} THREADS`, PAD, y, 1, INK.dim);
    this.textR(dc, 'UP 2D 4H', W - PAD, y, 1, INK.dim);
    return y + 7 + PAD;
  }
  claude(dc, y) {
    const c = this.feed.s.claude;
    this.text(dc, 'CLAUDE CODE', PAD, y, 2, INK.on);
    const live = `${c.live} LIVE`;
    this.textR(dc, live, W - PAD, y + 3.5, 1, INK.mid);
    this.pipPos = [W - PAD - textWidth(live, 1) - 10, y + 5];
    y += 26;
    this.text(dc, F.tok(c.week), PAD, y, 3, INK.on);
    this.text(dc, 'TOKENS THIS WEEK', PAD, y + 28, 1, INK.dim);
    this.week(dc, W - PAD - 112, y, 112, c.days, this.feed.todayIndex);
    y += 47;
    const cw = (INNER - 24) / 4;
    [['TODAY', F.tok(c.today)], ['LAST 5H', F.tok(c.five)], ['OUTPUT', F.tok(c.output)], ['SESSIONS', String(c.sessions)]].forEach(([l, v], i) => {
      this.text(dc, l, PAD + i * (cw + 8), y, 1, INK.dim);
      this.text(dc, v, PAD + i * (cw + 8), y + 12, 1.5, INK.on);
    });
    y += 35;
    this.text(dc, `IN ${F.tok(c.input)} · CACHED ${F.tok(c.cached)}`, PAD, y, 1, INK.dim);
    this.textR(dc, `${c.calls} CALLS`, W - PAD, y, 1, INK.dim);
    return y + 7;
  }
  compact(dc, now) {
    const s = this.feed.s;
    let y = this.header(dc, PAD);
    y = this.rule(dc, y, 12);
    const items = [['CPU', s.cpu, F.pct(s.cpu)], ['MEM', s.mem, F.pct(s.mem)], ['TMP', (s.temp - 30) / 70, `${Math.round(s.temp)}°`], ['DSK', s.diskUsed / s.diskTotal, F.pct(s.diskUsed / s.diskTotal)]];
    const cw = (INNER - 36) / 4;
    items.forEach(([l, f, v], i) => {
      const x = PAD + i * (cw + 12);
      this.text(dc, l, x, y, 1, INK.dim);
      this.text(dc, v, x, y + 13, 2, INK.on);
      this.bar(dc, 'c-' + l, x, y + 33, cw, 4, f, 8, l === 'TMP' && this.hot && s.tick, now);
    });
    y = this.rule(dc, y + 37, 12);
    this.pipPos = [PAD, y + 1.5];
    this.text(dc, `CLAUDE ${F.tok(s.claude.week)} WK`, PAD + 10, y, 1, INK.mid);
    this.textR(dc, `TODAY ${F.tok(s.claude.today)}`, W - PAD, y, 1, INK.dim);
    return y + 7 + PAD;
  }
  mini(dc) {
    const s = this.feed.s;
    this.scannerPos = null; this.pipPos = null;
    let x = 12;
    const y = (MINI_H - 10.5) / 2;
    this.rect(dc, alpha(INK.on, 0.85), x, (MINI_H - 4) / 2, 4, 4);
    x += 16;
    [['CPU', F.pct(s.cpu), false], ['MEM', F.pct(s.mem), false], ['TMP', `${Math.round(s.temp)}°`, this.hot]].forEach(([l, v, b]) => {
      this.text(dc, l, x, y + 1.75, 1, INK.dim);
      x += textWidth(l, 1) + 5;
      this.textR(dc, v, x + MINI_VAL, y, 1.5, b && s.tick ? INK.off : INK.on);
      x += MINI_VAL + 12;
    });
    return MINI_H;
  }
  body(dc, now) { return this.size === 'mini' ? this.mini(dc) : this.size === 'compact' ? this.compact(dc, now) : this.full(dc, now); }

  /* -- render */
  draw(now = performance.now()) {
    this.animating = false;
    const h = this.body(null, now), w = this.width, sc = this.scale, dpr = Math.min(window.devicePixelRatio || 1, 3);
    const cw = Math.round(w * sc), ch = Math.round(h * sc);
    if (this.canvas.width !== Math.round(cw * dpr) || this.canvas.height !== Math.round(ch * dpr)) {
      this.canvas.width = Math.round(cw * dpr); this.canvas.height = Math.round(ch * dpr);
      this.canvas.style.width = cw + 'px'; this.canvas.style.height = ch + 'px';
    }
    const dc = this.ctx;
    dc.setTransform(dpr * sc, 0, 0, dpr * sc, 0, 0);
    dc.clearRect(0, 0, w, h);
    dc.save();
    dc.beginPath(); dc.roundRect(0, 0, w, h, this.radius); dc.clip();
    dc.fillStyle = INK.bg; dc.fillRect(0, 0, w, h);
    dc.fillStyle = 'rgba(242,242,237,0.02)';
    for (let y = 0; y < h; y += 3) dc.fillRect(0, y, w, 1);
    this.body(dc, now);
    this.loops(dc, w, h, now);
    if (this.highlight && this.regions[this.highlight] && this.size === 'full') {
      const r = this.regions[this.highlight];
      dc.fillStyle = 'rgba(9,9,9,0.66)';
      dc.beginPath(); dc.rect(0, 0, w, h); dc.rect(r.x, r.y, r.w, r.h); dc.fill('evenodd');
      dc.fillStyle = INK.on;
      const L = 6;
      [[r.x, r.y, 1, 1], [r.x + r.w, r.y, -1, 1], [r.x, r.y + r.h, 1, -1], [r.x + r.w, r.y + r.h, -1, -1]].forEach(([x, y, dx, dy]) => {
        dc.fillRect(dx > 0 ? x : x - L, dy > 0 ? y : y - 1, L, 1);
        dc.fillRect(dx > 0 ? x : x - 1, dy > 0 ? y : y - L, 1, L);
      });
    }
    dc.restore();
    dc.strokeStyle = 'rgba(242,242,237,0.16)'; dc.lineWidth = 1;
    dc.beginPath(); dc.roundRect(0.5, 0.5, w - 1, h - 1, this.radius); dc.stroke();
    this.height = h;
  }

  /* the app's subtle loops: header scanner, breathing live pixel, slow CRT sweep (none in mini) */
  loops(dc, w, h, now) {
    if (this.size === 'mini') return;
    const t = still() ? 0 : now / 1000;
    if (this.scannerPos) {
      const [sx, sy] = this.scannerPos, beat = this.hot ? 0.07 : 0.16;
      const path = [0, 1, 2, 3, 4, 5, 6, 7, 6, 5, 4, 3, 2, 1];
      const step = Math.floor(t / beat);
      for (let i = 0; i < 8; i++) this.rect(dc, alpha(INK.on, 0.12), sx + i * 5, sy, 3, 3);
      [[2, 0.25], [1, 0.5], [0, 0.9]].forEach(([lag, a]) => {
        const p = path[((step - lag) % path.length + path.length) % path.length];
        this.rect(dc, alpha(INK.on, a), sx + p * 5, sy, 3, 3);
      });
    }
    if (this.pipPos) {
      const a = still() ? 0.85 : 0.3 + 0.7 * (Math.sin(t * 2.4) + 1) / 2;
      this.rect(dc, alpha(INK.on, a), this.pipPos[0], this.pipPos[1], 4, 4);
    }
    if (!still()) {
      const p = (t % 9) / 9, bh = 80, y = p * (h + bh) - bh;
      const g = dc.createLinearGradient(0, y, 0, y + bh);
      g.addColorStop(0, 'rgba(255,255,255,0)'); g.addColorStop(0.5, 'rgba(255,255,255,0.04)'); g.addColorStop(1, 'rgba(255,255,255,0)');
      dc.fillStyle = g; dc.fillRect(0, y, w, bh);
    }
  }
}

/* one loop for every widget: 12 fps for the ambient loops, full rate while a bar tweens */
function frame(now) {
  for (const w of widgets) {
    if (!w.visible) continue;
    const ambient = !still() && w.size !== 'mini' && now - w.lastLoop > 83;
    if (w.animating || ambient) { w.draw(now); w.lastLoop = now; }
  }
  requestAnimationFrame(frame);
}

/* ---------------------------------------------------------------- page wiring */

const feed = new Feed();

function fitScale(el, natural, max = 1) {
  const avail = el.getBoundingClientRect().width;
  return Math.min(max, avail / natural);
}

function setupDesktops() {
  const desks = [...document.querySelectorAll('[data-desktop]')];
  const ws = desks.map((d) => new Widget(d.querySelector('canvas'), feed, { platform: d.dataset.desktop, size: 'compact' }));
  const resize = () => desks.forEach((d, i) => ws[i].setScale(fitScale(d.querySelector('.desk-slot'), W, 1)));
  resize();
  addEventListener('resize', resize);

  // phones: one desktop at a time
  const tabs = [...document.querySelectorAll('[data-os-tab]')];
  const select = (os) => {
    tabs.forEach((t) => t.setAttribute('aria-selected', String(t.dataset.osTab === os)));
    desks.forEach((d) => d.classList.toggle('is-active', d.dataset.desktop === os));
    resize();
  };
  tabs.forEach((t) => t.addEventListener('click', () => select(t.dataset.osTab)));
  tabs.forEach((t, i) => t.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const n = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    n.focus(); select(n.dataset.osTab);
  }));
  const isWin = /Windows/i.test(navigator.userAgent);
  select(isWin ? 'win' : 'mac');
}

function setupVitals() {
  const holder = document.querySelector('[data-vitals-widget]');
  if (!holder) return;
  const w = new Widget(holder.querySelector('canvas'), feed, { platform: 'mac', size: 'full' });
  const resize = () => w.setScale(fitScale(holder, W, 1.25));
  resize();
  addEventListener('resize', resize);
  const rows = [...document.querySelectorAll('[data-metric]')];
  const set = (m) => { w.highlight = m; w.draw(); rows.forEach((r) => r.classList.toggle('is-lit', r.dataset.metric === m)); };
  rows.forEach((r) => {
    r.addEventListener('mouseenter', () => set(r.dataset.metric));
    r.addEventListener('focusin', () => set(r.dataset.metric));
  });
  document.querySelector('.metric-list')?.addEventListener('mouseleave', () => set(null));
  document.querySelector('.metric-list')?.addEventListener('focusout', (e) => { if (!e.currentTarget.contains(e.relatedTarget)) set(null); });
  document.querySelectorAll('[data-vitals-os]').forEach((b) => b.addEventListener('click', () => {
    w.platform = b.dataset.vitalsOs; w.draw();
    document.querySelectorAll('[data-vitals-os]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    document.querySelectorAll('[data-src]').forEach((el) => { el.hidden = el.dataset.src !== w.platform; });
  }));
}

function setupSizes() {
  const stage = document.querySelector('[data-stage]');
  if (!stage) return;
  const holder = stage.querySelector('.stage-widget');
  const canvas = holder.querySelector('canvas');
  const w = new Widget(canvas, feed, { platform: /Windows/i.test(navigator.userAgent) ? 'win' : 'mac', size: 'full', interactive: true });
  const segs = [...document.querySelectorAll('[data-size]')];
  const status = document.querySelector('[data-size-status]');
  const menu = document.querySelector('[data-menu]');
  const relaunch = document.querySelector('[data-relaunch]');
  let pos = { x: 0, y: 0 };

  const fit = () => {
    w.setScale(1);
    w.setScale(Math.min(1, (stage.clientWidth - 32) / w.width, (stage.clientHeight - 32) / w.height));
    keepInside();
  };
  const keepInside = () => {
    const maxX = Math.max(0, stage.clientWidth - canvas.offsetWidth - 16), maxY = Math.max(0, stage.clientHeight - canvas.offsetHeight - 16);
    pos.x = clamp(pos.x, 0, maxX); pos.y = clamp(pos.y, 0, maxY);
    holder.style.transform = `translate(${pos.x}px, ${pos.y}px)`;
  };
  const place = () => { pos = { x: (stage.clientWidth - canvas.offsetWidth) / 2, y: (stage.clientHeight - canvas.offsetHeight) / 2 }; keepInside(); };
  const setSize = (s) => {
    const right = pos.x + canvas.offsetWidth;
    w.setSize(s); fit();
    pos.x = right - canvas.offsetWidth; keepInside();         // like the app: the right edge stays put
    segs.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.size === s)));
    menu.querySelectorAll('[data-menu-size]').forEach((m) => m.setAttribute('aria-checked', String(m.dataset.menuSize === s)));
    if (status) status.textContent = `${s[0].toUpperCase()}${s.slice(1)} size`;
  };
  segs.forEach((b) => b.addEventListener('click', () => setSize(b.dataset.size)));

  // drag anywhere; a click without movement on the header cycles the size
  let drag = null;
  canvas.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    canvas.setPointerCapture(e.pointerId);
    drag = { sx: e.clientX, sy: e.clientY, ox: pos.x, oy: pos.y, moved: false, y: e.offsetY / w.scale };
    holder.classList.add('is-dragging');
  });
  canvas.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    pos = { x: drag.ox + dx, y: drag.oy + dy }; keepInside();
  });
  const end = () => {
    if (!drag) return;
    holder.classList.remove('is-dragging');
    if (!drag.moved && drag.y <= w.headerBottom) setSize(SIZES[(SIZES.indexOf(w.size) + 1) % 3]);
    drag = null;
  };
  canvas.addEventListener('pointerup', end);
  canvas.addEventListener('pointercancel', end);

  // the right-click menu, recreated
  const openMenu = (x, y) => {
    menu.hidden = false;
    const r = stage.getBoundingClientRect();
    menu.style.left = clamp(x - r.left, 8, r.width - menu.offsetWidth - 8) + 'px';
    menu.style.top = clamp(y - r.top, 8, r.height - menu.offsetHeight - 8) + 'px';
    menu.querySelector('[role="menuitemradio"][aria-checked="true"], [role="menuitem"], [role="menuitemcheckbox"]')?.focus();
  };
  const closeMenu = (focusBack) => { if (menu.hidden) return; menu.hidden = true; if (focusBack) document.querySelector('[data-open-menu]')?.focus(); };
  canvas.addEventListener('contextmenu', (e) => { e.preventDefault(); openMenu(e.clientX, e.clientY); });
  document.querySelector('[data-open-menu]')?.addEventListener('click', (e) => {
    const b = e.currentTarget.getBoundingClientRect(); openMenu(b.left, b.bottom + 6);
  });
  document.addEventListener('pointerdown', (e) => { if (!menu.contains(e.target) && !e.target.closest('[data-open-menu]')) closeMenu(false); });
  menu.addEventListener('keydown', (e) => {
    const items = [...menu.querySelectorAll('[role^="menuitem"]:not([aria-disabled="true"])')];
    const i = items.indexOf(document.activeElement);
    if (e.key === 'Escape') { e.preventDefault(); closeMenu(true); }
    if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
  });
  menu.querySelectorAll('[data-menu-size]').forEach((m) => m.addEventListener('click', () => { setSize(m.dataset.menuSize); closeMenu(true); }));
  menu.querySelectorAll('[role="menuitemcheckbox"]').forEach((m) => m.addEventListener('click', () => {
    m.setAttribute('aria-checked', String(m.getAttribute('aria-checked') !== 'true'));
  }));
  menu.querySelector('[data-quit]')?.addEventListener('click', () => {
    closeMenu(false); holder.classList.add('is-quit'); relaunch.hidden = false; relaunch.focus();
  });
  relaunch?.addEventListener('click', () => { holder.classList.remove('is-quit'); relaunch.hidden = true; });

  setSize('full');
  place();
  addEventListener('resize', () => { fit(); });
}

function setupClaude() {
  const el = document.querySelector('[data-claude-chart]');
  if (!el) return;
  const canvas = el.querySelector('canvas'), num = document.querySelector('[data-claude-week]');
  const today = document.querySelector('[data-claude-today]'), five = document.querySelector('[data-claude-five]');
  const draw = () => {
    const c = feed.s.claude, wpx = el.clientWidth, dpr = Math.min(devicePixelRatio || 1, 3);
    const scale = wpx >= 460 ? 3 : 2, chartH = 30 * scale, h = chartH + 6 * scale + 7 * scale;
    canvas.width = wpx * dpr; canvas.height = h * dpr; canvas.style.width = wpx + 'px'; canvas.style.height = h + 'px';
    const dc = canvas.getContext('2d');
    dc.setTransform(dpr, 0, 0, dpr, 0, 0); dc.clearRect(0, 0, wpx, h);
    Widget.prototype.week.call({ rect: Widget.prototype.rect, text: Widget.prototype.text }, dc, 0, 0, wpx, c.days, feed.todayIndex, chartH, 10, scale);
    if (num) num.dataset.pixel = F.tok(c.week), mountPixel(num);
    if (today) { today.dataset.pixel = F.tok(c.today); mountPixel(today); today.nextElementSibling.textContent = F.tok(c.today); }
    if (five) { five.dataset.pixel = F.tok(c.five); mountPixel(five); five.nextElementSibling.textContent = F.tok(c.five); }
  };
  draw();
  feed.on(draw);
  addEventListener('resize', draw);
}

async function setupStars() {
  const els = document.querySelectorAll('[data-stars]');
  if (!els.length) return;
  try {
    const r = await fetch('https://api.github.com/repos/itsnothyun/pulse', { headers: { Accept: 'application/vnd.github+json' } });
    if (!r.ok) return;
    const n = (await r.json()).stargazers_count;
    if (typeof n !== 'number') return;
    const label = n >= 1000 ? (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k' : String(n);
    if (n < 25) return;                                  // a tiny count advertises nothing; the button stands alone
    els.forEach((el) => { el.textContent = label; el.hidden = false; el.setAttribute('aria-label', `${n} stars`); });
  } catch { /* offline or rate-limited: the button works without a count */ }
}

function setupCopy() {
  document.querySelectorAll('[data-copy]').forEach((b) => b.addEventListener('click', async () => {
    const text = document.getElementById(b.dataset.copy)?.textContent.trim();
    try { await navigator.clipboard.writeText(text); b.dataset.state = 'done'; b.querySelector('span').textContent = 'Copied'; }
    catch { b.querySelector('span').textContent = 'Select & copy'; }
    setTimeout(() => { b.dataset.state = ''; b.querySelector('span').textContent = 'Copy'; }, 1800);
  }));
}

function setupNav() {
  const nav = document.querySelector('.nav');
  const onScroll = () => nav.classList.toggle('is-scrolled', scrollY > 8);
  onScroll();
  addEventListener('scroll', onScroll, { passive: true });
}

/* boot */
const pixels = [...document.querySelectorAll('[data-pixel]')];
const mountAll = () => pixels.forEach(mountPixel);
document.fonts?.ready.then(() => document.documentElement.classList.add('fonts-ready'));
mountAll();
let rt;
addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(mountAll, 120); });
setupNav();
setupDesktops();
setupVitals();
setupSizes();
setupClaude();
setupStars();
setupCopy();
requestAnimationFrame(frame);
motionQuery.addEventListener?.('change', () => widgets.forEach((w) => w.draw()));
