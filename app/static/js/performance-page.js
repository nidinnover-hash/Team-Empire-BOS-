/* Performance Dashboard — Nidin BOS */
(async function () {
  "use strict";

  const token = await window.__bootPromise;
  const H = { Authorization: "Bearer " + token, "Content-Type": "application/json" };
  async function api(p, o) {
    const r = await fetch("/api/v1" + p, { headers: H, ...o });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || r.statusText);
    }
    return r.json();
  }

  function toast(msg, type) {
    if (window.PCUI && window.PCUI.toast) { window.PCUI.toast(msg, type); return; }
    const el = document.createElement("div");
    el.textContent = msg;
    Object.assign(el.style, {
      position: "fixed", bottom: "1rem", right: "1rem", padding: ".6rem 1.2rem",
      borderRadius: ".35rem", fontSize: ".8rem", zIndex: "9999", color: "#fff",
      background: type === "error" ? "#ef4444" : type === "success" ? "#22c55e" : "#3b82f6",
    });
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  }

  function showLoading(elId) {
    const el = document.getElementById(elId);
    if (el) el.innerHTML = '<div class="empty" style="opacity:.5">Loading...</div>';
  }

  /* ── Tab switching ───────────────────────────────────────────────── */
  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      btn.classList.add("active");
      document.querySelectorAll(".panel").forEach(p => (p.style.display = "none"));
      const panel = document.getElementById("panel-" + btn.dataset.tab);
      if (panel) panel.style.display = "";
    });
  });

  /* ── Helpers ─────────────────────────────────────────────────────── */
  function scoreClass(s) { return s >= 0.6 ? "high" : s >= 0.35 ? "mid" : "low"; }
  function pct(v) { return Math.round(v * 100) + "%"; }
  function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

  /* ── Load Org KPIs ──────────────────────────────────────────────── */
  async function loadOrg() {
    showLoading("dept-cards");
    try {
      const d = await api("/performance/org?days=30");
      document.getElementById("k-employees").textContent = d.total_employees;
      document.getElementById("k-depts").textContent = d.total_departments;
      document.getElementById("k-hours").textContent = d.avg_hours?.toFixed(1) || "0";
      document.getElementById("k-focus").textContent = pct(d.avg_focus_ratio || 0);
      document.getElementById("k-tasks").textContent = d.avg_tasks_per_day?.toFixed(1) || "0";

      const grid = document.getElementById("dept-cards");
      if (!d.departments || d.departments.length === 0) {
        grid.innerHTML = '<div class="empty">No departments with data</div>';
        var emptyChart = document.getElementById("perf-trend-chart");
        if (emptyChart) emptyChart.innerHTML = '<div class="empty">No trend data yet</div>';
        return;
      }

      var chartHost = document.getElementById("perf-trend-chart");
      if (chartHost && window.PCChartsLite) {
        var byDept = d.departments.slice(0, 10);
        window.PCChartsLite.renderLineChart(chartHost, {
          caption: "Department-level averages (current window)",
          ariaLabel: "Organization performance trend",
          series: [
            {
              name: "Focus %",
              values: byDept.map(function (dep) { return Number(dep.avg_focus_ratio || 0) * 100; }),
              color: "var(--brand, #0a84ff)"
            },
            {
              name: "Tasks/Day",
              values: byDept.map(function (dep) { return Number(dep.avg_tasks_per_day || 0); }),
              color: "var(--ok, #34c759)"
            },
            {
              name: "Hours/Day",
              values: byDept.map(function (dep) { return Number(dep.avg_hours || 0); }),
              color: "var(--warn, #ff9f0a)"
            }
          ]
        });
      }

      grid.innerHTML = d.departments.map(dept => `
        <div class="dept-card" data-dept-id="${dept.department_id}">
          <div class="dept-card-name">${esc(dept.department_name)}</div>
          <div class="dept-card-meta">
            <span>${dept.employee_count} employees</span>
            <span>${dept.avg_hours?.toFixed(1) || 0}h avg</span>
            <span>Focus ${pct(dept.avg_focus_ratio || 0)}</span>
            <span>${dept.total_tasks} tasks</span>
          </div>
        </div>
      `).join("");

      grid.querySelectorAll(".dept-card").forEach(card => {
        card.addEventListener("click", () => loadDepartment(card.dataset.deptId));
      });
    } catch (e) { toast("Failed to load org data: " + e.message, "error"); }
  }

  /* ── Load Automation Level ──────────────────────────────────────── */
  async function loadAutomation() {
    try {
      const d = await api("/governance/automation-level");
      document.getElementById("k-auto").textContent = pct(d.current_level || 0.05);
    } catch (_e) { /* governance might not have data */ }
  }

  /* ── Load Department Detail ─────────────────────────────────────── */
  async function loadDepartment(deptId) {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelector('[data-tab="departments"]').classList.add("active");
    document.querySelectorAll(".panel").forEach(p => (p.style.display = "none"));
    document.getElementById("panel-departments").style.display = "";

    showLoading("dept-detail");
    try {
      const d = await api(`/performance/department/${deptId}?days=30`);
      const el = document.getElementById("dept-detail");
      if (!d.top_performers || d.top_performers.length === 0) {
        el.innerHTML = `<h3 style="font-size:.9rem;margin-bottom:.5rem">${esc(d.department_name)}</h3><div class="empty">No performance data</div>`;
        return;
      }
      el.innerHTML = `
        <h3 style="font-size:.9rem;margin-bottom:.5rem">${esc(d.department_name)} — ${d.employee_count} employees</h3>
        ${d.top_performers.map((e, i) => `
          <div class="perf-card">
            <div class="rank">#${i + 1}</div>
            <div class="perf-card-body">
              <div class="perf-card-name">${esc(e.employee_name)}</div>
              <div class="perf-card-stats">
                <span>${e.avg_hours?.toFixed(1)}h/day</span>
                <span>Focus ${pct(e.avg_focus_ratio || 0)}</span>
                <span>${e.avg_tasks_per_day?.toFixed(1)} tasks/day</span>
              </div>
            </div>
            <div class="score ${scoreClass(e.composite_score)}">${(e.composite_score * 100).toFixed(0)}</div>
          </div>
        `).join("")}
      `;
    } catch (e) { toast("Failed to load department: " + e.message, "error"); }
  }

  /* ── Load Top Performers ────────────────────────────────────────── */
  async function loadTop() {
    showLoading("top-list");
    try {
      const data = await api("/performance/top?days=30&limit=15");
      const el = document.getElementById("top-list");
      if (!data || data.length === 0) {
        el.innerHTML = '<div class="empty">No performance data yet</div>';
        return;
      }
      el.innerHTML = data.map((e, i) => `
        <div class="perf-card">
          <div class="rank">#${i + 1}</div>
          <div class="perf-card-body">
            <div class="perf-card-name">${esc(e.employee_name)}</div>
            <div class="perf-card-stats">
              <span>${e.avg_hours?.toFixed(1)}h/day</span>
              <span>Focus ${pct(e.avg_focus_ratio || 0)}</span>
              <span>${e.avg_tasks_per_day?.toFixed(1)} tasks/day</span>
              <span>${e.days_tracked}d tracked</span>
            </div>
          </div>
          <div class="score ${scoreClass(e.composite_score)}">${(e.composite_score * 100).toFixed(0)}</div>
        </div>
      `).join("");
    } catch (e) { toast("Failed to load top performers: " + e.message, "error"); }
  }

  /* ── Load Alerts ────────────────────────────────────────────────── */
  async function loadAlerts() {
    showLoading("alert-list");
    try {
      const data = await api("/performance/alerts?days=30&threshold=0.3");
      const el = document.getElementById("alert-list");
      if (!data || data.length === 0) {
        el.innerHTML = '<div class="empty">No performance alerts</div>';
        return;
      }
      el.innerHTML = data.map(a => `
        <div class="alert-card">
          <div class="alert-card-name">${esc(a.employee_name)}</div>
          <div class="alert-card-reason">${esc(a.alert_reason)}</div>
          <div class="alert-card-score">Score: ${(a.composite_score * 100).toFixed(0)}</div>
        </div>
      `).join("");
    } catch (e) { toast("Failed to load alerts: " + e.message, "error"); }
  }

  /* ── Load Learning Insights ─────────────────────────────────────── */
  async function loadLearning() {
    showLoading("learning-content");
    try {
      const d = await api("/performance/learning-insights?days=90");
      const el = document.getElementById("learning-content");
      const eff = d.effectiveness || {};
      el.innerHTML = `
        <div class="learning-grid">
          <div class="learning-card">
            <div class="lc-label">Total Reports</div>
            <div class="lc-val">${d.total_reports || 0}</div>
          </div>
          <div class="learning-card">
            <div class="lc-label">Approved</div>
            <div class="lc-val">${d.approved_reports || 0}</div>
            <div class="lc-note">Rate: ${pct(d.approval_rate || 0)}</div>
          </div>
          <div class="learning-card">
            <div class="lc-label">Outcomes Tracked</div>
            <div class="lc-val">${eff.total_outcomes || 0}</div>
          </div>
          <div class="learning-card">
            <div class="lc-label">Applied Recommendations</div>
            <div class="lc-val">${eff.applied_count || 0}</div>
            <div class="lc-note">Score: ${((eff.avg_score_when_applied || 0) * 100).toFixed(0)}%</div>
          </div>
          <div class="learning-card">
            <div class="lc-label">Improvement Delta</div>
            <div class="lc-val">${((d.improvement_delta || 0) * 100).toFixed(1)}%</div>
            <div class="lc-note">${esc(d.system_learning || '')}</div>
          </div>
        </div>
      `;
    } catch (e) { toast("Failed to load learning insights: " + e.message, "error"); }
  }

  /* ── AI Coaching Button ─────────────────────────────────────────── */
  document.getElementById("btn-coaching").addEventListener("click", async () => {
    const empId = prompt("Employee ID to generate coaching for:");
    if (!empId || isNaN(parseInt(empId, 10))) return;
    if (!confirm("Generate AI coaching report for employee #" + parseInt(empId, 10) + "?")) return;
    try {
      const r = await api("/performance/employee/" + parseInt(empId, 10) + "/coaching", { method: "POST" });
      toast("Coaching report created (ID: " + r.report_id + "). Status: " + r.status, "success");
    } catch (e) { toast("Coaching failed: " + e.message, "error"); }
  });

  document.getElementById("btn-org-plan").addEventListener("click", async () => {
    if (!confirm("Generate organization-wide AI improvement plan?")) return;
    try {
      const r = await api("/performance/org/improvement-plan", { method: "POST" });
      toast("Org improvement plan created (ID: " + r.report_id + "). Status: " + r.status, "success");
    } catch (e) { toast("Plan generation failed: " + e.message, "error"); }
  });

  /* ── Init ───────────────────────────────────────────────────────── */
  loadOrg();
  loadAutomation();
  loadTop();
  loadAlerts();
  loadLearning();

  if (typeof lucide !== "undefined") lucide.createIcons();
})();
