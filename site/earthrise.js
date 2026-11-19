// The footer: an earthrise in ASCII, monochrome, looping. A cratered horizon curves across the bottom while a
// planet slowly rises over it and sinks again (a 70 s loop), with a few twinkling stars. Drawn as characters
// from a ten-step ramp on a terminal-shaped grid; the canvas fades into the page colour on every side, so
// the footer reads as one piece with the background. Pauses off screen; one still frame under Reduce Motion.
const host = document.querySelector('.footer');
if (host) {
  const still = matchMedia('(prefers-reduced-motion: reduce)');
  const RAMP = ' .:-=+*#%@', NS = RAMP.length - 1;
  const CW = 8, CH = 13, LOOP = 70;
  const dpr = Math.min(devicePixelRatio || 1, 2);
  const canvas = document.createElement('canvas');
  canvas.className = 'earthrise';
  canvas.setAttribute('aria-hidden', 'true');
  host.prepend(canvas);
  const ctx = canvas.getContext('2d');

  const atlas = document.createElement('canvas');
  atlas.width = CW * dpr * (NS + 1); atlas.height = CH * dpr;
  {
    const a = atlas.getContext('2d');
    a.font = `600 ${Math.round(CH * dpr * 0.88)}px ui-monospace, Menlo, "SF Mono", Consolas, monospace`;
    a.textAlign = 'center'; a.textBaseline = 'middle';
    for (let i = 1; i <= NS; i++) {
      const v = Math.round(44 + (242 - 44) * (i / NS) ** 1.1);
      a.fillStyle = `rgb(${v},${v},${v - 4})`;
      a.fillText(RAMP[i], i * CW * dpr + (CW * dpr) / 2, (CH * dpr) / 2 + 1);
    }
  }

  const hash = (x, y) => { let h = Math.imul(x | 0, 374761393) + Math.imul(y | 0, 668265263); h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
  const noise = (x, y) => {
    const xi = Math.floor(x), yi = Math.floor(y), fx = x - xi, fy = y - yi, u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy);
    const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  };
  const fbm = (x, y, o) => { let s = 0, n = 0, a = 0.5; for (let i = 0; i < o; i++) { s += a * noise(x, y); n += a; x *= 2; y *= 2; a *= 0.5; } return s / n; };
  const clamp = (v, a = 0, b = 1) => (v < a ? a : v > b ? b : v);
  const smooth = (a, b, v) => { const k = clamp((v - a) / (b - a)); return k * k * (3 - 2 * k); };
  const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map((v) => v / 16 - 0.47);

  let cols = 0, rows = 0, W = 0, H = 0, base, cur, last, stars = [], hy, Rm, mcy, Re, visible = false, raf = 0, prev = 0, t = LOOP * 0.34;

  const build = () => {
    const r = host.getBoundingClientRect();
    cols = Math.ceil(r.width / CW); rows = Math.ceil(r.height / CH);
    W = cols * CW; H = rows * CH;
    canvas.width = cols * CW * dpr; canvas.height = rows * CH * dpr;
    base = new Float32Array(cols * rows); cur = new Float32Array(cols * rows); last = new Uint8Array(cols * rows).fill(255);
    hy = H * 0.6; Rm = W * 1.35; mcy = hy + Rm; Re = Math.min(W * 0.15, H * 0.25);
    stars = [];
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
      const k = y * cols + x, px = (x + 0.5) * CW, py = (y + 0.5) * CH;
      const d = Math.hypot(px - W / 2, py - mcy), depth = Rm - d;
      if (depth > 0) {
        // the moon: craters from noise, a bright limb at the horizon, darker toward the page's bottom edge
        const c = fbm(px * 0.012, py * 0.02, 4), ridge = 1 - Math.abs(fbm(px * 0.03 + 9, py * 0.045, 3) * 2 - 1);
        let v = 0.06 + 0.2 * c + 0.11 * ridge * ridge + 0.5 * Math.exp(-depth / 11);
        v *= 1 - 0.85 * smooth(hy + (H - hy) * 0.12, hy + (H - hy) * 0.75, py);
        base[k] = v;
      } else if (hash(x, y + 77) > 0.9935) {
        stars.push(k);
        base[k] = 0.25 + 0.5 * hash(y, x + 5);
      }
    }
  };

  const frame = (now) => {
    raf = visible && !still.matches ? requestAnimationFrame(frame) : 0;
    if (now && now - prev < 80) return;
    prev = now || 0;
    t = (t + 0.08) % LOOP;
    paint(t);
  };

  const paint = (tt) => {
    cur.set(base);
    for (const k of stars) cur[k] = base[k] * (0.55 + 0.45 * Math.sin(tt * 1.3 + k));
    const rise = 0.5 - 0.5 * Math.cos((tt / LOOP) * Math.PI * 2);
    const ex = W * 0.5 + W * 0.05 * Math.sin((tt / LOOP) * Math.PI * 2), ey = hy + Re * 0.95 - Re * 2.15 * rise, spin = tt * 0.1;
    const x0 = Math.max(0, Math.floor((ex - Re * 1.6) / CW)), x1 = Math.min(cols - 1, Math.ceil((ex + Re * 1.6) / CW));
    const y0 = Math.max(0, Math.floor((ey - Re * 1.6) / CH)), y1 = Math.min(rows - 1, Math.ceil((ey + Re * 1.6) / CH));
    const L = [-0.62, 0.5, 0.6];
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
      const k = y * cols + x, px = (x + 0.5) * CW, py = (y + 0.5) * CH;
      if (Math.hypot(px - W / 2, py - mcy) < Rm) continue;            // the horizon hides the planet
      const dx = (px - ex) / Re, dy = (py - ey) / Re, r2 = dx * dx + dy * dy;
      if (r2 < 1) {
        const nz = Math.sqrt(1 - r2), nx = dx, ny = -dy;
        const lon = Math.atan2(nx, nz) + spin, lat = Math.asin(clamp(ny, -1, 1));
        const land = fbm(lon * 1.7 + 3, lat * 2.6 + 1, 4), cloud = fbm(lon * 3.1 - spin * 0.6 + 40, lat * 4.2, 3);
        const diff = clamp(nx * L[0] + ny * L[1] + nz * L[2] + 0.12);
        let v = (land > 0.52 ? 0.62 : 0.26) * (0.2 + 1.0 * smooth(0, 0.7, diff));
        if (cloud > 0.6) v += 0.25 * diff;
        v += 0.4 * Math.pow(1 - nz, 3) * (0.35 + diff);
        cur[k] = Math.max(0.03, v);
      } else if (r2 < 1.7) {
        cur[k] = Math.max(cur[k], 0.16 * Math.exp(-(Math.sqrt(r2) - 1) * 5));   // a faint halo
      }
    }
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
      const k = y * cols + x;
      const lvl = clamp(Math.round(cur[k] * NS + BAYER[(y & 3) * 4 + (x & 3)] * 0.55), 0, NS);
      if (lvl === last[k]) continue;
      last[k] = lvl;
      const px = x * CW * dpr, py = y * CH * dpr;
      ctx.clearRect(px, py, CW * dpr, CH * dpr);
      if (lvl) ctx.drawImage(atlas, lvl * CW * dpr, 0, CW * dpr, CH * dpr, px, py, CW * dpr, CH * dpr);
    }
  };

  build();
  paint(t);
  let rt;
  new ResizeObserver(() => { clearTimeout(rt); rt = setTimeout(() => { build(); paint(t); }, 120); }).observe(host);
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible && !raf) raf = requestAnimationFrame(frame); }, { threshold: 0.02 }).observe(host);
}
