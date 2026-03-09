(function () {
  var apiJson = null;
  var fmtDate = null;
  var esc = null;

  function byId(id) { return document.getElementById(id); }

  async function tryApi(paths) {
    for (var i = 0; i < paths.length; i++) {
      try { return await apiJson(paths[i]); } catch (_e) { if (i === paths.length - 1) throw _e; }
    }
  }

  async function refreshSummary() {
    try {
      var summary = await tryApi([
        "/api/v1/workflow-observability/summary",
        "/api/v1/automations/insights?days=7",
      ]);
      var total = summary.total_runs || (summary.summary && summary.summary.total_runs) || 0;
      var awaiting = summary.awaiting_approval || 0;
      var successRate = summary.success_rate || (summary.summary && Math.round(summary.summary.success_rate * 100)) || 0;
      var stuck = summary.stuck_runs || 0;
      byId("wf-m-total").textContent = String(total);
      byId("wf-m-awaiting").textContent = String(awaiting);
      byId("wf-m-success").textContent = String(successRate) + "%";
      byId("wf-m-stuck").textContent = String(stuck);
    } catch (_err) {}
  }

  async function refreshRuns() {
    var filter = byId("workflow-run-filter");
    var qs = filter && filter.value ? "?status=" + encodeURIComponent(filter.value) : "";
    try {
      var runs = await tryApi([
        "/api/v1/workflow-observability/runs" + qs,
        "/api/v1/automations/workflow-runs" + qs,
      ]);
      var el = byId("workflow-run-list");
      if (!el) return;
      if (!runs || !runs.length) {
        el.innerHTML = '<div class="empty">No workflow runs yet. Publish a definition and run it to see results here.</div>';
        return;
      }
      el.innerHTML = runs.map(function (run) {
        var defName = run.definition_name || run.workflow_name || ("Def #" + (run.workflow_definition_id || "?"));
        return '<div class="auto-card status-' + esc(run.status) + '" data-workflow-run="' + run.id + '">' +
          '<div class="auto-card-body">' +
            '<div class="auto-card-name">Run #' + run.id + ' &mdash; ' + esc(defName) + ' <span class="pill">' + esc(run.status.toUpperCase()) + '</span></div>' +
            '<div class="auto-card-meta">' +
              '<span>Step: ' + esc(String(run.current_step_index != null ? run.current_step_index : 0)) + '</span>' +
              '<span>Trigger: ' + esc(run.trigger_source || "manual") + '</span>' +
              (run.started_at ? '<span>Started: ' + esc(fmtDate(run.started_at)) + '</span>' : '') +
              (run.finished_at ? '<span>Finished: ' + esc(fmtDate(run.finished_at)) + '</span>' : '') +
              (run.error_summary ? '<span style="color:var(--danger)">' + esc(run.error_summary.substring(0, 80)) + '</span>' : '') +
            '</div>' +
          '</div>' +
          '<div class="auto-card-actions">' +
            (run.status === "failed" ? '<button class="btn-secondary" type="button" data-retry-run="' + run.id + '">Retry</button>' : '') +
            (run.status === "running" || run.status === "awaiting_approval" ? '<button class="btn-secondary" type="button" data-pause-run="' + run.id + '">Pause</button>' : '') +
            (run.status === "paused" ? '<button class="btn-primary" type="button" data-resume-run="' + run.id + '">Resume</button>' : '') +
          '</div>' +
        '</div>';
      }).join("");
      bindRunActions();
    } catch (_err) {
      var el2 = byId("workflow-run-list");
      if (el2) el2.innerHTML = '<div class="empty">Could not load workflow runs.</div>';
    }
  }

  function bindRunActions() {
    document.querySelectorAll("[data-workflow-run]").forEach(function (card) {
      card.onclick = function (e) {
        if (e.target && e.target.closest("button")) return;
        loadRunDetail(card.getAttribute("data-workflow-run"));
      };
    });
    document.querySelectorAll("[data-retry-run]").forEach(function (btn) {
      btn.onclick = async function () {
        try { await apiJson("/api/v1/automations/workflow-runs/" + btn.getAttribute("data-retry-run") + "/retry", { method: "POST" }); } catch (_e) {}
        await refreshRuns(); await refreshSummary();
      };
    });
    document.querySelectorAll("[data-pause-run]").forEach(function (btn) {
      btn.onclick = async function () {
        try { await apiJson("/api/v1/automations/workflow-runs/" + btn.getAttribute("data-pause-run") + "/pause", { method: "POST" }); } catch (_e) {}
        await refreshRuns(); await refreshSummary();
      };
    });
    document.querySelectorAll("[data-resume-run]").forEach(function (btn) {
      btn.onclick = async function () {
        try { await apiJson("/api/v1/automations/workflow-runs/" + btn.getAttribute("data-resume-run") + "/resume", { method: "POST" }); } catch (_e) {}
        await refreshRuns(); await refreshSummary();
      };
    });
  }

  async function loadRunDetail(runId) {
    var detailEl = byId("workflow-run-detail");
    if (!detailEl) return;
    detailEl.innerHTML = '<div class="empty loading">Loading...</div>';
    try {
      var run = await tryApi([
        "/api/v1/workflow-observability/runs/" + runId,
        "/api/v1/automations/workflow-runs/" + runId,
      ]);
      var stepsHtml = (run.step_runs || []).map(function (step) {
        var cls = step.status === "succeeded" ? "step-chip-ok" :
                  step.status === "failed" ? "step-chip-fail" :
                  step.status === "running" ? "step-chip-run" : "";
        return '<span class="step-chip ' + cls + '">' +
          '<strong>' + esc(step.step_key || ("Step " + step.step_index)) + '</strong> ' +
          esc(step.action_type || "") + ' &rarr; ' + esc(step.status) +
          (step.latency_ms ? ' (' + step.latency_ms + 'ms)' : '') +
          (step.error_text ? '<br><small style="color:var(--danger)">' + esc(step.error_text.substring(0, 120)) + '</small>' : '') +
        '</span>';
      }).join("");

      detailEl.innerHTML =
        '<div class="run-detail-card">' +
          '<div class="run-detail-header">' +
            '<strong>Run #' + esc(String(run.id)) + '</strong>' +
            ' <span class="pill">' + esc((run.status || "").toUpperCase()) + '</span>' +
          '</div>' +
          '<div class="auto-card-meta" style="margin:.4rem 0">' +
            '<span>Trigger: ' + esc(run.trigger_source || "manual") + '</span>' +
            (run.approval_id ? '<span>Approval: #' + esc(String(run.approval_id)) + '</span>' : '') +
            (run.started_at ? '<span>Started: ' + esc(fmtDate(run.started_at)) + '</span>' : '') +
            (run.finished_at ? '<span>Finished: ' + esc(fmtDate(run.finished_at)) + '</span>' : '') +
          '</div>' +
          (run.error_summary ? '<div style="color:var(--danger);font-size:var(--text-sm);margin:.3rem 0">' + esc(run.error_summary) + '</div>' : '') +
          '<h4 style="margin:.5rem 0 .3rem;font-size:var(--text-sm)">Steps</h4>' +
          '<div class="step-chip-row">' + (stepsHtml || '<span class="empty">No steps recorded</span>') + '</div>' +
        '</div>';
    } catch (err) {
      detailEl.textContent = "Failed to load run detail: " + (err.message || err);
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
