window.__bootPromise = fetch('/web/api-token')
      .then(r => { if (!r.ok) throw new Error('Session expired'); return r.json(); })
      .then(d => d.token);
    function esc(s) { const d=document.createElement('div'); d.textContent=String(s??''); return d.innerHTML; }
    async function fetchJsonOrThrow(url, opts) {
      const r = await fetch(url, opts);
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `Request failed (${r.status})`);
      return d;
    }

    async function loadObservability() {
      const token = await window.__bootPromise;
      if (!token) throw new Error('Session expired');
      const h = {'Authorization': 'Bearer ' + token};
      try {
        const [summary, calls, decisions] = await Promise.all([
          fetchJsonOrThrow('/api/v1/observability/summary?days=7', {headers:h}),
          fetchJsonOrThrow('/api/v1/observability/ai-calls?limit=30', {headers:h}),
          fetchJsonOrThrow('/api/v1/observability/decision-traces?limit=15', {headers:h}),
        ]);

        document.getElementById('k-calls').textContent = summary.total_ai_calls;
        document.getElementById('k-fb').textContent = summary.fallback_rate + '%';
        document.getElementById('k-err').textContent = summary.error_rate + '%';
        document.getElementById('k-rej').textContent = summary.rejection_rate + '%';

        // Provider bars
        const ps = document.getElementById('provider-stats');
        if (summary.provider_stats && summary.provider_stats.length) {
          const maxLat = Math.max(...summary.provider_stats.map(p=>p.avg_latency_ms), 1);
          ps.innerHTML = summary.provider_stats.map(p => `
            <div style="margin-bottom:.7rem">
              <div style="display:flex;justify-content:space-between;font-size:.78rem">
                <span style="color:#111">${esc(p.provider)}</span>
                <span style="color:#666">${esc(p.avg_latency_ms)}ms avg / ${esc(p.call_count)} calls</span>
              </div>
              <div class="bar-wrap"><div class="bar-fill" style="width:${Math.round(p.avg_latency_ms/maxLat*100)}%"></div></div>
            </div>
          `).join('');
        }

        // AI calls table
        const tbody = document.getElementById('ai-calls-body');
        if (calls.length) {
          tbody.innerHTML = calls.map(c => {
            let status = '<span class="tag">OK</span>';
            if (c.error_type) status = '<span class="tag err">Error</span>';
            else if (c.used_fallback) status = `<span class="tag fb">Fallback from ${esc(c.fallback_from)}</span>`;
            const t = c.created_at ? new Date(c.created_at).toLocaleTimeString() : '';
            return `<tr><td>${esc(c.provider)}</td><td style="color:#999">${esc(c.model_name)}</td><td>${esc(c.latency_ms)}ms</td><td>${status}</td><td style="color:#999">${esc(t)}</td></tr>`;
          }).join('');
        }

        // Decisions table
        const dbody = document.getElementById('decisions-body');
        if (decisions.length) {
          dbody.innerHTML = decisions.map(d => {
            const conf = (d.confidence_score * 100).toFixed(0) + '%';
            const t = d.created_at ? new Date(d.created_at).toLocaleTimeString() : '';
            return `<tr><td><span class="tag">${esc(d.trace_type)}</span></td><td>${esc(d.title)}</td><td>${esc(conf)}</td><td style="color:#999">${esc(t)}</td></tr>`;
          }).join('');
        }

        document.getElementById('loading').style.display = 'none';
        document.getElementById('content').style.display = 'block';
      } catch(e) {
        document.getElementById('loading').textContent = String(e.message || 'Failed to load metrics.');
      }
    }
    loadObservability();

    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) logoutBtn.addEventListener('click', async () => {
      const csrf = document.cookie.split(';').map(c=>c.trim()).find(c=>c.startsWith('pc_csrf='));
      const csrfVal = csrf ? csrf.split('=')[1] : '';
      try {
        const r = await fetch('/web/logout', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrfVal}});
        if (!r.ok) throw new Error('Logout failed');
        window.location.href = '/web/login';
      } catch (e) {
        alert(String(e.message || e));
      }
    });

    if (typeof lucide !== "undefined") lucide.createIcons();
