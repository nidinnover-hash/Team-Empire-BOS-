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

  var renderRows = function (items) {
    var body = document.getElementById("report-body");
    if (!body) return;
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="5" style="text-align:center;opacity:.5">No coaching reports yet</td></tr>';
      return;
    }
    body.innerHTML = items
      .map(function (item) {
        var employee = esc(item.employee_id || "--");
        var reportType = esc(item.report_type || "--");
        var status = esc(item.status || "pending");
        var recs = item.recommendations && Array.isArray(item.recommendations.recommendations)
          ? item.recommendations.recommendations.length
          : 0;
        var createdAt = esc(item.created_at ? new Date(item.created_at).toLocaleString() : "--");
        return "<tr><td>" + employee + "</td><td>" + reportType + "</td><td>" + status + "</td><td>" + recs + "</td><td>" + createdAt + "</td></tr>";
      })
      .join("");
  };

  var updateKpis = function (items) {
    var total = items.length;
    var pending = items.filter(function (item) { return item.status === "pending"; }).length;
    var approved = items.filter(function (item) { return item.status === "approved"; }).length;
    var approvalRate = total ? Math.round((approved / total) * 100) + "%" : "--";
    var totalEl = document.getElementById("k-total");
    var scoreEl = document.getElementById("k-score");
    var pendingEl = document.getElementById("k-pending");
    if (totalEl) totalEl.textContent = String(total);
    if (scoreEl) scoreEl.textContent = approvalRate;
    if (pendingEl) pendingEl.textContent = String(pending);
  };

  try {
    var reportsResponse = await fetch("/api/v1/coaching?limit=20", { headers: headers() });
    if (reportsResponse.ok) {
      var reportsPayload = await reportsResponse.json();
      var items = reportsPayload.items || reportsPayload || [];
      updateKpis(items);
      renderRows(items);
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
        var numericEmployeeId = parseInt(employeeId, 10);
        if (!numericEmployeeId) {
          await showAlert("Please provide a valid numeric employee ID.", "Validation");
          return;
        }
        var generateResponse = await fetch("/api/v1/coaching/employee/" + encodeURIComponent(numericEmployeeId), {
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
