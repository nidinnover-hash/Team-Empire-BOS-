(function () {
  var bellBtn = document.getElementById("notif-bell-btn");
  var dropdown = document.getElementById("notif-dropdown");
  var notifList = document.getElementById("notif-list");
  var badge = document.getElementById("notif-badge");
  var markAllBtn = document.getElementById("notif-mark-all-btn");
  if (!bellBtn || !dropdown) return;

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
  function connectSSE() {
    if (!window.PCAPI) return;
    window.PCAPI.getApiToken().then(function (token) {
      if (!token) return;
      var es = new EventSource("/api/v1/notifications/stream?token=" + encodeURIComponent(token));
      es.onmessage = function (event) {
        try {
          var d = JSON.parse(event.data);
          badge.textContent = d.unread_count;
          badge.classList.toggle("active", d.unread_count > 0);
        } catch (e) { /* ignore */ }
      };
      es.onerror = function () {
        es.close();
        setTimeout(connectSSE, 30000);
      };
    }).catch(function () {
      setTimeout(connectSSE, 30000);
    });
  }

  // Initial load
  updateBadge();
  // Fallback polling every 30s (SSE is primary)
  setInterval(updateBadge, 30000);
})();
