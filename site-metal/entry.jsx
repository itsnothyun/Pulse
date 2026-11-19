// The metal-fx ring (silver, dark) around every .btn on the marketing site.
// The buttons stay plain HTML in index.html; each one is moved into a host span that
// MetalFx measures and paints over, so links, counts and handlers keep working.
// Without WebGL2 the buttons are left exactly as they are.
import { createRoot } from 'react-dom/client';
import { MetalFx, isMetalFxSupported } from 'metal-fx';

const still = matchMedia('(prefers-reduced-motion: reduce)');

function Metal({ btn }) {
  // buttons are pills now: the ring's radius is half the button's height (the token --r-pill, measured)
  const radius = Math.round((btn.getBoundingClientRect().height || 52) / 2);
  return (
    <MetalFx
      preset="silver"
      theme="dark"
      variant="button"
      borderRadius={radius}
      normalizeHostStyles={false}
      strength={btn.classList.contains('btn-primary') ? 1 : 0.8}
      innerShadow={btn.classList.contains('btn-primary')}
      paused={still.matches}
      className="metal"
    >
      <span className="metal-host" ref={(host) => { if (host && btn.parentNode !== host) host.appendChild(btn); }} />
    </MetalFx>
  );
}

function mount() {
  if (!isMetalFxSupported()) return;
  for (const btn of document.querySelectorAll('.btn:not([data-no-metal])')) {
    const slot = document.createElement('span');
    slot.className = 'metal-slot';
    btn.before(slot);
    createRoot(slot).render(<Metal btn={btn} />);
  }
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
else mount();
