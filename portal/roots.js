/* Roots thumbnail — a root drawn with | / \ grows down from a dotted ground line, branches,
   sprouts root hairs (· .) and ends every tip in a nucleotide (A T G C). When it is done it rests,
   then starts again from a new seed.

   Adapted from RootGrowth in the PGR Lab design system (BIOLIMON/pgrlab-site, sistema-de-diseno).
   Differences: no click interaction (the card around it is a link), it redraws when its box is resized,
   and with prefers-reduced-motion it shows the finished root and stays still.

   Use:  <div class="roots" data-roots data-seed="3" data-branch="0.1"></div>
     data-seed    number that picks the root's shape (default 3)
     data-branch  0–1, chance of branching: ~0.08 deep taproot, ~0.25 dense and lateral (default 0.1)
   The container needs a fixed size; the root fills it. Colours come from the .ascii rules in style.css. */
(function () {
  "use strict";
  var BASES = "ATGC";
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function rng(seed) {
    var s = (seed >>> 0) || 1;
    return function () { s ^= s << 13; s ^= s >>> 17; s ^= s << 5; return ((s >>> 0) % 100000) / 100000; };
  }
  function esc(c) { return c === "<" ? "&lt;" : c === ">" ? "&gt;" : c === "&" ? "&amp;" : c; }

  function Roots(el) {
    var seed = parseInt(el.getAttribute("data-seed"), 10) || 3;
    var branch = el.hasAttribute("data-branch") ? parseFloat(el.getAttribute("data-branch")) : 0.1;
    var r, grid, tips, cols, rows, rest, cw = 8, ch = 13, raf = 0, visible = true, last = 0;

    var pre = document.createElement("pre");
    pre.className = "ascii";
    pre.setAttribute("aria-hidden", "true");
    el.textContent = "";
    el.appendChild(pre);

    function measure() {
      var probe = document.createElement("span");
      probe.textContent = "MMMMMMMMMM";
      pre.appendChild(probe);
      var b = probe.getBoundingClientRect();
      pre.removeChild(probe);
      cw = b.width / 10 || 8;
      ch = b.height || 13;
      var box = el.getBoundingClientRect();
      cols = Math.max(8, Math.floor((box.width || 320) / cw));
      rows = Math.max(4, Math.floor((box.height || 200) / ch));
    }

    function reset() {
      grid = [];
      for (var y = 0; y < rows; y++) { grid.push([]); for (var x = 0; x < cols; x++) grid[y].push(null); }
      for (var sx = 0; sx < cols; sx++) if (r() < 0.55) grid[0][sx] = { c: r() < 0.7 ? "." : "_", k: "f" };   // the ground line
      var x0 = Math.floor(cols / 2);
      grid[0][x0] = { c: "v", k: "b" };                                                                        // the seed
      tips = [{ x: x0, y: 0, dx: 0, life: rows, main: true }];
      rest = 0;
    }

    function step() {
      var next = [];
      tips.forEach(function (p) {
        var turn = r(), dx = p.dx, wob = p.main ? 0.2 : 0.12;
        if (turn < wob) dx = Math.max(-1, dx - 1); else if (turn > 1 - wob) dx = Math.min(1, dx + 1);
        if (p.main && dx !== 0 && r() < 0.35) dx = 0;                      // the main root looks for the vertical
        var nx = p.x + dx, ny = p.y + 1, life = p.life - 1;
        if (ny >= rows || nx < 0 || nx >= cols || life <= 0 || grid[ny][nx]) {
          // this tip is finished: it ends in a nucleotide
          if (p.y > 0 && grid[p.y][p.x] && grid[p.y][p.x].k === "i") grid[p.y][p.x] = { c: BASES[Math.floor(r() * 4)], k: "b" };
          return;
        }
        grid[ny][nx] = { c: dx === 0 ? "|" : dx < 0 ? "/" : "\\", k: "i" };
        if (r() < 0.18) {                                                  // root hairs: fine dots at the sides
          var hx = nx + (r() < 0.5 ? -1 : 1);
          if (hx >= 0 && hx < cols && !grid[ny][hx]) grid[ny][hx] = { c: r() < 0.5 ? "." : "·", k: "u" };
        }
        next.push({ x: nx, y: ny, dx: dx, life: life, main: p.main });
        if (ny > 1 && r() < branch * (1 - 0.6 * ny / rows) && next.length < 24) {
          var side = r() < 0.5 ? -1 : 1;
          next.push({ x: nx, y: ny, dx: side, life: Math.max(3, Math.floor(life * (0.25 + r() * 0.45))), main: false });
        }
      });
      tips = next;
    }

    function render() {
      var out = "";
      for (var y = 0; y < rows; y++) {
        for (var x = 0; x < cols; x++) {
          var g = grid[y][x];
          out += !g ? " " : g.k === "f" ? esc(g.c) : g.k === "b" ? "<b>" + g.c + "</b>" : g.k === "u" ? "<u>" + esc(g.c) + "</u>" : "<i>" + esc(g.c) + "</i>";
        }
        out += "\n";
      }
      pre.innerHTML = out;
    }

    function start() {
      cancelAnimationFrame(raf);
      measure();
      r = rng(seed);
      reset();
      // begin already half grown (or fully grown when motion is reduced)
      for (var k = 0, n = reduced ? rows * 2 : Math.floor(rows * 0.45); k < n && tips.length; k++) step();
      render();
      if (reduced) return;
      function tick(now) {
        raf = requestAnimationFrame(tick);
        if (!visible || now - last < 1000 / 6) return;                   // ~6 frames a second, and nothing while off screen
        last = now;
        if (!tips.length) { if (++rest > 30) { r = rng(++seed); reset(); } }   // rest ~5 s, then a new root
        else step();
        render();
      }
      raf = requestAnimationFrame(tick);
    }

    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (e) { visible = e[0].isIntersecting; }).observe(el);
    }
    start();
    if ("ResizeObserver" in window) {
      var first = true, timer = 0;
      new ResizeObserver(function () {
        if (first) { first = false; return; }                            // observe() reports once on start
        clearTimeout(timer);
        timer = setTimeout(start, 150);
      }).observe(el);
    }
  }

  function init() {
    var nodes = document.querySelectorAll("[data-roots]");
    for (var i = 0; i < nodes.length; i++) Roots(nodes[i]);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
