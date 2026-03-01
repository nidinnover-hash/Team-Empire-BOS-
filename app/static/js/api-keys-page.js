/* eslint-disable no-var */
(function () {
  "use strict";
  var escHtml = window.PCUI.escapeHtml;
  var mapErr = window.PCUI.mapApiError;
  var reqJson = window.PCUI.requestJson;

  window.__bootPromise = fetch("/web/api-token")
    .then(function (r) { if (!r.ok) throw new Error("Session expired"); return r.json(); })
    .then(function (d) { return d.token; });

  var keys = [];

  // ── Helpers ──────────────────────────────────────────────────────────
  function $(id) { return document.getElementById(id); }

  function fmtTime(iso) {
    if (!iso) return "-";
    var d = new Date(iso);
    return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function closeModal(id) { $(id).style.display = "none"; }

  // ── Load & Render ───────────────────────────────────────────────────
  async function loadKeys() {
    var container = $("key-list");
    try {
      var token = await window.__bootPromise;
      if (!token) throw new Error("Session expired");
      var data = await reqJson("/api/v1/api-keys", { auth: true, token: token });
      keys = data.items || [];
      updateKPIs();
      renderList();
    } catch (e) {
      container.innerHTML = '<div class="empty">' + escHtml(mapErr(e)) + "</div>";
    }
  }

  function updateKPIs() {
    $("k-total").textContent = keys.length;
    $("k-active").textContent = keys.filter(function (k) { return k.is_active; }).length;
    $("k-revoked").textContent = keys.filter(function (k) { return !k.is_active; }).length;
  }

  function renderList() {
    var container = $("key-list");
    if (!keys.length) {
      container.innerHTML = '<div class="empty">No API keys created yet.</div>';
      return;
    }
    container.innerHTML = keys.map(function (k) {
      var statusCls = k.is_active ? "active" : "revoked";
      var cardCls = k.is_active ? "key-card" : "key-card revoked";
      var expired = k.expires_at && new Date(k.expires_at) < new Date();
      return '<div class="' + cardCls + '" data-id="' + k.id + '">' +
        '<div class="key-top">' +
          '<div class="key-status ' + statusCls + '"></div>' +
          '<div class="key-name">' + escHtml(k.name) + "</div>" +
          '<div class="key-prefix">' + escHtml(k.key_prefix) + "...</div>" +
          '<div class="key-actions">' +
            (k.is_active ? '<button type="button" class="key-revoke-btn" title="Revoke">Revoke</button>' : '<span style="font-size:.65rem;color:var(--text-faint)">Revoked</span>') +
          "</div>" +
        "</div>" +
        '<div class="key-meta">' +
          '<span class="key-scopes">' + escHtml(k.scopes) + "</span>" +
          "<span>Created " + fmtTime(k.created_at) + "</span>" +
          (k.last_used_at ? "<span>Last used " + fmtTime(k.last_used_at) + "</span>" : "") +
          (k.expires_at ? "<span>" + (expired ? "Expired" : "Expires") + " " + fmtTime(k.expires_at) + "</span>" : "") +
        "</div>" +
      "</div>";
    }).join("");

    // Bind revoke buttons
    container.querySelectorAll(".key-card").forEach(function (card) {
      var id = Number(card.dataset.id);
      var btn = card.querySelector(".key-revoke-btn");
      if (btn) {
        btn.addEventListener("click", function () { revokeKey(id); });
      }
    });
  }

  // ── Actions ─────────────────────────────────────────────────────────
  async function createKey(data) {
    var token = await window.__bootPromise;
    var result = await reqJson("/api/v1/api-keys", {
      method: "POST",
      auth: true,
      token: token,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (result.key) {
      $("secret-value").textContent = result.key;
      $("secret-modal").style.display = "";
    }
    await loadKeys();
  }

  async function revokeKey(id) {
    if (!window.confirm("Revoke this API key? This cannot be undone.")) return;
    try {
      var token = await window.__bootPromise;
      var res = await fetch("/api/v1/api-keys/" + id, {
        method: "DELETE",
        headers: { "Authorization": "Bearer " + token },
      });
      if (!res.ok) {
        var body = await res.json().catch(function () { return {}; });
        throw new Error(body.detail || ("Revoke failed (" + res.status + ")"));
      }
      if (window.showToast) window.showToast("API key revoked.", "ok");
      await loadKeys();
    } catch (e) {
      if (window.showToast) window.showToast(mapErr(e), "error");
    }
  }

  // ── Modal Logic ─────────────────────────────────────────────────────
  function openCreateModal() {
    $("key-name").value = "";
    $("key-scopes").value = "*";
    $("key-expiry").value = "";
    $("create-modal").style.display = "";
    $("key-name").focus();
  }

  // ── Event Bindings ──────────────────────────────────────────────────
  $("add-key-btn").addEventListener("click", openCreateModal);
  $("create-modal-close").addEventListener("click", function () { closeModal("create-modal"); });
  $("create-cancel").addEventListener("click", function () { closeModal("create-modal"); });
  $("secret-modal-close").addEventListener("click", function () { closeModal("secret-modal"); });

  $("secret-copy").addEventListener("click", function () {
    var val = $("secret-value").textContent;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(val).then(function () {
        if (window.showToast) window.showToast("Copied to clipboard.", "ok");
      });
    }
  });

  // Close modals on overlay click
  ["create-modal", "secret-modal"].forEach(function (id) {
    $(id).addEventListener("click", function (e) {
      if (e.target === this) closeModal(id);
    });
  });

  $("create-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    var btn = $("create-submit");
    var data = {
      name: $("key-name").value.trim(),
      scopes: $("key-scopes").value.trim() || "*",
    };
    var expiry = $("key-expiry").value.trim();
    if (expiry) data.expires_in_days = Number(expiry);
    window.PCUI.setButtonLoading(btn, true);
    try {
      await createKey(data);
      if (window.showToast) window.showToast("API key created.", "ok");
      closeModal("create-modal");
    } catch (err) {
      if (window.showToast) window.showToast(mapErr(err), "error");
    } finally {
      window.PCUI.setButtonLoading(btn, false);
    }
  });

  // ── Init ────────────────────────────────────────────────────────────
  loadKeys();
  if (typeof lucide !== "undefined") lucide.createIcons();
})();
