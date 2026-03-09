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
  var askInput = async function (title, message, defaultValue) {
    if (window.PCUI && window.PCUI.promptText) return window.PCUI.promptText(title, message, defaultValue);
    return window.prompt(message || "", defaultValue || "");
  };
  var askConfirm = async function (message) {
    if (window.PCUI && window.PCUI.confirmDanger) return window.PCUI.confirmDanger(message);
    return window.confirm(message);
  };

  async function loadProjects() {
    var body = document.getElementById("tbody");
    var removeSkeleton = window.Micro
      ? window.Micro.skeletonLoad(body, { rows: 4, style: 'table' })
      : function () {};

    var response = await fetch("/api/v1/projects?limit=100", { headers: headers() });
    if (!response.ok) { removeSkeleton(); return; }
    var items = await response.json();
    removeSkeleton();

    // Update KPIs with count-up
    var totalEl = document.getElementById("k-total");
    var activeEl = document.getElementById("k-active");
    var doneEl = document.getElementById("k-done");
    var activeCount = items.filter(function (item) { return item.status === "active"; }).length;
    var doneCount = items.filter(function (item) { return item.status === "completed"; }).length;
    totalEl.dataset.countTo = items.length; totalEl.dataset.counted = '';
    activeEl.dataset.countTo = activeCount; activeEl.dataset.counted = '';
    doneEl.dataset.countTo = doneCount; doneEl.dataset.counted = '';
    if (window.Micro) window.Micro.countUp(document.querySelector('.kpi-row'));

    if (!items.length) {
      if (window.Micro) {
        window.Micro.emptyState(body.parentNode.parentNode, {
          icon: 'folder-kanban',
          title: 'No projects yet',
          desc: 'Create your first project to start tracking work.'
        });
      } else {
        body.innerHTML = '<tr><td colspan="5" style="text-align:center;opacity:.5">No projects yet</td></tr>';
      }
      return;
    }

    body.innerHTML = items.map(function (item) {
      var title = esc(item.title || "--");
      var category = esc(item.category || "--");
      var status = safeStatus(item.status);
      var statusText = esc(status);
      var dueDate = esc(item.due_date || "--");
      var progress = Math.max(0, Math.min(100, item.progress || 0));
      var barColor = progress === 100 ? "var(--ok, #38a169)" : progress > 50 ? "var(--brand, #3182ce)" : "var(--text-faint, #aaa)";
      var progressBar = '<div style="display:flex;align-items:center;gap:.4rem">'
        + '<div style="flex:1;height:6px;background:var(--border,#ddd);border-radius:3px;overflow:hidden">'
        + '<div style="width:' + progress + '%;height:100%;background:' + barColor + ';border-radius:3px;transition:width .3s"></div>'
        + '</div><span style="font-size:.75rem;color:var(--text-faint);min-width:2.5em;text-align:right">' + progress + '%</span></div>';
      var projectId = Number(item.id);
      if (!Number.isFinite(projectId) || projectId < 1) projectId = 0;
      return "<tr><td>" + title + "</td><td>" + category + "</td><td><span class=\"badge badge-" + status + "\">" + statusText + "</span></td><td>" + progressBar + "</td><td>" + dueDate + "</td><td><button class=\"btn-sm\" data-del=\"" + projectId + "\" type=\"button\">Delete</button></td></tr>";
    }).join("");

    body.querySelectorAll("[data-del]").forEach(function (button) {
      button.addEventListener("click", async function () {
        var confirmed = await askConfirm("Delete project?");
        if (!confirmed) return;
        var projectId = button.getAttribute("data-del");
        await fetch("/api/v1/projects/" + encodeURIComponent(projectId), { method: "DELETE", headers: headers() });
        await loadProjects();
      });
    });
  }

  var addButton = document.getElementById("add-btn");
  if (addButton) {
    addButton.onclick = async function () {
      var title = await askInput("New Project", "Project title:", "");
      if (!title) return;
      await fetch("/api/v1/projects", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ title: title }),
      });
      await loadProjects();
    };
  }

  await loadProjects();
  if (typeof lucide !== "undefined") {
    lucide.createIcons();
  }
})();
