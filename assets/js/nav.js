/* Header + nav behaviour shared by every page.
 *
 * Marks the header once the page has scrolled (so it only casts a shadow when
 * it is actually overlapping content), and flags the nav item matching the
 * current page so the bar shows where you are.
 */
(function () {
  var header = document.querySelector('header');
  if (header) {
    var onScroll = function () {
      header.classList.toggle('scrolled', window.pageYOffset > 8);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  // Current page: compare pathnames, treating "/" and "/index.html" as one.
  var here = location.pathname.replace(/\/index\.html$/, '/');
  document.querySelectorAll('#nav-links a[href]').forEach(function (a) {
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#') return;
    var path;
    try {
      path = new URL(href, location.origin).pathname.replace(/\/index\.html$/, '/');
    } catch (e) {
      return;
    }
    if (path !== here) return;
    var li = a.closest('li');
    if (!li) return;
    li.classList.add('current');
    // A category page should also light up the "Shop" parent it sits under.
    var panel = a.closest('.nav-shop-panel');
    if (panel) {
      var parent = panel.closest('.nav-shop');
      if (parent) parent.classList.add('current');
    }
  });
})();
