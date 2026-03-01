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
    var summaryResponse = await fetch("/api/v1/finance/summary", { headers: headers() });
    if (summaryResponse.ok) {
      var summary = await summaryResponse.json();
      document.getElementById("k-revenue").textContent = "$" + (summary.total_revenue_usd || 0);
      document.getElementById("k-charges").textContent = String(summary.total_charges || 0);
      document.getElementById("k-refund").textContent = "$" + (summary.total_refunded_usd || 0);
      document.getElementById("k-disputes").textContent = String(summary.disputes_open || 0);
    }
  } catch (_error) {
    // no-op
  }

  try {
    var txResponse = await fetch("/api/v1/finance?limit=50", { headers: headers() });
    if (txResponse.ok) {
      var items = await txResponse.json();
      var body = document.getElementById("tbody");
      if (!items.length) {
        body.innerHTML = '<tr><td colspan="4" style="text-align:center;opacity:.5">No transactions</td></tr>';
      } else {
        body.innerHTML = items.map(function (item) {
          var rawDate = item.date || item.created_at;
          var displayDate = esc(rawDate ? new Date(rawDate).toLocaleDateString() : "--");
          var description = esc(item.description || "--");
          var category = esc(item.category || "--");
          var amount = Number(item.amount);
          if (!Number.isFinite(amount)) amount = 0;
          return "<tr><td>" + displayDate + "</td><td>" + description + "</td><td>" + category + "</td><td>$" + amount + "</td></tr>";
        }).join("");
      }
    }
  } catch (_error) {
    // no-op
  }

  if (typeof lucide !== "undefined") {
    lucide.createIcons();
  }
})();
