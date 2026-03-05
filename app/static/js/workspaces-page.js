/* ═══════════════════════════════════════════════════════════════════════════
   Workspaces Page — CRUD + Members management
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  const grid = document.getElementById("ws-grid");
  const createBtn = document.getElementById("ws-page-create-btn");
  const modalOverlay = document.getElementById("ws-page-modal-overlay");
  const modalTitle = document.getElementById("ws-page-modal-title");
  const modalClose = document.getElementById("ws-page-modal-close");
  const modalCancel = document.getElementById("ws-page-modal-cancel");
  const modalSave = document.getElementById("ws-page-modal-save");
  const editIdInput = document.getElementById("ws-edit-id");
  const nameInput = document.getElementById("ws-field-name");
  const typeSelect = document.getElementById("ws-field-type");
  const descInput = document.getElementById("ws-field-desc");

  const membersOverlay = document.getElementById("ws-members-overlay");
  const membersTitle = document.getElementById("ws-members-title");
  const membersClose = document.getElementById("ws-members-close");
  const membersList = document.getElementById("ws-members-list");
  const memberUserIdInput = document.getElementById("ws-member-user-id");
  const memberRoleSelect = document.getElementById("ws-member-role-override");
  const memberAddBtn = document.getElementById("ws-member-add-btn");

  const TYPE_ICONS = {
    general: "brain",
    department: "building-2",
    project: "folder-kanban",
    client: "briefcase",
  };

  let currentMembersWsId = null;

  // ── API helpers ────────────────────────────────────────────────────────
  async function api(path, opts = {}) {
    const token = window.__bootPromise ? await window.__bootPromise : null;
    const headers = { ...opts.headers };
    if (token) headers.Authorization = `Bearer ${token}`;
    if (opts.body) headers["Content-Type"] = "application/json";
    const resp = await fetch(`/api/v1${path}`, { ...opts, headers });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    if (resp.status === 204) return null;
    return resp.json();
  }

  // ── Load & render workspaces ───────────────────────────────────────────
  async function loadWorkspaces() {
    try {
      const list = await api("/workspaces?active_only=false");
      renderGrid(list);
    } catch (err) {
      grid.innerHTML = `<div class="ws-loading">Failed to load workspaces</div>`;
    }
  }

  function renderGrid(list) {
    if (!list.length) {
      grid.innerHTML = `<div class="ws-loading">No workspaces yet. Create one to get started.</div>`;
      return;
    }
    grid.innerHTML = list.map((ws, i) => {
      const icon = TYPE_ICONS[ws.workspace_type] || "brain";
      const inactive = !ws.is_active;
      return `
      <div class="ws-card" style="animation-delay:${i * 0.05}s">
        <div class="ws-card-head">
          <div class="ws-card-icon${inactive ? " inactive" : ""}"><i data-lucide="${icon}"></i></div>
          <div class="ws-card-info">
            <div class="ws-card-name">${_esc(ws.name)}</div>
            <div class="ws-card-slug">${_esc(ws.slug)}</div>
          </div>
        </div>
        ${ws.description ? `<div class="ws-card-desc">${_esc(ws.description)}</div>` : ""}
        <div class="ws-card-meta">
          <span class="ws-card-badge type">${_esc(ws.workspace_type)}</span>
          ${ws.is_default ? '<span class="ws-card-badge default">Default</span>' : ""}
          ${inactive ? '<span class="ws-card-badge inactive">Inactive</span>' : ""}
        </div>
        <div class="ws-card-actions">
          <button class="ws-card-btn" data-action="edit" data-ws='${JSON.stringify(ws).replace(/'/g, "&#39;")}' type="button">
            <i data-lucide="pencil"></i> Edit
          </button>
          <button class="ws-card-btn" data-action="members" data-ws-id="${ws.id}" data-ws-name="${_esc(ws.name)}" type="button">
            <i data-lucide="users"></i> Members
          </button>
          ${!ws.is_default ? `<button class="ws-card-btn" data-action="toggle" data-ws-id="${ws.id}" data-active="${ws.is_active}" type="button">
            <i data-lucide="${ws.is_active ? "eye-off" : "eye"}"></i> ${ws.is_active ? "Deactivate" : "Activate"}
          </button>` : ""}
        </div>
      </div>`;
    }).join("");

    if (window.lucide) lucide.createIcons({ nodes: grid.querySelectorAll("i[data-lucide]") });
    bindCardActions();
  }

  function bindCardActions() {
    grid.querySelectorAll("[data-action]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.action;
        if (action === "edit") {
          const ws = JSON.parse(btn.dataset.ws);
          openEditModal(ws);
        } else if (action === "members") {
          openMembers(parseInt(btn.dataset.wsId, 10), btn.dataset.wsName);
        } else if (action === "toggle") {
          const id = parseInt(btn.dataset.wsId, 10);
          const isActive = btn.dataset.active === "true";
          try {
            await api(`/workspaces/${id}`, {
              method: "PATCH",
              body: JSON.stringify({ is_active: !isActive }),
            });
            loadWorkspaces();
          } catch (err) {
            toast(err.message, "error");
          }
        }
      });
    });
  }

  // ── Create / Edit modal ────────────────────────────────────────────────
  function openCreateModal() {
    editIdInput.value = "";
    nameInput.value = "";
    typeSelect.value = "general";
    descInput.value = "";
    modalTitle.textContent = "New Workspace";
    modalSave.textContent = "Create";
    modalOverlay.style.display = "flex";
    setTimeout(() => nameInput.focus(), 50);
  }

  function openEditModal(ws) {
    editIdInput.value = ws.id;
    nameInput.value = ws.name;
    typeSelect.value = ws.workspace_type;
    descInput.value = ws.description || "";
    modalTitle.textContent = "Edit Workspace";
    modalSave.textContent = "Save";
    modalOverlay.style.display = "flex";
    setTimeout(() => nameInput.focus(), 50);
  }

  function closeModal() {
    modalOverlay.style.display = "none";
  }

  if (createBtn) createBtn.addEventListener("click", openCreateModal);
  if (modalClose) modalClose.addEventListener("click", closeModal);
  if (modalCancel) modalCancel.addEventListener("click", closeModal);
  if (modalOverlay) modalOverlay.addEventListener("click", (e) => { if (e.target === modalOverlay) closeModal(); });

  if (modalSave) {
    modalSave.addEventListener("click", async () => {
      const name = nameInput.value.trim();
      if (!name) { nameInput.focus(); return; }
      const id = editIdInput.value;
      modalSave.disabled = true;
      modalSave.textContent = id ? "Saving..." : "Creating...";

      try {
        if (id) {
          await api(`/workspaces/${id}`, {
            method: "PATCH",
            body: JSON.stringify({
              name,
              workspace_type: typeSelect.value,
              description: descInput.value.trim() || null,
            }),
          });
          toast("Workspace updated", "success");
        } else {
          const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
          await api("/workspaces", {
            method: "POST",
            body: JSON.stringify({
              name,
              slug,
              workspace_type: typeSelect.value,
              description: descInput.value.trim() || null,
            }),
          });
          toast("Workspace created", "success");
        }
        closeModal();
        loadWorkspaces();
      } catch (err) {
        toast(err.message, "error");
      } finally {
        modalSave.disabled = false;
        modalSave.textContent = editIdInput.value ? "Save" : "Create";
      }
    });
  }

  // ── Members drawer ─────────────────────────────────────────────────────
  async function openMembers(wsId, wsName) {
    currentMembersWsId = wsId;
    membersTitle.textContent = `Members — ${wsName}`;
    membersOverlay.style.display = "flex";
    membersList.innerHTML = '<div class="ws-loading">Loading...</div>';
    try {
      const members = await api(`/workspaces/${wsId}/members`);
      renderMembers(members);
    } catch (err) {
      membersList.innerHTML = `<div class="ws-members-empty">Failed to load members</div>`;
    }
  }

  function renderMembers(members) {
    if (!members.length) {
      membersList.innerHTML = '<div class="ws-members-empty">No members yet</div>';
      return;
    }
    membersList.innerHTML = members.map((m) => `
      <div class="ws-member-row">
        <div class="ws-member-avatar">U${m.user_id}</div>
        <div class="ws-member-info">
          <div class="ws-member-name">User #${m.user_id}</div>
          <div class="ws-member-detail">${m.role_override ? `Role: ${_esc(m.role_override)}` : "No role override"}</div>
        </div>
        <button class="ws-member-remove" data-user-id="${m.user_id}" type="button" aria-label="Remove member">
          <i data-lucide="x"></i>
        </button>
      </div>
    `).join("");
    if (window.lucide) lucide.createIcons({ nodes: membersList.querySelectorAll("i[data-lucide]") });

    membersList.querySelectorAll(".ws-member-remove").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const uid = btn.dataset.userId;
        try {
          await api(`/workspaces/${currentMembersWsId}/members/${uid}`, { method: "DELETE" });
          openMembers(currentMembersWsId, membersTitle.textContent.replace("Members — ", ""));
        } catch (err) {
          toast(err.message, "error");
        }
      });
    });
  }

  function closeMembers() { membersOverlay.style.display = "none"; }
  if (membersClose) membersClose.addEventListener("click", closeMembers);
  if (membersOverlay) membersOverlay.addEventListener("click", (e) => { if (e.target === membersOverlay) closeMembers(); });

  if (memberAddBtn) {
    memberAddBtn.addEventListener("click", async () => {
      const uid = parseInt(memberUserIdInput.value, 10);
      if (!uid) { memberUserIdInput.focus(); return; }
      try {
        await api(`/workspaces/${currentMembersWsId}/members`, {
          method: "POST",
          body: JSON.stringify({
            user_id: uid,
            role_override: memberRoleSelect.value || null,
          }),
        });
        memberUserIdInput.value = "";
        openMembers(currentMembersWsId, membersTitle.textContent.replace("Members — ", ""));
        toast("Member added", "success");
      } catch (err) {
        toast(err.message, "error");
      }
    });
  }

  // ── Helpers ────────────────────────────────────────────────────────────
  function _esc(s) {
    const d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  function toast(msg, type) {
    if (window.PCUI && window.PCUI.toast) window.PCUI.toast(msg, type);
  }

  // ── Init ───────────────────────────────────────────────────────────────
  loadWorkspaces();
})();
