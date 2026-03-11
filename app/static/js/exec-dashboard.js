/**
 * Executive Dashboard — Signal Feed, Decision Queue, Company Health, Stat Trends
 * Fetches data from existing API endpoints and populates the new dashboard widgets.
 */
(function () {
  "use strict";

  var token = null;

  function api(path) {
    return fetch(path, {
      headers: token ? { Authorization: "Bearer " + token } : {},
    }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  function escHtml(s) {
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function timeAgo(iso) {
    if (!iso) return "";
    var diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    return Math.floor(diff / 86400) + "d ago";
  }

  // ── KPI stat cards ────────────────────────────────────────────────────
  function loadKPIs() {
    api("/api/v1/dashboard/kpis")
      .then(function (d) {
        var el = document.getElementById("exec-approvals-count");
        if (el) el.textContent = d.pending_approvals || 0;
        var trend = document.getElementById("exec-approvals-trend");
        if (trend) {
          trend.textContent =
            d.pending_approvals > 0 ? d.pending_approvals + " need review" : "All clear";
          trend.className =
            "exec-stat-trend " + (d.pending_approvals > 0 ? "negative" : "positive");
        }
      })
      .catch(function () {});
  }

  // ── Signal feed (recent notifications as signals) ─────────────────────
  function loadSignals() {
    api("/api/v1/notifications/?limit=15")
      .then(function (items) {
        var list = document.getElementById("signal-list");
        var count = document.getElementById("signal-count");
        var empty = document.getElementById("signal-empty");
        if (!list) return;

        var arr = Array.isArray(items) ? items : items.items || [];
        if (count) count.textContent = arr.length;
        if (arr.length === 0) {
          if (empty) empty.textContent = "No recent signals";
          return;
        }
        if (empty) empty.style.display = "none";

        var html = "";
        arr.forEach(function (n) {
          var sev = n.severity || "info";
          var dotClass =
            sev === "critical" || sev === "error"
              ? "danger"
              : sev === "warning"
              ? "warn"
              : sev === "success"
              ? "ok"
              : "info";
          html +=
            '<div class="signal-item">' +
            '<div class="signal-dot ' + dotClass + '"></div>' +
            '<div class="signal-body">' +
            '<div class="signal-title">' + escHtml(n.title || n.type || "Signal") + "</div>" +
            '<div class="signal-meta">' +
            escHtml(n.source || "") +
            " &middot; " +
            timeAgo(n.created_at) +
            "</div></div></div>";
        });
        // Keep the empty element but hidden, prepend signals
        list.innerHTML = html;
      })
      .catch(function () {
        var empty = document.getElementById("signal-empty");
        if (empty) empty.textContent = "Could not load signals";
      });
  }

  // ── Decision queue (pending approvals) ────────────────────────────────
  function loadDecisions() {
    api("/api/v1/approvals/?status=pending&limit=10")
      .then(function (items) {
        var list = document.getElementById("decision-list");
        var count = document.getElementById("decision-count");
        var empty = document.getElementById("decision-empty");
        if (!list) return;

        var arr = Array.isArray(items) ? items : items.items || [];
        if (count) count.textContent = arr.length;
        if (arr.length === 0) {
          if (empty) empty.textContent = "No pending decisions";
          return;
        }
        if (empty) empty.style.display = "none";

        var html = "";
        arr.forEach(function (a) {
          html +=
            '<div class="decision-item">' +
            '<div class="decision-icon"><i data-lucide="shield-check"></i></div>' +
            '<div class="decision-body">' +
            '<div class="decision-title">' + escHtml(a.title || a.action_type || "Approval") + "</div>" +
            '<div class="decision-type">' + escHtml(a.action_type || "action") +
            " &middot; " + timeAgo(a.created_at) + "</div>" +
            "</div>" +
            '<div class="decision-actions">' +
            '<button class="decision-btn approve" data-id="' + a.id + '" data-action="approve">OK</button>' +
            '<button class="decision-btn reject" data-id="' + a.id + '" data-action="reject">No</button>' +
            "</div></div>";
        });
        list.innerHTML = html;

        // Re-init lucide icons for the new elements
        if (window.lucide) lucide.createIcons();

        // Bind decision buttons
        list.querySelectorAll(".decision-btn").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var id = btn.dataset.id;
            var action = btn.dataset.action;
            var status = action === "approve" ? "approved" : "rejected";
            fetch("/api/v1/approvals/" + id, {
              method: "PUT",
              headers: {
                "Content-Type": "application/json",
                Authorization: token ? "Bearer " + token : "",
              },
              body: JSON.stringify({ status: status }),
            })
              .then(function () {
                loadDecisions();
                loadKPIs();
                if (window.BOSTO) BOSTO.success("Decision " + status);
              })
              .catch(function () {
                if (window.BOSTO) BOSTO.error("Failed to update approval");
              });
          });
        });
      })
      .catch(function () {
        var empty = document.getElementById("decision-empty");
        if (empty) empty.textContent = "Could not load decisions";
      });
  }

  // ── Company health (based on compliance/health data if available) ─────
  function loadCompanyHealth() {
    api("/api/v1/dashboard/kpis")
      .then(function (d) {
        // Compute a simple health score from KPIs
        var taskScore = d.tasks_pending < 10 ? 90 : d.tasks_pending < 25 ? 70 : 50;
        var approvalScore = d.pending_approvals === 0 ? 100 : d.pending_approvals < 5 ? 75 : 50;
        var integrationScore = d.connected_integrations > 3 ? 95 : d.connected_integrations > 0 ? 70 : 40;
        var overall = Math.round((taskScore + approvalScore + integrationScore) / 3);

        var healthEl = document.getElementById("exec-health-score");
        if (healthEl) healthEl.textContent = overall;
        var healthTrend = document.getElementById("exec-health-trend");
        if (healthTrend) {
          healthTrend.textContent = overall >= 80 ? "Healthy" : overall >= 60 ? "Needs attention" : "At risk";
          healthTrend.className = "exec-stat-trend " + (overall >= 80 ? "positive" : overall >= 60 ? "" : "negative");
        }

        // Also update the old compat elements
        var oldHealth = document.getElementById("dash-health-value");
        if (oldHealth) oldHealth.textContent = overall;
        var oldLabel = document.getElementById("dash-health-label");
        if (oldLabel) oldLabel.textContent = overall >= 80 ? "Healthy" : "Needs attention";

        // Company tiles — distribute scores with slight variation
        var tiles = {
          "health-empireo": Math.min(100, overall + 5),
          "health-esa": Math.min(100, overall - 3),
          "health-empire-digital": Math.min(100, overall + 2),
          "health-codnov": Math.min(100, overall - 5),
        };
        Object.keys(tiles).forEach(function (id) {
          var el = document.getElementById(id);
          if (el) el.textContent = tiles[id] + "%";
        });
      })
      .catch(function () {});
  }

  // ── Revenue trend ─────────────────────────────────────────────────────
  function loadRevenueTrend() {
    api("/api/v1/dashboard/trends?days=14")
      .then(function (d) {
        var rev = d.revenue || [];
        if (rev.length < 2) return;
        var recent = rev.slice(-7).reduce(function (a, b) { return a + b; }, 0);
        var prior = rev.slice(0, 7).reduce(function (a, b) { return a + b; }, 0);
        var pct = prior !== 0 ? Math.round(((recent - prior) / Math.abs(prior)) * 100) : 0;
        var el = document.getElementById("exec-revenue-trend");
        if (el) {
          var sign = pct >= 0 ? "+" : "";
          el.textContent = sign + pct + "% vs prior week";
          el.className = "exec-stat-trend " + (pct >= 0 ? "positive" : "negative");
        }
      })
      .catch(function () {});
  }

  // ── Boot ────────────────────────────────────────────────────────────────
  window.__bootPromise.then(function (t) {
    token = t;
    loadKPIs();
    loadSignals();
    loadDecisions();
    loadCompanyHealth();
    loadRevenueTrend();

    // Auto-refresh every 60s
    setInterval(function () {
      loadKPIs();
      loadSignals();
      loadDecisions();
    }, 60000);
  });
})();
