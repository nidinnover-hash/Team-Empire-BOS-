/**
 * PWA polish: theme-color sync with light/dark, install prompt, service worker registration.
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

  // Register service worker for offline support
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/static/js/service-worker.js', { scope: '/' })
        .then(function (reg) {
          reg.addEventListener('updatefound', function () {
            var newWorker = reg.installing;
            if (newWorker) {
              newWorker.addEventListener('statechange', function () {
                if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                  // New version available — notify app if handler registered
                  if (typeof window.__bosSwUpdate === 'function') {
                    window.__bosSwUpdate();
                  }
                }
              });
            }
          });
        })
        .catch(function (err) {
          console.warn('[BOS SW] Registration failed:', err);
        });
    });
  }
})();
