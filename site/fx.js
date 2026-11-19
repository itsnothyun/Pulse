// Hover polish: product cards follow the cursor (a soft spotlight, a lit edge, a little parallax on the art).
// Only fine pointers; touch and Reduce Motion get the plain state. Values go through CSS custom properties.
const fine = matchMedia('(hover: hover) and (pointer: fine)');
const still = matchMedia('(prefers-reduced-motion: reduce)');

if (fine.matches) {
  for (const card of document.querySelectorAll('.product')) {
    let raf = 0, ev = null;
    const apply = () => {
      raf = 0;
      if (!ev) return;
      const r = card.getBoundingClientRect();
      const x = ev.clientX - r.left, y = ev.clientY - r.top;
      card.style.setProperty('--mx', x + 'px');
      card.style.setProperty('--my', y + 'px');
      if (!still.matches) {
        card.style.setProperty('--px', ((x / r.width) * 2 - 1).toFixed(3));
        card.style.setProperty('--py', ((y / r.height) * 2 - 1).toFixed(3));
      }
    };
    card.addEventListener('pointermove', (e) => { ev = e; if (!raf) raf = requestAnimationFrame(apply); });
    card.addEventListener('pointerleave', () => {
      ev = null;
      card.style.setProperty('--px', '0');
      card.style.setProperty('--py', '0');
    });
  }
}
