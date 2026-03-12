(async function () {
  var token = await window.__bootPromise;
  var caps = await (window.PCUI && window.PCUI.loadRoleCapabilities ? window.PCUI.loadRoleCapabilities() : Promise.resolve({}));
  var canAccessCockpit = !!caps.canAccessEmpireCockpit;
  var canManageRouting = !!caps.canManageEmpireRouting;
  var canReviewIntelligence = !!caps.canReviewEmpireIntelligence;
  var esc = function (value) {
    return window.PCUI && window.PCUI.escapeHtml ? window.PCUI.escapeHtml(String(value == null ? "" : value)) : String(value == null ? "" : value);
  };
  var $ = function (id) { return document.getElementById(id); };
  var currentLeadId = null;

  function headers() {
    return { Authorization: "Bearer " + token, "Content-Type": "application/json" };
  }
  async function postJson(path, body) {
    return fetch(path, { method: "POST", headers: headers(), body: JSON.stringify(body || {}) });
  }
  async function patchJson(path, body) {
    return fetch(path, { method: "PATCH", headers: headers(), body: JSON.stringify(body || {}) });
  }
  function selectedLeadIds() {
    return Array.from(document.querySelectorAll(".lead-checkbox:checked")).map(function (node) {
      return Number(node.getAttribute("data-id"));
    }).filter(function (id) { return !!id; });
  }

  function leadStatusActions(status) {
    var current = String(status || "unrouted");
    var map = {
      unrouted: ["under_review", "routed", "closed"],
      under_review: ["routed", "rejected", "closed"],
      routed: ["accepted", "rejected", "closed"],
      accepted: ["closed"],
      rejected: ["closed"],
      closed: [],
    };
    return map[current] || [];
  }

  function renderCounts(containerId, rows, emptyLabel) {
    var host = $(containerId);
    if (!host) return;
    if (!rows || !rows.length) {
      host.innerHTML = '<div class="empty">' + esc(emptyLabel || "No data") + "</div>";
      return;
    }
    host.innerHTML = rows.map(function (row) {
      var label = row && row.label ? row.label : row.key;
      return '<div class="row" style="display:flex;justify-content:space-between;padding:.35rem 0;border-bottom:1px solid var(--line)"><span>' +
        esc(label) + "</span><strong>" + esc(row.count) + "</strong></div>";
    }).join("");
  }

  function trendBadgeText(value) {
    if (value <= 2) return "Low";
    if (value <= 5) return "Watch";
    return "High";
  }

  function applyWarningStrip(data) {
    var warning = $("cockpit-warning");
    if (!warning) return;
    if (!data || !data.stale_warning_triggered) {
      warning.style.display = "none";
      warning.textContent = "";
      return;
    }
    warning.style.display = "block";
    warning.textContent =
      "Routing warning: stale(" + esc(data.stale_unrouted_leads) + "/" + esc(data.stale_warning_threshold_count) +
      "), unrouted(" + esc(data.unrouted_leads) + "/" + esc(data.warning_unrouted_threshold_count) + ").";
  }

  async function loadCockpit() {
    if (!canAccessCockpit) return;
    var resp = await fetch("/api/v1/empire-digital/cockpit", { headers: headers() });
    if (!resp.ok) return;
    var data = await resp.json();
    $("k-total-leads").textContent = String(data.total_visible_leads || 0);
    $("k-unrouted").textContent = String(data.unrouted_leads || 0);
    $("k-stale").textContent = String(data.stale_unrouted_leads || 0);
    $("k-routing-hours").textContent = data.average_routing_hours == null ? "--" : String(data.average_routing_hours);
    $("k-pending-intel").textContent = String(data.pending_intelligence || 0);
    $("k-unrouted-badge").textContent = trendBadgeText(data.unrouted_leads || 0);
    $("k-stale-badge").textContent = trendBadgeText(data.stale_unrouted_leads || 0);
    applyWarningStrip(data);
    renderCounts("aging-buckets", data.unrouted_aging_buckets, "No unrouted leads.");
    renderCounts("lead-types", data.by_lead_type, "No lead type data.");
    renderCounts("routed-companies", data.by_routed_company, "No routing data.");
    renderCounts("top-sources", data.top_sources, "No source data.");
  }

  async function loadScorecard() {
    var section = $("scorecard-section");
    var container = $("scorecard-tiles");
    if (!section || !container) return;
    var resp = await fetch("/api/v1/empire-digital/scorecard?window_days=7", { headers: headers() });
    if (resp.status === 403) {
      section.style.display = "none";
      return;
    }
    if (!resp.ok) {
      container.innerHTML = '<div class="empty">Scorecard unavailable</div>';
      return;
    }
    var data = await resp.json();
    var tiles = data.tiles || [];
    if (!tiles.length) {
      container.innerHTML = '<div class="empty">No scorecard data</div>';
      return;
    }
    container.innerHTML = tiles.map(function (t) {
      var band = (t.band || "green").toLowerCase();
      var targetStr = t.target != null ? " / " + t.target : "";
      return '<div class="kpi scorecard-tile scorecard--' + band + '"><div class="label">' + esc(t.label) + '</div><div class="val">' + esc(t.value) + targetStr + '</div></div>';
    }).join("");
  }

  async function reviewIntelligence(itemId, status, withDecisionCard) {
    if (!canReviewIntelligence) return;
    var resp = await postJson("/api/v1/empire-digital/intelligence/" + itemId + "/review", {
      status: status,
      create_decision_card: !!withDecisionCard,
    });
    if (!resp.ok) return;
    await Promise.all([loadIntelligence(), loadCockpit(), loadFounderReport()]);
  }

  async function loadIntelligence() {
    if (!canAccessCockpit) return;
    var host = $("intel-list");
    if (!host) return;
    var resp = await fetch("/api/v1/empire-digital/intelligence?limit=20", { headers: headers() });
    if (!resp.ok) {
      host.innerHTML = '<div class="empty">Could not load intelligence.</div>';
      return;
    }
    var rows = await resp.json();
    if (!rows.length) {
      host.innerHTML = '<div class="empty">No intelligence submissions yet.</div>';
      return;
    }
    host.innerHTML = rows.map(function (row) {
      var actions = "";
      if (canReviewIntelligence && (row.status === "submitted" || row.status === "reviewing")) {
        actions =
          '<div style="margin-top:.45rem;display:flex;gap:.4rem;flex-wrap:wrap">' +
          '<button type="button" class="btn-primary btn-intel-accept" data-id="' + esc(row.id) + '" style="padding:.3rem .6rem">Accept + Card</button>' +
          '<button type="button" class="btn-intel-reject" data-id="' + esc(row.id) + '" style="padding:.3rem .6rem;border:1px solid var(--line);background:transparent;color:var(--text)">Reject</button>' +
          "</div>";
      }
      return '<div style="padding:.55rem 0;border-bottom:1px solid var(--line)">' +
        '<div style="display:flex;justify-content:space-between;gap:.6rem"><strong>' + esc(row.title) + '</strong><span class="badge">' + esc(row.status) + "</span></div>" +
        '<div style="opacity:.8;font-size:.85rem;margin-top:.2rem">' + esc(row.summary || "") + "</div>" +
        '<div style="opacity:.7;font-size:.75rem;margin-top:.25rem">Source Company: ' + esc(row.source_company_id) + " | Category: " + esc(row.category) + "</div>" +
        actions +
        "</div>";
    }).join("");
    host.querySelectorAll(".btn-intel-accept").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        await reviewIntelligence(Number(btn.getAttribute("data-id")), "accepted", true);
      });
    });
    host.querySelectorAll(".btn-intel-reject").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        await reviewIntelligence(Number(btn.getAttribute("data-id")), "rejected", false);
      });
    });
  }

  async function deactivateRule(ruleId) {
    if (!canManageRouting) return;
    await patchJson("/api/v1/empire-digital/routing-rules/" + ruleId, { is_active: false });
    await loadRoutingRules();
  }

  async function editRule(ruleId, currentPriority, currentTargetCompany, currentReason) {
    if (!canManageRouting) return;
    var priority = await window.PCUI.promptText("Edit Rule", "Priority", String(currentPriority || 100));
    if (!priority) return;
    var targetCompanyId = await window.PCUI.promptText("Edit Rule", "Target company ID", String(currentTargetCompany || 2));
    if (!targetCompanyId) return;
    var reason = await window.PCUI.promptText("Edit Rule", "Routing reason", String(currentReason || ""));
    await patchJson("/api/v1/empire-digital/routing-rules/" + ruleId, {
      priority: Number(priority),
      target_company_id: Number(targetCompanyId),
      routing_reason: reason || null,
    });
    await loadRoutingRules();
  }

  async function loadRoutingRules() {
    var host = $("routing-rules-list");
    if (!host) return;
    if (!canManageRouting) {
      host.innerHTML = '<div class="empty">Restricted. Empire CEO/Admin only.</div>';
      return;
    }
    var resp = await fetch("/api/v1/empire-digital/routing-rules?active_only=true", { headers: headers() });
    if (!resp.ok) {
      host.innerHTML = '<div class="empty">Could not load routing rules.</div>';
      return;
    }
    var rows = await resp.json();
    if (!rows.length) {
      host.innerHTML = '<div class="empty">No active routing rules.</div>';
      return;
    }
    host.innerHTML = rows.map(function (row) {
      return '<div style="padding:.45rem 0;border-bottom:1px solid var(--line)">' +
        "<strong>" + esc(row.lead_type) + "</strong> -> Company " + esc(row.target_company_id) +
        ' <span class="badge">P' + esc(row.priority) + "</span>" +
        (row.routing_reason ? '<div style="opacity:.75;font-size:.8rem">' + esc(row.routing_reason) + "</div>" : "") +
        '<div style="margin-top:.35rem;display:flex;gap:.4rem;flex-wrap:wrap">' +
        '<button type="button" class="btn-rule-edit" data-id="' + esc(row.id) + '" data-priority="' + esc(row.priority) + '" data-target="' + esc(row.target_company_id) + '" data-reason="' + esc(row.routing_reason || "") + '" style="padding:.25rem .55rem;border:1px solid var(--line);background:transparent;color:var(--text)">Edit</button>' +
        '<button type="button" class="btn-rule-off" data-id="' + esc(row.id) + '" style="padding:.25rem .55rem;border:1px solid var(--line);background:transparent;color:var(--text)">Deactivate</button>' +
        "</div></div>";
    }).join("");
    host.querySelectorAll(".btn-rule-edit").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        await editRule(Number(btn.getAttribute("data-id")), Number(btn.getAttribute("data-priority")), Number(btn.getAttribute("data-target")), btn.getAttribute("data-reason"));
      });
    });
    host.querySelectorAll(".btn-rule-off").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        await deactivateRule(Number(btn.getAttribute("data-id")));
      });
    });
  }

  async function loadLeadQueue() {
    if (!canAccessCockpit) return;
    var status = $("lead-filter-status") ? $("lead-filter-status").value : "";
    var type = $("lead-filter-type") ? $("lead-filter-type").value : "";
    var params = "?limit=100";
    if (status) params += "&routing_status=" + encodeURIComponent(status);
    if (type) params += "&lead_type=" + encodeURIComponent(type);
    var host = $("lead-queue-list");
    var resp = await fetch("/api/v1/empire-digital/leads" + params, { headers: headers() });
    if (!resp.ok) {
      host.innerHTML = '<div class="empty">Could not load lead queue.</div>';
      return;
    }
    var rows = await resp.json();
    if (!rows.length) {
      host.innerHTML = '<div class="empty">No leads in this filter.</div>';
      var emptyDetail = $("lead-detail-panel");
      if (emptyDetail) emptyDetail.innerHTML = '<div class="empty">No lead selected.</div>';
      return;
    }
    host.innerHTML = rows.map(function (row) {
      return '<div class="lead-row" data-id="' + esc(row.id) + '" style="display:grid;grid-template-columns:24px 1fr auto;gap:.55rem;padding:.45rem 0;border-bottom:1px solid var(--line);cursor:pointer">' +
        '<input type="checkbox" class="lead-checkbox" data-id="' + esc(row.id) + '" />' +
        '<div><strong>' + esc(row.name) + '</strong><div style="opacity:.75;font-size:.8rem">Type: ' + esc(row.lead_type) + ' | Status: ' + esc(row.routing_status) + ' | Source: ' + esc(row.routing_source || "--") + ' | Rule: ' + esc(row.routing_rule_id || "--") + "</div></div>" +
        '<span class="badge">#' + esc(row.id) + "</span>" +
        "</div>";
    }).join("");
    host.querySelectorAll(".lead-row").forEach(function (rowNode) {
      rowNode.addEventListener("click", async function (ev) {
        var target = ev.target;
        if (target && (target.classList && target.classList.contains("lead-checkbox"))) return;
        var id = Number(rowNode.getAttribute("data-id"));
        if (!id) return;
        currentLeadId = id;
        await loadLeadDetail(id);
      });
    });
    if (currentLeadId) {
      await loadLeadDetail(currentLeadId);
    }
  }

  function renderLeadDetail(row) {
    var host = $("lead-detail-panel");
    if (!host) return;
    if (!row) {
      host.innerHTML = '<div class="empty">Select a lead to view details and actions.</div>';
      return;
    }
    var actions = "";
    if (canManageRouting) {
      actions +=
        '<div style="display:flex;gap:.4rem;flex-wrap:wrap;margin-top:.5rem">' +
        '<button type="button" id="lead-route-now-btn" class="btn-primary">Route Now</button>' +
        '<button type="button" id="lead-escalate-btn" class="btn-primary">Escalate</button>' +
        "</div>";
    }
    var statusButtons = leadStatusActions(row.routing_status).map(function (status) {
      return '<button type="button" class="btn-lead-status" data-status="' + esc(status) + '" style="padding:.25rem .55rem;border:1px solid var(--line);background:transparent;color:var(--text)">' + esc(status) + "</button>";
    }).join("");
    host.innerHTML =
      '<div style="padding:.2rem 0">' +
      '<div style="display:flex;justify-content:space-between;gap:.5rem;align-items:center"><strong>' + esc(row.name) + '</strong><span class="badge">#' + esc(row.id) + "</span></div>" +
      '<div style="opacity:.82;font-size:.83rem;margin-top:.35rem">Type: ' + esc(row.lead_type || "general") + " | Routing Status: " + esc(row.routing_status || "unrouted") + "</div>" +
      '<div style="opacity:.82;font-size:.83rem;margin-top:.2rem">Routing Source: ' + esc(row.routing_source || "default") + " | Rule ID: " + esc(row.routing_rule_id || "--") + "</div>" +
      '<div style="opacity:.82;font-size:.83rem;margin-top:.2rem">Owner Company: ' + esc(row.lead_owner_company_id) + " | Routed Company: " + esc(row.routed_company_id || "unrouted") + "</div>" +
      '<div style="opacity:.82;font-size:.83rem;margin-top:.2rem">Reason: ' + esc(row.routing_reason || "--") + "</div>" +
      '<div style=\"opacity:.82;font-size:.83rem;margin-top:.2rem\">Trail: created ' + esc(row.created_at || "--") + " -> routed " + esc(row.routed_at || "--") + " by " + esc(row.routed_by_user_id || "--") + "</div>" +
      '<div style="opacity:.82;font-size:.83rem;margin-top:.2rem">Qualified: ' + esc(row.qualified_status || "unqualified") + " (" + esc(row.qualified_score || "--") + ")</div>" +
      (statusButtons ? '<div style="display:flex;gap:.35rem;flex-wrap:wrap;margin-top:.55rem">' + statusButtons + "</div>" : "") +
      actions +
      "</div>";
    host.querySelectorAll(".btn-lead-status").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        await setLeadRoutingStatus(Number(row.id), btn.getAttribute("data-status"));
      });
    });
    var routeBtn = $("lead-route-now-btn");
    if (routeBtn) {
      routeBtn.addEventListener("click", async function () {
        await runSingleRoute(Number(row.id));
      });
    }
    var escalateBtn = $("lead-escalate-btn");
    if (escalateBtn) {
      escalateBtn.addEventListener("click", async function () {
        await escalateLead(Number(row.id));
      });
    }
  }

  async function loadLeadDetail(leadId) {
    if (!canAccessCockpit) return;
    var host = $("lead-detail-panel");
    if (!host) return;
    host.innerHTML = '<div class="empty">Loading lead detail...</div>';
    var resp = await fetch("/api/v1/empire-digital/leads/" + encodeURIComponent(String(leadId)), { headers: headers() });
    if (!resp.ok) {
      if (resp.status === 404) {
        host.innerHTML = '<div class="empty">Lead not found in your scope.</div>';
        return;
      }
      host.innerHTML = '<div class="empty">Could not load lead detail.</div>';
      return;
    }
    var row = await resp.json();
    renderLeadDetail(row);
  }

  async function runBulkRoute() {
    if (!canManageRouting) return;
    var ids = selectedLeadIds();
    if (!ids.length) return;
    var leadType = await window.PCUI.promptText("Bulk Route", "Lead type", "general");
    if (!leadType) return;
    var targetCompany = await window.PCUI.promptText("Bulk Route", "Target company ID", "2");
    if (!targetCompany) return;
    await postJson("/api/v1/empire-digital/leads/bulk-route", {
      contact_ids: ids,
      lead_type: leadType,
      routed_company_id: Number(targetCompany),
      routing_reason: "bulk_route_action",
    });
    await Promise.all([loadLeadQueue(), loadCockpit(), loadFounderReport()]);
  }

  async function runSingleRoute(leadId) {
    if (!canManageRouting) return;
    var leadType = await window.PCUI.promptText("Route Lead", "Lead type", "general");
    if (!leadType) return;
    var targetCompany = await window.PCUI.promptText("Route Lead", "Target company ID", "2");
    if (!targetCompany) return;
    await postJson("/api/v1/empire-digital/leads/bulk-route", {
      contact_ids: [Number(leadId)],
      lead_type: leadType,
      routed_company_id: Number(targetCompany),
      routing_reason: "manual_panel_route",
    });
    await Promise.all([loadLeadQueue(), loadCockpit(), loadFounderReport()]);
  }

  async function setLeadRoutingStatus(leadId, status) {
    if (!canAccessCockpit || !status) return;
    await postJson("/api/v1/empire-digital/leads/bulk-qualify", {
      contact_ids: [Number(leadId)],
      routing_status: String(status),
      qualification_notes: "panel_status_action",
    });
    await Promise.all([loadLeadQueue(), loadCockpit(), loadFounderReport()]);
  }

  async function escalateLead(leadId) {
    if (!canManageRouting) return;
    await postJson("/api/v1/empire-digital/leads/escalate-stale", { contact_ids: [Number(leadId)], limit: 1 });
    await loadFounderReport();
  }

  async function runBulkEscalate() {
    if (!canManageRouting) return;
    var ids = selectedLeadIds();
    var body = ids.length ? { contact_ids: ids, limit: ids.length } : { limit: 20 };
    await postJson("/api/v1/empire-digital/leads/escalate-stale", body);
    await loadFounderReport();
  }

  async function runBulkQualify() {
    if (!canAccessCockpit) return;
    var ids = selectedLeadIds();
    if (!ids.length) return;
    var score = await window.PCUI.promptText("Bulk Qualify", "Qualified score (0-100)", "70");
    if (!score) return;
    var status = await window.PCUI.promptText("Bulk Qualify", "Status (qualified/disqualified/needs_review)", "qualified");
    if (!status) return;
    await postJson("/api/v1/empire-digital/leads/bulk-qualify", {
      contact_ids: ids,
      qualified_score: Number(score),
      qualified_status: status,
      qualification_notes: "bulk_qualify_action",
    });
    await Promise.all([loadLeadQueue(), loadCockpit()]);
  }

  async function loadFounderReport() {
    if (!canAccessCockpit) return;
    var host = $("founder-report-list");
    var resp = await fetch("/api/v1/empire-digital/founder-report?window_days=7", { headers: headers() });
    if (!resp.ok) {
      host.innerHTML = '<div class="empty">Could not load founder report.</div>';
      return;
    }
    var data = await resp.json();
    var points = data && data.points ? data.points : [];
    if (!points.length) {
      host.innerHTML = '<div class="empty">No founder report data yet.</div>';
      return;
    }
    host.innerHTML = points.map(function (row) {
      return '<div style="display:grid;grid-template-columns:110px repeat(6, minmax(0,1fr));gap:.45rem;padding:.4rem 0;border-bottom:1px solid var(--line)">' +
        '<strong>' + esc(row.day) + "</strong>" +
        '<span>New: ' + esc(row.leads_created) + "</span>" +
        '<span>Routed: ' + esc(row.leads_routed) + "</span>" +
        '<span>Stale: ' + esc(row.stale_unrouted) + "</span>" +
        '<span>Accepted: ' + esc(row.intelligence_accepted) + "</span>" +
        '<span>Rejected: ' + esc(row.intelligence_rejected) + "</span>" +
        '<span>Escalated: ' + esc(row.escalations_created || 0) + "</span>" +
        "</div>";
    }).join("");
  }

  function exportLeads(format) {
    if (!canAccessCockpit) return;
    window.location.href = "/api/v1/empire-digital/leads/export?format=" + encodeURIComponent(format || "json");
  }

  async function submitInsight() {
    if (!canAccessCockpit) return;
    var title = await window.PCUI.promptText("Marketing Intelligence", "Title", "");
    if (!title) return;
    var summary = await window.PCUI.promptText("Marketing Intelligence", "Summary", "");
    if (!summary) return;
    await postJson("/api/v1/empire-digital/intelligence", { category: "other", title: title, summary: summary });
    await Promise.all([loadIntelligence(), loadCockpit(), loadFounderReport()]);
  }

  async function addRule() {
    if (!canManageRouting) return;
    var leadType = await window.PCUI.promptText("Routing Rule", "Lead type (general/study_abroad/recruitment)", "general");
    if (!leadType) return;
    var targetCompany = await window.PCUI.promptText("Routing Rule", "Target company ID", "2");
    if (!targetCompany) return;
    await postJson("/api/v1/empire-digital/routing-rules", { lead_type: leadType, target_company_id: Number(targetCompany), priority: 100 });
    await loadRoutingRules();
  }

  if (!canAccessCockpit) {
    $("cockpit-warning").style.display = "block";
    $("cockpit-warning").textContent = "Restricted for your role.";
    $("intel-list").innerHTML = '<div class="empty">Restricted for your role.</div>';
    $("routing-rules-list").innerHTML = '<div class="empty">Restricted for your role.</div>';
    $("lead-queue-list").innerHTML = '<div class="empty">Restricted for your role.</div>';
    $("founder-report-list").innerHTML = '<div class="empty">Restricted for your role.</div>';
    return;
  }
  if (!canManageRouting && $("add-rule-btn")) $("add-rule-btn").style.display = "none";
  if (!canManageRouting && $("bulk-route-btn")) $("bulk-route-btn").style.display = "none";
  if (!canManageRouting && $("bulk-escalate-btn")) $("bulk-escalate-btn").style.display = "none";
  if ($("submit-intel-btn")) $("submit-intel-btn").addEventListener("click", submitInsight);
  if ($("add-rule-btn")) $("add-rule-btn").addEventListener("click", addRule);
  if ($("lead-refresh-btn")) $("lead-refresh-btn").addEventListener("click", loadLeadQueue);
  if ($("bulk-route-btn")) $("bulk-route-btn").addEventListener("click", runBulkRoute);
  if ($("bulk-qualify-btn")) $("bulk-qualify-btn").addEventListener("click", runBulkQualify);
  if ($("bulk-escalate-btn")) $("bulk-escalate-btn").addEventListener("click", runBulkEscalate);
  if ($("export-json-btn")) $("export-json-btn").addEventListener("click", function () { exportLeads("json"); });
  if ($("export-csv-btn")) $("export-csv-btn").addEventListener("click", function () { exportLeads("csv"); });
  if ($("founder-report-refresh-btn")) $("founder-report-refresh-btn").addEventListener("click", loadFounderReport);
  if ($("lead-filter-status")) $("lead-filter-status").addEventListener("change", loadLeadQueue);
  if ($("lead-filter-type")) $("lead-filter-type").addEventListener("change", loadLeadQueue);

  await Promise.all([loadCockpit(), loadScorecard(), loadIntelligence(), loadRoutingRules(), loadLeadQueue(), loadFounderReport()]);
  if (typeof lucide !== "undefined") lucide.createIcons();
})();
