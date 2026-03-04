(function () {
  'use strict';
  function getCookie(name) {
    var key = name + "=";
    var parts = document.cookie.split("; ");
    for (var i = 0; i < parts.length; i++) {
      if (parts[i].indexOf(key) === 0) return decodeURIComponent(parts[i].slice(key.length));
    }
    return "";
  }

  var scope = getCookie("pc_theme_scope") || "professional";
  var defaultTheme = getCookie("pc_theme_default") || "";
  var KEY = "pc_theme:" + scope;

  // v2: force light reset — clear any old stored 'dark' preference
  if (!localStorage.getItem("pc_theme_v2_reset")) {
    localStorage.removeItem(KEY);
    localStorage.setItem("pc_theme_v2_reset", "1");
  }

  function getPreferred() {
    var stored = localStorage.getItem(KEY);
    if (stored === 'dark' || stored === 'light') return stored;
    if (defaultTheme === 'dark' || defaultTheme === 'light') return defaultTheme;
    return 'light';
  }

  function apply(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(KEY, theme);
    var newIcon = theme === 'dark' ? 'sun' : 'moon';
    var icons = document.querySelectorAll('.theme-icon');
    icons.forEach(function (el) { el.setAttribute('data-lucide', newIcon); });
    if (typeof lucide !== 'undefined') lucide.createIcons();
  }

  // Apply immediately to prevent flash
  apply(getPreferred());

  // Bind toggle buttons (one per page)
  document.addEventListener('DOMContentLoaded', function () {
    var btns = document.querySelectorAll('.theme-toggle');
    btns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        apply(getPreferred() === 'dark' ? 'light' : 'dark');
      });
    });
    // Update icons after lucide renders
    apply(getPreferred());
  });
})();
