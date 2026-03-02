/* eslint-disable no-var */
(function () {
  "use strict";
  var escHtml = window.PCUI.escapeHtml;
  var mapErr = window.PCUI.mapApiError;
  var reqJson = window.PCUI.requestJson;

  window.__bootPromise = fetch("/web/api-token")
    .then(function (r) { if (!r.ok) throw new Error("Session expired"); return r.json(); })
    .then(function (d) { return d.token; });

  var allNotifications = [];
  var unreadCount = 0;
  var currentOffset = 0;
  var PAGE_SIZE = 50;

  // ── Helpers ──────────────────────────────────────────────────────────
  function $(id) { return document.getElementById(id); }

  function timeAgo(iso) {
    if (!iso) return "";
    var diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    return Math.floor(diff / 86400) + "d ago";
  }

  // ── Load & Render ───────────────────────────────────────────────────
  async function loadNotifications() {
    var container = $("notif-list");
    try {
      var token = await window.__bootPromise;
      if (!token) throw new Error("Session expired");
      var unreadOnly = $("filter-unread").checked;
      var params = "?limit=" + PAGE_SIZE;
      if (unreadOnly) params += "&unread_only=true";
      var data = await reqJson("/api/v1/notifications" + params, { auth: true, token: token });
      allNotifications = data.items || [];
      unreadCount = data.unread_count || 0;
      updateKPIs();
      renderList();
    } catch (e) {
      container.innerHTML = '<div class="empty">' + escHtml(mapErr(e)) + "</div>";
    }
  }

  function updateKPIs() {
    $("k-total").textContent = allNotifications.length;
    $("k-unread").textContent = unreadCount;
    $("k-critical").textContent = allNotifications.filter(function (n) {
      return n.severity === "critical" || n.severity === "high";
    }).length;
  }

  function getFilteredNotifications() {
    var sev = $("filter-severity").value;
    if (!sev) return allNotifications;
    return allNotifications.filter(function (n) { return n.severity === sev; });
  }

  function renderList() {
    var container = $("notif-list");
    var filtered = getFilteredNotifications();
    if (!filtered.length) {
      container.innerHTML = '<div class="empty">No notifications found.</div>';
      $("pagination").innerHTML = "";
      return;
    }
    container.innerHTML = filtered.map(function (n) {
      var cls = n.is_read ? "notif-card" : "notif-card unread";
      var sevCls = "notif-sev " + escHtml(n.severity || "info");
      return '<div class="' + cls + '" data-id="' + n.id + '">' +
        '<div class="notif-top">' +
          '<span class="' + sevCls + '">' + escHtml(n.severity || "info") + "</span>" +
          '<div class="notif-body">' +
            '<div class="notif-title">' + escHtml(n.title) + "</div>" +
            '<div class="notif-msg">' + escHtml(n.message || "") + "</div>" +
            '<div class="notif-meta">' +
              '<span class="notif-type-tag">' + escHtml(n.type || "") + "</span>" +
              "<span>" + timeAgo(n.created_at) + "</span>" +
              (n.source ? "<span>" + escHtml(n.source) + "</span>" : "") +
            "</div>" +
          "</div>" +
          (n.is_read ? "" : '<button type="button" class="notif-mark-btn" title="Mark read">Mark read</button>') +
        "</div>" +
      "</div>";
    }).join("");

    // Bind mark-read buttons
    container.querySelectorAll(".notif-card").forEach(function (card) {
      var id = Number(card.dataset.id);
      var btn = card.querySelector(".notif-mark-btn");
      if (btn) {
        btn.addEventListener("click", function (e) {
          e.stopPropagation();
          markRead([id]);
        });
      }
    });
  }

  // ── Actions ─────────────────────────────────────────────────────────
  async function markRead(ids) {
    try {
      var token = await window.__bootPromise;
      await reqJson("/api/v1/notifications/mark-read", {
        method: "POST",
        auth: true,
        token: token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notification_ids: ids }),
      });
      await loadNotifications();
    } catch (e) {
      if (window.showToast) window.showToast(mapErr(e), "error");
    }
  }

  async function markAllRead() {
    try {
      var token = await window.__bootPromise;
      await reqJson("/api/v1/notifications/mark-read", {
        method: "POST",
        auth: true,
        token: token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notification_ids: [] }),
      });
      if (window.showToast) window.showToast("All notifications marked as read.", "ok");
      await loadNotifications();
    } catch (e) {
      if (window.showToast) window.showToast(mapErr(e), "error");
    }
  }

  // ── Event Bindings ──────────────────────────────────────────────────
  $("mark-all-read-btn").addEventListener("click", markAllRead);
  $("filter-severity").addEventListener("change", renderList);
  $("filter-unread").addEventListener("change", loadNotifications);

  // ── SSE Real-Time Consumer ─────────────────────────────────────────
  function startSSE() {
    var evtSource;
    window.__bootPromise.then(function (token) {
      if (!token) return;
      evtSource = new EventSource("/api/v1/notifications/stream?token=" + encodeURIComponent(token));
      evtSource.onmessage = function (event) {
        try {
          var data = JSON.parse(event.data);
          var newCount = data.unread_count;
          if (newCount !== unreadCount) {
            unreadCount = newCount;
            $("k-unread").textContent = String(unreadCount);
            // Reload full list when new notifications arrive
            loadNotifications();
          }
        } catch (_e) { /* ignore parse errors */ }
      };
      evtSource.onerror = function () {
        // Browser will auto-reconnect; just log it
        if (evtSource.readyState === EventSource.CLOSED) {
          // Retry after 10s if the connection closed permanently
          setTimeout(startSSE, 10000);
        }
      };
    });
    // Clean up on page unload
    window.addEventListener("beforeunload", function () {
      if (evtSource) evtSource.close();
    });
  }

  // ── Init ────────────────────────────────────────────────────────────
  loadNotifications();
  startSSE();
  if (typeof lucide !== "undefined") lucide.createIcons();
})();
