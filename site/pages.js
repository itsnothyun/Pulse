// The smaller Pulse pages (Pulse Explorer, Ecosystem): pixel headings, the nav shadow and
// copy buttons, without the widget simulation that pulse.js runs on the landing page.
import { GLYPHS } from './glyphs.js';

const motionQuery = matchMedia('(prefers-reduced-motion: reduce)');

/** <span data-pixel="LINE ONE|LINE TWO"> becomes crisp SVG; the real text stays for assistive tech. */
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
  const want = parseFloat(getComputedStyle(el).getPropertyValue('--dot')) || 4;
  const box = el.parentElement.getBoundingClientRect().width || 320;
  const cols = Math.max(...lines.map((l) => l.length * 6 - 1));
  const dot = Math.max(1.5, Math.min(want, Math.floor((box / cols) * 4) / 4));
  const gap = dot >= 6 ? Math.round(dot * 0.12 * 4) / 4 : 0;
  const assemble = el.hasAttribute('data-assemble') && !el.dataset.done && !motionQuery.matches;
  el.innerHTML = lines.map((l) => `<span class="px-line">${pixelSVG(l, dot, gap, assemble)}</span>`).join('');
  if (assemble) { el.classList.add('assembling'); el.dataset.done = '1'; }
}

function setupNav() {
  const nav = document.querySelector('.nav');
  const onScroll = () => nav.classList.toggle('is-scrolled', scrollY > 8);
  onScroll();
  addEventListener('scroll', onScroll, { passive: true });
}

function setupCopy() {
  document.querySelectorAll('[data-copy]').forEach((b) => b.addEventListener('click', async () => {
    const text = document.getElementById(b.dataset.copy)?.textContent.trim();
    try { await navigator.clipboard.writeText(text); b.dataset.state = 'done'; b.querySelector('span').textContent = 'Copied'; }
    catch { b.querySelector('span').textContent = 'Select & copy'; }
    setTimeout(() => { b.dataset.state = ''; b.querySelector('span').textContent = 'Copy'; }, 1800);
  }));
}

const pixels = [...document.querySelectorAll('[data-pixel]')];
const mountAll = () => pixels.forEach(mountPixel);
mountAll();
let rt;
addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(mountAll, 120); });
setupNav();
setupCopy();
