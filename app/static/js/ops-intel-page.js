window.__bootPromise = fetch('/web/api-token')
      .then(r => { if (!r.ok) throw new Error('Session expired'); return r.json(); })
      .then(d => d.token);
    function esc(s) { const d=document.createElement('div'); d.textContent=String(s??''); return d.innerHTML; }
    function notify(msg, type) {
      if (window.showToast) window.showToast(msg, type || "info");
      else window.alert(msg);
    }

    // Tab switching
    document.querySelectorAll('.tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
      });
    });

    let TOKEN = '';

    async function api(method, path, body) {
      const opts = { method, headers: { 'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json' } };
      if (body) opts.body = JSON.stringify(body);
      const r = await fetch(path, opts);
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `Request failed (${r.status})`);
      return d;
    }

    async function loadEmployees() {
      const data = await api('GET', '/api/v1/ops/employees?active_only=false');
      document.getElementById('k-emp').textContent = data.filter(e => e.is_active).length;
      const tbody = document.getElementById('emp-body');
      if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">No employees mapped</td></tr>';
        return;
      }
      tbody.innerHTML = data.map(e => `<tr>
        <td>${esc(e.name)}</td>
        <td style="color:#666">${esc(e.email)}</td>
        <td>${esc(e.role || '-')}</td>
        <td style="color:#999">${esc(e.github_username || '-')}</td>
        <td style="color:#999">${esc(e.clickup_user_id || '-')}</td>
        <td>${e.is_active ? '<span class="tag ok">Active</span>' : '<span class="tag err">Inactive</span>'}</td>
      </tr>`).join('');
    }

    async function loadDecisions() {
      const data = await api('GET', '/api/v1/ops/decision-log?limit=50');
      document.getElementById('k-decisions').textContent = data.length;
      const tbody = document.getElementById('decisions-body');
      if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">No decisions logged</td></tr>';
        return;
      }
      tbody.innerHTML = data.map(d => {
        const typeClass = d.decision_type === 'approve' ? 'ok' : (d.decision_type === 'reject' ? 'err' : 'warn');
        const dt = d.created_at ? new Date(d.created_at).toLocaleDateString() : '';
        return `<tr>
          <td><span class="tag ${typeClass}">${esc(d.decision_type)}</span></td>
          <td>${esc((d.context || '').substring(0, 80))}</td>
          <td style="color:#666">${esc((d.objective || '').substring(0, 60))}</td>
          <td style="color:#666">${esc((d.reason || '').substring(0, 60))}</td>
          <td style="color:#999">${esc(d.risk || '-')}</td>
          <td style="color:#999">${esc(dt)}</td>
        </tr>`;
      }).join('');
    }

    async function loadPolicies() {
      const data = await api('GET', '/api/v1/ops/policies');
      document.getElementById('k-policies').textContent = data.filter(p => p.is_active).length;
      const tbody = document.getElementById('policies-body');
      if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="empty">No policies yet. Generate drafts from decision patterns.</td></tr>';
        return;
      }
      tbody.innerHTML = data.map(p => `<tr>
        <td>${esc(p.title)}</td>
        <td style="color:#666;font-size:.75rem">${esc((p.rule_text || '').substring(0, 100))}</td>
        <td>${p.is_active ? '<span class="tag ok">Active</span>' : '<span class="tag draft">Draft</span>'}</td>
        <td>${!p.is_active ? `<button class="btn" onclick="activatePolicy(${p.id})">Activate</button>` : '<span style="color:#999;font-size:.72rem">-</span>'}</td>
      </tr>`).join('');
    }

    async function activatePolicy(id) {
      try {
        await api('POST', '/api/v1/ops/policy/activate/' + id);
        await loadPolicies();
        notify("Policy activated.", "success");
      } catch (e) {
        notify(String(e.message || e), "error");
      }
    }

    // Sync buttons
    async function syncSource(source, statusId) {
      const el = document.getElementById(statusId);
      el.textContent = 'syncing...';
      try {
        const d = await api('POST', '/api/v1/ops/sync/' + source);
        if (d.error) {
          el.textContent = d.error;
        } else {
          el.textContent = d.synced + ' synced';
          document.getElementById('k-signals').textContent = parseInt(document.getElementById('k-signals').textContent) + (d.synced || 0);
        }
      } catch(e) {
        el.textContent = String(e.message || 'failed');
        notify(String(e.message || e), "error");
      }
    }

    document.getElementById('btn-sync-clickup').addEventListener('click', () => syncSource('clickup', 'sync-clickup-status'));
    document.getElementById('btn-sync-github').addEventListener('click', () => syncSource('github', 'sync-github-status'));
    document.getElementById('btn-sync-gmail').addEventListener('click', () => syncSource('gmail', 'sync-gmail-status'));
    document.getElementById('btn-sync-cicd').addEventListener('click', async () => {
      const el = document.getElementById('sync-cicd-status');
      el.textContent = 'syncing...';
      try {
        const d = await api('POST', '/api/v1/ops/sync/github-cicd');
        if (d.error) { el.textContent = d.error; }
        else {
          const total = (d.workflow_runs || 0) + (d.deployments || 0);
          el.textContent = d.workflow_runs + ' runs, ' + d.deployments + ' deploys';
          document.getElementById('k-signals').textContent = parseInt(document.getElementById('k-signals').textContent) + total;
        }
      } catch(e) { el.textContent = String(e.message || 'failed'); notify(String(e.message || e), "error"); }
    });
    document.getElementById('btn-compute-metrics').addEventListener('click', async () => {
      const btn = document.getElementById('btn-compute-metrics');
      btn.disabled = true;
      btn.textContent = 'Computing...';
      try {
        const d = await api('POST', '/api/v1/ops/compute/weekly-metrics?weeks=4');
        btn.textContent = `Done (${d.employees_processed || 0} employees)`;
      } catch(e) {
        btn.textContent = 'Failed';
        notify(String(e.message || e), "error");
      }
      setTimeout(() => { btn.textContent = 'Compute Metrics'; btn.disabled = false; }, 3000);
    });

    // Generate policy drafts
    document.getElementById('btn-gen-policies').addEventListener('click', async () => {
      const btn = document.getElementById('btn-gen-policies');
      btn.disabled = true;
      btn.textContent = 'Generating...';
      try {
        await api('POST', '/api/v1/ops/policy/generate');
        await loadPolicies();
        notify("Policy drafts generated.", "success");
      } catch(e) {
        notify(String(e.message || e), "error");
      }
      btn.textContent = 'Generate Drafts';
      btn.disabled = false;
    });

    // Reports
    async function generateReport(type) {
      const container = document.getElementById('report-content');
      container.innerHTML = '<p style="color:#999">Generating report...</p>';
      const today = new Date();
      const day = today.getDay();
      const diff = today.getDate() - day + (day === 0 ? -6 : 1);
      const monday = new Date(today.setDate(diff));
      const weekStart = monday.toISOString().split('T')[0];
      try {
        const d = await api('POST', '/api/v1/ops/reports/weekly?week_start=' + weekStart + '&report_type=' + type);
        container.innerHTML = '<pre style="white-space:pre-wrap;font-family:inherit;font-size:.82rem;line-height:1.6">' + esc(d.content_markdown || 'No content') + '</pre>';
      } catch(e) {
        container.innerHTML = '<p class="empty">Failed to generate report</p>';
        notify(String(e.message || e), "error");
      }
    }
    document.getElementById('btn-report-health').addEventListener('click', () => generateReport('team_health'));
    document.getElementById('btn-report-risk').addEventListener('click', () => generateReport('project_risk'));
    document.getElementById('btn-report-review').addEventListener('click', () => generateReport('founder_review'));

    // Employee modal
    const modalEmp = document.getElementById('modal-emp');
    document.getElementById('btn-add-emp').addEventListener('click', () => { modalEmp.classList.add('open'); });
    document.getElementById('emp-cancel').addEventListener('click', () => { modalEmp.classList.remove('open'); });
    document.getElementById('emp-save').addEventListener('click', async () => {
      const body = {
        name: document.getElementById('emp-name').value,
        email: document.getElementById('emp-email').value,
      };
      const role = document.getElementById('emp-role').value;
      const gh = document.getElementById('emp-github').value;
      const cu = document.getElementById('emp-clickup').value;
      if (role) body.role = role;
      if (gh) body.github_username = gh;
      if (cu) body.clickup_user_id = cu;
      try {
        await api('POST', '/api/v1/ops/employees', body);
        modalEmp.classList.remove('open');
        ['emp-name','emp-email','emp-role','emp-github','emp-clickup'].forEach(id => document.getElementById(id).value = '');
        await loadEmployees();
        notify("Employee saved.", "success");
      } catch (e) {
        notify(String(e.message || e), "error");
      }
    });

    // Decision modal
    const modalDec = document.getElementById('modal-decision');
    document.getElementById('btn-add-decision').addEventListener('click', () => { modalDec.classList.add('open'); });
    document.getElementById('dec-cancel').addEventListener('click', () => { modalDec.classList.remove('open'); });
    document.getElementById('dec-save').addEventListener('click', async () => {
      const body = {
        decision_type: document.getElementById('dec-type').value,
        context: document.getElementById('dec-context').value,
        objective: document.getElementById('dec-objective').value,
        reason: document.getElementById('dec-reason').value,
      };
      const risk = document.getElementById('dec-risk').value;
      if (risk) body.risk = risk;
      try {
        await api('POST', '/api/v1/ops/decision-log', body);
        modalDec.classList.remove('open');
        ['dec-context','dec-objective','dec-reason','dec-risk'].forEach(id => document.getElementById(id).value = '');
        await loadDecisions();
        notify("Decision logged.", "success");
      } catch (e) {
        notify(String(e.message || e), "error");
      }
    });

    // Boot
    async function boot() {
      TOKEN = await window.__bootPromise;
      try {
        await Promise.all([loadEmployees(), loadDecisions(), loadPolicies()]);
        document.getElementById('loading').style.display = 'none';
        document.getElementById('content').style.display = 'block';
      } catch(e) {
        document.getElementById('loading').textContent = 'Failed to load ops data.';
      }
    }
    boot();

    // Logout
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) logoutBtn.addEventListener('click', async () => {
      const csrf = document.cookie.split(';').map(c=>c.trim()).find(c=>c.startsWith('pc_csrf='));
      const csrfVal = csrf ? csrf.split('=')[1] : '';
      try {
        const r = await fetch('/web/logout', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrfVal}});
        if (!r.ok) throw new Error("Logout failed");
        window.location.href = '/web/login';
      } catch (e) {
        notify(String(e.message || e), "error");
      }
    });

    if (typeof lucide !== "undefined") lucide.createIcons();
