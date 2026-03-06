(async function () {
  var token = await window.__bootPromise;
  var roleName = "";
  var canViewDealValues = false;
  var canViewPipeline = false;
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
  var $ = function (id) { return document.getElementById(id); };
  var debounceTimer = null;

  async function loadRole() {
    try {
      if (window.PCUI && window.PCUI.loadRoleCapabilities) {
        var caps = await window.PCUI.loadRoleCapabilities();
        roleName = String(caps.roleName || "").toUpperCase();
        canViewPipeline = !!caps.canViewPipelineSummary;
        canViewDealValues = !!caps.canViewContactFinancials;
        return;
      }
      var r = await fetch("/web/session");
      if (!r.ok) return;
      var d = await r.json();
      roleName = String(d && d.user && d.user.role ? d.user.role : "").toUpperCase();
      canViewPipeline = roleName === "CEO" || roleName === "ADMIN" || roleName === "MANAGER";
      canViewDealValues = canViewPipeline;
    } catch (_e) {
      roleName = "";
      canViewDealValues = false;
      canViewPipeline = false;
    }
  }

  function formatCurrency(val) {
    if (val == null) return "--";
    return "$" + Number(val).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  }

  function formatDate(iso) {
    if (!iso) return "--";
    var d = new Date(iso);
    var now = new Date();
    var diff = (now - d) / 86400000;
    if (diff > 0 && diff < 1) return "Today";
    if (diff >= 1 && diff < 2) return "Yesterday";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function scoreBadge(score) {
    var cls = score >= 70 ? "badge-ok" : score >= 40 ? "badge-info" : "badge-muted";
    return '<span class="badge ' + cls + '">' + esc(score) + '</span>';
  }

  function stageBadge(stage) {
    var colors = { new: "badge-info", contacted: "badge-info", qualified: "badge-ok", proposal: "badge-ok", negotiation: "badge-warn", won: "badge-ok", lost: "badge-muted" };
    var cls = colors[stage] || "badge-muted";
    return '<span class="badge ' + cls + '">' + esc(stage) + '</span>';
  }

  // ── Pipeline Summary ──────────────────────────────────────────────
  async function loadPipelineSummary() {
    if (!canViewPipeline) {
      $("k-pipeline-val").textContent = "Restricted";
      return;
    }
    try {
      var resp = await fetch("/api/v1/contacts/pipeline-summary", { headers: headers() });
      if (!resp.ok) return;
      var data = await resp.json();
      var totalValue = 0;
      data.forEach(function (s) {
        var el = $("pf-" + s.stage);
        if (el) el.textContent = String(s.count);
        totalValue += s.total_deal_value || 0;
      });
      $("k-pipeline-val").textContent = formatCurrency(totalValue);
    } catch (_e) { /* ignore */ }
  }

  // ── Follow-up Due Count ───────────────────────────────────────────
  async function loadFollowUpCount() {
    try {
      var resp = await fetch("/api/v1/contacts/follow-up-due?limit=200", { headers: headers() });
      if (!resp.ok) return;
      var data = await resp.json();
      $("k-followup").textContent = String(data.length);
    } catch (_e) { /* ignore */ }
  }

  // ── Contact List ──────────────────────────────────────────────────
  async function loadContacts() {
    var params = "?limit=200";
    var stage = $("filter-stage").value;
    var rel = $("filter-relationship").value;
    var search = ($("filter-search").value || "").trim();
    if (stage) params += "&pipeline_stage=" + encodeURIComponent(stage);
    if (rel) params += "&relationship=" + encodeURIComponent(rel);
    if (search) params += "&search=" + encodeURIComponent(search);

    var body = $("tbody");
    var removeSkeleton = window.Micro
      ? window.Micro.skeletonLoad(body, { rows: 6, style: 'table' })
      : function () {};

    var response = await fetch("/api/v1/contacts" + params, { headers: headers() });
    if (!response.ok) { removeSkeleton(); return; }
    var items = await response.json();
    removeSkeleton();

    // Update KPIs with count-up
    var totalCount = items.length;
    var bizCount = items.filter(function (c) { return c.relationship === "business"; }).length;
    var perCount = items.filter(function (c) { return c.relationship === "personal"; }).length;
    var kTotal = $("k-total"); kTotal.dataset.countTo = totalCount; kTotal.dataset.counted = '';
    var kBiz = $("k-biz"); kBiz.dataset.countTo = bizCount; kBiz.dataset.counted = '';
    var kPer = $("k-per"); kPer.dataset.countTo = perCount; kPer.dataset.counted = '';
    if (window.Micro) window.Micro.countUp(document.querySelector('.kpi-row'));

    if (!items.length) {
      if (window.Micro) {
        window.Micro.emptyState(body.parentNode.parentNode, {
          icon: 'contact',
          title: 'No contacts found',
          desc: 'Add your first contact to start building your network.'
        });
      } else {
        body.innerHTML = '<tr><td colspan="7" style="text-align:center;opacity:.5">No contacts found</td></tr>';
      }
      return;
    }

    body.innerHTML = items.map(function (c) {
      var nameCell = '<td><strong>' + esc(c.name) + '</strong>' +
        (c.email ? '<div style="font-size:.75rem;color:var(--text-muted)">' + esc(c.email) + '</div>' : '') +
        '</td>';
      var companyCell = '<td>' + esc(c.company || "--") +
        (c.role ? '<div style="font-size:.75rem;color:var(--text-muted)">' + esc(c.role) + '</div>' : '') +
        '</td>';
      var stageCell = '<td>' + stageBadge(c.pipeline_stage || "new") + '</td>';
      var scoreCell = '<td>' + scoreBadge(c.lead_score || 0) + '</td>';
      var dealCell = '<td>' + (canViewDealValues ? (c.deal_value ? formatCurrency(c.deal_value) : '--') : "Restricted") + '</td>';
      var relCell = '<td><span class="badge">' + esc(c.relationship || "unknown") + '</span></td>';
      var followUp = '<td>' + formatDate(c.next_follow_up_at) + '</td>';
      return '<tr>' + nameCell + companyCell + stageCell + scoreCell + dealCell + relCell + followUp + '</tr>';
    }).join("");
    if (window.Micro) window.Micro.staggerIn(body);
  }

  // ── Filter Events ─────────────────────────────────────────────────
  $("filter-stage").addEventListener("change", loadContacts);
  $("filter-relationship").addEventListener("change", loadContacts);
  $("filter-search").addEventListener("input", function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(loadContacts, 300);
  });

  // ── Add Contact ───────────────────────────────────────────────────
  var addButton = $("add-btn");
  if (addButton) {
    addButton.onclick = async function () {
      var name = await askInput("New Contact", "Contact name:", "");
      if (!name) return;
      var email = await askInput("New Contact", "Email (optional):", "");
      email = email || undefined;
      var company = await askInput("New Contact", "Company (optional):", "");
      company = company || undefined;
      var stage = await askInput("New Contact", "Pipeline stage (new/contacted/qualified/proposal/negotiation/won/lost):", "new");
      stage = stage || "new";
      await fetch("/api/v1/contacts", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ name: name, email: email, company: company, pipeline_stage: stage }),
      });
      await loadContacts();
      await loadPipelineSummary();
    };
  }

  // ── Init ──────────────────────────────────────────────────────────
  await loadRole();
  if (!canViewPipeline) {
    var funnel = $("pipeline-funnel");
    if (funnel) {
      funnel.innerHTML = '<div class="kpi" style="width:100%"><div class="label">Pipeline</div><div class="val" style="font-size:.95rem">Restricted for your role</div></div>';
    }
  }
  await Promise.all([loadContacts(), loadPipelineSummary(), loadFollowUpCount()]);
  if (typeof lucide !== "undefined") lucide.createIcons();
})();
