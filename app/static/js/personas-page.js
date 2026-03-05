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

  try {
    var response = await fetch("/api/v1/personas/dashboard", { headers: headers() });
    if (response.ok) {
      var payload = await response.json();
      var kpis = payload.kpis || {};
      var rows = payload.rows || [];
      var totalEl = document.getElementById("k-total");
      var aiEl = document.getElementById("k-ai");
      var readyEl = document.getElementById("k-ready");
      if (totalEl) totalEl.textContent = String(kpis.total_clones || 0);
      if (aiEl) aiEl.textContent = String(kpis.avg_ai_level || 0);
      if (readyEl) readyEl.textContent = String(kpis.ready_count || 0);

      var body = document.getElementById("clone-body");
      if (body) {
        if (!rows.length) {
          body.innerHTML = '<tr><td colspan="5" style="text-align:center;opacity:.5">No clone profiles found</td></tr>';
        } else {
          body.innerHTML = rows.map(function (row) {
            return "<tr><td>"
              + esc(row.employee_name || "--")
              + "</td><td>"
              + esc(row.job_title || "--")
              + "</td><td>"
              + esc(row.readiness || "--")
              + "</td><td>"
              + esc(row.ai_level || 0)
              + "</td><td>"
              + esc(row.confidence || 0)
              + "</td></tr>";
          }).join("");
        }
      }
    }
  } catch (_error) {
    // no-op
  }

  if (typeof lucide !== "undefined") {
    lucide.createIcons();
  }
})();
