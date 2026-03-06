(async function () {
  var token = await window.__bootPromise;
  if (!token) return;
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
  var fmtMoney = function (n) {
    var v = Number(n);
    if (!Number.isFinite(v)) v = 0;
    return "$" + v.toLocaleString();
  };
  var byDayKey = function (item) {
    var raw = item && (item.entry_date || item.date || item.created_at);
    if (!raw) return null;
    var d = new Date(raw);
    if (Number.isNaN(d.getTime())) return null;
    return d.toISOString().slice(0, 10);
  };

  var body = document.getElementById("tbody");
  var removeSkeleton = window.Micro
    ? window.Micro.skeletonLoad(body, { rows: 5, style: 'table' })
    : function () {};

  try {
    var summaryResponse = await fetch("/api/v1/finance/summary", { headers: headers() });
    if (summaryResponse.ok) {
      var summary = await summaryResponse.json();
      var kRev = document.getElementById("k-revenue");
      var kChg = document.getElementById("k-charges");
      var kRef = document.getElementById("k-refund");
      var kDis = document.getElementById("k-disputes");
      kRev.dataset.countTo = summary.total_income || summary.total_revenue_usd || 0; kRev.dataset.counted = '';
      kChg.dataset.countTo = summary.total_charges || 0; kChg.dataset.counted = '';
      kRef.dataset.countTo = summary.total_expense || summary.total_refunded_usd || 0; kRef.dataset.counted = '';
      kDis.dataset.countTo = summary.disputes_open || 0; kDis.dataset.counted = '';
      if (window.Micro) window.Micro.countUp(document.querySelector('.kpi-row'));
    }
  } catch (_error) {
    // no-op
  }

  try {
    var txResponse = await fetch("/api/v1/finance?limit=50", { headers: headers() });
    removeSkeleton();
    if (txResponse.ok) {
      var items = await txResponse.json();
      var chartHost = document.getElementById("finance-revenue-chart");
      if (!items.length) {
        if (chartHost) chartHost.innerHTML = '<div class="empty">No trend data yet</div>';
        if (window.Micro) {
          window.Micro.emptyState(body.parentNode.parentNode, {
            icon: 'wallet',
            title: 'No transactions',
            desc: 'Financial data will appear here once transactions are recorded.'
          });
        } else {
          body.innerHTML = '<tr><td colspan="4" style="text-align:center;opacity:.5">No transactions</td></tr>';
        }
      } else {
        var ordered = items.slice().sort(function (a, b) {
          return new Date(a.entry_date || a.created_at).getTime() - new Date(b.entry_date || b.created_at).getTime();
        });
        var daily = {};
        for (var i = 0; i < ordered.length; i++) {
          var tx = ordered[i];
          var amt = Number(tx.amount);
          if (!Number.isFinite(amt)) amt = 0;
          var key = byDayKey(tx);
          if (!key) continue;
          if (!daily[key]) daily[key] = { income: 0, expense: 0 };
          if (String(tx.type || "").toLowerCase() === "income") daily[key].income += amt;
          else daily[key].expense += amt;
        }
        var keys = Object.keys(daily).sort();
        var incomeSeries = [];
        var expenseSeries = [];
        var balanceSeries = [];
        var running = 0;
        for (var dIdx = 0; dIdx < keys.length; dIdx++) {
          var bucket = daily[keys[dIdx]];
          var income = Number(bucket.income || 0);
          var expense = Number(bucket.expense || 0);
          running += income - expense;
          incomeSeries.push(income);
          expenseSeries.push(expense);
          balanceSeries.push(running);
        }
        if (chartHost && window.PCChartsLite) {
          window.PCChartsLite.renderLineChart(chartHost, {
            caption: "Daily cashflow from recorded entries",
            ariaLabel: "Finance trend chart",
            series: [
              { name: "Income", values: incomeSeries, color: "var(--ok, #34c759)" },
              { name: "Expense", values: expenseSeries, color: "var(--danger, #ff3b30)" },
              { name: "Balance", values: balanceSeries, color: "var(--brand, #0a84ff)" }
            ]
          });
        }

        body.innerHTML = items.map(function (item) {
          var rawDate = item.entry_date || item.date || item.created_at;
          var displayDate = esc(rawDate ? new Date(rawDate).toLocaleDateString() : "--");
          var description = esc(item.description || "--");
          var category = esc(item.category || "--");
          var amount = Number(item.amount);
          if (!Number.isFinite(amount)) amount = 0;
          var signed = String(item.type || "").toLowerCase() === "income" ? amount : -amount;
          var amountStyle = signed >= 0 ? "color:var(--ok,#34c759)" : "color:var(--danger,#ff3b30)";
          return "<tr><td>" + displayDate + "</td><td>" + description + "</td><td>" + category + "</td><td style=\"" + amountStyle + "\">" + fmtMoney(signed) + "</td></tr>";
        }).join("");
        if (window.Micro) window.Micro.staggerIn(body);
      }
    }
  } catch (_error) {
    // no-op
  }

  if (typeof lucide !== "undefined") {
    lucide.createIcons();
  }
})();
