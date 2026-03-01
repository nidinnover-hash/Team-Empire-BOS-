/* eslint-disable no-var */
(function () {
  "use strict";
  var escHtml = window.PCUI.escapeHtml;
  var mapErr = window.PCUI.mapApiError;
  var reqJson = window.PCUI.requestJson;

  window.__bootPromise = fetch("/web/api-token")
    .then(function (r) { if (!r.ok) throw new Error("Session expired"); return r.json(); })
    .then(function (d) { return d.token; });

  var PAGE_SIZE = 50;
  var currentOffset = 0;
  var allEvents = [];
  var knownTypes = new Set();

  function $(id) { return document.getElementById(id); }

  function fmtTime(iso) {
    if (!iso) return "-";
    var d = new Date(iso);
    return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function isToday(iso) {
    if (!iso) return false;
    var d = new Date(iso);
    var now = new Date();
    return d.toDateString() === now.toDateString();
  }

  function getRisk(evt) {
    if (evt.payload_json && evt.payload_json.risk_level) return evt.payload_json.risk_level;
    return "";
  }

  function getEntityLabel(evt) {
    var parts = [];
    if (evt.entity_type) parts.push(evt.entity_type);
    if (evt.entity_id) parts.push("#" + evt.entity_id);
    return parts.join(" ") || "";
  }

  function getEventIcon(type) {
    if (type.indexOf("created") >= 0) return "+";
    if (type.indexOf("deleted") >= 0) return "x";
    if (type.indexOf("updated") >= 0 || type.indexOf("changed") >= 0) return "~";
    if (type.indexOf("approved") >= 0) return "ok";
    if (type.indexOf("rejected") >= 0) return "no";
    if (type.indexOf("login") >= 0) return "in";
    return "ev";
  }

  // ── Load & Render ───────────────────────────────────────────────────
  async function loadEvents() {
    var container = $("event-list");
    try {
      var token = await window.__bootPromise;
      if (!token) throw new Error("Session expired");

      var params = "?limit=" + PAGE_SIZE;
      var dateVal = $("filter-date").value;
      if (dateVal) params += "&event_date=" + dateVal;

      allEvents = await reqJson("/api/v1/ops/events" + params, { auth: true, token: token });
      if (!Array.isArray(allEvents)) allEvents = [];

      // Populate event type filter
      allEvents.forEach(function (e) { knownTypes.add(e.event_type); });
      populateTypeFilter();
      applyClientFilters();
      updateKPIs();
    } catch (e) {
      container.innerHTML = '<div class="empty">' + escHtml(mapErr(e)) + "</div>";
    }
  }

  function populateTypeFilter() {
    var sel = $("filter-event-type");
    var current = sel.value;
    var opts = '<option value="">All event types</option>';
    Array.from(knownTypes).sort().forEach(function (t) {
      opts += '<option value="' + escHtml(t) + '">' + escHtml(t) + "</option>";
    });
    sel.innerHTML = opts;
    sel.value = current;
  }

  function applyClientFilters() {
    var typeFilter = $("filter-event-type").value;
    var filtered = allEvents;
    if (typeFilter) {
      filtered = filtered.filter(function (e) { return e.event_type === typeFilter; });
    }
    renderList(filtered);
  }

  function updateKPIs() {
    $("k-total").textContent = allEvents.length;
    $("k-high").textContent = allEvents.filter(function (e) {
      var r = getRisk(e);
      return r === "high" || r === "critical";
    }).length;
    $("k-today").textContent = allEvents.filter(function (e) { return isToday(e.created_at); }).length;
  }

  function renderList(events) {
    var container = $("event-list");
    if (!events.length) {
      container.innerHTML = '<div class="empty">No audit events found.</div>';
      return;
    }
    container.innerHTML = events.map(function (e) {
      var risk = getRisk(e);
      var riskCls = risk ? " risk-" + risk : "";
      var riskBadge = risk ? '<span class="risk-badge ' + escHtml(risk) + '">' + escHtml(risk) + "</span>" : "";
      var entity = getEntityLabel(e);
      var icon = getEventIcon(e.event_type);

      return '<div class="evt-card' + riskCls + '">' +
        '<div class="evt-icon">' + escHtml(icon) + "</div>" +
        '<div class="evt-body">' +
          '<span class="evt-type">' + escHtml(e.event_type) + "</span> " + riskBadge +
          (entity ? '<div class="evt-detail">' + escHtml(entity) + "</div>" : "") +
          '<div class="evt-meta">' +
            '<span>Actor: ' + (e.actor_user_id ? "#" + e.actor_user_id : "system") + "</span>" +
            '<span>' + fmtTime(e.created_at) + "</span>" +
          "</div>" +
        "</div>" +
      "</div>";
    }).join("");
  }

  // ── Filter Bindings ────────────────────────────────────────────────
  $("filter-apply").addEventListener("click", function () { loadEvents(); });
  $("filter-reset").addEventListener("click", function () {
    $("filter-event-type").value = "";
    $("filter-date").value = "";
    loadEvents();
  });
  $("filter-event-type").addEventListener("change", function () { applyClientFilters(); });

  // ── Init ───────────────────────────────────────────────────────────
  loadEvents();
  if (typeof lucide !== "undefined") lucide.createIcons();
})();
