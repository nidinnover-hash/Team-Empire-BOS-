(async function () {
  var token = null;
  var triggers = [];
  var workflows = [];

  function byId(id) { return document.getElementById(id); }
  function esc(s) { return window.PCUI ? window.PCUI.escapeHtml(s) : String(s).replace(/[&<>"']/g, function(c) { return "&#" + c.charCodeAt(0) + ";"; }); }
  function fmtDate(d) { if (!d) return "--"; try { return new Date(d).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); } catch (_e) { return "--"; } }

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
    ["triggers", "workflows", "studio"].forEach(function(name) {
      var panel = byId("panel-" + name);
      if (panel) panel.style.display = name === tab ? "" : "none";
    });
  }

  function initTabs() {
    document.querySelectorAll(".tab").forEach(function(btn) {
      btn.addEventListener("click", function() {
        showTab(btn.getAttribute("data-tab"));
      });
    });
  }

  async function fetchTriggers() {
    try { triggers = await apiJson("/api/v1/automations/triggers"); } catch (_e) { triggers = []; }
    renderTriggers();
  }

  function renderTriggers() {
    var el = byId("trigger-list");
    if (!el) return;
    if (!triggers.length) {
      el.innerHTML = '<div class="empty">No triggers yet. Create one to automate events.</div>';
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
      await fetchTriggers();
    } catch (e) { alert("Failed to update trigger: " + (e.message || e)); }
  }

  async function deleteTrigger(id) {
    if (!confirm("Delete this trigger?")) return;
    try {
      await apiJson("/api/v1/automations/triggers/" + id, { method: "DELETE" });
      await fetchTriggers();
    } catch (e) { alert("Failed to delete trigger: " + (e.message || e)); }
  }

  async function fetchWorkflows() {
    try { workflows = await apiJson("/api/v1/automations/workflows"); } catch (_e) { workflows = []; }
    renderWorkflows();
  }

  function renderWorkflows() {
    var el = byId("workflow-list");
    if (!el) return;
    if (!workflows.length) {
      el.innerHTML = '<div class="empty">No workflows yet. Create one to orchestrate multi-step processes.</div>';
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
      await fetchWorkflows();
    } catch (e) { alert("Failed to run workflow: " + (e.message || e)); }
  }

  function updateKpis() {
    var activeTriggers = triggers.filter(function(t) { return t.is_active; }).length;
    var totalFires = triggers.reduce(function(s, t) { return s + (t.fire_count || 0); }, 0);
    var running = workflows.filter(function(w) { return w.status === "running"; }).length;
    var completed = workflows.filter(function(w) { return w.status === "completed"; }).length;
    var k = function(id, v) { var e = byId(id); if (e) e.textContent = String(v); };
    k("k-triggers", activeTriggers);
    k("k-fires", totalFires);
    k("k-running", running);
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
        await fetchTriggers();
      } catch (err) { alert("Failed to create trigger: " + (err.message || err)); }
    });

    byId("form-workflow").addEventListener("submit", async function(e) {
      e.preventDefault();
      var f = e.target;
      var stepsRaw = f.steps.value.trim();
      var steps;
      try { steps = JSON.parse(stepsRaw); } catch (_e) { alert("Steps must be valid JSON array"); return; }
      if (!Array.isArray(steps) || !steps.length) { alert("Steps must be a non-empty array"); return; }
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
        await fetchWorkflows();
      } catch (err) { alert("Failed to create workflow: " + (err.message || err)); }
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
      if (copilotResult) copilotResult.innerHTML = '<div class="empty">Thinking...</div>';
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
              copilotResult.innerHTML = '<div class="empty">Workflow "' + esc(saved.name) + '" saved as draft (#' + saved.id + '). Switch to the Workflows tab to review and publish.</div>';
              copilotInput.value = "";
              showTab("workflows");
              await fetchWorkflows();
            } catch (err) { alert("Failed to save: " + (err.message || err)); }
          });
        }
      } catch (err) {
        if (copilotResult) copilotResult.innerHTML = '<div class="empty" style="color:var(--danger)">' + esc(err.message || "Failed to generate plan") + '</div>';
      }
      copilotBtn.disabled = false;
      copilotBtn.textContent = "Generate Plan";
    });
  }

  try {
    await bootToken();
    window.workflowApiJson = apiJson;
    window.workflowApiToken = function () { return token; };
    initTabs();
    initModals();
    initCopilot();
    await Promise.all([fetchTriggers(), fetchWorkflows()]);
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
