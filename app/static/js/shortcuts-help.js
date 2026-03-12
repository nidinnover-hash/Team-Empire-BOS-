/**
 * ? key opens keyboard shortcuts help overlay.
 */
(function () {
  'use strict';
  var overlay = null;
  var SHORTCUTS = [
    { keys: 'Ctrl+K', mac: '⌘K', desc: 'Open command palette' },
    { keys: '?', mac: '?', desc: 'Show this help' },
    { keys: 'Esc', mac: 'Esc', desc: 'Close palette or modal' },
  ];

  function createOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'shortcuts-help-overlay';
    overlay.className = 'shortcuts-help';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-label', 'Keyboard shortcuts');
    overlay.innerHTML =
      '<div class="shortcuts-help-modal">' +
        '<div class="shortcuts-help-head">' +
          '<h2 class="shortcuts-help-title">Keyboard shortcuts</h2>' +
          '<button type="button" class="shortcuts-help-close" aria-label="Close">×</button>' +
        '</div>' +
        '<ul class="shortcuts-help-list"></ul>' +
      '</div>';
    var list = overlay.querySelector('.shortcuts-help-list');
    var isMac = typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform);
    SHORTCUTS.forEach(function (s) {
      var li = document.createElement('li');
      li.className = 'shortcuts-help-item';
      li.innerHTML =
        '<kbd class="shortcuts-help-kbd">' + (isMac ? s.mac : s.keys) + '</kbd>' +
        '<span class="shortcuts-help-desc">' + escapeHtml(s.desc) + '</span>';
      list.appendChild(li);
    });
    overlay.querySelector('.shortcuts-help-close').addEventListener('click', close);
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) close();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && overlay.classList.contains('is-open')) close();
    });
    document.body.appendChild(overlay);
    return overlay;
  }
  function escapeHtml(s) {
    var div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }
  function open() {
    createOverlay();
    overlay.classList.add('is-open');
    overlay.querySelector('.shortcuts-help-close').focus();
  }
  function close() {
    if (overlay) overlay.classList.remove('is-open');
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      var tag = (e.target && e.target.tagName) || '';
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target && e.target.isContentEditable)) return;
      e.preventDefault();
      open();
    }
  });
})();
