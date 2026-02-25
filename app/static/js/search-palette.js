/**
 * Ctrl+K / Cmd+K global search palette.
 * Requires window.__bootPromise or window.__apiToken to be set for auth.
 */
(function () {
  'use strict';

  // Build overlay + modal
  var overlay = document.createElement('div');
  overlay.id = 'search-overlay';
  overlay.innerHTML =
    '<div id="search-modal">' +
      '<input id="search-input" type="text" placeholder="Search tasks, notes, contacts, projects..." autocomplete="off" />' +
      '<div id="search-results"></div>' +
      '<div id="search-hint" style="padding:0.5rem 0.75rem;font-size:0.7rem;color:var(--text-faint)">Press Escape to close</div>' +
    '</div>';
  document.body.appendChild(overlay);

  // Styles (injected once)
  var style = document.createElement('style');
  style.textContent =
    '#search-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:9999;align-items:flex-start;justify-content:center;padding-top:15vh}' +
    '#search-overlay.open{display:flex}' +
    '#search-modal{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius-lg);width:min(560px,92vw);max-height:60vh;overflow:hidden;box-shadow:var(--shadow-lg);display:flex;flex-direction:column}' +
    '#search-input{border:none;border-bottom:1px solid var(--line);padding:0.75rem;font-size:0.95rem;outline:none;background:transparent;color:var(--text);font-family:var(--font)}' +
    '#search-results{overflow-y:auto;flex:1;max-height:45vh}' +
    '.sr-item{padding:0.55rem 0.75rem;cursor:pointer;display:flex;align-items:center;gap:0.6rem;border-bottom:1px solid var(--line-soft);font-size:0.82rem;color:var(--text)}' +
    '.sr-item:hover{background:var(--surface-alt)}' +
    '.sr-type{font-size:0.65rem;text-transform:uppercase;letter-spacing:0.05em;padding:0.15rem 0.4rem;border-radius:4px;background:var(--info-soft);color:var(--info);border:1px solid var(--info-border);white-space:nowrap}' +
    '.sr-title{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
    '.sr-empty{padding:1.5rem;text-align:center;color:var(--text-muted);font-size:0.82rem}';
  document.head.appendChild(style);

  var inputEl = document.getElementById('search-input');
  var resultsEl = document.getElementById('search-results');
  var debounceTimer = null;
  var searchAbort = null;

  function open() {
    overlay.classList.add('open');
    inputEl.value = '';
    resultsEl.innerHTML = '';
    setTimeout(function () { inputEl.focus(); }, 50);
  }
  function close() {
    overlay.classList.remove('open');
  }

  async function getToken() {
    if (window.__apiToken) return window.__apiToken;
    if (window.__bootPromise) return await window.__bootPromise;
    // Try fetching
    try {
      var r = await fetch('/web/api-token');
      var d = await r.json();
      window.__apiToken = d.token;
      return d.token;
    } catch (_) { return null; }
  }

  async function doSearch(query) {
    if (!query || query.length < 1) { resultsEl.innerHTML = ''; return; }
    var token = await getToken();
    if (!token) { resultsEl.innerHTML = '<div class="sr-empty">Not authenticated</div>'; return; }
    if (searchAbort) searchAbort.abort();
    searchAbort = new AbortController();
    try {
      var res = await fetch('/api/v1/search?q=' + encodeURIComponent(query), {
        headers: { Authorization: 'Bearer ' + token },
        signal: searchAbort.signal,
      });
      if (!res.ok) throw new Error(res.status);
      var data = await res.json();
      if (!data.results || !data.results.length) {
        var noResultEl = document.createElement('div');
        noResultEl.className = 'sr-empty';
        noResultEl.textContent = 'No results for "' + query + '"';
        resultsEl.innerHTML = '';
        resultsEl.appendChild(noResultEl);
        return;
      }
      resultsEl.innerHTML = data.results.map(function (r) {
        var safeType = String(r.type || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        var safeId = String(r.id || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        var safeTitle = (r.title || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').substring(0,80);
        return '<div class="sr-item" data-type="' + safeType + '" data-id="' + safeId + '">' +
          '<span class="sr-type">' + safeType + '</span>' +
          '<span class="sr-title">' + safeTitle + '</span>' +
        '</div>';
      }).join('');
    } catch (err) {
      if (err && err.name === 'AbortError') return;
      resultsEl.innerHTML = '<div class="sr-empty">Search failed</div>';
    }
  }

  inputEl.addEventListener('input', function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () { doSearch(inputEl.value.trim()); }, 250);
  });

  // Keyboard shortcuts
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      if (overlay.classList.contains('open')) close();
      else open();
    }
    if (e.key === 'Escape' && overlay.classList.contains('open')) {
      close();
    }
  });

  // Click overlay to close
  overlay.addEventListener('click', function (e) {
    if (e.target === overlay) close();
  });

  // Click result to navigate
  resultsEl.addEventListener('click', function (e) {
    var item = e.target.closest('.sr-item');
    if (!item) return;
    var type = item.dataset.type;
    // Navigate to the relevant page
    var routes = { task: '/web/tasks', note: '/web/data-hub', contact: '/', project: '/', goal: '/', command: '/' };
    window.location.href = routes[type] || '/';
    close();
  });
})();
