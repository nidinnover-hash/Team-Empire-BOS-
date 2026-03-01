/* eslint-disable no-var */
(function () {
  "use strict";
  var escHtml = window.PCUI.escapeHtml;
  var mapErr = window.PCUI.mapApiError;
  var reqJson = window.PCUI.requestJson;

  window.__bootPromise = fetch("/web/api-token")
    .then(function (r) { if (!r.ok) throw new Error("Session expired"); return r.json(); })
    .then(function (d) { return d.token; });

  var endpoints = [];

  // ── Helpers ──────────────────────────────────────────────────────────
  function $(id) { return document.getElementById(id); }

  function fmtTime(iso) {
    if (!iso) return "-";
    var d = new Date(iso);
    return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  // ── Load & Render ───────────────────────────────────────────────────
  async function loadEndpoints() {
    var container = $("webhook-list");
    try {
      var token = await window.__bootPromise;
      if (!token) throw new Error("Session expired");
      endpoints = await reqJson("/api/v1/webhooks", { auth: true, token: token });
      updateKPIs();
      renderList();
    } catch (e) {
      container.innerHTML = '<div class="empty">' + escHtml(mapErr(e)) + "</div>";
    }
  }

  function updateKPIs() {
    $("k-total").textContent = endpoints.length;
    $("k-active").textContent = endpoints.filter(function (w) { return w.is_active; }).length;
    $("k-inactive").textContent = endpoints.filter(function (w) { return !w.is_active; }).length;
  }

  function renderList() {
    var container = $("webhook-list");
    if (!endpoints.length) {
      container.innerHTML = '<div class="empty">No webhook endpoints configured yet.</div>';
      return;
    }
    container.innerHTML = endpoints.map(function (w) {
      var statusCls = w.is_active ? "active" : "inactive";
      var evTags = (w.event_types && w.event_types.length)
        ? w.event_types.map(function (e) { return '<span class="ev-tag">' + escHtml(e) + "</span>"; }).join("")
        : '<span class="ev-tag">all events</span>';
      return '<div class="wh-card" data-id="' + w.id + '">' +
        '<div class="wh-top">' +
          '<div class="wh-status ' + statusCls + '"></div>' +
          '<div class="wh-url">' + escHtml(w.url) + "</div>" +
          '<div class="wh-actions">' +
            '<button type="button" class="wh-test-btn" title="Send test">Test</button>' +
            '<button type="button" class="wh-log-btn" title="View deliveries">Log</button>' +
            '<button type="button" class="wh-edit-btn" title="Edit">Edit</button>' +
            '<button type="button" class="wh-toggle-btn" title="' + (w.is_active ? "Disable" : "Enable") + '">' + (w.is_active ? "Disable" : "Enable") + "</button>" +
            '<button type="button" class="wh-del-btn danger" title="Delete">Del</button>' +
          "</div>" +
        "</div>" +
        (w.description ? '<div class="wh-meta"><span class="wh-desc">' + escHtml(w.description) + "</span></div>" : "") +
        '<div class="wh-events-tags">' + evTags + "</div>" +
      "</div>";
    }).join("");

    // Bind card actions
    container.querySelectorAll(".wh-card").forEach(function (card) {
      var id = Number(card.dataset.id);
      card.querySelector(".wh-test-btn").addEventListener("click", function () { testEndpoint(id); });
      card.querySelector(".wh-log-btn").addEventListener("click", function () { showDeliveries(id); });
      card.querySelector(".wh-edit-btn").addEventListener("click", function () { openEditModal(id); });
      card.querySelector(".wh-toggle-btn").addEventListener("click", function () { toggleEndpoint(id); });
      card.querySelector(".wh-del-btn").addEventListener("click", function () { deleteEndpoint(id); });
    });
  }

  // ── CRUD Actions ────────────────────────────────────────────────────
  async function createEndpoint(data) {
    var token = await window.__bootPromise;
    var result = await reqJson("/api/v1/webhooks", {
      method: "POST",
      auth: true,
      token: token,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    // Show signing secret
    if (result.signing_secret) {
      $("secret-value").textContent = result.signing_secret;
      $("secret-modal").style.display = "";
    }
    await loadEndpoints();
  }

  async function updateEndpoint(id, data) {
    var token = await window.__bootPromise;
    await reqJson("/api/v1/webhooks/" + id, {
      method: "PATCH",
      auth: true,
      token: token,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    await loadEndpoints();
  }

  async function deleteEndpoint(id) {
    if (!window.confirm("Delete this webhook endpoint? This cannot be undone.")) return;
    try {
      var token = await window.__bootPromise;
      await fetch("/api/v1/webhooks/" + id, {
        method: "DELETE",
        headers: { "Authorization": "Bearer " + token },
      });
      if (window.showToast) window.showToast("Endpoint deleted.", "ok");
      await loadEndpoints();
    } catch (e) {
      if (window.showToast) window.showToast(mapErr(e), "error");
    }
  }

  async function toggleEndpoint(id) {
    var ep = endpoints.find(function (w) { return w.id === id; });
    if (!ep) return;
    try {
      await updateEndpoint(id, { is_active: !ep.is_active });
      if (window.showToast) window.showToast(ep.is_active ? "Disabled." : "Enabled.", "ok");
    } catch (e) {
      if (window.showToast) window.showToast(mapErr(e), "error");
    }
  }

  async function testEndpoint(id) {
    try {
      var token = await window.__bootPromise;
      var result = await reqJson("/api/v1/webhooks/" + id + "/test", {
        method: "POST",
        auth: true,
        token: token,
      });
      if (result.ok) {
        if (window.showToast) window.showToast("Test delivery succeeded (" + result.duration_ms + "ms).", "ok");
      } else {
        if (window.showToast) window.showToast("Test failed: " + (result.error || "unknown error"), "error");
      }
    } catch (e) {
      if (window.showToast) window.showToast(mapErr(e), "error");
    }
  }

  async function showDeliveries(id) {
    var container = $("deliveries-list");
    $("deliveries-modal").style.display = "";
    container.innerHTML = '<div class="empty">Loading...</div>';
    try {
      var token = await window.__bootPromise;
      var data = await reqJson("/api/v1/webhooks/" + id + "/deliveries?limit=50", {
        auth: true,
        token: token,
      });
      var items = data.items || [];
      if (!items.length) {
        container.innerHTML = '<div class="empty">No deliveries yet.</div>';
        return;
      }
      container.innerHTML = items.map(function (d) {
        return '<div class="dlv-row">' +
          '<span class="dlv-event">' + escHtml(d.event) + "</span>" +
          '<span class="dlv-status ' + escHtml(d.status) + '">' + escHtml(d.status) + (d.response_status_code ? " (" + d.response_status_code + ")" : "") + "</span>" +
          '<span class="dlv-ms">' + (d.duration_ms != null ? d.duration_ms + "ms" : "-") + "</span>" +
          '<span class="dlv-time">' + fmtTime(d.created_at) + "</span>" +
        "</div>";
      }).join("");
    } catch (e) {
      container.innerHTML = '<div class="empty">' + escHtml(mapErr(e)) + "</div>";
    }
  }

  // ── Modal Logic ─────────────────────────────────────────────────────
  function openCreateModal() {
    $("wh-modal-title").textContent = "Add Webhook Endpoint";
    $("wh-submit").textContent = "Create";
    $("wh-edit-id").value = "";
    $("wh-url").value = "";
    $("wh-desc").value = "";
    $("wh-events").querySelectorAll("input").forEach(function (cb) { cb.checked = false; });
    $("wh-modal").style.display = "";
    $("wh-url").focus();
  }

  function openEditModal(id) {
    var ep = endpoints.find(function (w) { return w.id === id; });
    if (!ep) return;
    $("wh-modal-title").textContent = "Edit Webhook Endpoint";
    $("wh-submit").textContent = "Save";
    $("wh-edit-id").value = String(id);
    $("wh-url").value = ep.url;
    $("wh-desc").value = ep.description || "";
    var evSet = new Set(ep.event_types || []);
    $("wh-events").querySelectorAll("input").forEach(function (cb) {
      cb.checked = evSet.has(cb.value);
    });
    $("wh-modal").style.display = "";
    $("wh-url").focus();
  }

  function closeModal(id) { $(id).style.display = "none"; }

  function getCheckedEvents() {
    var checked = [];
    $("wh-events").querySelectorAll("input:checked").forEach(function (cb) {
      checked.push(cb.value);
    });
    return checked;
  }

  // ── Event Bindings ──────────────────────────────────────────────────
  $("add-webhook-btn").addEventListener("click", openCreateModal);
  $("wh-modal-close").addEventListener("click", function () { closeModal("wh-modal"); });
  $("wh-cancel").addEventListener("click", function () { closeModal("wh-modal"); });
  $("secret-modal-close").addEventListener("click", function () { closeModal("secret-modal"); });
  $("deliveries-modal-close").addEventListener("click", function () { closeModal("deliveries-modal"); });

  $("secret-copy").addEventListener("click", function () {
    var val = $("secret-value").textContent;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(val).then(function () {
        if (window.showToast) window.showToast("Copied to clipboard.", "ok");
      });
    }
  });

  // Close modals on overlay click
  ["wh-modal", "secret-modal", "deliveries-modal"].forEach(function (id) {
    $(id).addEventListener("click", function (e) {
      if (e.target === this) closeModal(id);
    });
  });

  $("wh-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    var btn = $("wh-submit");
    var editId = $("wh-edit-id").value;
    var data = {
      url: $("wh-url").value.trim(),
      description: $("wh-desc").value.trim() || null,
      event_types: getCheckedEvents(),
    };
    window.PCUI.setButtonLoading(btn, true);
    try {
      if (editId) {
        await updateEndpoint(Number(editId), data);
        if (window.showToast) window.showToast("Endpoint updated.", "ok");
      } else {
        await createEndpoint(data);
        if (window.showToast) window.showToast("Endpoint created.", "ok");
      }
      closeModal("wh-modal");
    } catch (err) {
      if (window.showToast) window.showToast(mapErr(err), "error");
    } finally {
      window.PCUI.setButtonLoading(btn, false);
    }
  });

  // ── Init ────────────────────────────────────────────────────────────
  loadEndpoints();
  if (typeof lucide !== "undefined") lucide.createIcons();
})();
