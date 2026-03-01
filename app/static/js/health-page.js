/* eslint-disable no-var */
(function () {
  "use strict";
  var escHtml = window.PCUI.escapeHtml;
  var mapErr = window.PCUI.mapApiError;
  var reqJson = window.PCUI.requestJson;

  window.__bootPromise = fetch("/web/api-token")
    .then(function (r) { if (!r.ok) throw new Error("Session expired"); return r.json(); })
    .then(function (d) { return d.token; });

  function $(id) { return document.getElementById(id); }

  function fmtTime(iso) {
    if (!iso) return "never";
    var d = new Date(iso);
    return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  // ── Load Integration Health ────────────────────────────────────────
  async function loadIntegrationHealth() {
    var container = $("integration-list");
    try {
      var token = await window.__bootPromise;
      if (!token) throw new Error("Session expired");
      var data = await reqJson("/api/v1/control/integrations/health", { auth: true, token: token });
      var items = data.integrations || data || [];
      if (!Array.isArray(items)) items = [];

      // Update KPIs
      var counts = { healthy: 0, degraded: 0, down: 0 };
      items.forEach(function (i) {
        var s = (i.state || i.status || "").toLowerCase();
        if (s === "healthy") counts.healthy++;
        else if (s === "degraded" || s === "stale") counts.degraded++;
        else counts.down++;
      });
      $("k-healthy").textContent = counts.healthy;
      $("k-degraded").textContent = counts.degraded;
      $("k-down").textContent = counts.down;
      $("k-total").textContent = items.length;

      if (!items.length) {
        container.innerHTML = '<div class="empty">No integrations connected.</div>';
        return;
      }
      container.innerHTML = items.map(function (i) {
        var state = (i.state || i.status || "unknown").toLowerCase();
        return '<div class="health-card status-' + escHtml(state) + '">' +
          '<div class="health-dot ' + escHtml(state) + '"></div>' +
          '<span class="health-name">' + escHtml(i.name || i.type || "Unknown") + '</span>' +
          '<span class="health-badge ' + escHtml(state) + '">' + escHtml(state) + '</span>' +
          '<span class="health-meta">Last sync: ' + fmtTime(i.last_synced_at || i.last_sync) + '</span>' +
        '</div>';
      }).join("");
    } catch (e) {
      container.innerHTML = '<div class="empty">' + escHtml(mapErr(e)) + "</div>";
    }
  }

  // ── Load Token Health ──────────────────────────────────────────────
  async function loadTokenHealth() {
    var container = $("token-list");
    try {
      var token = await window.__bootPromise;
      if (!token) throw new Error("Session expired");
      var data = await reqJson("/api/v1/integrations/token-health", { auth: true, token: token });
      var items = data.tokens || data || [];
      if (!Array.isArray(items)) {
        // May be an object with integration names as keys
        if (typeof data === "object") {
          items = Object.entries(data).map(function (entry) {
            var val = typeof entry[1] === "object" ? entry[1] : { status: entry[1] };
            val.name = entry[0];
            return val;
          });
        } else {
          items = [];
        }
      }

      if (!items.length) {
        container.innerHTML = '<div class="empty">No tokens to display.</div>';
        return;
      }
      container.innerHTML = items.map(function (t) {
        var status = (t.status || t.state || "unknown").toLowerCase();
        var canRotate = t.type === "oauth" || t.oauth === true;
        var rotateBtn = canRotate
          ? ' <button class="rotate-btn" data-type="' + escHtml(t.name || t.type || "") + '">Rotate</button>'
          : "";
        return '<div class="health-card">' +
          '<div class="health-dot ' + escHtml(status) + '"></div>' +
          '<span class="health-name">' + escHtml(t.name || t.type || "Unknown") + '</span>' +
          '<span class="health-badge ' + escHtml(status) + '">' + escHtml(status) + '</span>' +
          '<span class="health-meta">' + (t.expires_at ? "Expires: " + fmtTime(t.expires_at) : "") + '</span>' +
          rotateBtn +
        '</div>';
      }).join("");

      // Bind rotate buttons
      container.querySelectorAll(".rotate-btn").forEach(function (btn) {
        btn.addEventListener("click", function () { rotateToken(btn.dataset.type); });
      });
    } catch (e) {
      container.innerHTML = '<div class="empty">' + escHtml(mapErr(e)) + "</div>";
    }
  }

  // ── Load System Health ─────────────────────────────────────────────
  async function loadSystemHealth() {
    var container = $("system-list");
    try {
      var token = await window.__bootPromise;
      if (!token) throw new Error("Session expired");
      var data = await reqJson("/api/v1/control/system-health", { auth: true, token: token });
      var checks = data.checks || data || {};

      if (typeof checks !== "object" || !Object.keys(checks).length) {
        container.innerHTML = '<div class="empty">No system health data available.</div>';
        return;
      }
      var entries = Object.entries(checks);
      container.innerHTML = entries.map(function (entry) {
        var name = entry[0];
        var val = entry[1];
        var status = "ok";
        var detail = "";
        if (typeof val === "object") {
          status = (val.status || val.state || "ok").toLowerCase();
          detail = val.detail || val.message || "";
        } else if (typeof val === "string") {
          status = val.toLowerCase();
        }
        return '<div class="health-card">' +
          '<div class="health-dot ' + escHtml(status) + '"></div>' +
          '<span class="health-name">' + escHtml(name) + '</span>' +
          '<span class="health-badge ' + escHtml(status) + '">' + escHtml(status) + '</span>' +
          (detail ? '<span class="health-meta">' + escHtml(detail) + '</span>' : "") +
        '</div>';
      }).join("");
    } catch (e) {
      container.innerHTML = '<div class="empty">' + escHtml(mapErr(e)) + "</div>";
    }
  }

  // ── Rotate Token ──────────────────────────────────────────────────
  async function rotateToken(type) {
    if (!window.confirm("Rotate OAuth token for " + type + "? The current token will be invalidated.")) return;
    try {
      var token = await window.__bootPromise;
      await reqJson("/api/v1/integrations/token-rotate/" + encodeURIComponent(type), {
        method: "POST", auth: true, token: token,
      });
      if (window.showToast) window.showToast("Token rotated for " + type + ".", "ok");
      loadTokenHealth();
    } catch (e) {
      if (window.showToast) window.showToast(mapErr(e), "error");
    }
  }

  // ── Refresh All ───────────────────────────────────────────────────
  function loadAll() {
    loadIntegrationHealth();
    loadTokenHealth();
    loadSystemHealth();
  }

  $("refresh-btn").addEventListener("click", loadAll);

  // ── Init ──────────────────────────────────────────────────────────
  loadAll();
  if (typeof lucide !== "undefined") lucide.createIcons();
})();
