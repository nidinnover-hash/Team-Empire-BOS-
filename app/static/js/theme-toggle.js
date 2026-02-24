(function () {
  'use strict';
  var KEY = 'pc_theme';

  function getPreferred() {
    var stored = localStorage.getItem(KEY);
    if (stored === 'dark' || stored === 'light') return stored;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function apply(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(KEY, theme);
    var icons = document.querySelectorAll('.theme-icon');
    icons.forEach(function (el) { el.textContent = theme === 'dark' ? 'sun' : 'moon'; });
  }

  // Apply immediately to prevent flash
  apply(getPreferred());

  // Bind toggle buttons (one per page)
  document.addEventListener('DOMContentLoaded', function () {
    var btns = document.querySelectorAll('.theme-toggle');
    btns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        apply(getPreferred() === 'dark' ? 'light' : 'dark');
        if (typeof lucide !== 'undefined') lucide.createIcons();
      });
    });
    // Update icons after lucide renders
    var cur = getPreferred();
    var icons = document.querySelectorAll('.theme-icon');
    icons.forEach(function (el) { el.textContent = cur === 'dark' ? 'sun' : 'moon'; });
  });
})();
