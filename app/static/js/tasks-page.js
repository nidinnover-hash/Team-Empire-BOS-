const mapUiError = window.PCUI.mapApiError;

    window.__bootPromise = fetch('/web/api-token')
      .then(r => { if (!r.ok) throw new Error('Session expired'); return r.json(); })
      .then(d => d.token);
    let allTasks = [];
    let currentFilter = 'all';

    async function loadTasks() {
      const container = document.getElementById('task-list');
      const removeSkeleton = window.Micro
        ? window.Micro.skeletonLoad(container, { rows: 5, style: 'list' })
        : function () { container.innerHTML = ''; };
      try {
        const token = await window.__bootPromise;
        if (!token) throw new Error('Session expired');
        allTasks = await window.PCUI.requestJson('/api/v1/tasks?limit=100&is_done=false', {
          auth: true,
          token: token,
        });
        removeSkeleton();
        updateKPIs();
        renderTasks();
      } catch (e) {
        removeSkeleton();
        container.innerHTML = '<div class="empty">' + escHtml(mapUiError(e)) + '</div>';
      }
    }

    function updateKPIs() {
      const openEl = document.getElementById('k-open');
      const highEl = document.getElementById('k-high');
      const openCount = allTasks.length;
      const highCount = allTasks.filter(t=>t.priority>=4).length;
      const sources = new Set(allTasks.map(t=>t.external_source||'internal'));

      openEl.dataset.countTo = openCount;
      openEl.dataset.counted = '';
      highEl.dataset.countTo = highCount;
      highEl.dataset.counted = '';
      document.getElementById('k-src').textContent = sources.size;

      if (window.Micro) window.Micro.countUp(document.querySelector('.kpi-row'));
    }

    function renderTasks() {
      let filtered = allTasks;
      if (currentFilter === 'high') filtered = allTasks.filter(t=>t.priority>=4);
      else if (currentFilter === 'internal') filtered = allTasks.filter(t=>!t.external_source);
      else if (currentFilter !== 'all') filtered = allTasks.filter(t=>t.external_source===currentFilter);

      const container = document.getElementById('task-list');
      if (!filtered.length) {
        if (window.Micro) {
          window.Micro.emptyState(container, {
            icon: 'check-square',
            title: 'No tasks match this filter',
            desc: 'Try a different filter or create a new task.'
          });
        } else {
          container.innerHTML = '<div class="empty">No tasks match this filter</div>';
        }
        return;
      }
      container.innerHTML = filtered.map(t => {
        const pClass = t.priority >= 4 ? 'p-high' : t.priority >= 3 ? 'p-med' : t.priority >= 2 ? 'p-low' : 'p-none';
        const src = t.external_source ? `<span class="task-source">${escHtml(t.external_source)}</span>` : '';
        const due = t.due_date ? ` &middot; due ${escHtml(t.due_date)}` : '';
        return `<div class="task-item${t.is_done?' task-done':''}">
          <div class="p-dot ${pClass}"></div>
          <div class="task-info">
            <div class="task-title">${escHtml(t.title)}</div>
            <div class="task-meta">P${t.priority}${due}${src}</div>
          </div>
        </div>`;
      }).join('');
      if (window.Micro) window.Micro.staggerIn(container);
    }

    function escHtml(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

    document.querySelector('.filters').addEventListener('click', e => {
      const btn = e.target.closest('.filter-btn');
      if (!btn) return;
      document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.dataset.filter;
      renderTasks();
    });

    loadTasks();

    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) logoutBtn.addEventListener('click', async () => {
      if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(logoutBtn, true, 'Signing out...');
      const csrf = document.cookie.split(';').map(c=>c.trim()).find(c=>c.startsWith('pc_csrf='));
      const csrfVal = csrf ? decodeURIComponent(csrf.split('=').slice(1).join('=')) : '';
      try {
        await window.PCUI.requestJson('/web/logout', {
          method: 'POST',
          headers: {'Content-Type':'application/json','X-CSRF-Token':csrfVal},
        });
        window.location.href = '/web/login';
      } catch (e) {
        alert(mapUiError(e));
      } finally {
        if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(logoutBtn, false);
      }
    });

    if (typeof lucide !== "undefined") lucide.createIcons();
