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

  async function confirmDanger(message, detail) {
    var text = message || "Are you sure?";
    if (detail) text += "\n" + detail;
    return window.confirm(text);
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

  function getCsrfToken() {
    var pair = document.cookie.split("; ").find(function (c) { return c.startsWith("pc_csrf="); });
    return pair ? decodeURIComponent(pair.split("=").slice(1).join("=") || "") : "";
  }

  window.PCUI = {
    mapApiError: mapApiError,
    setButtonLoading: setButtonLoading,
    confirmDanger: confirmDanger,
    requestJson: requestJson,
    escapeHtml: escapeHtml,
    getCsrfToken: getCsrfToken,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _ensureReadAloudControl, { once: true });
  } else {
    _ensureReadAloudControl();
  }
})();
