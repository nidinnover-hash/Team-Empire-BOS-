/**
 * Ctrl+K / Cmd+K global command palette.
 * Combines page navigation, quick actions, and API search.
 */
(function () {
  'use strict';

  /* ── Static commands (always available) ─────────────────────────────── */
  var NAV_COMMANDS = [
    { type: 'nav', title: 'Dashboard', icon: 'layout-dashboard', href: '/' },
    { type: 'nav', title: 'Agent Chat', icon: 'message-circle', href: '/web/talk' },
    { type: 'nav', title: 'Strategy', icon: 'lightbulb', href: '/web/strategy' },
    { type: 'nav', title: 'Tasks', icon: 'check-square', href: '/web/tasks' },
    { type: 'nav', title: 'Projects', icon: 'folder-kanban', href: '/web/projects' },
    { type: 'nav', title: 'Contacts', icon: 'contact', href: '/web/contacts' },
    { type: 'nav', title: 'Finance', icon: 'wallet', href: '/web/finance' },
    { type: 'nav', title: 'Workspaces', icon: 'brain', href: '/web/workspaces' },
    { type: 'nav', title: 'Integrations', icon: 'plug', href: '/web/integrations' },
    { type: 'nav', title: 'Notifications', icon: 'bell', href: '/web/notifications' },
    { type: 'nav', title: 'API Docs', icon: 'book-open', href: '/docs' },
    { type: 'action', title: 'Toggle dark mode', icon: 'moon', action: 'toggle-theme' },
  ];

  var esc = function (t) {
    return String(t == null ? '' : t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  };

  /* ── Build DOM ──────────────────────────────────────────────────────── */
  var overlay = document.createElement('div');
  overlay.id = 'cmd-palette';
  overlay.innerHTML =
    '<div class="cmd-modal">' +
      '<div class="cmd-search-row">' +
        '<svg class="cmd-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>' +
        '<input id="cmd-input" type="text" placeholder="Type a command or search..." autocomplete="off" spellcheck="false" />' +
        '<kbd class="cmd-kbd">esc</kbd>' +
      '</div>' +
      '<div id="cmd-results"></div>' +
    '</div>';
  document.body.appendChild(overlay);

  /* ── Styles ─────────────────────────────────────────────────────────── */
  var style = document.createElement('style');
  style.textContent = [
    '#cmd-palette{display:none;position:fixed;inset:0;background:rgba(0,0,0,.4);-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px);z-index:9999;align-items:flex-start;justify-content:center;padding-top:min(18vh,140px)}',
    '#cmd-palette.open{display:flex}',
    '.cmd-modal{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius-lg,10px);width:min(520px,92vw);max-height:min(420px,60vh);overflow:hidden;box-shadow:var(--shadow-lg);display:flex;flex-direction:column}',
    '.cmd-search-row{display:flex;align-items:center;gap:.5rem;padding:.6rem .75rem;border-bottom:1px solid var(--line-soft)}',
    '.cmd-search-icon{color:var(--text-faint);flex-shrink:0}',
    '#cmd-input{flex:1;border:none;outline:none;background:transparent;color:var(--text);font-size:var(--text-base,.85rem);font-family:var(--font,sans-serif)}',
    '#cmd-input::placeholder{color:var(--text-faint)}',
    '.cmd-kbd{font-size:.6rem;padding:.1rem .35rem;border:1px solid var(--line);border-radius:4px;color:var(--text-faint);background:var(--surface-alt);font-family:var(--font);line-height:1.4}',
    '#cmd-results{overflow-y:auto;flex:1}',
    '.cmd-group{padding:.3rem 0}',
    '.cmd-group-label{padding:.2rem .75rem;font-size:.62rem;text-transform:uppercase;letter-spacing:.06em;color:var(--text-faint);font-weight:600}',
    '.cmd-item{display:flex;align-items:center;gap:.55rem;padding:.4rem .75rem;cursor:pointer;font-size:var(--text-sm,.78rem);color:var(--text);border-radius:var(--radius-sm,6px);margin:1px .4rem;transition:background .1s}',
    '.cmd-item:hover,.cmd-item.active{background:var(--brand-soft,rgba(0,122,255,.08))}',
    '.cmd-item.active{color:var(--brand)}',
    '.cmd-item-icon{width:18px;height:18px;opacity:.45;flex-shrink:0}',
    '.cmd-item-icon svg{width:18px;height:18px}',
    '.cmd-item-title{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.cmd-item-type{font-size:.6rem;text-transform:uppercase;letter-spacing:.04em;padding:.1rem .35rem;border-radius:3px;color:var(--text-faint);background:var(--surface-alt);white-space:nowrap}',
    '.cmd-item-shortcut{font-size:.6rem;color:var(--text-faint);margin-left:auto}',
    '.cmd-empty{padding:1.5rem;text-align:center;color:var(--text-muted);font-size:var(--text-sm,.78rem)}',
  ].join('\n');
  document.head.appendChild(style);

  var inputEl = document.getElementById('cmd-input');
  var resultsEl = document.getElementById('cmd-results');
  var activeIndex = -1;
  var currentItems = [];
  var debounceTimer = null;
  var searchAbort = null;

  /* ── Open / Close ───────────────────────────────────────────────────── */
  function open() {
    overlay.classList.add('open');
    inputEl.value = '';
    activeIndex = -1;
    renderCommands('');
    setTimeout(function () { inputEl.focus(); }, 30);
  }
  function close() {
    overlay.classList.remove('open');
    if (searchAbort) searchAbort.abort();
  }

  /* ── Render static commands filtered by query ───────────────────────── */
  function renderCommands(query) {
    var q = query.toLowerCase();
    var filtered = NAV_COMMANDS.filter(function (c) {
      return !q || c.title.toLowerCase().indexOf(q) !== -1;
    });
    currentItems = filtered;
    if (!filtered.length && !q) {
      resultsEl.innerHTML = '<div class="cmd-empty">Start typing...</div>';
      return;
    }

    var navItems = filtered.filter(function (c) { return c.type === 'nav'; });
    var actionItems = filtered.filter(function (c) { return c.type === 'action'; });
    var html = '';

    if (navItems.length) {
      html += '<div class="cmd-group"><div class="cmd-group-label">Navigation</div>';
      navItems.forEach(function (c, i) {
        html += renderItem(c, i);
      });
      html += '</div>';
    }
    if (actionItems.length) {
      html += '<div class="cmd-group"><div class="cmd-group-label">Actions</div>';
      actionItems.forEach(function (c, i) {
        html += renderItem(c, navItems.length + i);
      });
      html += '</div>';
    }
    resultsEl.innerHTML = html;
    if (activeIndex >= 0) highlightItem(activeIndex);
  }

  function renderItem(item, idx) {
    var iconHtml = '<span class="cmd-item-icon"><i data-lucide="' + esc(item.icon || 'circle') + '"></i></span>';
    var typeTag = item.type === 'search' ? '<span class="cmd-item-type">' + esc(item.searchType || '') + '</span>' : '';
    return '<div class="cmd-item" data-idx="' + idx + '">' +
      iconHtml +
      '<span class="cmd-item-title">' + esc(item.title) + '</span>' +
      typeTag +
    '</div>';
  }

  function highlightItem(idx) {
    var items = resultsEl.querySelectorAll('.cmd-item');
    items.forEach(function (el) { el.classList.remove('active'); });
    if (idx >= 0 && idx < items.length) {
      items[idx].classList.add('active');
      items[idx].scrollIntoView({ block: 'nearest' });
    }
  }

  /* ── API Search ─────────────────────────────────────────────────────── */
  async function getToken() {
    if (window.__apiToken) return window.__apiToken;
    if (window.__bootPromise) return await window.__bootPromise;
    try {
      var r = await fetch('/web/api-token');
      var d = await r.json();
      window.__apiToken = d.token;
      return d.token;
    } catch (_) { return null; }
  }

  async function doSearch(query) {
    if (!query || query.length < 2) return;
    var token = await getToken();
    if (!token) return;
    if (searchAbort) searchAbort.abort();
    searchAbort = new AbortController();
    try {
      var res = await fetch('/api/v1/search?q=' + encodeURIComponent(query), {
        headers: { Authorization: 'Bearer ' + token },
        signal: searchAbort.signal,
      });
      if (!res.ok) return;
      var data = await res.json();
      if (!data.results || !data.results.length) {
        var noResultEl = document.createElement('div');
        noResultEl.className = 'cmd-empty';
        noResultEl.textContent = 'No results for \u201c' + query + '\u201d';
        resultsEl.appendChild(noResultEl);
        return;
      }

      // Append search results below nav commands
      var searchItems = data.results.slice(0, 8).map(function (r) {
        var routes = { task: '/web/tasks', note: '/web/data-hub', contact: '/web/contacts', project: '/web/projects', goal: '/web/strategy' };
        return {
          type: 'search',
          searchType: r.type || 'result',
          title: r.title || 'Untitled',
          icon: { task: 'check-square', note: 'file-text', contact: 'contact', project: 'folder-kanban', goal: 'target' }[r.type] || 'search',
          href: routes[r.type] || '/',
        };
      });

      var startIdx = currentItems.length;
      currentItems = currentItems.concat(searchItems);

      var group = document.createElement('div');
      group.className = 'cmd-group';
      group.innerHTML = '<div class="cmd-group-label">Search Results</div>' +
        searchItems.map(function (item, i) { return renderItem(item, startIdx + i); }).join('');
      resultsEl.appendChild(group);

      if (typeof lucide !== 'undefined') lucide.createIcons({ nameAttr: 'data-lucide', attrs: { class: '' } });
    } catch (err) {
      if (err && err.name === 'AbortError') return;
    }
  }

  /* ── Execute selected item ──────────────────────────────────────────── */
  function executeItem(idx) {
    var item = currentItems[idx];
    if (!item) return;
    if (item.action === 'toggle-theme') {
      var btn = document.querySelector('.theme-toggle');
      if (btn) btn.click();
      close();
      return;
    }
    if (item.href) {
      if (window.Micro && window.Micro.navigate) {
        window.Micro.navigate(item.href);
      } else {
        window.location.href = item.href;
      }
      close();
    }
  }

  /* ── Input handling ─────────────────────────────────────────────────── */
  inputEl.addEventListener('input', function () {
    var q = inputEl.value.trim();
    activeIndex = -1;
    renderCommands(q);
    if (typeof lucide !== 'undefined') lucide.createIcons({ nameAttr: 'data-lucide', attrs: { class: '' } });

    clearTimeout(debounceTimer);
    if (q.length >= 2) {
      debounceTimer = setTimeout(function () { doSearch(q); }, 300);
    }
  });

  /* ── Keyboard navigation ────────────────────────────────────────────── */
  document.addEventListener('keydown', function (e) {
    // Open/close with Ctrl/Cmd+K
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      if (overlay.classList.contains('open')) close();
      else open();
      return;
    }
    if (!overlay.classList.contains('open')) return;

    if (e.key === 'Escape') {
      e.preventDefault();
      close();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, currentItems.length - 1);
      highlightItem(activeIndex);
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      highlightItem(activeIndex);
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIndex >= 0) executeItem(activeIndex);
      return;
    }
  });

  // Click overlay to close
  overlay.addEventListener('click', function (e) {
    if (e.target === overlay) close();
  });

  // Click result item
  resultsEl.addEventListener('click', function (e) {
    var item = e.target.closest('.cmd-item');
    if (!item) return;
    var idx = parseInt(item.dataset.idx, 10);
    executeItem(idx);
  });

  // Expose for external use
  window.CommandPalette = { open: open, close: close };
})();
