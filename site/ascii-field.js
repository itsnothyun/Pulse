// Bento cards: a quiet ASCII field behind each card's art. Characters drift in slow waves and brighten
// under the cursor. Monochrome, masked to dissolve at the edges, paused when off screen.
const still = matchMedia('(prefers-reduced-motion: reduce)');
const RAMP = ' .:-=+*#%@', NS = RAMP.length - 1;
const CW = 9, CH = 14;
const GREY = (l) => { const v = Math.round(58 + (242 - 58) * l); return `rgb(${v},${v},${v - 4})`; };

const dpr = Math.min(devicePixelRatio || 1, 2);
const atlas = document.createElement('canvas');
atlas.width = CW * dpr * (NS + 1); atlas.height = CH * dpr;
{
  const a = atlas.getContext('2d');
  a.font = `500 ${Math.round(CH * dpr * 0.86)}px ui-monospace, Menlo, "SF Mono", Consolas, monospace`;
  a.textAlign = 'center'; a.textBaseline = 'middle';
  for (let i = 1; i <= NS; i++) { a.fillStyle = GREY(i / NS); a.fillText(RAMP[i], i * CW * dpr + (CW * dpr) / 2, (CH * dpr) / 2 + 1); }
}

function field(card) {
  const canvas = document.createElement('canvas');
  canvas.className = 'ascii-field';
  canvas.setAttribute('aria-hidden', 'true');
  card.prepend(canvas);
  const ctx = canvas.getContext('2d');
  let cols = 0, rows = 0, last = null, visible = false, raf = 0, t0 = performance.now(), prev = 0;

  const size = () => {
    const r = card.getBoundingClientRect();
    cols = Math.ceil(r.width / CW); rows = Math.ceil(r.height / CH);
    canvas.width = cols * CW * dpr; canvas.height = rows * CH * dpr;
    last = new Uint8Array(cols * rows).fill(255);
  };
  size();
  new ResizeObserver(size).observe(card);

  const frame = (now) => {
    raf = visible && !still.matches ? requestAnimationFrame(frame) : 0;
    if (now - prev < 110) return;
    prev = now;
    const t = (now - t0) / 1000;
    const hover = card.matches(':hover');
    const mx = parseFloat(card.style.getPropertyValue('--mx')) || -999, my = parseFloat(card.style.getPropertyValue('--my')) || -999;
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
      const k = y * cols + x;
      const wave = 0.5 + 0.5 * Math.sin(x * 0.11 + t * 0.55 + Math.sin(y * 0.09 - t * 0.35) * 1.7);
      let v = wave ** 4 * 0.42;
      if (hover) {
        const dx = x * CW - mx, dy = y * CH - my;
        v += 0.75 * Math.exp(-(dx * dx + dy * dy) / (2 * 110 * 110)) * (0.55 + 0.45 * wave);
      }
      const lvl = Math.min(NS, Math.round(v * NS));
      if (lvl === last[k]) continue;
      last[k] = lvl;
      const px = x * CW * dpr, py = y * CH * dpr;
      ctx.clearRect(px, py, CW * dpr, CH * dpr);
      if (lvl) ctx.drawImage(atlas, lvl * CW * dpr, 0, CW * dpr, CH * dpr, px, py, CW * dpr, CH * dpr);
    }
  };
  new IntersectionObserver(([e]) => {
    visible = e.isIntersecting;
    if (visible && !raf) raf = requestAnimationFrame(frame);
  }, { threshold: 0.02 }).observe(card);
  if (still.matches) frame(1000);
}

document.querySelectorAll('.feat').forEach(field);
