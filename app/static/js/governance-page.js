/* Governance Dashboard — Nidin BOS */
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
    if (!el) return;
    if (window.PCUI && typeof window.PCUI.setSectionState === "function") {
      window.PCUI.setSectionState(el, "loading");
      return;
    }
    el.innerHTML = '<div class="empty" style="opacity:.5">Loading...</div>';
  }

  function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
  let driftTrendDays = 14;
  function normalizeTrendPoints(raw) {
    if (!Array.isArray(raw)) return [];
    return raw.map(point => {
      if (!point || typeof point !== "object") return null;
      const value = Number(point.max_drift_percent);
      if (!Number.isFinite(value)) return null;
      return { value, timestamp: point.timestamp || null };
    }).filter(v => v !== null);
  }

  function renderTrendCard(points, options) {
    const opts = options || {};
    const title = opts.title || "Trend";
    const valueLabel = opts.valueLabel || "";
    const lineClass = opts.lineClass || "";
    const panel = opts.panel || "";
    const days = Number(opts.days || 14);
    const controls = (
      '<span class="trend-controls">' +
      [7, 14, 30].map(d => (
        '<button type="button" class="trend-btn ' + (d === days ? "active" : "") + '" data-trend-panel="' + esc(panel) + '" data-trend-days="' + d + '">' + d + "d</button>"
      )).join("") +
      '</span>'
    );
    if (!Array.isArray(points) || points.length < 2) {
      return (
        '<div class="mini-trend">' +
          '<div class="mini-trend__head"><span>' + esc(title) + '</span><span>' + controls + '</span></div>' +
          '<div class="mini-trend__subhead"><span>' + esc(valueLabel) + '</span><span>No snapshots in selected window.</span></div>' +
          '<div class="mini-trend__empty">Scheduler snapshots are generated automatically.</div>' +
        '</div>'
      );
    }
    const values = points.map(p => Number(p.value || 0));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = (max - min) || 1;
    const width = 260;
    const height = 56;
    const step = values.length > 1 ? (width / (values.length - 1)) : width;
    const coords = values.map((v, idx) => {
      const x = Math.round(idx * step * 100) / 100;
      const y = Math.round((height - ((v - min) / range) * height) * 100) / 100;
      return x + "," + y;
    }).join(" ");
    const last = points[points.length - 1];
    const lastTs = last && last.timestamp ? new Date(last.timestamp) : null;
    const updated = lastTs && !isNaN(lastTs.getTime())
      ? ("Updated " + lastTs.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }))
      : "Updated --";
    return (
      '<div class="mini-trend">' +
        '<div class="mini-trend__head"><span>' + esc(title) + '</span><span>' + controls + '</span></div>' +
        '<div class="mini-trend__subhead"><span>' + esc(valueLabel) + '</span><span>' + esc(updated) + '</span></div>' +
        '<svg class="mini-trend__svg" viewBox="0 0 ' + width + " " + height + '" preserveAspectRatio="none" role="img" aria-label="' + esc(title) + '">' +
          '<polyline class="mini-trend__line ' + esc(lineClass) + '" points="' + coords + '"></polyline>' +
        '</svg>' +
      '</div>'
    );
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

  function pct(v) { return Math.round(v * 100) + "%"; }

  /* ── Load Dashboard KPIs ────────────────────────────────────────── */
  async function loadDashboard() {
    try {
      const d = await api("/governance/dashboard");
      document.getElementById("k-policies").textContent = d.active_policies;
      document.getElementById("k-open").textContent = d.open_violations;
      document.getElementById("k-resolved").textContent = d.resolved_violations;
      document.getElementById("k-rate").textContent = pct(d.compliance_rate || 0);
    } catch (e) { toast("Failed to load dashboard: " + e.message, "error"); }
  }

  /* ── Load Automation Level ──────────────────────────────────────── */
  async function loadAutomation() {
    showLoading("automation-content");
    try {
      const d = await api("/governance/automation-level");
      let drift = null;
      let driftTrend = [];
      try {
        drift = await api("/governance/policy-drift?window_days=14");
        const trendResp = await api("/governance/policy-drift/trend?limit=" + encodeURIComponent(String(driftTrendDays)));
        driftTrend = normalizeTrendPoints(trendResp && trendResp.points);
      } catch (_err) {
        drift = null;
        driftTrend = [];
      }
      document.getElementById("k-auto").textContent = pct(d.current_level || 0.05);

      const el = document.getElementById("automation-content");
      const driftHtml = (!drift || !Array.isArray(drift.signals) || drift.signals.length === 0)
        ? '<div class="drift-empty">No policy drift signals detected in the current window.</div>'
        : (
          '<div class="drift-list">' + drift.signals.slice(0, 6).map(function(s) {
            var sev = String(s.severity || "low").toLowerCase();
            if (["low", "medium", "high"].indexOf(sev) === -1) sev = "low";
            return (
              '<div class="drift-item">' +
                '<div class="drift-item-head">' +
                  '<span class="pill drift-' + sev + '">' + esc(sev) + '</span>' +
                  '<strong>' + esc(s.policy_name || "Policy") + '</strong>' +
                  '<span>' + esc(s.metric || "") + '</span>' +
                '</div>' +
                '<div class="drift-item-meta">' +
                  'Baseline: ' + esc(String(s.baseline)) + ' | Current: ' + esc(String(s.current)) +
                  ' | Drift: ' + esc(String(s.drift_percent)) + '%' +
                '</div>' +
                '<div class="drift-item-meta">' + esc(s.recommendation || "") + '</div>' +
              '</div>'
            );
          }).join("") + '</div>'
        );
      const driftSignals = (drift && Array.isArray(drift.signals)) ? drift.signals : [];
      const maxDrift = driftSignals.reduce(function(acc, signal) {
        const val = Math.abs(Number(signal && signal.drift_percent || 0));
        return val > acc ? val : acc;
      }, 0);
      const driftTrendTone = maxDrift >= 20 ? "danger" : (maxDrift >= 10 ? "warn" : "ok");
      el.innerHTML = `
        <div class="auto-meter">
          <div style="font-size:.85rem;font-weight:700;color:var(--text)">Progressive Automation Level</div>
          <div class="auto-meter-bar">
            <div class="auto-meter-fill" style="width:${pct(d.current_level)}"></div>
          </div>
          <div class="auto-meter-labels">
            <span>5% (Human Control: ${pct(d.human_control)})</span>
            <span>Current: ${pct(d.current_level)}</span>
            <span>Target: 95%</span>
          </div>
          <div class="auto-meta">
            <strong>Data Confidence:</strong> ${pct(d.data_confidence)}<br>
            <strong>Recommendations Applied:</strong> ${d.recommendations_applied} / ${d.recommendations_total}<br>
            <strong>Policy Compliance:</strong> ${pct(d.policy_compliance_rate)}<br>
            <strong>Suggested Next Level:</strong> ${pct(d.suggested_next_level)}<br>
            <strong>Reasoning:</strong> ${esc(d.reasoning)}
          </div>
        </div>
        <div class="auto-meter">
          <div style="font-size:.85rem;font-weight:700;color:var(--text);margin-bottom:.45rem">Policy Drift (14 days)</div>
          ${renderTrendCard(driftTrend, {
            title: "Max Drift Trend (Org Shared)",
            valueLabel: "Now " + Math.round(maxDrift) + "%",
            lineClass: driftTrendTone,
            panel: "drift",
            days: driftTrendDays
          })}
          ${driftHtml}
        </div>
      `;
    } catch (e) { toast("Failed to load automation level: " + e.message, "error"); }
  }

  /* ── Load Policies ──────────────────────────────────────────────── */
  async function loadPolicies() {
    showLoading("policy-list");
    try {
      const data = await api("/governance/policies?active_only=false");
      const el = document.getElementById("policy-list");
      if (!data || data.length === 0) {
        el.innerHTML = '<div class="empty">No governance policies yet</div>';
        return;
      }
      el.innerHTML = data.map(p => `
        <div class="policy-card${p.is_active ? '' : ' inactive'}">
          <div class="policy-card-body">
            <div class="policy-card-name">${esc(p.name)}</div>
            <div class="policy-card-desc">${esc(p.description || '')}</div>
            <div class="policy-card-meta">
              <span class="pill${p.is_active ? ' active' : ''}">${p.is_active ? 'Active' : 'Inactive'}</span>
              <span>${esc(p.policy_type)}</span>
              <span>${p.requires_ceo_approval ? 'CEO approval required' : ''}</span>
            </div>
          </div>
        </div>
      `).join("");
    } catch (e) { toast("Failed to load policies: " + e.message, "error"); }
  }

  /* ── Load Violations ────────────────────────────────────────────── */
  async function loadViolations() {
    showLoading("violation-list");
    try {
      const data = await api("/governance/violations");
      const el = document.getElementById("violation-list");
      if (!data || data.length === 0) {
        el.innerHTML = '<div class="empty">No violations recorded</div>';
        return;
      }
      el.innerHTML = data.map(v => {
        const details = v.details_json || {};
        return `
          <div class="violation-card${v.status === 'resolved' ? ' resolved' : ''}" data-vid="${v.id}">
            <div class="violation-card-body">
              <div class="violation-card-type">${esc(details.policy_name || v.violation_type)}</div>
              <div class="violation-card-details">
                ${esc(details.employee_name || 'Employee #' + v.employee_id)}
                ${details.reasons ? ': ' + details.reasons.map(function(r) { return esc(r); }).join(', ') : ''}
              </div>
              <div style="font-size:.65rem;color:var(--text-faint);margin-top:.15rem">
                Status: ${esc(v.status)} | ${new Date(v.created_at).toLocaleDateString()}
              </div>
            </div>
            ${v.status === 'open' ? '<div class="violation-card-actions"><button class="btn-danger btn-resolve">Resolve</button></div>' : ''}
          </div>
        `;
      }).join("");

      // Event delegation for resolve buttons
      el.querySelectorAll(".btn-resolve").forEach(btn => {
        btn.addEventListener("click", async function(e) {
          const card = e.target.closest("[data-vid]");
          if (!card) return;
          const vid = card.dataset.vid;
          if (!confirm("Resolve violation #" + vid + "?")) return;
          btn.disabled = true;
          try {
            await api("/governance/violations/" + vid + "/resolve?status=resolved", { method: "POST" });
            toast("Violation resolved", "success");
            loadViolations();
            loadDashboard();
          } catch (err) { toast("Failed: " + err.message, "error"); btn.disabled = false; }
        });
      });
    } catch (e) { toast("Failed to load violations: " + e.message, "error"); }
  }

  /* ── New Policy Modal ───────────────────────────────────────────── */
  const modal = document.getElementById("modal-policy");
  document.getElementById("btn-new-policy").addEventListener("click", () => { modal.style.display = "flex"; });
  document.getElementById("modal-policy-close").addEventListener("click", () => { modal.style.display = "none"; });
  modal.addEventListener("click", e => { if (e.target === modal) modal.style.display = "none"; });

  let policySubmitting = false;
  document.getElementById("form-policy").addEventListener("submit", async e => {
    e.preventDefault();
    if (policySubmitting) return;
    policySubmitting = true;
    const submitBtn = e.target.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;

    const fd = new FormData(e.target);
    const rules = {};
    const mh = fd.get("min_hours"); if (mh) rules.min_hours_per_day = parseFloat(mh);
    const mt = fd.get("min_tasks"); if (mt) rules.min_tasks_per_day = parseFloat(mt);
    const mf = fd.get("min_focus"); if (mf) rules.min_focus_ratio = parseFloat(mf);

    try {
      await api("/governance/policies", {
        method: "POST",
        body: JSON.stringify({
          name: fd.get("name"),
          policy_type: fd.get("policy_type"),
          description: fd.get("description") || null,
          rules_json: rules,
        }),
      });
      modal.style.display = "none";
      e.target.reset();
      toast("Policy created", "success");
      loadPolicies();
      loadDashboard();
    } catch (err) { toast("Failed: " + err.message, "error"); }
    finally { policySubmitting = false; if (submitBtn) submitBtn.disabled = false; }
  });

  /* ── Evaluate Compliance ────────────────────────────────────────── */
  document.getElementById("btn-evaluate").addEventListener("click", async () => {
    if (!confirm("Run compliance evaluation across all employees?")) return;
    const btn = document.getElementById("btn-evaluate");
    btn.disabled = true;
    try {
      const violations = await api("/governance/evaluate", { method: "POST" });
      toast("Compliance check complete. " + violations.length + " violation(s) found.", "success");
      loadViolations();
      loadDashboard();
    } catch (e) { toast("Failed: " + e.message, "error"); }
    finally { btn.disabled = false; }
  });

  /* ── Init ───────────────────────────────────────────────────────── */
  loadDashboard();
  loadPolicies();
  loadViolations();
  loadAutomation();
  const automationHost = document.getElementById("automation-content");
  if (automationHost) {
    automationHost.addEventListener("click", function(e) {
      const btn = e.target.closest("[data-trend-panel='drift'][data-trend-days]");
      if (!btn) return;
      const nextDays = Number(btn.getAttribute("data-trend-days"));
      if (!Number.isFinite(nextDays) || nextDays <= 0 || nextDays === driftTrendDays) return;
      driftTrendDays = nextDays;
      loadAutomation();
    });
  }

  if (typeof lucide !== "undefined") lucide.createIcons();
})();
