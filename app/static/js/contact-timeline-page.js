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

  function getContactId() {
    var params = new URLSearchParams(window.location.search);
    return parseInt(params.get("id"), 10) || null;
  }

  function relativeTime(isoStr) {
    if (!isoStr) return "";
    var d = new Date(isoStr);
    var now = new Date();
    var diffMs = now - d;
    var mins = Math.floor(diffMs / 60000);
    if (mins < 60) return mins + "m ago";
    var hrs = Math.floor(mins / 60);
    if (hrs < 24) return hrs + "h ago";
    var days = Math.floor(hrs / 24);
    if (days < 30) return days + "d ago";
    return d.toLocaleDateString("en", { month: "short", day: "numeric", year: "2-digit" });
  }

  async function load() {
    var contactId = getContactId();
    if (!contactId) {
      $("contact-profile").innerHTML = '<div class="empty">No contact ID specified.</div>';
      $("timeline-container").innerHTML = "";
      return;
    }

    try {
      var token = await window.__bootPromise;
      if (!token) throw new Error("Session expired");

      var contact = await reqJson("/api/v1/contacts/" + contactId, { auth: true, token: token });
      renderProfile(contact);
      $("page-title").textContent = escHtml(contact.name) + " — Timeline";

      var timeline = await reqJson("/api/v1/contacts/" + contactId + "/timeline?limit=100", { auth: true, token: token });
      renderTimeline(timeline);
    } catch (e) {
      $("timeline-container").innerHTML = '<div class="empty">' + escHtml(mapErr(e)) + "</div>";
    }
  }

  function renderProfile(c) {
    var stageClass = "stage-" + (c.pipeline_stage || "new");
    var html = '<div>';
    html += '<div class="cp-name">' + escHtml(c.name) + "</div>";
    html += '<div class="cp-detail">';
    if (c.email) html += escHtml(c.email);
    if (c.phone) html += (c.email ? " &middot; " : "") + escHtml(c.phone);
    if (c.company) html += " &middot; " + escHtml(c.company);
    html += "</div></div>";
    html += '<span class="cp-badge ' + stageClass + '">' + escHtml(c.pipeline_stage || "new") + "</span>";
    if (c.lead_score) html += '<span class="cp-detail" style="margin-left:.5rem">Score: ' + c.lead_score + "</span>";
    $("contact-profile").innerHTML = html;
  }

  function renderTimeline(items) {
    var container = $("timeline-container");
    if (!items || !items.length) {
      container.innerHTML = '<div class="empty">No activity found for this contact.</div>';
      return;
    }
    var html = "";
    items.forEach(function (item) {
      var typeClass = "type-" + (item.type || "event");
      html += '<div class="tl-item ' + typeClass + '">';
      html += '<div class="tl-header">';
      html += '<span class="tl-type">' + escHtml(item.type || "event") + "</span>";
      html += '<span class="tl-time">' + relativeTime(item.timestamp) + "</span>";
      html += "</div>";
      html += '<div class="tl-title">' + escHtml(item.event_type || "") + "</div>";
      var detail = item.detail || {};
      var detailStr = "";
      if (item.type === "deal") {
        detailStr = escHtml(detail.title || "") + " — $" + Number(detail.value || 0).toLocaleString();
      } else if (item.type === "note") {
        detailStr = escHtml(detail.title || "");
      } else if (typeof detail === "object") {
        var keys = Object.keys(detail).slice(0, 3);
        detailStr = keys.map(function (k) { return escHtml(k) + ": " + escHtml(String(detail[k] || "")); }).join(" &middot; ");
      }
      if (detailStr) html += '<div class="tl-detail">' + detailStr + "</div>";
      html += "</div>";
    });
    container.innerHTML = html;
  }

  load();
  if (typeof lucide !== "undefined") lucide.createIcons();
})();
