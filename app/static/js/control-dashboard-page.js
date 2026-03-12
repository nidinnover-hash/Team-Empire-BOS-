(async function () {
  if (!window.__bootPromise) window.__bootPromise = fetch("/web/api-token").then(function (r) { return r.ok ? r.json() : {}; }).then(function (d) { return d.token || null; });
  var token = await window.__bootPromise;
  if (!token) return;

  function headers() {
    var h = { Authorization: "Bearer " + token, "Content-Type": "application/json" };
    if (window.BOS_COMPANY) h["X-BOS-Company"] = window.BOS_COMPANY;
    return h;
  }
  function esc(s) {
    if (s == null) return "";
    var t = String(s);
    return t.replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }
  function loadControlSummary() {
    if (!token) return;
    var pendingEl = document.getElementById("pending-list");
    if (!pendingEl) return;
    var placementsEl = document.getElementById("placements-list");
    var moneyEl = document.getElementById("money-list");
    pendingEl.innerHTML = "<div class=\"empty loading\">Loading...</div>";
    if (placementsEl) placementsEl.innerHTML = "<div class=\"empty loading\">Loading...</div>";
    if (moneyEl) moneyEl.innerHTML = "<div class=\"empty loading\">Loading...</div>";
    fetch("/api/v1/control/dashboard/control-summary", { headers: headers() })
      .then(function (res) { return res.ok ? res.json() : Promise.reject(res); })
      .then(function (data) { renderControlSummary(data); })
      .catch(function () {
        if (pendingEl) pendingEl.innerHTML = "<div class=\"empty\">Failed to load</div>";
      });
  }
  function renderControlSummary(data) {
    var pendingEl = document.getElementById("pending-list");
    var placementsEl = document.getElementById("placements-list");
    var moneyEl = document.getElementById("money-list");
    var kPending = document.getElementById("k-pending");
    var kAtRisk = document.getElementById("k-at-risk");
    var generatedAt = document.getElementById("generated-at");
    if (kPending) kPending.textContent = data.pending_approvals_count != null ? data.pending_approvals_count : 0;
    if (kAtRisk) kAtRisk.textContent = data.study_abroad_at_risk_count != null ? data.study_abroad_at_risk_count : 0;

    var recent = data.pending_approvals_recent || [];
    if (pendingEl) {
      if (recent.length === 0) {
        pendingEl.innerHTML = "<div class=\"empty\">No pending approvals</div>";
      } else {
        pendingEl.innerHTML = "<ul class=\"item-list\">" + recent.map(function (a) {
        var created = a.created_at ? new Date(a.created_at).toLocaleString() : "";
        return "<li><span class=\"badge\">" + esc(a.approval_type) + "</span> <a href=\"/#ap-" + esc(a.id) + "\" class=\"link\" title=\"Open approval in Dashboard\">ID " + esc(a.id) + "</a> — " + esc(created) + "</li>";
      }).join("") + "</ul>";
      }
    }

    var placements = data.recent_placements || [];
    if (placementsEl) {
      if (placements.length === 0) {
        placementsEl.innerHTML = "<div class=\"empty\">No placements in last 7 days</div>";
      } else {
        placementsEl.innerHTML = "<ul class=\"item-list\">" + placements.map(function (p) {
        var created = p.created_at ? new Date(p.created_at).toLocaleString() : "";
        var contactHref = "/web/contacts" + (p.candidate_id ? "?contact_id=" + encodeURIComponent(p.candidate_id) : "");
        return "<li><a href=\"" + contactHref + "\" class=\"link\" title=\"View candidate contact\">Candidate " + esc(p.candidate_id) + " → Job " + esc(p.job_id) + "</a> — " + esc(created) + "</li>";
      }).join("") + "</ul>";
      }
    }

    var money = data.recent_money_approvals || [];
    if (moneyEl) {
      if (money.length === 0) {
        moneyEl.innerHTML = "<div class=\"empty\">No money approvals in last 7 days</div>";
      } else {
        moneyEl.innerHTML = "<ul class=\"item-list\">" + money.map(function (a) {
        var created = a.created_at ? new Date(a.created_at).toLocaleString() : "";
        return "<li><span class=\"badge\">" + esc(a.approval_type) + "</span> " + esc(a.status) + " — <a href=\"/#ap-" + esc(a.id) + "\" class=\"link\" title=\"Open approval in Dashboard\">ID " + esc(a.id) + "</a> — " + esc(created) + "</li>";
      }).join("") + "</ul>";
      }
    }

    if (generatedAt && data.generated_at) generatedAt.textContent = "Data as of " + new Date(data.generated_at).toLocaleString();

    var sectorKpis = data.sector_kpis || [];
    var sectorCard = document.getElementById("sector-kpis");
    var sectorList = document.getElementById("sector-kpis-list");
    if (sectorCard && sectorList) {
      if (sectorKpis.length > 0) {
        sectorList.innerHTML = "<ul class=\"item-list\">" + sectorKpis.map(function (k) {
          return "<li><strong>" + esc(k.slug) + "</strong> (" + esc(k.industry_type || "—") + ") — Pending: " + k.pending_approvals_count + ", At risk: " + k.study_abroad_at_risk_count + ", Placements 7d: " + k.placements_count_7d + ", Money 7d: " + k.money_approvals_count_7d + "</li>";
        }).join("") + "</ul>";
        sectorCard.style.display = "block";
      } else {
        sectorCard.style.display = "none";
      }
    }
  }

  function loadControlReport() {
    var el = document.getElementById("control-report-list");
    if (!el) return;
    fetch("/api/v1/control/observability/control-report", { headers: headers() })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
      .then(function (d) {
        var byOrg = d.by_organization || [];
        if (byOrg.length === 0) {
          el.innerHTML = "<div class=\"empty\">No control events in last 7 days</div>";
          return;
        }
        el.innerHTML = "<ul class=\"item-list\">" + byOrg.map(function (r) {
          return "<li><strong>" + esc(r.organization_slug || r.organization_id) + "</strong> — " + esc(r.event_type) + ": " + r.count + "</li>";
        }).join("") + "</ul>";
      })
      .catch(function () { if (el) el.innerHTML = "<div class=\"empty\">Failed to load report</div>"; });
  }

  document.addEventListener("bos:company-changed", function () { loadControlSummary(); loadControlReport(); });

  try {
    var res = await fetch("/api/v1/control/dashboard/control-summary", { headers: headers() });
    if (!res.ok) {
      if (pendingEl) pendingEl.innerHTML = "<div class=\"empty\">Failed to load (" + res.status + ")</div>";
      return;
    }
    var data = await res.json();
    renderControlSummary(data);
  } catch (e) {
    if (pendingEl) pendingEl.innerHTML = "<div class=\"empty\">Error loading control summary</div>";
  }

  loadControlReport();

  if (typeof lucide !== "undefined") lucide.createIcons();
})();
