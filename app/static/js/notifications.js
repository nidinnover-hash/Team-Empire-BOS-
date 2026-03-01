(function () {
  var bellBtn = document.getElementById("notif-bell-btn");
  var dropdown = document.getElementById("notif-dropdown");
  var notifList = document.getElementById("notif-list");
  var badge = document.getElementById("notif-badge");
  var markAllBtn = document.getElementById("notif-mark-all-btn");
  if (!bellBtn || !dropdown) return;

  var baseTitle = document.title;
  var _sseTimer = null;
  var _sseRetryMs = 5000;
  var _sseMaxRetryMs = 120000;
  var _sseClient = null;
  var _sseFailNotified = false;

  function setTitleBadge(count) {
    document.title = count > 0 ? "(" + count + ") " + baseTitle : baseTitle;
  }

  function escapeHtml(s) {
    return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function timeAgo(iso) {
    var diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    return Math.floor(diff / 86400) + "d ago";
  }

  bellBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    var open = dropdown.style.display === "none";
    dropdown.style.display = open ? "flex" : "none";
    if (open) loadNotifications();
  });

  document.addEventListener("click", function (e) {
    if (!e.target.closest(".notif-bell-container")) {
      dropdown.style.display = "none";
    }
  });

  async function loadNotifications() {
    try {
      notifList.innerHTML = '<div class="notif-empty">Loading...</div>';
      var data = await window.PCAPI.safeFetchJson("/api/v1/notifications?limit=30", { method: "GET", auth: true });
      if (!data.items || data.items.length === 0) {
        notifList.innerHTML = '<div class="notif-empty">No notifications</div>';
        return;
      }
      notifList.innerHTML = data.items.map(function (n) {
        return '<div class="notif-item ' + (n.is_read ? "" : "unread") + '">' +
          '<div class="notif-item-title">' + escapeHtml(n.title) + '</div>' +
          '<div class="notif-item-msg">' + escapeHtml(n.message) + '</div>' +
          '<div class="notif-item-meta"><span>' + timeAgo(n.created_at) + '</span>' +
          '<span class="notif-sev ' + escapeHtml(n.severity) + '">' + escapeHtml(n.severity) + '</span></div></div>';
      }).join("");
    } catch (err) {
      notifList.innerHTML = '<div class="notif-empty">Error loading</div>';
    }
  }

  async function updateBadge() {
    try {
      var data = await window.PCAPI.safeFetchJson("/api/v1/notifications/count", { method: "GET", auth: true });
      var count = data.unread_count || 0;
      badge.textContent = count;
      badge.classList.toggle("active", count > 0);
      setTitleBadge(count);
    } catch (err) { /* silent */ }
  }

  markAllBtn.addEventListener("click", async function () {
    try {
      await window.PCAPI.safeFetchJson("/api/v1/notifications/mark-read", {
        method: "POST", auth: true,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });
      updateBadge();
      loadNotifications();
      if (window.showToast) window.showToast("All marked read", "success");
    } catch (err) {
      if (window.showToast) window.showToast("Failed", "error");
    }
  });

  // SSE real-time badge updates
  function scheduleReconnect() {
    if (_sseTimer) return;
    if (document.visibilityState === "hidden") return;
    if (_sseRetryMs >= _sseMaxRetryMs && !_sseFailNotified) {
      _sseFailNotified = true;
      if (window.showToast) window.showToast("Live updates unavailable. Using polling fallback.", "warning");
    }
    _sseTimer = setTimeout(function () {
      _sseTimer = null;
      connectSSE();
    }, _sseRetryMs);
    _sseRetryMs = Math.min(_sseRetryMs * 2, _sseMaxRetryMs);
  }

  function connectSSE() {
    if (document.visibilityState === "hidden") return;
    if (_sseClient) {
      _sseClient.close();
      _sseClient = null;
    }
    var es = new EventSource("/api/v1/notifications/stream");
    _sseClient = es;
    es.onmessage = function (event) {
      try {
        var d = JSON.parse(event.data);
        badge.textContent = d.unread_count;
        badge.classList.toggle("active", d.unread_count > 0);
        setTitleBadge(d.unread_count);
        _sseRetryMs = 5000;
      } catch (e) { /* ignore */ }
    };
    es.onerror = function () {
      es.close();
      if (_sseClient === es) _sseClient = null;
      scheduleReconnect();
    };
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      _sseRetryMs = 5000;
      _sseFailNotified = false;
      connectSSE();
      return;
    }
    if (_sseClient) {
      _sseClient.close();
      _sseClient = null;
    }
  });

  window.addEventListener("online", function () {
    _sseRetryMs = 5000;
    connectSSE();
  });

  // Initial load
  updateBadge();
  connectSSE();
  // Fallback polling every 30s (SSE is primary)
  setInterval(updateBadge, 30000);
})();
