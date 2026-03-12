(function () {
  function mapApiError(err) {
    var status = err && err.status ? Number(err.status) : 0;
    var msg = String((err && err.message) || "Request failed");
    if (msg.indexOf("session_expired") >= 0 || status === 401) return "Session expired. Please sign in again.";
    if (status === 403) return "You do not have permission for this action.";
    if (status === 404) return "Requested resource was not found.";
    if (status === 409) return "Conflict detected. Refresh and try again.";
    if (status === 422) return "Please check input fields and try again.";
    if (status === 429) return "Too many requests. Please wait and retry.";
    if (status >= 500) return "Server temporarily unavailable. Try again shortly.";
    if (msg.toLowerCase().indexOf("network") >= 0) return "Network issue. Check connection and retry.";
    return msg;
  }

  function setButtonLoading(button, loading, label) {
    if (!button) return;
    if (loading) {
      if (!button.dataset.baseText) button.dataset.baseText = button.textContent || "";
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      button.classList.add("is-loading");
      button.textContent = label || "Working...";
      return;
    }
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.classList.remove("is-loading");
    if (button.dataset.baseText) button.textContent = button.dataset.baseText;
  }

  function _ensureDialogRoot() {
    var existing = document.getElementById("pcui-dialog-root");
    if (existing) return existing;
    var root = document.createElement("div");
    root.id = "pcui-dialog-root";
    root.className = "pcui-dialog-root";
    root.innerHTML =
      '<div class="pcui-dialog" role="dialog" aria-modal="true">' +
      '<h3 id="pcui-dialog-title" class="pcui-dialog-title"></h3>' +
      '<p id="pcui-dialog-message" class="pcui-dialog-message"></p>' +
      '<div id="pcui-dialog-input-wrap" class="pcui-dialog-input-wrap u-hidden">' +
      '<input id="pcui-dialog-input" type="text" class="pcui-dialog-input" />' +
      "</div>" +
      '<div class="pcui-dialog-actions">' +
      '<button id="pcui-dialog-cancel" type="button" class="pcui-dialog-cancel">Cancel</button>' +
      '<button id="pcui-dialog-ok" type="button" class="pcui-dialog-ok">OK</button>' +
      "</div>" +
      "</div>";
    document.body.appendChild(root);
    return root;
  }

  function _runDialog(options) {
    return new Promise(function (resolve) {
      var root = _ensureDialogRoot();
      var dialog = root.querySelector(".pcui-dialog");
      var titleEl = document.getElementById("pcui-dialog-title");
      var msgEl = document.getElementById("pcui-dialog-message");
      var inputWrap = document.getElementById("pcui-dialog-input-wrap");
      var inputEl = document.getElementById("pcui-dialog-input");
      var okBtn = document.getElementById("pcui-dialog-ok");
      var cancelBtn = document.getElementById("pcui-dialog-cancel");
      var previousActive = document.activeElement;

      titleEl.textContent = options.title || "Confirm";
      msgEl.textContent = options.message || "";
      okBtn.textContent = options.okLabel || "OK";
      cancelBtn.textContent = options.cancelLabel || "Cancel";
      cancelBtn.classList.toggle("u-hidden", options.cancelLabel === "");

      var expectInput = options.mode === "prompt";
      inputWrap.classList.toggle("u-hidden", !expectInput);
      inputEl.value = expectInput ? (options.defaultValue || "") : "";

      function getFocusables() {
        var sel = "button, [href], input, select, textarea, [tabindex]:not([tabindex=\"-1\"])";
        return [].slice.call(dialog.querySelectorAll(sel)).filter(function (el) {
          return !el.disabled && (el.offsetWidth || el.offsetHeight);
        });
      }
      function onKeydown(evt) {
        if (evt.key !== "Tab") return;
        var focusables = getFocusables();
        if (focusables.length === 0) return;
        var first = focusables[0];
        var last = focusables[focusables.length - 1];
        if (evt.shiftKey) {
          if (document.activeElement === first) {
            evt.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            evt.preventDefault();
            first.focus();
          }
        }
      }

      function cleanup() {
        root.classList.remove("is-open");
        root.removeEventListener("click", onBackdropClick);
        dialog.removeEventListener("keydown", onKeydown);
        okBtn.removeEventListener("click", onOk);
        cancelBtn.removeEventListener("click", onCancel);
        if (previousActive && typeof previousActive.focus === "function") {
          try { previousActive.focus(); } catch (e) {}
        }
      }
      function onBackdropClick(evt) {
        if (evt.target === root) {
          cleanup();
          resolve(expectInput ? null : false);
        }
      }
      function onOk() {
        cleanup();
        resolve(expectInput ? inputEl.value : true);
      }
      function onCancel() {
        cleanup();
        resolve(expectInput ? null : false);
      }

      root.addEventListener("click", onBackdropClick);
      dialog.addEventListener("keydown", onKeydown);
      okBtn.addEventListener("click", onOk);
      cancelBtn.addEventListener("click", onCancel);
      root.classList.add("is-open");
      if (expectInput) inputEl.focus();
      else okBtn.focus();
    });
  }

  async function confirmDanger(message, detail) {
    var text = message || "Are you sure?";
    if (detail) text += "\n" + detail;
    try {
      return await _runDialog({ mode: "confirm", title: "Please Confirm", message: text, okLabel: "Confirm" });
    } catch (_err) {
      return window.confirm(text);
    }
  }

  async function promptText(title, message, defaultValue) {
    try {
      return await _runDialog({
        mode: "prompt",
        title: title || "Input Required",
        message: message || "",
        defaultValue: defaultValue || "",
        okLabel: "Submit",
      });
    } catch (_err) {
      return window.prompt(message || "", defaultValue || "");
    }
  }

  async function alertInfo(message, title) {
    try {
      await _runDialog({
        mode: "confirm",
        title: title || "Notice",
        message: message || "",
        okLabel: "OK",
        cancelLabel: "",
      });
      return;
    } catch (_err) {
      window.alert(message || "");
    }
  }

  async function requestJson(path, options) {
    var opts = options || {};
    var method = opts.method || "GET";
    var headers = opts.headers || {};
    var body = opts.body;
    var timeoutMs = typeof opts.timeoutMs === "number" ? opts.timeoutMs : 15000;

    if (window.PCAPI && window.PCAPI.safeFetchJson) {
      return window.PCAPI.safeFetchJson(path, {
        method: method,
        headers: headers,
        body: body,
        signal: opts.signal,
        auth: opts.auth === true,
        csrf: opts.csrf === true,
        token: opts.token,
        retries: typeof opts.retries === "number" ? opts.retries : 1,
        timeoutMs: timeoutMs,
      });
    }

    var controller = new AbortController();
    var onAbort = null;
    if (opts.signal) {
      if (opts.signal.aborted) controller.abort();
      else {
        onAbort = function () { controller.abort(); };
        opts.signal.addEventListener("abort", onAbort, { once: true });
      }
    }
    var timer = setTimeout(function () { controller.abort(); }, timeoutMs);
    try {
      var response = await fetch(path, {
        method: method,
        headers: headers,
        body: body,
        signal: controller.signal,
      });
      var payload = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        var err = new Error(payload.detail || ("Request failed (" + response.status + ")"));
        err.status = response.status;
        throw err;
      }
      return payload;
    } finally {
      clearTimeout(timer);
      if (opts.signal && onAbort) opts.signal.removeEventListener("abort", onAbort);
    }
  }

  function _extractReadableText() {
    var selected = "";
    try { selected = (window.getSelection && String(window.getSelection() || "")) || ""; } catch (_e) { selected = ""; }
    if (selected.trim()) return selected.trim();
    var root = document.querySelector("main") || document.querySelector(".main-wrap") || document.body;
    var text = (root && root.innerText) ? root.innerText : "";
    return String(text || "").replace(/\s+/g, " ").trim();
  }

  function _ensureReadAloudControl() {
    if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) return;
    if (document.getElementById("read-aloud-fab")) return;

    var fab = document.createElement("button");
    fab.id = "read-aloud-fab";
    fab.type = "button";
    fab.textContent = "Read";
    fab.setAttribute("aria-label", "Read page aloud");
    fab.style.position = "fixed";
    fab.style.right = "14px";
    fab.style.bottom = "14px";
    fab.style.zIndex = "9998";
    fab.style.minHeight = "44px";
    fab.style.minWidth = "92px";
    fab.style.padding = "10px 14px";
    fab.style.borderRadius = "999px";
    fab.style.border = "1px solid rgba(201,206,214,0.55)";
    fab.style.background = "linear-gradient(145deg, #2a2e35 0%, #1a1d23 100%)";
    fab.style.color = "#eef0f3";
    fab.style.fontSize = "12px";
    fab.style.fontWeight = "700";
    fab.style.letterSpacing = ".06em";
    fab.style.textTransform = "uppercase";
    fab.style.boxShadow = "0 8px 24px -12px rgba(0,0,0,.9)";
    fab.style.touchAction = "manipulation";

    var speaking = false;
    function updateFab() {
      fab.textContent = speaking ? "Stop" : "Read";
      fab.setAttribute("aria-label", speaking ? "Stop reading aloud" : "Read page aloud");
    }

    fab.addEventListener("click", function () {
      if (speaking || window.speechSynthesis.speaking) {
        window.speechSynthesis.cancel();
        speaking = false;
        updateFab();
        return;
      }
      var text = _extractReadableText();
      if (!text) return;
      var utterance = new SpeechSynthesisUtterance(text.slice(0, 6000));
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      utterance.volume = 1.0;
      utterance.onend = function () { speaking = false; updateFab(); };
      utterance.onerror = function () { speaking = false; updateFab(); };
      speaking = true;
      updateFab();
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    });

    document.body.appendChild(fab);

    // Hide Read Aloud FAB when a modal overlay is visible
    var _fabObserver = new MutationObserver(function () {
      var modalVisible = document.querySelector(".modal-overlay, .modal-mask, .modal-backdrop");
      fab.style.display = modalVisible ? "none" : "";
    });
    _fabObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "style"] });
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setSectionState(el, state, message) {
    if (!el) return;
    var safeState = String(state || "loading").toLowerCase();
    var msg = String(message || "");
    if (safeState === "loading") {
      el.innerHTML = '<div class="empty" style="opacity:.6">Loading...</div>';
      return;
    }
    if (safeState === "error") {
      el.innerHTML = '<div class="empty" style="color:#b91c1c">' + escapeHtml(msg || "Failed to load.") + "</div>";
      return;
    }
    if (safeState === "empty") {
      el.innerHTML = '<div class="empty">' + escapeHtml(msg || "No data available.") + "</div>";
      return;
    }
  }

  function getCsrfToken() {
    var pair = document.cookie.split("; ").find(function (c) { return c.startsWith("pc_csrf="); });
    return pair ? decodeURIComponent(pair.split("=").slice(1).join("=") || "") : "";
  }

  var _roleCapabilitiesPromise = null;
  function _buildRoleCapabilities(user) {
    var roleName = String(user && user.role ? user.role : "").toUpperCase();
    var orgId = Number(user && user.org_id ? user.org_id : 0);
    var canViewSensitiveFinancials = roleName === "CEO" || roleName === "ADMIN" || roleName === "MANAGER";
    var isSecurityAdmin = roleName === "CEO" || roleName === "ADMIN";
    var canManageApprovals = roleName === "CEO" || roleName === "ADMIN";
    var canAccessEmpireCockpit = roleName === "CEO" || roleName === "ADMIN" || roleName === "MANAGER";
    var canManageEmpireRouting = orgId === 1 && (roleName === "CEO" || roleName === "ADMIN");
    var canReviewEmpireIntelligence = orgId === 1 && (roleName === "CEO" || roleName === "ADMIN" || roleName === "MANAGER");
    return {
      roleName: roleName,
      orgId: orgId,
      canViewSensitiveFinancials: canViewSensitiveFinancials,
      canViewContactFinancials: canViewSensitiveFinancials,
      canViewPipelineSummary: canViewSensitiveFinancials,
      canCollectData: canViewSensitiveFinancials,
      canViewStorage: isSecurityAdmin,
      canExportData: roleName === "CEO",
      canManageTokens: isSecurityAdmin,
      canManageMedia: isSecurityAdmin,
      canManageSecurity: isSecurityAdmin,
      canManageIntegrations: isSecurityAdmin,
      canManageApprovals: canManageApprovals,
      canForgetLearned: roleName === "CEO",
      canAccessEmpireCockpit: canAccessEmpireCockpit,
      canManageEmpireRouting: canManageEmpireRouting,
      canReviewEmpireIntelligence: canReviewEmpireIntelligence,
    };
  }

  async function loadRoleCapabilities() {
    if (_roleCapabilitiesPromise) return _roleCapabilitiesPromise;
    _roleCapabilitiesPromise = (async function () {
      try {
        var response = await fetch("/web/session");
        if (!response.ok) return _buildRoleCapabilities(null);
        var payload = await response.json();
        var user = payload && payload.user ? payload.user : null;
        return _buildRoleCapabilities(user);
      } catch (_err) {
        return _buildRoleCapabilities(null);
      }
    })();
    return _roleCapabilitiesPromise;
  }

  // Global error handlers — capture unhandled JS errors for debugging
  var _errThrottle = 0;
  window.onerror = function(msg, src, line, col, err) {
    console.error("[GlobalError]", msg, src + ":" + line + ":" + col, err);
    if (Date.now() - _errThrottle > 10000 && window.showToast) {
      _errThrottle = Date.now();
      window.showToast("A client error occurred. Check console for details.", "error");
    }
  };
  window.addEventListener("unhandledrejection", function(event) {
    console.error("[UnhandledPromise]", event.reason);
    if (Date.now() - _errThrottle > 10000 && window.showToast) {
      _errThrottle = Date.now();
      window.showToast("An unhandled error occurred. Check console for details.", "error");
    }
  });

  var _retryToastTimer = null;
  function showRetryToast(seconds) {
    if (_retryToastTimer) { clearInterval(_retryToastTimer); _retryToastTimer = null; }
    var remaining = Math.max(1, seconds);
    var toastEl = document.getElementById("retry-toast");
    if (!toastEl) {
      toastEl = document.createElement("div");
      toastEl.id = "retry-toast";
      toastEl.style.cssText = "position:fixed;top:16px;right:16px;z-index:10000;background:#2d3748;color:#fff;padding:12px 18px;border-radius:8px;font-size:.82rem;box-shadow:0 4px 16px rgba(0,0,0,.3);display:flex;align-items:center;gap:10px;";
      var msgSpan = document.createElement("span");
      msgSpan.id = "retry-toast-msg";
      toastEl.appendChild(msgSpan);
      var closeBtn = document.createElement("button");
      closeBtn.type = "button";
      closeBtn.textContent = "Dismiss";
      closeBtn.style.cssText = "background:none;border:1px solid rgba(255,255,255,.3);color:#fff;border-radius:4px;padding:2px 8px;font-size:.7rem;cursor:pointer;";
      closeBtn.addEventListener("click", function () {
        if (_retryToastTimer) { clearInterval(_retryToastTimer); _retryToastTimer = null; }
        toastEl.style.display = "none";
      });
      toastEl.appendChild(closeBtn);
      document.body.appendChild(toastEl);
    }
    toastEl.style.display = "flex";
    var msgEl = document.getElementById("retry-toast-msg");
    function update() {
      if (remaining <= 0) {
        toastEl.style.display = "none";
        if (_retryToastTimer) { clearInterval(_retryToastTimer); _retryToastTimer = null; }
        return;
      }
      msgEl.textContent = "Rate limited. Retry in " + remaining + "s...";
      remaining--;
    }
    update();
    _retryToastTimer = setInterval(update, 1000);
  }

  window.PCUI = {
    mapApiError: mapApiError,
    setButtonLoading: setButtonLoading,
    confirmDanger: confirmDanger,
    promptText: promptText,
    alertInfo: alertInfo,
    requestJson: requestJson,
    escapeHtml: escapeHtml,
    setSectionState: setSectionState,
    getCsrfToken: getCsrfToken,
    showRetryToast: showRetryToast,
    loadRoleCapabilities: loadRoleCapabilities,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _ensureReadAloudControl, { once: true });
  } else {
    _ensureReadAloudControl();
  }
})();
