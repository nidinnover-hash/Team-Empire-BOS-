/**
 * BOS Toast Notification System
 * Usage:
 *   BOSTO.success("Contact created")
 *   BOSTO.error("Failed to save")
 *   BOSTO.warning("Approval required")
 *   BOSTO.info("Syncing with ClickUp...")
 */
(function () {
  "use strict";

  const MAX_TOASTS = 4;
  const AUTO_DISMISS_MS = 4000;
  let container = null;

  function ensureContainer() {
    if (container) return container;
    container = document.createElement("div");
    container.id = "bos-toast-container";
    Object.assign(container.style, {
      position: "fixed",
      top: "16px",
      right: "16px",
      zIndex: "99999",
      display: "flex",
      flexDirection: "column",
      gap: "8px",
      pointerEvents: "none",
      maxWidth: "380px",
      width: "100%",
    });
    document.body.appendChild(container);
    return container;
  }

  const ICONS = {
    success: "&#10003;",
    error: "&#10007;",
    warning: "&#9888;",
    info: "&#8505;",
  };

  const COLORS = {
    success: { bg: "rgba(34,197,94,0.15)", border: "#22c55e", text: "#22c55e" },
    error: { bg: "rgba(239,68,68,0.15)", border: "#ef4444", text: "#ef4444" },
    warning: { bg: "rgba(245,158,11,0.15)", border: "#f59e0b", text: "#f59e0b" },
    info: { bg: "rgba(99,102,241,0.15)", border: "#6366f1", text: "#6366f1" },
  };

  function show(type, message) {
    const c = ensureContainer();

    // Enforce max toasts
    while (c.children.length >= MAX_TOASTS) {
      c.removeChild(c.firstChild);
    }

    const colors = COLORS[type] || COLORS.info;
    const el = document.createElement("div");
    Object.assign(el.style, {
      background: colors.bg,
      borderLeft: "4px solid " + colors.border,
      color: colors.text,
      padding: "12px 16px",
      borderRadius: "8px",
      fontSize: "14px",
      fontWeight: "500",
      fontFamily: "Inter, -apple-system, sans-serif",
      display: "flex",
      alignItems: "center",
      gap: "10px",
      pointerEvents: "auto",
      cursor: "pointer",
      opacity: "0",
      transform: "translateX(100%)",
      transition: "opacity 200ms ease, transform 200ms ease",
      backdropFilter: "blur(8px)",
      boxShadow: "0 4px 24px rgba(0,0,0,0.3)",
    });

    el.innerHTML =
      '<span style="font-size:16px;flex-shrink:0">' +
      (ICONS[type] || "") +
      "</span>" +
      '<span style="flex:1">' +
      escapeHtml(message) +
      "</span>";

    el.addEventListener("click", function () {
      dismiss(el);
    });

    c.appendChild(el);

    // Animate in
    requestAnimationFrame(function () {
      el.style.opacity = "1";
      el.style.transform = "translateX(0)";
    });

    // Auto-dismiss
    setTimeout(function () {
      dismiss(el);
    }, AUTO_DISMISS_MS);
  }

  function dismiss(el) {
    if (!el.parentNode) return;
    el.style.opacity = "0";
    el.style.transform = "translateX(100%)";
    setTimeout(function () {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 200);
  }

  function escapeHtml(str) {
    var d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  // Public API
  window.BOSTO = {
    success: function (msg) { show("success", msg); },
    error: function (msg) { show("error", msg); },
    warning: function (msg) { show("warning", msg); },
    info: function (msg) { show("info", msg); },
  };
})();
