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

  window.PCUI = {
    mapApiError: mapApiError,
    setButtonLoading: setButtonLoading,
    confirmDanger: confirmDanger,
  };
})();

