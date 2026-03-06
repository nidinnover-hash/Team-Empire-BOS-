/* eslint-disable no-var */
(function () {
  "use strict";
  var mapErr = window.PCUI.mapApiError;
  var reqJson = window.PCUI.requestJson;

  window.__bootPromise = fetch("/web/api-token")
    .then(function (r) { if (!r.ok) throw new Error("Session expired"); return r.json(); })
    .then(function (d) { return d.token; });

  // ── Helpers ──────────────────────────────────────────────────────────
  function $(id) { return document.getElementById(id); }
  function closeModal(id) { $(id).style.display = "none"; }

  // ── Load MFA Status ─────────────────────────────────────────────────
  async function loadMFAStatus() {
    try {
      var token = await window.__bootPromise;
      var data = await reqJson("/api/v1/mfa/status", { auth: true, token: token });
      renderMFACard(data.mfa_enabled);
    } catch (e) {
      $("mfa-status-badge").textContent = "Error";
      $("mfa-actions").innerHTML = '<p class="hint">' + mapErr(e) + "</p>";
    }
  }

  function renderMFACard(enabled) {
    var badge = $("mfa-status-badge");
    var actions = $("mfa-actions");
    if (enabled) {
      badge.textContent = "Enabled";
      badge.className = "status-badge enabled";
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn-primary danger";
      btn.textContent = "Disable MFA";
      btn.addEventListener("click", openDisableModal);
      actions.innerHTML = "";
      actions.appendChild(btn);
    } else {
      badge.textContent = "Disabled";
      badge.className = "status-badge disabled";
      var btn2 = document.createElement("button");
      btn2.type = "button";
      btn2.className = "btn-primary";
      btn2.textContent = "Enable MFA";
      btn2.addEventListener("click", startSetup);
      actions.innerHTML = "";
      actions.appendChild(btn2);
    }
  }

  // ── Setup Flow ──────────────────────────────────────────────────────
  async function startSetup() {
    try {
      var token = await window.__bootPromise;
      var data = await reqJson("/api/v1/mfa/setup", {
        method: "POST",
        auth: true,
        token: token,
      });
      // Display QR code
      var qr = $("qr-container");
      qr.innerHTML = "";
      if (data.qr_data_uri) {
        var img = document.createElement("img");
        img.src = data.qr_data_uri;
        img.alt = "TOTP QR Code";
        qr.appendChild(img);
      } else {
        qr.innerHTML = '<p class="hint">QR code generation unavailable. Use the manual secret below.</p>';
      }
      $("mfa-secret-text").textContent = data.secret || "";
      $("mfa-confirm-code").value = "";
      $("mfa-setup-modal").style.display = "";
      $("mfa-confirm-code").focus();
    } catch (e) {
      if (window.showToast) window.showToast(mapErr(e), "error");
    }
  }

  async function confirmSetup(e) {
    e.preventDefault();
    var code = $("mfa-confirm-code").value.trim();
    if (!code || code.length !== 6) return;
    var btn = $("mfa-confirm-btn");
    window.PCUI.setButtonLoading(btn, true);
    try {
      var token = await window.__bootPromise;
      await reqJson("/api/v1/mfa/confirm", {
        method: "POST",
        auth: true,
        token: token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ totp_code: code }),
      });
      closeModal("mfa-setup-modal");
      if (window.showToast) window.showToast("MFA enabled successfully.", "ok");
      await loadMFAStatus();
    } catch (err) {
      if (window.showToast) window.showToast(mapErr(err), "error");
    } finally {
      window.PCUI.setButtonLoading(btn, false);
    }
  }

  // ── Disable Flow ────────────────────────────────────────────────────
  function openDisableModal() {
    $("mfa-disable-code").value = "";
    $("mfa-disable-modal").style.display = "";
    $("mfa-disable-code").focus();
  }

  async function confirmDisable(e) {
    e.preventDefault();
    var code = $("mfa-disable-code").value.trim();
    if (!code || code.length !== 6) return;
    var btn = $("mfa-disable-btn");
    window.PCUI.setButtonLoading(btn, true);
    try {
      var token = await window.__bootPromise;
      await reqJson("/api/v1/mfa/disable", {
        method: "POST",
        auth: true,
        token: token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ totp_code: code }),
      });
      closeModal("mfa-disable-modal");
      if (window.showToast) window.showToast("MFA disabled.", "ok");
      await loadMFAStatus();
    } catch (err) {
      if (window.showToast) window.showToast(mapErr(err), "error");
    } finally {
      window.PCUI.setButtonLoading(btn, false);
    }
  }

  // ── Event Bindings ──────────────────────────────────────────────────
  $("mfa-setup-close").addEventListener("click", function () { closeModal("mfa-setup-modal"); });
  $("mfa-setup-cancel").addEventListener("click", function () { closeModal("mfa-setup-modal"); });
  $("mfa-disable-close").addEventListener("click", function () { closeModal("mfa-disable-modal"); });
  $("mfa-disable-cancel").addEventListener("click", function () { closeModal("mfa-disable-modal"); });

  $("mfa-confirm-form").addEventListener("submit", confirmSetup);
  $("mfa-disable-form").addEventListener("submit", confirmDisable);

  // Close modals on overlay click
  ["mfa-setup-modal", "mfa-disable-modal"].forEach(function (id) {
    $(id).addEventListener("click", function (e) {
      if (e.target === this) closeModal(id);
    });
  });

  // ── Init ────────────────────────────────────────────────────────────
  (async function initSecurityPage() {
    if (window.PCUI && window.PCUI.loadRoleCapabilities) {
      var caps = await window.PCUI.loadRoleCapabilities();
      if (!caps.canManageSecurity) {
        $("mfa-status-badge").textContent = "Restricted";
        $("mfa-actions").innerHTML = '<p class="hint">Security controls are restricted for your role.</p>';
        if (typeof lucide !== "undefined") lucide.createIcons();
        return;
      }
    }
    loadMFAStatus();
    if (typeof lucide !== "undefined") lucide.createIcons();
  })();
})();
