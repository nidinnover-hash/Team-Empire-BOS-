/* eslint-disable no-var */
(function () {
  "use strict";
  var escHtml = window.PCUI.escapeHtml;
  var mapErr = window.PCUI.mapApiError;
  var reqJson = window.PCUI.requestJson;

  var STAGES = ["discovery", "proposal", "negotiation", "contract", "won", "lost"];
  var TOKEN = null;

  window.__bootPromise = fetch("/web/api-token")
    .then(function (r) { if (!r.ok) throw new Error("Session expired"); return r.json(); })
    .then(function (d) { TOKEN = d.token; return d.token; });

  function $(id) { return document.getElementById(id); }
  var fmt$ = function (n) { return "$" + Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 }); };

  async function load() {
    var board = $("kanban-board");
    try {
      TOKEN = await window.__bootPromise;
      if (!TOKEN) throw new Error("Session expired");

      var deals = await reqJson("/api/v1/deals?limit=500", { auth: true, token: TOKEN });
      if (!Array.isArray(deals)) deals = [];

      var summary = null;
      try { summary = await reqJson("/api/v1/deals/summary", { auth: true, token: TOKEN }); } catch (_) {}

      updateKPIs(deals, summary);
      renderBoard(board, deals);
    } catch (e) {
      board.innerHTML = '<div class="empty">' + escHtml(mapErr(e)) + "</div>";
    }
  }

  function updateKPIs(deals, summary) {
    $("k-total").textContent = deals.length;
    if (summary) {
      $("k-value").textContent = fmt$(summary.total_value);
      $("k-won").textContent = fmt$(summary.won_value);
      $("k-winrate").textContent = (summary.win_rate || 0) + "%";
    } else {
      var total = deals.reduce(function (s, d) { return s + (d.value || 0); }, 0);
      var won = deals.filter(function (d) { return d.stage === "won"; }).reduce(function (s, d) { return s + (d.value || 0); }, 0);
      $("k-value").textContent = fmt$(total);
      $("k-won").textContent = fmt$(won);
      var closed = deals.filter(function (d) { return d.stage === "won" || d.stage === "lost"; }).length;
      var wonCount = deals.filter(function (d) { return d.stage === "won"; }).length;
      $("k-winrate").textContent = closed ? Math.round((wonCount / closed) * 100) + "%" : "0%";
    }
  }

  function renderBoard(board, deals) {
    var byStage = {};
    STAGES.forEach(function (s) { byStage[s] = []; });
    deals.forEach(function (d) {
      var s = (d.stage || "discovery").toLowerCase();
      if (!byStage[s]) byStage[s] = [];
      byStage[s].push(d);
    });

    board.innerHTML = "";

    STAGES.forEach(function (stage) {
      var items = byStage[stage] || [];
      var colValue = items.reduce(function (s, d) { return s + (d.value || 0); }, 0);

      var col = document.createElement("div");
      col.className = "kanban-col";
      col.dataset.stage = stage;

      var header = document.createElement("div");
      header.className = "kanban-col-header";
      header.innerHTML =
        '<span>' + escHtml(stage.charAt(0).toUpperCase() + stage.slice(1)) +
        ' <span class="col-count">' + items.length + '</span></span>' +
        '<span class="col-value">' + escHtml(fmt$(colValue)) + '</span>';
      col.appendChild(header);

      var body = document.createElement("div");
      body.className = "kanban-col-body";

      items.forEach(function (deal) {
        var card = document.createElement("div");
        card.className = "kanban-card";
        card.draggable = true;
        card.dataset.dealId = deal.id;
        card.innerHTML =
          '<div class="kanban-card-title" title="' + escHtml(deal.title) + '">' + escHtml(deal.title) + "</div>" +
          '<div class="kanban-card-value">' + escHtml(fmt$(deal.value)) + "</div>" +
          '<div class="kanban-card-prob">' + (deal.probability || 0) + '% probability' +
          (deal.expected_close_date ? " &middot; Close: " + escHtml(deal.expected_close_date.slice(0, 10)) : "") +
          "</div>";

        card.addEventListener("dragstart", function (e) {
          card.classList.add("dragging");
          e.dataTransfer.setData("text/plain", deal.id);
          e.dataTransfer.effectAllowed = "move";
        });
        card.addEventListener("dragend", function () { card.classList.remove("dragging"); });

        body.appendChild(card);
      });

      col.appendChild(body);

      // Drop handling
      col.addEventListener("dragover", function (e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        col.classList.add("drag-over");
      });
      col.addEventListener("dragleave", function () { col.classList.remove("drag-over"); });
      col.addEventListener("drop", function (e) {
        e.preventDefault();
        col.classList.remove("drag-over");
        var dealId = e.dataTransfer.getData("text/plain");
        if (!dealId) return;
        moveDeal(parseInt(dealId, 10), stage, board);
      });

      board.appendChild(col);
    });
  }

  async function moveDeal(dealId, newStage, board) {
    try {
      await reqJson("/api/v1/deals/" + dealId, {
        auth: true,
        token: TOKEN,
        method: "PATCH",
        body: JSON.stringify({ stage: newStage }),
      });
      // Reload board
      var deals = await reqJson("/api/v1/deals?limit=500", { auth: true, token: TOKEN });
      if (!Array.isArray(deals)) deals = [];
      renderBoard(board, deals);
    } catch (e) {
      /* silently ignore — board will show stale state */
    }
  }

  load();
  if (typeof lucide !== "undefined") lucide.createIcons();
})();
