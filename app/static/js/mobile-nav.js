(function () {
  'use strict';
  var BREAKPOINT = 768;

  var sidebar = document.querySelector('.sidebar');
  if (!sidebar) return;

  // Create hamburger button
  var btn = document.createElement('button');
  btn.className = 'mobile-hamburger';
  btn.setAttribute('aria-label', 'Open navigation');
  btn.innerHTML = '<span></span>';
  document.body.prepend(btn);

  // Create overlay
  var overlay = document.createElement('div');
  overlay.className = 'sidebar-overlay';
  document.body.prepend(overlay);

  function openNav() {
    sidebar.classList.add('mobile-open');
    overlay.classList.add('visible');
    btn.classList.add('open');
    btn.setAttribute('aria-label', 'Close navigation');
    document.body.style.overflow = 'hidden';
  }

  function closeNav() {
    sidebar.classList.remove('mobile-open');
    overlay.classList.remove('visible');
    btn.classList.remove('open');
    btn.setAttribute('aria-label', 'Open navigation');
    document.body.style.overflow = '';
  }

  btn.addEventListener('click', function () {
    if (sidebar.classList.contains('mobile-open')) closeNav();
    else openNav();
  });

  overlay.addEventListener('click', closeNav);

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && sidebar.classList.contains('mobile-open')) closeNav();
  });

  sidebar.addEventListener('click', function (e) {
    if (e.target.closest('a[href]')) closeNav();
  });

  window.addEventListener('resize', function () {
    if (window.innerWidth > BREAKPOINT && sidebar.classList.contains('mobile-open')) closeNav();
  });

  // Touch swipe gestures: edge swipe opens nav, left swipe closes nav.
  var touchStartX = 0;
  var touchStartY = 0;
  var touchActive = false;
  document.addEventListener('touchstart', function (e) {
    if (!e.touches || !e.touches.length) return;
    var t = e.touches[0];
    touchStartX = t.clientX;
    touchStartY = t.clientY;
    touchActive = true;
  }, { passive: true });

  document.addEventListener('touchend', function (e) {
    if (!touchActive || !e.changedTouches || !e.changedTouches.length) return;
    var t = e.changedTouches[0];
    var dx = t.clientX - touchStartX;
    var dy = t.clientY - touchStartY;
    touchActive = false;

    if (Math.abs(dy) > 70 || Math.abs(dx) < 45) return;
    if (window.innerWidth > BREAKPOINT) return;
    if (!sidebar.classList.contains('mobile-open') && touchStartX < 24 && dx > 45) {
      openNav();
      return;
    }
    if (sidebar.classList.contains('mobile-open') && dx < -45) {
      closeNav();
    }
  }, { passive: true });
})();
