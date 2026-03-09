(async function () {
  var token = null;
  var triggers = [];
  var workflows = [];
  var definitions = [];

  function byId(id) { return document.getElementById(id); }
  function esc(s) { return window.PCUI ? window.PCUI.escapeHtml(s) : String(s).replace(/[&<>"']/g, function(c) { return "&#" + c.charCodeAt(0) + ";"; }); }
  function fmtDate(d) { if (!d) return "--"; try { return new Date(d).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); } catch (_e) { return "--"; } }

  // ── Toast Notification ────────────────────────────────────────────────────
  function toast(msg, type) {
    var el = document.createElement("div");
    el.className = "auto-toast " + (type || "info");
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function() { el.classList.add("show"); }, 10);
    setTimeout(function() { el.classList.remove("show"); setTimeout(function() { el.remove(); }, 300); }, 3000);
  }

  async function apiJson(path, opts) {
    if (window.PCAPI && window.PCAPI.safeFetchJson) {
      return window.PCAPI.safeFetchJson(path, {
        method: (opts && opts.method) || "GET",
        headers: (opts && opts.headers) || {},
        body: opts && opts.body,
        auth: true,
        token: token,
      });
    }
    var o = opts || {};
    var h = o.headers || {};
    if (!h.Authorization && token) h.Authorization = "Bearer " + token;
    o.headers = h;
    var r = await fetch(path, o);
    var b = await r.json().catch(function(){ return {}; });
    if (!r.ok) { var e = new Error(b.detail || "Request failed (" + r.status + ")"); e.status = r.status; throw e; }
    return b;
  }

  async function bootToken() {
    if (window.PCAPI && window.PCAPI.getApiToken) { token = await window.PCAPI.getApiToken(); return; }
    var r = await fetch("/web/api-token");
    if (!r.ok) throw new Error("session_expired");
    token = (await r.json()).token;
  }

  function showTab(tab) {
    document.querySelectorAll(".tab").forEach(function(btn) {
      btn.classList.toggle("active", btn.getAttribute("data-tab") === tab);
    });
    ["triggers", "workflows", "studio", "insights"].forEach(function(name) {
      var panel = byId("panel-" + name);
      if (panel) panel.style.display = name === tab ? "" : "none";
    });
    if (tab === "insights" && !insightsLoaded) {
      insightsLoaded = true;
      var periodSel = byId("insights-period");
      fetchInsights(periodSel ? parseInt(periodSel.value, 10) : 30);
    }
    if (tab === "workflows" && !definitionsLoaded) {
      definitionsLoaded = true;
      fetchDefinitions();
    }
  }

  function initTabs() {
    document.querySelectorAll(".tab").forEach(function(btn) {
      btn.addEventListener("click", function() {
        showTab(btn.getAttribute("data-tab"));
      });
    });
  }

  // ── Triggers ────────────────────────────────────────────────────────────

  async function fetchTriggers() {
    try { triggers = await apiJson("/api/v1/automations/triggers"); } catch (_e) { triggers = []; }
    renderTriggers();
  }

  function renderTriggers() {
    var el = byId("trigger-list");
    if (!el) return;
    if (!triggers.length) {
      el.innerHTML = '<div class="empty-state"><div class="empty-icon">&#9889;</div><p>No triggers yet</p><span>Triggers fire automatically when events happen — like a new contact or task completion.</span></div>';
      updateKpis();
      return;
    }
    var html = "";
    triggers.forEach(function(t) {
      var cls = t.is_active ? "" : " inactive";
      var pillCls = t.is_active ? "pill active" : "pill inactive";
      var pillText = t.is_active ? "ACTIVE" : "INACTIVE";
      html += '<div class="auto-card' + cls + '">' +
        '<div class="auto-card-body">' +
          '<div class="auto-card-name">' + esc(t.name) + ' <span class="' + pillCls + '">' + pillText + '</span></div>' +
          (t.description ? '<div class="auto-card-desc">' + esc(t.description) + '</div>' : '') +
          '<div class="auto-card-meta">' +
            '<span>Event: ' + esc(t.source_event) + '</span>' +
            '<span>Action: ' + esc(t.action_type) + '</span>' +
            '<span>Fires: ' + (t.fire_count || 0) + '</span>' +
            (t.last_fired_at ? '<span>Last: ' + fmtDate(t.last_fired_at) + '</span>' : '') +
          '</div>' +
        '</div>' +
        '<div class="auto-card-actions">' +
          '<button class="btn-secondary" data-toggle="' + t.id + '" type="button">' + (t.is_active ? "Disable" : "Enable") + '</button>' +
          '<button class="btn-danger" data-delete-trigger="' + t.id + '" type="button">Delete</button>' +
        '</div>' +
      '</div>';
    });
    el.innerHTML = html;
    el.querySelectorAll("[data-toggle]").forEach(function(btn) {
      btn.addEventListener("click", function() { toggleTrigger(parseInt(btn.getAttribute("data-toggle"), 10)); });
    });
    el.querySelectorAll("[data-delete-trigger]").forEach(function(btn) {
      btn.addEventListener("click", function() { deleteTrigger(parseInt(btn.getAttribute("data-delete-trigger"), 10)); });
    });
    updateKpis();
  }

  async function toggleTrigger(id) {
    var t = triggers.find(function(x) { return x.id === id; });
    if (!t) return;
    try {
      await apiJson("/api/v1/automations/triggers/" + id, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !t.is_active }),
      });
      toast(t.is_active ? "Trigger disabled" : "Trigger enabled", "success");
      await fetchTriggers();
    } catch (e) { toast("Failed to update trigger: " + (e.message || e), "error"); }
  }

  async function deleteTrigger(id) {
    if (!confirm("Delete this trigger?")) return;
    try {
      await apiJson("/api/v1/automations/triggers/" + id, { method: "DELETE" });
      toast("Trigger deleted", "success");
      await fetchTriggers();
    } catch (e) { toast("Failed to delete trigger: " + (e.message || e), "error"); }
  }

  // ── V1 Workflows ────────────────────────────────────────────────────────

  async function fetchWorkflows() {
    try { workflows = await apiJson("/api/v1/automations/workflows"); } catch (_e) { workflows = []; }
    renderWorkflows();
  }

  function renderWorkflows() {
    var el = byId("workflow-list");
    if (!el) return;
    if (!workflows.length) {
      el.innerHTML = '<div class="empty-state"><div class="empty-icon">&#128736;</div><p>No legacy workflows</p><span>Use the Workflow Studio tab to build modern multi-step automations with approval gates.</span></div>';
      updateKpis();
      return;
    }
    var html = "";
    workflows.forEach(function(w) {
      var steps = Array.isArray(w.steps_json) ? w.steps_json : [];
      var progress = steps.length > 0 ? Math.min(w.current_step || 0, steps.length) + "/" + steps.length : "0/0";
      html += '<div class="auto-card status-' + esc(w.status || "draft") + '">' +
        '<div class="auto-card-body">' +
          '<div class="auto-card-name">' + esc(w.name) + ' <span class="pill">' + esc((w.status || "draft").toUpperCase()) + '</span></div>' +
          (w.description ? '<div class="auto-card-desc">' + esc(w.description) + '</div>' : '') +
          '<div class="auto-card-meta">' +
            '<span>Steps: ' + progress + '</span>' +
            (w.started_at ? '<span>Started: ' + fmtDate(w.started_at) + '</span>' : '') +
            (w.finished_at ? '<span>Finished: ' + fmtDate(w.finished_at) + '</span>' : '') +
            (w.error_text ? '<span style="color:var(--danger)">Error: ' + esc(w.error_text.substring(0, 80)) + '</span>' : '') +
          '</div>' +
        '</div>' +
        '<div class="auto-card-actions">' +
          (w.status === "draft" || w.status === "paused" ? '<button class="btn-primary" data-run="' + w.id + '" type="button">Run</button>' : '') +
        '</div>' +
      '</div>';
    });
    el.innerHTML = html;
    el.querySelectorAll("[data-run]").forEach(function(btn) {
      btn.addEventListener("click", function() { runWorkflow(parseInt(btn.getAttribute("data-run"), 10)); });
    });
    updateKpis();
  }

  async function runWorkflow(id) {
    try {
      await apiJson("/api/v1/automations/workflows/" + id + "/run", { method: "POST" });
      toast("Workflow started", "success");
      await fetchWorkflows();
    } catch (e) { toast("Failed to run workflow: " + (e.message || e), "error"); }
  }

  // ── V2 Definitions ────────────────────────────────────────────────────────

  var definitionsLoaded = false;

  async function fetchDefinitions() {
    try { definitions = await apiJson("/api/v1/automations/workflow-definitions"); } catch (_e) { definitions = []; }
    renderDefinitions();
  }

  function renderDefinitions() {
    var el = byId("definitions-list");
    if (!el) return;
    if (!definitions.length) {
      el.innerHTML = '<div class="empty-state"><div class="empty-icon">&#128221;</div><p>No workflow definitions</p><span>Create one using the Studio builder, copilot, or start from a template below.</span></div>';
      return;
    }
    var html = "";
    definitions.forEach(function(d) {
      var steps = Array.isArray(d.steps_json) ? d.steps_json : [];
      var riskCls = d.risk_level === "high" ? "pill-risk-high" : d.risk_level === "low" ? "pill-risk-low" : "pill-risk-med";
      html += '<div class="auto-card status-' + esc(d.status) + '">' +
        '<div class="auto-card-body">' +
          '<div class="auto-card-name">' + esc(d.name) +
            ' <span class="pill">' + esc(d.status.toUpperCase()) + '</span>' +
            ' <span class="pill ' + riskCls + '">' + esc(d.risk_level) + '</span>' +
          '</div>' +
          (d.description ? '<div class="auto-card-desc">' + esc(d.description) + '</div>' : '') +
          '<div class="auto-card-meta">' +
            '<span>v' + (d.version || 1) + '</span>' +
            '<span>' + steps.length + ' steps</span>' +
            '<span>Trigger: ' + esc(d.trigger_mode) + '</span>' +
            (d.published_at ? '<span>Published: ' + fmtDate(d.published_at) + '</span>' : '') +
          '</div>' +
        '</div>' +
        '<div class="auto-card-actions">' +
          (d.status === "draft" ? '<button class="btn-primary" data-publish-def="' + d.id + '" type="button">Publish</button>' : '') +
          (d.status === "published" ? '<button class="btn-primary" data-run-def="' + d.id + '" type="button">Run</button>' : '') +
        '</div>' +
      '</div>';
    });
    el.innerHTML = html;

    el.querySelectorAll("[data-publish-def]").forEach(function(btn) {
      btn.addEventListener("click", function() { publishDefinition(parseInt(btn.getAttribute("data-publish-def"), 10)); });
    });
    el.querySelectorAll("[data-run-def]").forEach(function(btn) {
      btn.addEventListener("click", function() { runDefinition(parseInt(btn.getAttribute("data-run-def"), 10)); });
    });
  }

  async function publishDefinition(id) {
    try {
      await apiJson("/api/v1/automations/workflow-definitions/" + id + "/publish", { method: "POST" });
      toast("Workflow published successfully", "success");
      await fetchDefinitions();
    } catch (e) { toast("Failed to publish: " + (e.message || e), "error"); }
  }

  async function runDefinition(id) {
    try {
      await apiJson("/api/v1/automations/workflow-definitions/" + id + "/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input_json: {}, trigger_source: "manual" }),
      });
      toast("Workflow run started", "success");
      showTab("studio");
    } catch (e) { toast("Failed to start run: " + (e.message || e), "error"); }
  }

  // ── Templates ─────────────────────────────────────────────────────────────

  async function fetchTemplates() {
    var el = byId("template-gallery");
    if (!el) return;
    try {
      var templates = await apiJson("/api/v1/automations/templates");
      if (!templates.length) { el.style.display = "none"; return; }
      var html = '<div class="template-grid">';
      templates.forEach(function(t) {
        html += '<div class="template-card" data-use-template="' + esc(t.id) + '">' +
          '<div class="template-category">' + esc(t.category) + '</div>' +
          '<div class="template-name">' + esc(t.name) + '</div>' +
          '<div class="template-desc">' + esc(t.description) + '</div>' +
          '<div class="auto-card-meta">' +
            '<span>' + t.step_count + ' steps</span>' +
            '<span>' + esc(t.trigger_mode) + '</span>' +
            '<span class="pill ' + (t.risk_level === "high" ? "pill-risk-high" : t.risk_level === "low" ? "pill-risk-low" : "pill-risk-med") + '">' + esc(t.risk_level) + '</span>' +
          '</div>' +
        '</div>';
      });
      html += '</div>';
      el.innerHTML = '<h3>Quick Start Templates</h3>' + html;
      el.querySelectorAll("[data-use-template]").forEach(function(card) {
        card.addEventListener("click", function() { useTemplate(card.getAttribute("data-use-template")); });
      });
    } catch (_e) { el.style.display = "none"; }
  }

  async function useTemplate(templateId) {
    try {
      var saved = await apiJson("/api/v1/automations/templates/" + templateId + "/create", { method: "POST" });
      toast('Draft "' + saved.name + '" created from template', "success");
      definitionsLoaded = false;
      showTab("workflows");
      await fetchDefinitions();
    } catch (e) { toast("Failed to create from template: " + (e.message || e), "error"); }
  }

  // ── Job Queue Status ──────────────────────────────────────────────────────

  async function fetchJobQueueStats() {
    var el = byId("jq-status");
    if (!el) return;
    try {
      var stats = await apiJson("/api/v1/automations/job-queue-stats");
      var workerStatus = stats.worker_running ? "running" : "stopped";
      el.innerHTML =
        '<span class="jq-dot jq-' + workerStatus + '"></span>' +
        '<span>Queue: ' + (stats.pending || 0) + ' pending, ' + (stats.running || 0) + ' running</span>' +
        (stats.dead > 0 ? '<span class="jq-dead">' + stats.dead + ' dead</span>' : '');
    } catch (_e) { el.innerHTML = '<span class="jq-dot jq-stopped"></span><span>Queue unavailable</span>'; }
  }

  function updateKpis() {
    var activeTriggers = triggers.filter(function(t) { return t.is_active; }).length;
    var totalFires = triggers.reduce(function(s, t) { return s + (t.fire_count || 0); }, 0);
    var running = workflows.filter(function(w) { return w.status === "running"; }).length;
    var completed = workflows.filter(function(w) { return w.status === "completed"; }).length;
    var publishedDefs = definitions.filter(function(d) { return d.status === "published"; }).length;
    var k = function(id, v) { var e = byId(id); if (e) e.textContent = String(v); };
    k("k-triggers", activeTriggers);
    k("k-fires", totalFires);
    k("k-running", running + publishedDefs);
    k("k-completed", completed);
  }

  function initModals() {
    var triggerModal = byId("modal-trigger");
    var workflowModal = byId("modal-workflow");
    if (!triggerModal || !workflowModal) return;

    byId("btn-new-trigger").addEventListener("click", function() { triggerModal.style.display = "flex"; });
    byId("modal-trigger-close").addEventListener("click", function() { triggerModal.style.display = "none"; });

    byId("btn-new-workflow").addEventListener("click", function() { workflowModal.style.display = "flex"; });
    byId("modal-workflow-close").addEventListener("click", function() { workflowModal.style.display = "none"; });

    byId("form-trigger").addEventListener("submit", async function(e) {
      e.preventDefault();
      var f = e.target;
      try {
        await apiJson("/api/v1/automations/triggers", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: f.name.value.trim(),
            source_event: f.source_event.value.trim(),
            action_type: f.action_type.value.trim(),
            description: f.description.value.trim() || null,
            requires_approval: f.requires_approval.checked,
          }),
        });
        triggerModal.style.display = "none";
        f.reset();
        toast("Trigger created", "success");
        await fetchTriggers();
      } catch (err) { toast("Failed to create trigger: " + (err.message || err), "error"); }
    });

    byId("form-workflow").addEventListener("submit", async function(e) {
      e.preventDefault();
      var f = e.target;
      var stepsRaw = f.steps.value.trim();
      var steps;
      try { steps = JSON.parse(stepsRaw); } catch (_e) { toast("Steps must be valid JSON array", "error"); return; }
      if (!Array.isArray(steps) || !steps.length) { toast("Steps must be a non-empty array", "error"); return; }
      try {
        await apiJson("/api/v1/automations/workflows", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: f.name.value.trim(),
            description: f.description.value.trim() || null,
            steps: steps,
          }),
        });
        workflowModal.style.display = "none";
        f.reset();
        toast("Workflow created", "success");
        await fetchWorkflows();
      } catch (err) { toast("Failed to create workflow: " + (err.message || err), "error"); }
    });
  }

  function initCopilot() {
    var copilotInput = byId("copilot-input");
    var copilotBtn = byId("copilot-btn");
    var copilotResult = byId("copilot-result");
    if (!copilotInput || !copilotBtn) return;

    copilotBtn.addEventListener("click", async function() {
      var intent = copilotInput.value.trim();
      if (!intent) return;
      copilotBtn.disabled = true;
      copilotBtn.textContent = "Generating...";
      if (copilotResult) copilotResult.innerHTML = '<div class="empty loading">AI is analyzing your intent...</div>';
      try {
        var plan = await apiJson("/api/v1/automations/copilot/plan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ intent: intent }),
        });
        if (copilotResult) {
          var html = '<div class="copilot-plan">' +
            '<h4>' + esc(plan.name) + '</h4>' +
            '<p>' + esc(plan.summary) + '</p>' +
            '<div class="auto-card-meta"><span>Risk: ' + esc(plan.risk_level) + '</span>' +
            '<span>Confidence: ' + Math.round((plan.confidence || 0) * 100) + '%</span></div>' +
            '<div class="copilot-steps">';
          (plan.steps || []).forEach(function(s, i) {
            var badge = s.requires_approval ? ' <span class="pill inactive">APPROVAL</span>' : '';
            html += '<div class="copilot-step">' +
              '<span class="step-num">' + (i + 1) + '</span> ' +
              esc(s.name) + ' <code>' + esc(s.action_type) + '</code>' + badge +
            '</div>';
          });
          html += '</div>' +
            '<button class="btn-primary" id="copilot-save-btn" type="button">Save as Draft Workflow</button>' +
          '</div>';
          copilotResult.innerHTML = html;
          byId("copilot-save-btn").addEventListener("click", async function() {
            try {
              var saved = await apiJson("/api/v1/automations/copilot/plan-and-save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ intent: intent }),
              });
              copilotResult.innerHTML = '<div class="empty">Workflow "' + esc(saved.name) + '" saved as draft (#' + saved.id + ').</div>';
              copilotInput.value = "";
              toast("Draft workflow saved", "success");
              definitionsLoaded = false;
              showTab("workflows");
              await fetchDefinitions();
            } catch (err) { toast("Failed to save: " + (err.message || err), "error"); }
          });
        }
      } catch (err) {
        if (copilotResult) copilotResult.innerHTML = '<div class="empty" style="color:var(--danger)">' + esc(err.message || "Failed to generate plan") + '</div>';
      }
      copilotBtn.disabled = false;
      copilotBtn.textContent = "Generate Plan";
    });
  }

  // ── Insights ──────────────────────────────────────────────────────────────
  var insightsLoaded = false;

  async function fetchInsights(days) {
    days = days || 30;
    try {
      var data = await apiJson("/api/v1/automations/insights?days=" + days);
      renderInsights(data);
    } catch (_e) {
      var el = byId("insights-kpis");
      if (el) el.innerHTML = '<div class="empty">Insights not available.</div>';
    }
  }

  function renderInsights(data) {
    var s = data.summary || {};
    var k = function(id, v) { var e = byId(id); if (e) e.textContent = String(v); };
    k("ik-total", s.total_runs || 0);
    k("ik-completed", s.completed || 0);
    k("ik-failed", s.failed || 0);
    k("ik-rate", s.total_runs ? Math.round(s.success_rate * 100) + "%" : "N/A");
    k("ik-running", s.running || 0);
    k("ik-pending", s.pending || 0);

    renderDailyChart(data.daily_counts || []);
    renderRankings(data.workflow_rankings || []);
    renderStepPerf(data.step_performance || []);
    renderFailures(data.failure_patterns || []);
  }

  function renderDailyChart(daily) {
    var el = byId("insights-daily-chart");
    if (!el) return;
    if (!daily.length) { el.innerHTML = '<div class="empty">No run data yet.</div>'; return; }
    var maxVal = Math.max.apply(null, daily.map(function(d) { return d.total; })) || 1;
    var html = '<div class="daily-bars">';
    daily.forEach(function(d) {
      var pctOk = Math.round((d.completed / maxVal) * 100);
      var pctFail = Math.round((d.failed / maxVal) * 100);
      html += '<div class="daily-bar-col" title="' + esc(d.date) + ': ' + d.total + ' runs">' +
        '<div class="daily-bar-stack">' +
          '<div class="daily-bar ok" style="height:' + pctOk + '%"></div>' +
          '<div class="daily-bar fail" style="height:' + pctFail + '%"></div>' +
        '</div>' +
        '<span>' + esc(d.date.slice(5)) + '</span>' +
      '</div>';
    });
    html += '</div>';
    el.innerHTML = html;
  }

  function renderRankings(rankings) {
    var el = byId("insights-rankings");
    if (!el) return;
    if (!rankings.length) { el.innerHTML = '<div class="empty">No workflow runs yet.</div>'; return; }
    var html = '<table class="insights-table"><thead><tr><th>Workflow</th><th>Runs</th><th>Success</th></tr></thead><tbody>';
    rankings.forEach(function(r) {
      html += '<tr><td>' + esc(r.workflow_name) + '</td><td>' + r.total_runs +
        '</td><td>' + Math.round(r.success_rate * 100) + '%</td></tr>';
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  }

  function renderStepPerf(steps) {
    var el = byId("insights-steps");
    if (!el) return;
    if (!steps.length) { el.innerHTML = '<div class="empty">No step data yet.</div>'; return; }
    var html = '<table class="insights-table"><thead><tr><th>Action</th><th>Count</th><th>Avg ms</th><th>Fail %</th></tr></thead><tbody>';
    steps.forEach(function(s) {
      html += '<tr><td><code>' + esc(s.action_type) + '</code></td><td>' + s.total_executions +
        '</td><td>' + (s.avg_latency_ms != null ? s.avg_latency_ms : '--') +
        '</td><td>' + Math.round(s.failure_rate * 100) + '%</td></tr>';
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  }

  function renderFailures(failures) {
    var el = byId("insights-failures");
    if (!el) return;
    if (!failures.length) { el.innerHTML = '<div class="empty">No failures recorded.</div>'; return; }
    var html = '';
    failures.forEach(function(f) {
      html += '<div class="failure-row">' +
        '<div class="failure-error">' + esc((f.error_summary || "Unknown").substring(0, 120)) + '</div>' +
        '<div class="failure-meta">' + esc(f.workflow_name) + ' &middot; ' + f.count + 'x &middot; Last: ' + fmtDate(f.last_seen) + '</div>' +
      '</div>';
    });
    el.innerHTML = html;
  }

  function initInsights() {
    var periodSel = byId("insights-period");
    if (!periodSel) return;
    periodSel.addEventListener("change", function() {
      fetchInsights(parseInt(periodSel.value, 10));
    });
  }

  try {
    await bootToken();
    window.workflowApiJson = apiJson;
    window.workflowApiToken = function () { return token; };
    initTabs();
    initModals();
    initCopilot();
    initInsights();
    await Promise.all([fetchTriggers(), fetchWorkflows(), fetchTemplates(), fetchJobQueueStats()]);
    if (window.WorkflowBuilderPage && window.WorkflowBuilderPage.init) {
      window.WorkflowBuilderPage.init({ apiJson: apiJson });
    }
    if (window.WorkflowRunMonitor && window.WorkflowRunMonitor.init) {
      window.WorkflowRunMonitor.init({ apiJson: apiJson, fmtDate: fmtDate, esc: esc });
    }
  } catch (e) {
    if (String(e.message || "").includes("session_expired")) {
      window.location.href = "/web/login";
    }
  }
  if (typeof lucide !== "undefined") lucide.createIcons();
})();
