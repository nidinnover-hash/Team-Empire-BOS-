/* eslint-disable no-var */
(function () {
  "use strict";
  var escHtml = window.PCUI.escapeHtml;
  var mapErr = window.PCUI.mapApiError;
  var reqJson = window.PCUI.requestJson;

  window.__bootPromise = fetch("/web/api-token")
    .then(function (r) { if (!r.ok) throw new Error("Session expired"); return r.json(); })
    .then(function (d) { return d.token; });

  var members = [];
  var employees = [];
  var ROLES = ["CEO", "ADMIN", "MANAGER", "STAFF", "OWNER", "TECH_LEAD", "OPS_MANAGER", "DEVELOPER", "VIEWER"];

  function $(id) { return document.getElementById(id); }

  function getInitials(name) {
    if (!name) return "?";
    var parts = name.trim().split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    return name.slice(0, 2).toUpperCase();
  }

  // ── Load & Render ───────────────────────────────────────────────────
  async function loadMembers() {
    var container = $("member-list");
    try {
      var token = await window.__bootPromise;
      if (!token) throw new Error("Session expired");
      var usersP = reqJson("/api/v1/users?limit=200", { auth: true, token: token });
      var empsP = reqJson("/api/v1/ops/employees?limit=200", { auth: true, token: token }).catch(function () { return []; });
      var results = await Promise.all([usersP, empsP]);
      members = Array.isArray(results[0]) ? results[0] : [];
      employees = Array.isArray(results[1]) ? results[1] : [];
      updateKPIs();
      renderList();
    } catch (e) {
      container.innerHTML = '<div class="empty">' + escHtml(mapErr(e)) + "</div>";
    }
  }

  function findEmployee(userEmail) {
    return employees.find(function (emp) { return emp.email === userEmail; }) || null;
  }

  function updateKPIs() {
    $("k-total").textContent = members.length;
    $("k-active").textContent = members.filter(function (m) { return m.is_active; }).length;
    $("k-inactive").textContent = members.filter(function (m) { return !m.is_active; }).length;
  }

  function getFilteredMembers() {
    var query = ($("filter-query") ? $("filter-query").value : "").toLowerCase().trim();
    var roleFilter = $("filter-role") ? $("filter-role").value : "";
    var statusFilter = $("filter-status") ? $("filter-status").value : "";
    return members.filter(function (m) {
      if (query && m.name.toLowerCase().indexOf(query) === -1 && m.email.toLowerCase().indexOf(query) === -1) return false;
      if (roleFilter && m.role !== roleFilter) return false;
      if (statusFilter === "active" && !m.is_active) return false;
      if (statusFilter === "inactive" && m.is_active) return false;
      return true;
    });
  }

  function renderList() {
    var container = $("member-list");
    var filtered = getFilteredMembers();
    if (!filtered.length) {
      container.innerHTML = '<div class="empty">' + (members.length ? "No members match your filters." : "No team members found.") + '</div>';
      return;
    }
    container.innerHTML = filtered.map(function (m) {
      var roleCls = (m.role === "CEO" || m.role === "ADMIN" || m.role === "MANAGER") ? " " + m.role : "";
      var statusCls = m.is_active ? "active" : "inactive";
      var roleOpts = ROLES.map(function (r) {
        return '<option value="' + r + '"' + (r === m.role ? ' selected' : '') + '>' + r + '</option>';
      }).join("");

      var emp = findEmployee(m.email);
      var jobTitle = emp && emp.job_title ? emp.job_title : "";
      return '<div class="member-card" data-id="' + m.id + '">' +
        '<div class="member-avatar">' + escHtml(getInitials(m.name)) + '</div>' +
        '<div class="member-info">' +
          '<div class="member-name">' + escHtml(m.name) + '</div>' +
          '<div class="member-email">' + escHtml(m.email) + '</div>' +
          (jobTitle ? '<div class="member-title">' + escHtml(jobTitle) + '</div>' : '') +
        '</div>' +
        '<span class="role-badge' + roleCls + '">' + escHtml(m.role) + '</span>' +
        '<div class="status-dot ' + statusCls + '" title="' + statusCls + '"></div>' +
        '<div class="member-actions">' +
          '<select class="role-select" title="Change role">' + roleOpts + '</select>' +
          '<button type="button" class="toggle-active-btn">' + (m.is_active ? "Deactivate" : "Activate") + '</button>' +
        '</div>' +
      '</div>';
    }).join("");

    // Bind actions
    container.querySelectorAll(".member-card").forEach(function (card) {
      var id = Number(card.dataset.id);
      card.querySelector(".role-select").addEventListener("change", function () {
        changeRole(id, this.value);
      });
      card.querySelector(".toggle-active-btn").addEventListener("click", function () {
        toggleActive(id);
      });
    });
  }

  // ── Actions ────────────────────────────────────────────────────────
  async function changeRole(userId, newRole) {
    try {
      var token = await window.__bootPromise;
      await reqJson("/api/v1/users/" + userId + "/role", {
        method: "PATCH", auth: true, token: token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: newRole }),
      });
      if (window.showToast) window.showToast("Role updated.", "ok");
      await loadMembers();
    } catch (e) {
      if (window.showToast) window.showToast(mapErr(e), "error");
      await loadMembers();
    }
  }

  async function toggleActive(userId) {
    var member = members.find(function (m) { return m.id === userId; });
    if (!member) return;
    var newState = !member.is_active;
    var action = newState ? "activate" : "deactivate";
    if (!window.confirm("Are you sure you want to " + action + " " + member.name + "?")) return;
    try {
      var token = await window.__bootPromise;
      await reqJson("/api/v1/users/" + userId + "/active", {
        method: "PATCH", auth: true, token: token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: newState }),
      });
      if (window.showToast) window.showToast("User " + action + "d.", "ok");
      await loadMembers();
    } catch (e) {
      if (window.showToast) window.showToast(mapErr(e), "error");
    }
  }

  async function createMember(data) {
    var token = await window.__bootPromise;
    await reqJson("/api/v1/users/team-member", {
      method: "POST", auth: true, token: token,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    await loadMembers();
  }

  async function loadDepartments() {
    try {
      var token = await window.__bootPromise;
      var depts = await reqJson("/api/v1/departments?limit=200", { auth: true, token: token });
      var sel = $("inv-department");
      if (!sel || !Array.isArray(depts)) return;
      depts.forEach(function (d) {
        var opt = document.createElement("option");
        opt.value = d.id;
        opt.textContent = d.name;
        sel.appendChild(opt);
      });
    } catch (_) {
      // departments endpoint may not exist yet — silently skip
    }
  }

  // ── Modal Logic ───────────────────────────────────────────────────
  function closeModal(id) { $(id).style.display = "none"; }

  $("invite-btn").addEventListener("click", function () {
    $("invite-form").reset();
    $("invite-modal").style.display = "";
    $("inv-name").focus();
  });
  $("invite-modal-close").addEventListener("click", function () { closeModal("invite-modal"); });
  $("invite-cancel").addEventListener("click", function () { closeModal("invite-modal"); });
  $("invite-modal").addEventListener("click", function (e) {
    if (e.target === this) closeModal("invite-modal");
  });

  $("invite-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    var btn = $("invite-submit");
    // Get org_id from session
    var sessionRes = await fetch("/web/session");
    var session = await sessionRes.json();
    var orgId = session.user && session.user.org_id ? session.user.org_id : 1;

    var deptVal = $("inv-department") ? $("inv-department").value : "";
    var data = {
      organization_id: orgId,
      name: $("inv-name").value.trim(),
      email: $("inv-email").value.trim(),
      password: $("inv-password").value,
      role: $("inv-role").value,
      job_title: $("inv-job-title") ? $("inv-job-title").value.trim() || null : null,
      department_id: deptVal ? Number(deptVal) : null,
      github_username: $("inv-github") ? $("inv-github").value.trim() || null : null,
      clickup_user_id: $("inv-clickup") ? $("inv-clickup").value.trim() || null : null,
    };
    window.PCUI.setButtonLoading(btn, true);
    try {
      await createMember(data);
      if (window.showToast) window.showToast("Team member added.", "ok");
      closeModal("invite-modal");
    } catch (err) {
      if (window.showToast) window.showToast(mapErr(err), "error");
    } finally {
      window.PCUI.setButtonLoading(btn, false);
    }
  });

  // ── Mini-map (location tracking) ───────────────────────────────
  async function loadMiniMap() {
    if (typeof L === "undefined") return; // Leaflet not loaded
    try {
      var token = await window.__bootPromise;
      var res = await fetch("/api/v1/locations/active", {
        headers: { Authorization: "Bearer " + token },
      });
      if (!res.ok) return; // silently skip if no access
      var locs = await res.json();
      if (!locs.length) return;

      $("team-map-card").style.display = "";
      var map = L.map("team-mini-map").setView([locs[0].latitude, locs[0].longitude], 10);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
        maxZoom: 19,
      }).addTo(map);

      var markers = [];
      locs.forEach(function (loc) {
        var m = L.marker([loc.latitude, loc.longitude]).addTo(map);
        m.bindPopup('<strong>' + escHtml(loc.employee_name || "Employee #" + loc.employee_id) + '</strong>');
        markers.push(m);
      });
      if (markers.length) map.fitBounds(L.featureGroup(markers).getBounds().pad(0.1));
    } catch (_) {
      // silently ignore — feature may not be enabled
    }
  }

  // ── Filters ─────────────────────────────────────────────────────
  if ($("filter-query")) $("filter-query").addEventListener("input", renderList);
  if ($("filter-role")) $("filter-role").addEventListener("change", renderList);
  if ($("filter-status")) $("filter-status").addEventListener("change", renderList);

  // ── Init ──────────────────────────────────────────────────────────
  loadMembers();
  loadDepartments();
  loadMiniMap();
  if (typeof lucide !== "undefined") lucide.createIcons();
})();
