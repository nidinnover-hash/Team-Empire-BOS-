(function () {
  var apiJson = null;
  var fmtDate = null;
  var esc = null;

  function byId(id) { return document.getElementById(id); }

  async function refreshSummary() {
    try {
      var summary = await apiJson("/api/v1/workflow-observability/summary");
      byId("wf-m-total").textContent = String(summary.total_runs || 0);
      byId("wf-m-awaiting").textContent = String(summary.awaiting_approval || 0);
      byId("wf-m-success").textContent = String(summary.success_rate || 0) + "%";
      byId("wf-m-stuck").textContent = String(summary.stuck_runs || 0);
    } catch (_err) {}
  }

  async function refreshRuns() {
    var filter = byId("workflow-run-filter");
    var path = "/api/v1/workflow-observability/runs";
    if (filter && filter.value) path += "?status=" + encodeURIComponent(filter.value);
    try {
      var runs = await apiJson(path);
      var el = byId("workflow-run-list");
      if (!el) return;
      if (!runs.length) {
        el.innerHTML = '<div class="empty">No workflow runs yet.</div>';
        return;
      }
      el.innerHTML = runs.map(function (run) {
        return '<div class="auto-card status-' + esc(run.status) + '" data-workflow-run="' + run.id + '">' +
          '<div class="auto-card-body">' +
            '<div class="auto-card-name">Run #' + run.id + ' <span class="pill">' + esc(run.status.toUpperCase()) + '</span></div>' +
            '<div class="auto-card-meta">' +
              '<span>Definition: ' + esc(String(run.workflow_definition_id)) + '</span>' +
              '<span>Step: ' + esc(String(run.current_step_index)) + '</span>' +
              '<span>Started: ' + esc(fmtDate(run.started_at)) + '</span>' +
            '</div>' +
          '</div>' +
          '<div class="auto-card-actions">' +
            (run.status === "failed" ? '<button class="btn-secondary" type="button" data-retry-run="' + run.id + '">Retry</button>' : '') +
            ((run.status === "running" || run.status === "awaiting_approval") ? '<button class="btn-secondary" type="button" data-pause-run="' + run.id + '">Pause</button>' : '') +
            ((run.status === "paused" || run.status === "retry_wait") ? '<button class="btn-primary" type="button" data-resume-run="' + run.id + '">Resume</button>' : '') +
          '</div>' +
        '</div>';
      }).join("");
      bindRunActions();
    } catch (_err) {}
  }

  function bindRunActions() {
    document.querySelectorAll("[data-workflow-run]").forEach(function (card) {
      card.onclick = function (e) {
        if (e.target && e.target.closest("button")) return;
        loadRunDetail(card.getAttribute("data-workflow-run"));
      };
    });
    document.querySelectorAll("[data-retry-run]").forEach(function (btn) {
      btn.onclick = async function () { await apiJson("/api/v1/automations/workflow-runs/" + btn.getAttribute("data-retry-run") + "/retry", { method: "POST" }); await refreshRuns(); await refreshSummary(); };
    });
    document.querySelectorAll("[data-pause-run]").forEach(function (btn) {
      btn.onclick = async function () { await apiJson("/api/v1/automations/workflow-runs/" + btn.getAttribute("data-pause-run") + "/pause", { method: "POST" }); await refreshRuns(); await refreshSummary(); };
    });
    document.querySelectorAll("[data-resume-run]").forEach(function (btn) {
      btn.onclick = async function () { await apiJson("/api/v1/automations/workflow-runs/" + btn.getAttribute("data-resume-run") + "/resume", { method: "POST" }); await refreshRuns(); await refreshSummary(); };
    });
  }

  async function loadRunDetail(runId) {
    try {
      var run = await apiJson("/api/v1/workflow-observability/runs/" + runId);
      byId("workflow-run-detail").innerHTML =
        '<div class="run-detail-card">' +
          '<strong>Run #' + esc(String(run.id)) + '</strong>' +
          '<p>Status: ' + esc(run.status) + '</p>' +
          '<p>Approval: ' + esc(String(run.approval_id || "--")) + '</p>' +
          '<div class="step-chip-row">' +
            (run.step_runs || []).map(function (step) {
              return '<span class="step-chip">Step ' + esc(String(step.step_index)) + ': ' + esc(step.status) + '</span>';
            }).join("") +
          '</div>' +
        '</div>';
    } catch (err) {
      byId("workflow-run-detail").textContent = "Failed to load run detail: " + (err.message || err);
    }
  }

  window.WorkflowRunMonitor = {
    init: function (deps) {
      apiJson = deps.apiJson;
      fmtDate = deps.fmtDate;
      esc = deps.esc;
      if (!byId("workflow-run-list")) return;
      if (byId("workflow-run-filter")) byId("workflow-run-filter").onchange = refreshRuns;
      if (byId("workflow-runs-refresh")) byId("workflow-runs-refresh").onclick = async function () { await refreshSummary(); await refreshRuns(); };
      refreshSummary();
      refreshRuns();
    }
  };
})();
