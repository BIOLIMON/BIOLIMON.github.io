/* ───────── CURSOR: a lagging outline square + a snappy dot (desktop pointers only) ───────── */
(() => {
  if (!matchMedia('(hover: hover) and (pointer: fine)').matches) return; // touch keeps the native cursor
  const root = document.documentElement;
  root.classList.add('has-cursor');
  const mk = id => { const d = document.createElement('div'); d.id = id; d.className = 'cur'; document.body.append(d); return d; };
  const big = mk('cur-big'), small = mk('cur-small'), label = mk('cur-label'), coords = mk('cur-coords');
  const parts = [big, small, label, coords];
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const HOT = 'a, button, .portal, .win header';
  let x = -100, y = -100, bx = x, by = y, seen = false, frame = 0;
  const place = (el, px, py) => { el.style.transform = `translate3d(${px}px,${py}px,0)`; };

  // carry the pointer across page changes so the cursor doesn't blink out while navigating
  try {
    const [sx, sy] = (sessionStorage.getItem('cur') || '').split(',').map(Number);
    if (Number.isFinite(sx) && Number.isFinite(sy) && sessionStorage.getItem('cur')) {
      x = bx = sx; y = by = sy; seen = true;
      place(small, x, y); parts.forEach(el => el.classList.add('on'));
    }
  } catch (e) {}
  addEventListener('pagehide', () => {
    try { seen ? sessionStorage.setItem('cur', x + ',' + y) : sessionStorage.removeItem('cur'); } catch (e) {}
  });

  addEventListener('pointermove', e => {
    x = e.clientX; y = e.clientY;
    if (!seen) { seen = true; bx = x; by = y; parts.forEach(el => el.classList.add('on')); }
    place(small, x, y);
  }, { passive: true });
  root.addEventListener('mouseleave', () => { seen = false; parts.forEach(el => el.classList.remove('on')); });
  addEventListener('pointerdown', () => root.classList.add('cur-down'));
  addEventListener('pointerup', () => root.classList.remove('cur-down'));
  addEventListener('blur', () => root.classList.remove('cur-down'));

  (function loop() {
    const k = reduce ? 1 : 0.16;                 // easing: the outline trails the dot
    bx += (x - bx) * k; by += (y - by) * k;
    place(big, bx, by); place(label, bx, by); place(coords, bx, by);
    const c = `${Math.round(x)},${Math.round(y)}`;   // real pointer position, not the trailing square
    if (coords.textContent !== c) coords.textContent = c;
    if (seen && ++frame % 6 === 0) {             // cheap hover check, also catches elements that vanish
      const el = document.elementFromPoint(x, y);
      root.classList.toggle('cur-hot', !!(el && el.closest(HOT)));
      const tag = el && el.closest('[data-cursor]');
      const txt = tag ? tag.dataset.cursor : '';
      if (label.textContent !== txt) label.textContent = txt;
    }
    requestAnimationFrame(loop);
  })();
})();
