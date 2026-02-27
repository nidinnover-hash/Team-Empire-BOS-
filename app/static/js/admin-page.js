(function () {
  "use strict";

  var token = null;
  var orgs = [];
  var users = [];
  var readinessFleet = [];
  var selectedOrgId = null;
  var fleetStatusFilter = "";
  var trendDays = 7;
  var autonomyPolicy = null;
  var policyBaselineKey = "";
  var _suppressUrlWrite = false;

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatDate(value) {
    if (!value) return "-";
    var d = new Date(value);
    return isNaN(d.getTime()) ? "-" : d.toLocaleDateString();
  }

  function getCsrf() {
    return document.cookie.split(";").reduce(function (acc, c) {
      var p = c.trim().split("=");
      return p[0] === "pc_csrf" ? decodeURIComponent(p[1]) : acc;
    }, "");
  }

  async function getToken() {
    if (token) return token;
    var r = await fetch("/web/api-token", { credentials: "include" });
    if (!r.ok) {
      window.location.href = "/web/login";
      return null;
    }
    token = (await r.json()).token;
    return token;
  }

  function statusPill(status) {
    var text = esc(status || "unknown");
    var css = "status-watch";
    if (status === "ready") css = "status-ready";
    if (status === "blocked") css = "status-blocked";
    if (status === "ok") css = "status-ready";
    if (status === "critical") css = "status-blocked";
    return '<span class="status-pill ' + css + '">' + text + "</span>";
  }

  function modeChip(mode, denied) {
    return '<span class="mode-chip ' + (denied ? "denied" : "allowed") + '">' + esc(mode) + "</span>";
  }

  function readUrlState() {
    var q = new URLSearchParams(window.location.search || "");
    var status = (q.get("status") || "").trim().toLowerCase();
    if (status === "ready" || status === "watch" || status === "blocked") {
      fleetStatusFilter = status;
    } else {
      fleetStatusFilter = "";
    }
    var days = Number(q.get("days") || "7");
    trendDays = (days === 7 || days === 14 || days === 30) ? days : 7;
    var org = Number(q.get("org") || "");
    selectedOrgId = Number.isFinite(org) && org > 0 ? org : null;
  }

  function writeUrlState() {
    if (_suppressUrlWrite) return;
    var q = new URLSearchParams();
    if (fleetStatusFilter) q.set("status", fleetStatusFilter);
    if (trendDays !== 7) q.set("days", String(trendDays));
    if (selectedOrgId) q.set("org", String(selectedOrgId));
    var qs = q.toString();
    var url = window.location.pathname + (qs ? "?" + qs : "");
    window.history.replaceState(null, "", url);
  }

  async function apiGet(path) {
    var tok = await getToken();
    if (!tok) return null;
    var r = await fetch(path, { headers: { Authorization: "Bearer " + tok } });
    if (!r.ok) return null;
    return r.json();
  }

  async function apiPatch(path, payload) {
    var tok = await getToken();
    if (!tok) return null;
    var r = await fetch(path, {
      method: "PATCH",
      headers: {
        Authorization: "Bearer " + tok,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload || {}),
    });
    if (!r.ok) return null;
    return r.json();
  }

  async function apiPost(path, payload) {
    var tok = await getToken();
    if (!tok) return null;
    var headers = { Authorization: "Bearer " + tok };
    var options = { method: "POST", headers: headers };
    if (payload && typeof payload === "object") {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(payload);
    }
    var r = await fetch(path, options);
    if (!r.ok) return null;
    return r.json();
  }

  function setPolicyMessage(text, cls) {
    var msg = document.getElementById("policy-msg");
    if (!msg) return;
    msg.className = "policy-msg" + (cls ? " " + cls : "");
    msg.textContent = text || "";
  }

  function toIsoLocal(value) {
    if (!value) return "-";
    var d = new Date(value);
    if (isNaN(d.getTime())) return "-";
    return d.toLocaleString();
  }

  function renderPolicyMeta(policy) {
    var meta = document.getElementById("policy-meta");
    if (!meta) return;
    if (!policy || !policy.updated_at) {
      meta.textContent = "Not updated yet.";
      return;
    }
    var by = policy.updated_by_email || (policy.updated_by_user_id ? ("user #" + policy.updated_by_user_id) : "unknown");
    meta.textContent = "Last updated: " + toIsoLocal(policy.updated_at) + " by " + by;
  }

  function canonicalPolicy(policy) {
    if (!policy) return "";
    return JSON.stringify({
      current_mode: policy.current_mode || "approved_execution",
      allow_auto_approval: !!policy.allow_auto_approval,
      min_readiness_for_auto_approval: Number(policy.min_readiness_for_auto_approval || 0),
      min_readiness_for_approved_execution: Number(policy.min_readiness_for_approved_execution || 0),
      min_readiness_for_autonomous: Number(policy.min_readiness_for_autonomous || 0),
      block_on_unread_high_alerts: !!policy.block_on_unread_high_alerts,
      block_on_stale_integrations: !!policy.block_on_stale_integrations,
      block_on_sla_breaches: !!policy.block_on_sla_breaches,
    });
  }

  function setSaveButtonEnabled(enabled) {
    var saveBtn = document.getElementById("policy-save-btn");
    if (!saveBtn) return;
    saveBtn.disabled = !enabled;
  }

  function refreshPolicyDirtyState() {
    if (!selectedOrgId || !policyBaselineKey) {
      setSaveButtonEnabled(false);
      return;
    }
    var dirty = canonicalPolicy(readPolicyForm()) !== policyBaselineKey;
    setSaveButtonEnabled(dirty);
  }

  function populatePolicyForm(policy) {
    autonomyPolicy = policy || null;
    var mode = document.getElementById("policy-current-mode");
    var allowAuto = document.getElementById("policy-allow-auto");
    var minAuto = document.getElementById("policy-min-auto");
    var minApproved = document.getElementById("policy-min-approved");
    var minAutonomous = document.getElementById("policy-min-autonomous");
    var blockAlerts = document.getElementById("policy-block-alerts");
    var blockStale = document.getElementById("policy-block-stale");
    var blockSla = document.getElementById("policy-block-sla");
    if (!policy) {
      if (mode) mode.value = "approved_execution";
      if (allowAuto) allowAuto.checked = false;
      if (minAuto) minAuto.value = "70";
      if (minApproved) minApproved.value = "65";
      if (minAutonomous) minAutonomous.value = "90";
      if (blockAlerts) blockAlerts.checked = true;
      if (blockStale) blockStale.checked = true;
      if (blockSla) blockSla.checked = true;
      policyBaselineKey = "";
      renderPolicyMeta(null);
      refreshPolicyDirtyState();
      return;
    }
    if (mode) mode.value = policy.current_mode || "approved_execution";
    if (allowAuto) allowAuto.checked = Boolean(policy.allow_auto_approval);
    if (minAuto) minAuto.value = String(Number(policy.min_readiness_for_auto_approval || 0));
    if (minApproved) minApproved.value = String(Number(policy.min_readiness_for_approved_execution || 0));
    if (minAutonomous) minAutonomous.value = String(Number(policy.min_readiness_for_autonomous || 0));
    if (blockAlerts) blockAlerts.checked = Boolean(policy.block_on_unread_high_alerts);
    if (blockStale) blockStale.checked = Boolean(policy.block_on_stale_integrations);
    if (blockSla) blockSla.checked = Boolean(policy.block_on_sla_breaches);
    policyBaselineKey = canonicalPolicy(policy);
    renderPolicyMeta(policy);
    refreshPolicyDirtyState();
  }

  function readPolicyForm() {
    var modeEl = document.getElementById("policy-current-mode");
    var minAutoEl = document.getElementById("policy-min-auto");
    var minApprovedEl = document.getElementById("policy-min-approved");
    var minAutonomousEl = document.getElementById("policy-min-autonomous");
    var allowAutoEl = document.getElementById("policy-allow-auto");
    var blockAlertsEl = document.getElementById("policy-block-alerts");
    var blockStaleEl = document.getElementById("policy-block-stale");
    var blockSlaEl = document.getElementById("policy-block-sla");
    function clamp(v) {
      var n = Number(v);
      if (!Number.isFinite(n)) return 0;
      return Math.max(0, Math.min(100, Math.round(n)));
    }
    return {
      current_mode: modeEl ? modeEl.value : "approved_execution",
      allow_auto_approval: !!(allowAutoEl && allowAutoEl.checked),
      min_readiness_for_auto_approval: clamp(minAutoEl ? minAutoEl.value : 0),
      min_readiness_for_approved_execution: clamp(minApprovedEl ? minApprovedEl.value : 0),
      min_readiness_for_autonomous: clamp(minAutonomousEl ? minAutonomousEl.value : 0),
      block_on_unread_high_alerts: !!(blockAlertsEl && blockAlertsEl.checked),
      block_on_stale_integrations: !!(blockStaleEl && blockStaleEl.checked),
      block_on_sla_breaches: !!(blockSlaEl && blockSlaEl.checked),
    };
  }

  async function savePolicy() {
    if (!selectedOrgId) return;
    var saveBtn = document.getElementById("policy-save-btn");
    if (saveBtn) saveBtn.disabled = true;
    setPolicyMessage("Saving...", "");
    try {
      var payload = readPolicyForm();
      var updated = await apiPatch("/api/v1/admin/orgs/" + selectedOrgId + "/autonomy-policy", payload);
      if (!updated) {
        setPolicyMessage("Failed to save policy.", "err");
        return;
      }
      populatePolicyForm(updated);
      await loadOrgDetail(selectedOrgId);
      setPolicyMessage("Policy saved.", "ok");
    } finally {
      refreshPolicyDirtyState();
    }
  }

  async function loadAll() {
    var readinessPath = "/api/v1/admin/orgs/readiness";
    if (fleetStatusFilter) readinessPath += "?status=" + encodeURIComponent(fleetStatusFilter);
    try {
      var res = await Promise.all([
        apiGet("/api/v1/admin/orgs"),
        apiGet("/api/v1/admin/users"),
        apiGet(readinessPath),
      ]);
      orgs = Array.isArray(res[0]) ? res[0] : [];
      users = Array.isArray(res[1]) ? res[1] : [];
      readinessFleet = Array.isArray(res[2]) ? res[2] : [];
      if (selectedOrgId && readinessFleet.some(function (r) { return r.org_id === selectedOrgId; })) {
        // keep existing selection
      } else {
        selectedOrgId = readinessFleet.length ? readinessFleet[0].org_id : null;
      }
    } catch (_e) {
      orgs = [];
      users = [];
      readinessFleet = [];
      selectedOrgId = null;
    }
    render();
    writeUrlState();
    if (selectedOrgId) await loadOrgDetail(selectedOrgId);
  }

  function render() {
    var loadingOrgs = document.getElementById("loading-orgs");
    var loadingUsers = document.getElementById("loading-users");
    var loadingReadiness = document.getElementById("loading-readiness");
    if (loadingOrgs) loadingOrgs.style.display = "none";
    if (loadingUsers) loadingUsers.style.display = "none";
    if (loadingReadiness) loadingReadiness.style.display = "none";
    var fleetFilter = document.getElementById("fleet-status-filter");
    if (fleetFilter) fleetFilter.value = fleetStatusFilter;

    document.getElementById("k-orgs").textContent = orgs.length;
    document.getElementById("k-users").textContent = users.length;
    document.getElementById("k-tasks").textContent = orgs.reduce(function (s, o) { return s + (o.task_count || 0); }, 0);
    document.getElementById("k-active").textContent = orgs.filter(function (o) { return o.last_activity_at; }).length;

    var orgTbody = document.getElementById("orgs-body");
    if (!orgs.length) {
      orgTbody.innerHTML = '<tr><td colspan="6" class="empty">No organisations</td></tr>';
    } else {
      orgTbody.innerHTML = orgs.map(function (o) {
        return "<tr>" +
          '<td><span class="org-name">' + esc(o.name) + "</span></td>" +
          '<td><span class="slug-chip">' + esc(o.slug) + "</span></td>" +
          '<td class="num">' + esc(o.user_count) + "</td>" +
          '<td class="num">' + esc(o.task_count) + "</td>" +
          '<td class="num">' + esc(o.approval_count) + "</td>" +
          "<td>" + esc(formatDate(o.last_activity_at)) + "</td>" +
          "</tr>";
      }).join("");
    }

    var readinessBody = document.getElementById("readiness-body");
    if (!readinessFleet.length) {
      readinessBody.innerHTML = '<tr><td colspan="5" class="empty">No readiness data</td></tr>';
    } else {
      readinessBody.innerHTML = readinessFleet.map(function (item) {
        var selectedClass = item.org_id === selectedOrgId ? " selected-row" : "";
        return '<tr class="click-row' + selectedClass + '" data-org-id="' + esc(item.org_id) + '">' +
          "<td>" + esc(item.org_name) + "</td>" +
          '<td class="num">' + esc(item.score) + "</td>" +
          "<td>" + statusPill(item.status) + "</td>" +
          '<td class="num">' + esc(item.blocker_count) + "</td>" +
          "<td>" + esc(formatDate(item.generated_at)) + "</td>" +
          "</tr>";
      }).join("");
      Array.prototype.forEach.call(readinessBody.querySelectorAll("tr.click-row"), function (row) {
        row.addEventListener("click", async function () {
          selectedOrgId = Number(row.getAttribute("data-org-id"));
          render();
          writeUrlState();
          await loadOrgDetail(selectedOrgId);
        });
      });
    }

    var userTbody = document.getElementById("users-body");
    if (!users.length) {
      userTbody.innerHTML = '<tr><td colspan="5" class="empty">No users</td></tr>';
    } else {
      userTbody.innerHTML = users.map(function (u) {
        var superBadge = u.is_super_admin ? '<span class="super-dot" title="Super Admin"></span>' : "";
        return "<tr>" +
          "<td>" + esc(u.name) + "</td>" +
          "<td>" + esc(u.email) + "</td>" +
          '<td><span class="role-chip">' + esc(u.role) + "</span></td>" +
          "<td>Org " + esc(u.organization_id) + "</td>" +
          "<td>" + superBadge + (u.is_active ? "Active" : '<span style="color:#ef4444">Inactive</span>') + "</td>" +
          "</tr>";
      }).join("");
    }
  }

  function renderPolicyHistory(history) {
    var body = document.getElementById("policy-history-body");
    if (!body) return;
    var rows = Array.isArray(history) ? history : [];
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="5" class="empty">No policy history</td></tr>';
      return;
    }
    body.innerHTML = rows.map(function (row) {
      var updatedAt = toIsoLocal(row.updated_at);
      var by = esc(row.updated_by_email || (row.updated_by_user_id ? ("user #" + row.updated_by_user_id) : "-"));
      var mode = esc((row.policy && row.policy.current_mode) || "-");
      var source = row.rollback_of_version_id ? ("rollback " + esc(row.rollback_of_version_id)) : "direct update";
      return "<tr>" +
        "<td>" + esc(updatedAt) + "</td>" +
        "<td>" + by + "</td>" +
        "<td>" + mode + "</td>" +
        "<td>" + source + "</td>" +
        '<td><button class="policy-history-action" data-version-id="' + esc(row.version_id) + '" type="button">Rollback</button></td>' +
        "</tr>";
    }).join("");
    Array.prototype.forEach.call(body.querySelectorAll(".policy-history-action"), function (btn) {
      btn.addEventListener("click", async function () {
        var versionId = btn.getAttribute("data-version-id");
        if (!versionId || !selectedOrgId) return;
        btn.disabled = true;
        setPolicyMessage("Rolling back...", "");
        var out = await apiPost("/api/v1/admin/orgs/" + selectedOrgId + "/autonomy-policy/rollback/" + encodeURIComponent(versionId));
        if (!out) {
          setPolicyMessage("Rollback failed.", "err");
          btn.disabled = false;
          return;
        }
        await loadOrgDetail(selectedOrgId);
        setPolicyMessage("Rollback applied.", "ok");
      });
    });
  }

  function renderDetail(readiness, gates, trend, policy, history) {
    var empty = document.getElementById("readiness-detail-empty");
    var detail = document.getElementById("readiness-detail");
    if (!readiness || !gates || !trend) {
      empty.style.display = "";
      detail.style.display = "none";
      populatePolicyForm(null);
      setPolicyMessage("", "");
      return;
    }
    empty.style.display = "none";
    detail.style.display = "";

    document.getElementById("detail-org-name").textContent = readiness.org_name || "-";
    document.getElementById("detail-score").textContent = String(readiness.score || 0);
    document.getElementById("detail-status").innerHTML = statusPill(readiness.status);

    document.getElementById("detail-allowed-modes").innerHTML = (gates.allowed_modes || []).map(function (m) {
      return modeChip(m, false);
    }).join(" ");
    document.getElementById("detail-denied-modes").innerHTML = (gates.denied_modes || []).map(function (m) {
      return modeChip(m, true);
    }).join(" ");

    var reasonList = document.getElementById("detail-reasons");
    var reasons = (gates.reasons || []).slice(0, 8);
    if (!reasons.length) reasons = ["No blocking reasons."];
    reasonList.innerHTML = reasons.map(function (r) { return "<li>" + esc(r) + "</li>"; }).join("");
    populatePolicyForm(policy || null);
    renderPolicyHistory(history || []);
    setPolicyMessage("", "");

    var trendBody = document.getElementById("trend-body");
    Array.prototype.forEach.call(document.querySelectorAll(".trend-btn"), function (btn) {
      btn.classList.toggle("active", Number(btn.getAttribute("data-days")) === trendDays);
    });
    var series = Array.isArray(trend.series) ? trend.series : [];
    if (!series.length) {
      trendBody.innerHTML = '<tr><td colspan="4" class="empty">No trend data</td></tr>';
      return;
    }
    trendBody.innerHTML = series.map(function (p) {
      return "<tr>" +
        "<td>" + esc(p.day) + "</td>" +
        '<td class="num">' + esc(p.integration_failures) + "</td>" +
        '<td class="num">' + esc(p.high_alerts_created) + "</td>" +
        '<td class="num">' + esc(p.pending_approvals_created) + "</td>" +
        "</tr>";
    }).join("");
  }

  async function loadOrgDetail(orgId) {
    if (!orgId) return;
    var data = await Promise.all([
      apiGet("/api/v1/admin/orgs/" + orgId + "/readiness"),
      apiGet("/api/v1/admin/orgs/" + orgId + "/autonomy-gates"),
      apiGet("/api/v1/admin/orgs/" + orgId + "/readiness/trend?days=" + trendDays),
      apiGet("/api/v1/admin/orgs/" + orgId + "/autonomy-policy"),
      apiGet("/api/v1/admin/orgs/" + orgId + "/autonomy-policy/history?limit=12"),
    ]);
    renderDetail(data[0], data[1], data[2], data[3], data[4]);
  }

  var fleetFilter = document.getElementById("fleet-status-filter");
  if (fleetFilter) {
    fleetFilter.addEventListener("change", async function () {
      fleetStatusFilter = fleetFilter.value || "";
      await loadAll();
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll(".trend-btn"), function (btn) {
    btn.addEventListener("click", async function () {
      var nextDays = Number(btn.getAttribute("data-days") || "7");
      if (!nextDays || nextDays === trendDays) return;
      trendDays = nextDays;
      writeUrlState();
      if (selectedOrgId) {
        await loadOrgDetail(selectedOrgId);
      } else {
        renderDetail(null, null, null);
      }
    });
  });

  var logoutBtn = document.getElementById("logout-btn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async function () {
      var csrf = getCsrf();
      await fetch("/web/logout", { method: "POST", credentials: "include", headers: { "X-CSRF-Token": csrf } });
      window.location.href = "/web/login";
    });
  }
  var savePolicyBtn = document.getElementById("policy-save-btn");
  if (savePolicyBtn) {
    savePolicyBtn.addEventListener("click", savePolicy);
  }
  [
    "policy-current-mode",
    "policy-allow-auto",
    "policy-min-auto",
    "policy-min-approved",
    "policy-min-autonomous",
    "policy-block-alerts",
    "policy-block-stale",
    "policy-block-sla",
  ].forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("change", refreshPolicyDirtyState);
    el.addEventListener("input", refreshPolicyDirtyState);
  });

  _suppressUrlWrite = true;
  readUrlState();
  _suppressUrlWrite = false;
  window.addEventListener("popstate", function () {
    _suppressUrlWrite = true;
    readUrlState();
    _suppressUrlWrite = false;
    loadAll();
  });

  if (typeof lucide !== "undefined") lucide.createIcons();
  loadAll();
})();
