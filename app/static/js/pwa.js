/**
 * PWA polish: theme-color sync with light/dark, install prompt (optional).
 * No service worker by default; add sw.js and register here if needed.
 */
(function () {
  'use strict';

  function setThemeColor(theme) {
    var meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
      meta = document.createElement('meta');
      meta.name = 'theme-color';
      document.head.appendChild(meta);
    }
    meta.content = theme === 'dark' ? '#000000' : '#f5f5f7';
  }

  function onThemeChange() {
    var theme = document.documentElement.getAttribute('data-theme') || 'light';
    setThemeColor(theme);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onThemeChange);
  } else {
    onThemeChange();
  }

  var observer = new MutationObserver(function (mutations) {
    mutations.forEach(function (m) {
      if (m.attributeName === 'data-theme') onThemeChange();
    });
  });
  observer.observe(document.documentElement, { attributes: true });

  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    if (typeof window.__bosInstallPrompt === 'function') {
      window.__bosInstallPrompt(e);
    }
  });
})();
