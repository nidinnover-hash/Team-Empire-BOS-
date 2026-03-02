(async function () {
  var token = await window.__bootPromise;
  var esc = function (value) {
    var text = String(value == null ? "" : value);
    if (window.PCUI && window.PCUI.escapeHtml) return window.PCUI.escapeHtml(text);
    return text.replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  };
  var headers = function () {
    return { Authorization: "Bearer " + token, "Content-Type": "application/json" };
  };
  var askInput = async function (title, message, defaultValue) {
    if (window.PCUI && window.PCUI.promptText) return window.PCUI.promptText(title, message, defaultValue);
    return window.prompt(message || "", defaultValue || "");
  };
  var showAlert = async function (message, title) {
    if (window.PCUI && window.PCUI.alertInfo) return window.PCUI.alertInfo(message, title);
    window.alert(message);
  };

  try {
    var reportsResponse = await fetch("/api/v1/performance/coaching?limit=20", { headers: headers() });
    if (reportsResponse.ok) {
      var reportsPayload = await reportsResponse.json();
      var items = reportsPayload.items || reportsPayload || [];
      document.getElementById("k-total").textContent = String(items.length);
      var body = document.getElementById("report-body");
      if (!items.length) {
        body.innerHTML = '<tr><td colspan="5" style="text-align:center;opacity:.5">No coaching reports yet</td></tr>';
      } else {
        body.innerHTML = items
          .map(function (item) {
            var employeeId = esc(item.employee_id || "--");
            var period = esc(item.period || "--");
            var score = esc(item.overall_score || "--");
            var status = esc(item.status || "draft");
            var createdAt = esc(item.created_at ? new Date(item.created_at).toLocaleDateString() : "--");
            return "<tr><td>" + employeeId + "</td><td>" + period + "</td><td>" + score + "</td><td>" + status + "</td><td>" + createdAt + "</td></tr>";
          })
          .join("");
      }
    }
  } catch (_error) {
    // no-op for dashboard bootstrap
  }

  var generateButton = document.getElementById("generate-btn");
  if (generateButton) {
    generateButton.onclick = async function () {
      var employeeId = await askInput("Generate Coaching", "Employee ID to coach:", "");
      if (!employeeId) return;
      try {
        var generateResponse = await fetch("/api/v1/performance/coaching/generate?employee_id=" + encodeURIComponent(employeeId), {
          method: "POST",
          headers: headers(),
        });
        if (generateResponse.ok) {
          await showAlert("Coaching report generated.", "Success");
          location.reload();
          return;
        }
        var errorPayload = await generateResponse.json().catch(function () { return {}; });
        await showAlert(errorPayload.detail || "Error generating report", "Error");
      } catch (error) {
        await showAlert("Error: " + (error && error.message ? error.message : "unknown"), "Error");
      }
    };
  }

  if (typeof lucide !== "undefined") {
    lucide.createIcons();
  }
})();
