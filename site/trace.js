// The ecosystem's one moving part: a pixel trace in the widget's dot grammar. Each product has its own
// rhythm. On the front page, hovering or focusing a product switches the trace to that product's rhythm.
const RHYTHMS = {
  all: [0,0,0,1,0,0,-1,7,-3,1,0,0,0,0,2,0,0,2,0,0,0,1,2,4,3,1,0,0,0,3,3,3,0,0,3,3,3,0,0,0,1,2,3,4,5,0,0,0],
  pulse: [0,0,0,0,1,0,0,-1,7,-3,1,0,0,0,0,0,1,2,1,0,0,0,0,0],
  sync: [0,0,2,0,0,0,0,0,2,0,0,0,0,0,2,0,0,0,0,0,5,0,0,0],
  track: [1,3,0,2,5,1,0,4,2,0,0,1,6,3,0,2,0,0,1,4],
  connect: [0,0,3,3,3,0,0,0,3,3,3,3,3,0,0,3,0,0,0],
  explorer: [1,2,3,4,5,6,0,0,1,2,3,4,0,0,0,1,2,3,4,5,0,0],
};
const reduce = matchMedia('(prefers-reduced-motion: reduce)');
const STEP = 5, DOT = 4, ROWS = 15, BASE = 11;

function mount(canvas) {
  const ctx = canvas.getContext('2d');
  let name = canvas.dataset.trace || 'all', offset = 0, cols = 0, visible = true, last = 0;
  let wave = [];
  const fill = () => {
    const r = RHYTHMS[name] || RHYTHMS.all;
    wave = Array.from({ length: cols + 1 }, (_, i) => r[i % r.length]);
  };
  const size = () => {
    const w = canvas.parentElement.getBoundingClientRect().width, dpr = devicePixelRatio || 1;
    cols = Math.floor(w / STEP);
    canvas.style.width = `${cols * STEP}px`;
    canvas.style.height = `${ROWS * STEP}px`;
    canvas.width = cols * STEP * dpr;
    canvas.height = ROWS * STEP * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    fill();
    draw();
  };
  function draw() {
    ctx.clearRect(0, 0, cols * STEP, ROWS * STEP);
    for (let c = 0; c < cols; c++) {
      const h = wave[c] || 0, age = c / cols;
      ctx.fillStyle = '#262626';
      ctx.fillRect(c * STEP, BASE * STEP, DOT, DOT);
      if (h === 0) continue;
      ctx.fillStyle = `rgba(242,242,237,${(0.18 + 0.82 * age).toFixed(3)})`;
      const a = Math.min(BASE, BASE - h), b = Math.max(BASE, BASE - h);
      for (let y = a; y <= b; y++) ctx.fillRect(c * STEP, y * STEP, DOT, DOT);
    }
  }
  const tick = (now) => {
    requestAnimationFrame(tick);
    if (!visible || reduce.matches || document.hidden || now - last < 70) return;
    last = now;
    const r = RHYTHMS[name] || RHYTHMS.all;
    offset = (offset + 1) % r.length;
    wave.shift();
    wave.push(r[(offset + cols) % r.length]);
    draw();
  };
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; }).observe(canvas);
  canvas.setRhythm = (next) => {
    if (next === name) return;
    name = next;
    // New beats enter from the right; what is on screen scrolls away.
    offset = 0;
    if (reduce.matches) { fill(); draw(); }
  };
  addEventListener('resize', size);
  size();
  requestAnimationFrame(tick);
}

const canvases = [...document.querySelectorAll('canvas[data-trace]')];
canvases.forEach(mount);
const main = canvases[0];
document.querySelectorAll('[data-rhythm]').forEach((row) => {
  const on = () => main?.setRhythm(row.dataset.rhythm);
  const off = () => main?.setRhythm('all');
  row.addEventListener('pointerenter', on);
  row.addEventListener('pointerleave', off);
  row.addEventListener('focusin', on);
  row.addEventListener('focusout', off);
});

// The widget's page lived at / until the ecosystem page took over. Old links with a section still land.
if (location.pathname === '/' && /^#(vitals|sizes|claude|install)$/.test(location.hash)) location.replace('/pulse/' + location.hash);
