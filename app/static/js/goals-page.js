(async function () {
  var token = await window.__bootPromise;
  var esc = function (value) {
    var text = String(value == null ? "" : value);
    if (window.PCUI && window.PCUI.escapeHtml) return window.PCUI.escapeHtml(text);
    return text.replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  };
  var safeStatus = function (value) {
    var status = String(value || "").toLowerCase();
    if (status === "active" || status === "completed" || status === "paused" || status === "draft") {
      return status;
    }
    return "unknown";
  };
  var headers = function () {
    return { Authorization: "Bearer " + token, "Content-Type": "application/json" };
  };

  async function loadGoals() {
    var response = await fetch("/api/v1/goals?limit=100", { headers: headers() });
    if (!response.ok) return;
    var items = await response.json();
    document.getElementById("k-total").textContent = String(items.length);
    document.getElementById("k-active").textContent = String(items.filter(function (item) { return item.status === "active"; }).length);
    document.getElementById("k-done").textContent = String(items.filter(function (item) { return item.status === "completed"; }).length);

    var body = document.getElementById("tbody");
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="5" style="text-align:center;opacity:.5">No goals yet</td></tr>';
      return;
    }

    body.innerHTML = items.map(function (item) {
      var title = esc(item.title || "--");
      var category = esc(item.category || "--");
      var progress = Number(item.progress);
      if (!Number.isFinite(progress)) progress = 0;
      progress = Math.max(0, Math.min(100, progress));
      var progressText = esc(Math.round(progress));
      var status = safeStatus(item.status);
      var statusText = esc(status);
      var targetDate = esc(item.target_date || "--");
      return "<tr><td>" + title + "</td><td>" + category + "</td><td><div class=\"progress-bar\"><div class=\"fill\" style=\"width:" + progress + "%\"></div></div> " + progressText + "%</td><td><span class=\"badge badge-" + status + "\">" + statusText + "</span></td><td>" + targetDate + "</td></tr>";
    }).join("");
  }

  var addButton = document.getElementById("add-btn");
  if (addButton) {
    addButton.onclick = async function () {
      var title = prompt("Goal title:");
      if (!title) return;
      await fetch("/api/v1/goals", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ title: title }),
      });
      await loadGoals();
    };
  }

  await loadGoals();
  if (typeof lucide !== "undefined") {
    lucide.createIcons();
  }
})();
