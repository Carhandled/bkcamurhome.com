/* Floating call-to-action.
 *
 * The header CTA is hidden below 1279px, so on a phone there was no way to get
 * to the shop without scrolling back up to the hamburger. This adds a pill that
 * appears once you are past the hero.
 *
 * It is context-aware rather than a fixed "Shop the Collection" everywhere:
 * on a category page you are already in a collection, so the useful action is
 * jumping over the editorial copy to the pieces - and once you have reached
 * them, back to top. Anywhere else it routes to the collections hub.
 */
(function () {
  var SHOW_AFTER = 520; // roughly past the hero on every template

  var grid = document.querySelector('.product-grid');
  var btn = document.createElement('a');
  btn.className = 'floating-cta';

  var modes = {
    toGrid: { label: 'View the pieces', arrow: '↓' },
    toTop: { label: 'Back to top', arrow: '↑' },
    toShop: { label: 'Shop the Collection', arrow: '→' }
  };
  var mode = null;

  function setMode(next) {
    if (mode === next) return;
    mode = next;
    var m = modes[next];
    btn.innerHTML = m.label + ' <span class="floating-cta-arrow">' + m.arrow + '</span>';
    btn.setAttribute('href', next === 'toShop' ? '/#collections' : '#');
  }

  btn.addEventListener('click', function (e) {
    if (mode === 'toShop') return; // let the browser navigate
    e.preventDefault();
    if (mode === 'toGrid' && grid) {
      grid.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  });

  function update() {
    var y = window.pageYOffset;
    btn.classList.toggle('visible', y > SHOW_AFTER);

    if (!grid) {
      setMode('toShop');
      return;
    }
    // Once the top of the grid has come up past the middle of the screen,
    // "jump to the pieces" is spent - offer the way back instead.
    var reached = grid.getBoundingClientRect().top < window.innerHeight * 0.5;
    setMode(reached ? 'toTop' : 'toGrid');
  }

  setMode(grid ? 'toGrid' : 'toShop');
  document.body.appendChild(btn);

  var ticking = false;
  window.addEventListener('scroll', function () {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(function () {
      update();
      ticking = false;
    });
  }, { passive: true });

  update();
})();
