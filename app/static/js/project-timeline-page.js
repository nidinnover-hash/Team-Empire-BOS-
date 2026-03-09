/* eslint-disable no-var */
(function () {
  "use strict";
  var escHtml = window.PCUI.escapeHtml;
  var mapErr = window.PCUI.mapApiError;
  var reqJson = window.PCUI.requestJson;

  window.__bootPromise = fetch("/web/api-token")
    .then(function (r) { if (!r.ok) throw new Error("Session expired"); return r.json(); })
    .then(function (d) { return d.token; });

  function $(id) { return document.getElementById(id); }

  async function load() {
    var container = $("timeline-container");
    try {
      var token = await window.__bootPromise;
      if (!token) throw new Error("Session expired");

      var projects = await reqJson("/api/v1/projects?limit=200", { auth: true, token: token });
      if (!Array.isArray(projects)) projects = [];

      // Load goals for grouping
      var goals = [];
      try {
        goals = await reqJson("/api/v1/goals?limit=200", { auth: true, token: token });
        if (!Array.isArray(goals)) goals = [];
      } catch (_) { /* optional */ }

      updateKPIs(projects);
      renderTimeline(container, projects, goals);
    } catch (e) {
      container.innerHTML = '<div class="empty">' + escHtml(mapErr(e)) + "</div>";
    }
  }

  function updateKPIs(projects) {
    $("k-total").textContent = projects.length;
    $("k-active").textContent = projects.filter(function (p) { return p.status === "active"; }).length;
    $("k-completed").textContent = projects.filter(function (p) { return p.status === "completed"; }).length;
    var totalProgress = projects.reduce(function (s, p) { return s + (p.progress || 0); }, 0);
    $("k-progress").textContent = projects.length ? Math.round(totalProgress / projects.length) + "%" : "0%";
  }

  function renderTimeline(container, projects, goals) {
    if (!projects.length) {
      container.innerHTML = '<div class="empty">No projects found.</div>';
      return;
    }

    // Determine date range
    var now = new Date();
    var dates = [];
    projects.forEach(function (p) {
      if (p.created_at) dates.push(new Date(p.created_at));
      if (p.due_date) dates.push(new Date(p.due_date));
    });
    if (!dates.length) dates.push(now);

    var minDate = new Date(Math.min.apply(null, dates));
    var maxDate = new Date(Math.max.apply(null, dates.concat([now])));

    // Extend range by 1 month each side
    minDate.setDate(1);
    maxDate.setMonth(maxDate.getMonth() + 2);
    maxDate.setDate(0);

    var totalMs = maxDate.getTime() - minDate.getTime();
    if (totalMs <= 0) totalMs = 1;

    // Build month labels
    var months = [];
    var d = new Date(minDate);
    while (d <= maxDate) {
      months.push(d.toLocaleDateString("en", { month: "short", year: "2-digit" }));
      d.setMonth(d.getMonth() + 1);
    }

    // Group projects by goal
    var goalMap = {};
    goals.forEach(function (g) { goalMap[g.id] = g.title; });

    var grouped = {};
    projects.forEach(function (p) {
      var key = p.goal_id ? "goal-" + p.goal_id : "ungrouped";
      if (!grouped[key]) grouped[key] = { label: p.goal_id ? goalMap[p.goal_id] || "Goal #" + p.goal_id : "No Goal", items: [] };
      grouped[key].items.push(p);
    });

    // Render
    var html = "";

    // Header
    html += '<div class="tl-header">';
    html += '<div class="tl-name-col">Project</div>';
    html += '<div class="tl-chart-col">';
    months.forEach(function (m) { html += '<div class="tl-month">' + escHtml(m) + "</div>"; });
    html += "</div></div>";

    // Groups
    Object.keys(grouped).sort().forEach(function (key) {
      var group = grouped[key];
      html += '<div class="tl-goal-group">' + escHtml(group.label) + "</div>";

      group.items.forEach(function (p) {
        var start = p.created_at ? new Date(p.created_at) : now;
        var end = p.due_date ? new Date(p.due_date) : new Date(start.getTime() + 30 * 86400000);

        var leftPct = Math.max(0, ((start.getTime() - minDate.getTime()) / totalMs) * 100);
        var widthPct = Math.max(1, ((end.getTime() - start.getTime()) / totalMs) * 100);

        html += '<div class="tl-row">';
        html += '<div class="tl-row-name" title="' + escHtml(p.title) + '">' + escHtml(p.title) + "</div>";
        html += '<div class="tl-row-chart">';
        html += '<div class="tl-bar ' + escHtml(p.status || "active") + '" style="left:' + leftPct.toFixed(1) + '%;width:' + widthPct.toFixed(1) + '%">';
        html += (p.progress || 0) + "%";
        html += "</div></div></div>";
      });
    });

    container.innerHTML = html;
  }

  load();
  if (typeof lucide !== "undefined") lucide.createIcons();
})();
