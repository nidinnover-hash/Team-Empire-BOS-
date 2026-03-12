/* Deals dashboard page */
(function () {
  "use strict";

  let TOKEN = null;
  const H = (s) => Object.assign(document.createElement("div"), { innerHTML: s }).textContent;
  const $ = (sel) => document.querySelector(sel);
  const fmt$ = (n) => "$" + Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });

  async function api(path, opts = {}) {
    const headers = { Authorization: "Bearer " + TOKEN, "Content-Type": "application/json" };
    const res = await fetch("/api/v1" + path, { ...opts, headers });
    if (!res.ok) throw new Error(res.statusText);
    if (res.status === 204) return null;
    return res.json();
  }

  async function boot() {
    const r = await fetch("/web/api-token", { credentials: "same-origin" });
    if (!r.ok) return (location.href = "/web/login");
    const d = await r.json();
    TOKEN = d.token;
  }

  async function loadSummary() {
    const s = await api("/deals/summary");
    $("#k-total").textContent = s.total_deals;
    $("#k-value").textContent = fmt$(s.total_value);
    $("#k-won").textContent = fmt$(s.won_value);
    $("#k-winrate").textContent = s.win_rate + "%";
    $("#k-avg").textContent = fmt$(s.avg_deal_size);

    const stagesEl = $("#pipeline-stages");
    stagesEl.innerHTML = "";
    const colors = { discovery: "#6366f1", proposal: "#8b5cf6", negotiation: "#f59e0b", contract: "#3b82f6", won: "#22c55e", lost: "#ef4444" };
    (s.pipeline || []).forEach((p) => {
      const el = document.createElement("div");
      el.className = "kpi";
      el.style.borderLeft = "4px solid " + (colors[p.stage] || "#888");
      el.style.flex = "1";
      el.style.minWidth = "140px";
      el.innerHTML =
        '<div class="label">' + H(p.stage.charAt(0).toUpperCase() + p.stage.slice(1)) + "</div>" +
        '<div class="val">' + p.count + " &middot; " + fmt$(p.total_value) + "</div>";
      stagesEl.appendChild(el);
    });
  }

  async function loadDeals() {
    const stage = $("#filter-stage").value;
    const q = stage ? "?stage=" + stage : "";
    const tbody = $("#deals-body");
    const emptyMsg = $("#empty-msg");
    tbody.innerHTML = '<tr id="deals-loading-row"><td colspan="6" class="loading-cell"><div class="loading-inline loading-placeholder"><span class="spinner" aria-hidden="true"></span>Loading deals…</div></td></tr>';
    if (emptyMsg) emptyMsg.classList.add("u-hidden");

    const deals = await api("/deals" + q);
    tbody.innerHTML = "";
    if (emptyMsg) emptyMsg.classList.toggle("u-hidden", deals.length > 0);

    deals.forEach((d) => {
      const tr = document.createElement("tr");
      const stageClass = d.stage === "won" ? "badge-green" : d.stage === "lost" ? "badge-red" : "badge-blue";
      tr.innerHTML =
        "<td>" + H(d.title) + "</td>" +
        '<td><span class="badge ' + stageClass + '">' + H(d.stage) + "</span></td>" +
        "<td>" + fmt$(d.value) + "</td>" +
        "<td>" + (d.probability || 0) + "%</td>" +
        "<td>" + (d.expected_close_date || "—") + "</td>" +
        "<td>" + new Date(d.updated_at).toLocaleDateString() + "</td>";
      tbody.appendChild(tr);
    });
  }

  async function createDeal(e) {
    e.preventDefault();
    const titleInput = e.target.querySelector('input[name="title"]');
    const title = (titleInput && titleInput.value || '').trim();
    const fv = window.BOS && window.BOS.formValidation;
    if (fv && titleInput) {
      fv.clear(titleInput);
      if (!title) {
        fv.showError(titleInput, 'Title is required');
        titleInput.focus();
        return;
      }
    } else if (!title) return;
    const fd = new FormData(e.target);
    const body = {
      title: fd.get("title"),
      value: parseFloat(fd.get("value")) || 0,
      stage: fd.get("stage"),
      probability: parseInt(fd.get("probability")) || 0,
      description: fd.get("description") || null,
    };
    const ecd = fd.get("expected_close_date");
    if (ecd) body.expected_close_date = ecd;
    await api("/deals", { method: "POST", body: JSON.stringify(body) });
    $("#modal-overlay").style.display = "none";
    e.target.reset();
    loadSummary();
    loadDeals();
  }

  async function init() {
    await boot();
    loadSummary();
    loadDeals();

    $("#filter-stage").addEventListener("change", loadDeals);
    $("#btn-new-deal").addEventListener("click", () => ($("#modal-overlay").style.display = "flex"));
    $("#btn-cancel").addEventListener("click", () => ($("#modal-overlay").style.display = "none"));
    $("#deal-form").addEventListener("submit", createDeal);
  }

  init();
})();
if (typeof lucide !== "undefined") lucide.createIcons();
