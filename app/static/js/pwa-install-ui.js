/**
 * PWA install banner: show when beforeinstallprompt fires, call prompt() on Install click.
 * Depends on pwa.js (which calls window.__bosInstallPrompt(e) when event fires).
 */
(function () {
  'use strict';

  var DISMISS_KEY = 'bos_pwa_install_dismiss';
  var DISMISS_DAYS = 7;

  var installEvent = null;
  var banner = null;
  var installBtn = null;
  var dismissBtn = null;

  function getBanner() {
    if (banner) return banner;
    banner = document.getElementById('pwa-install-banner');
    if (banner) {
      installBtn = banner.querySelector('[data-pwa-install]');
      dismissBtn = banner.querySelector('[data-pwa-dismiss]');
      if (dismissBtn) dismissBtn.addEventListener('click', dismiss);
      if (installBtn) installBtn.addEventListener('click', onInstallClick);
    }
    return banner;
  }

  function isDismissed() {
    try {
      var raw = localStorage.getItem(DISMISS_KEY);
      if (!raw) return false;
      var t = parseInt(raw, 10);
      return Date.now() - t < DISMISS_DAYS * 24 * 60 * 60 * 1000;
    } catch (_) { return false; }
  }

  function dismiss() {
    try {
      localStorage.setItem(DISMISS_KEY, String(Date.now()));
    } catch (_) {}
    hideBanner();
  }

  function hideBanner() {
    var el = getBanner();
    if (el) el.classList.add('u-hidden');
  }

  function showBanner() {
    if (isDismissed()) return;
    var el = getBanner();
    if (el) el.classList.remove('u-hidden');
  }

  function onInstallClick() {
    if (!installEvent) return;
    installEvent.prompt();
    installEvent.userChoice.then(function (choice) {
      installEvent = null;
      hideBanner();
    });
  }

  window.__bosInstallPrompt = function (e) {
    installEvent = e;
    showBanner();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { getBanner(); });
  } else {
    getBanner();
  }
})();
