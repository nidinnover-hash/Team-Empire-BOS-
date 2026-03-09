/* Integration Health Dashboard */
(function () {
  "use strict";

  let TOKEN = null;
  const $ = (sel) => document.querySelector(sel);
  const H = (s) => Object.assign(document.createElement("div"), { innerHTML: s }).textContent;

  async function api(path) {
    const res = await fetch("/api/v1" + path, {
      headers: { Authorization: "Bearer " + TOKEN },
    });
    if (!res.ok) throw new Error(res.statusText);
    return res.json();
  }

  async function boot() {
    const r = await fetch("/web/api-token", { credentials: "same-origin" });
    if (!r.ok) return (location.href = "/web/login");
    TOKEN = (await r.json()).token;
  }

  const healthColors = {
    healthy: "#22c55e",
    degraded: "#f59e0b",
    error: "#ef4444",
    disconnected: "#94a3b8",
    never_synced: "#8b5cf6",
  };

  const healthBadge = {
    healthy: "badge-green",
    degraded: "badge-yellow",
    error: "badge-red",
    disconnected: "badge-gray",
    never_synced: "badge-blue",
  };

  async function load() {
    const data = await api("/integrations/health");
    const s = data.summary;

    $("#k-total").textContent = s.total;
    $("#k-healthy").textContent = s.healthy;
    $("#k-degraded").textContent = s.degraded;
    $("#k-errored").textContent = s.errored;
    $("#k-score").textContent = Math.round(s.health_score * 100) + "%";

    const tbody = $("#health-body");
    tbody.innerHTML = "";
    const integrations = data.integrations || [];
    $("#empty-msg").style.display = integrations.length ? "none" : "block";

    integrations.forEach((ig) => {
      const tr = document.createElement("tr");
      const cls = healthBadge[ig.health] || "badge-gray";
      const age = ig.age_hours != null ? ig.age_hours + "h" : "—";
      const lastSync = ig.last_sync_at
        ? new Date(ig.last_sync_at).toLocaleString()
        : "Never";

      tr.innerHTML =
        "<td><strong>" + H(ig.type) + "</strong></td>" +
        "<td>" + H(ig.status) + "</td>" +
        '<td><span class="badge ' + cls + '">' + H(ig.health) + "</span></td>" +
        "<td>" + lastSync + "</td>" +
        "<td>" + age + "</td>" +
        "<td>" + (ig.sync_error_count || 0) + "</td>";
      tbody.appendChild(tr);
    });
  }

  async function init() {
    await boot();
    load();
    $("#btn-refresh").addEventListener("click", load);
    // Auto-refresh every 30 seconds
    setInterval(load, 30000);
  }

  init();
})();
