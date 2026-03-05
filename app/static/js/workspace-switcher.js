/* ═══════════════════════════════════════════════════════════════════════════
   Workspace Switcher — dropdown + create modal
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  const STORAGE_KEY = "nidin_bos_workspace_id";
  const btn = document.getElementById("ws-switcher-btn");
  const dropdown = document.getElementById("ws-dropdown");
  const listEl = document.getElementById("ws-dropdown-list");
  const nameEl = document.getElementById("ws-current-name");
  const createBtn = document.getElementById("ws-create-btn");

  if (!btn || !dropdown) return;

  let workspaces = [];
  let activeWsId = parseInt(localStorage.getItem(STORAGE_KEY) || "0", 10) || null;

  // ── Icon map per workspace type ────────────────────────────────────────
  const TYPE_ICONS = {
    general: "brain",
    department: "building-2",
    project: "folder-kanban",
    client: "briefcase",
  };

  // ── Fetch workspaces ───────────────────────────────────────────────────
  async function loadWorkspaces() {
    try {
      const token = window.__bootPromise ? await window.__bootPromise : null;
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const resp = await fetch("/api/v1/workspaces?active_only=true", { headers });
      if (!resp.ok) return;
      workspaces = await resp.json();
      renderList();
    } catch (_) {
      // silently fail — workspaces are optional
    }
  }

  // ── Render dropdown list ───────────────────────────────────────────────
  function renderList() {
    if (workspaces.length === 0) {
      listEl.innerHTML = '<div class="ws-dropdown-empty">No workspaces yet</div>';
      nameEl.textContent = "Default";
      return;
    }

    // If stored ID doesn't match any workspace, reset to default
    const match = workspaces.find((w) => w.id === activeWsId);
    if (!match) {
      const defaultWs = workspaces.find((w) => w.is_default);
      activeWsId = defaultWs ? defaultWs.id : workspaces[0].id;
    }

    const active = workspaces.find((w) => w.id === activeWsId) || workspaces[0];
    nameEl.textContent = active.name;

    listEl.innerHTML = workspaces
      .map((ws) => {
        const isActive = ws.id === activeWsId;
        const icon = TYPE_ICONS[ws.workspace_type] || "brain";
        return `
        <button class="ws-dropdown-item${isActive ? " active" : ""}" data-ws-id="${ws.id}" type="button">
          <div class="ws-dropdown-item-icon"><i data-lucide="${icon}"></i></div>
          <div class="ws-dropdown-item-info">
            <div class="ws-dropdown-item-name">${_esc(ws.name)}</div>
            <div class="ws-dropdown-item-type">${_esc(ws.workspace_type)}${ws.is_default ? " (default)" : ""}</div>
          </div>
          <i data-lucide="check" class="ws-dropdown-item-check"></i>
        </button>`;
      })
      .join("");

    if (window.lucide) lucide.createIcons({ nodes: listEl.querySelectorAll("i[data-lucide]") });

    // Bind click
    listEl.querySelectorAll(".ws-dropdown-item").forEach((el) => {
      el.addEventListener("click", () => selectWorkspace(parseInt(el.dataset.wsId, 10)));
    });
  }

  // ── Select workspace ───────────────────────────────────────────────────
  function selectWorkspace(id) {
    activeWsId = id;
    localStorage.setItem(STORAGE_KEY, String(id));
    renderList();
    closeDropdown();
    // Dispatch event so other modules can react
    window.dispatchEvent(new CustomEvent("workspace:changed", { detail: { workspaceId: id } }));
  }

  // ── Toggle dropdown ────────────────────────────────────────────────────
  function openDropdown() {
    dropdown.style.display = "flex";
    btn.setAttribute("aria-expanded", "true");
    loadWorkspaces();
  }

  function closeDropdown() {
    dropdown.style.display = "none";
    btn.setAttribute("aria-expanded", "false");
  }

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (dropdown.style.display === "none") openDropdown();
    else closeDropdown();
  });

  document.addEventListener("click", (e) => {
    if (!dropdown.contains(e.target) && !btn.contains(e.target)) closeDropdown();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && dropdown.style.display !== "none") closeDropdown();
  });

  // ── Create workspace modal ─────────────────────────────────────────────
  if (createBtn) {
    createBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      closeDropdown();
      showCreateModal();
    });
  }

  function showCreateModal() {
    const overlay = document.createElement("div");
    overlay.className = "ws-modal-overlay";
    overlay.innerHTML = `
      <div class="ws-modal">
        <div class="ws-modal-header">
          <span>New Workspace</span>
          <button class="ws-modal-close" type="button" aria-label="Close"><i data-lucide="x"></i></button>
        </div>
        <div class="ws-modal-body">
          <div class="ws-modal-field">
            <label class="ws-modal-label" for="ws-new-name">Name</label>
            <input class="ws-modal-input" id="ws-new-name" type="text" placeholder="e.g. Sales Brain" maxlength="120" autofocus />
          </div>
          <div class="ws-modal-field">
            <label class="ws-modal-label" for="ws-new-type">Type</label>
            <select class="ws-modal-select" id="ws-new-type">
              <option value="general">General</option>
              <option value="department">Department</option>
              <option value="project">Project</option>
              <option value="client">Client</option>
            </select>
          </div>
          <div class="ws-modal-field">
            <label class="ws-modal-label" for="ws-new-desc">Description (optional)</label>
            <input class="ws-modal-input" id="ws-new-desc" type="text" placeholder="What is this workspace for?" maxlength="500" />
          </div>
        </div>
        <div class="ws-modal-footer">
          <button class="btn-secondary ws-modal-cancel" type="button">Cancel</button>
          <button class="btn-primary ws-modal-submit" type="button">Create</button>
        </div>
      </div>`;

    document.body.appendChild(overlay);
    if (window.lucide) lucide.createIcons({ nodes: overlay.querySelectorAll("i[data-lucide]") });

    const nameInput = overlay.querySelector("#ws-new-name");
    const typeSelect = overlay.querySelector("#ws-new-type");
    const descInput = overlay.querySelector("#ws-new-desc");
    const submitBtn = overlay.querySelector(".ws-modal-submit");

    function close() {
      overlay.remove();
    }

    overlay.querySelector(".ws-modal-close").addEventListener("click", close);
    overlay.querySelector(".ws-modal-cancel").addEventListener("click", close);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close();
    });

    submitBtn.addEventListener("click", async () => {
      const name = nameInput.value.trim();
      if (!name) {
        nameInput.focus();
        return;
      }
      const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      submitBtn.disabled = true;
      submitBtn.textContent = "Creating...";

      try {
        const token = window.__bootPromise ? await window.__bootPromise : null;
        const headers = { "Content-Type": "application/json" };
        if (token) headers.Authorization = `Bearer ${token}`;

        const resp = await fetch("/api/v1/workspaces", {
          method: "POST",
          headers,
          body: JSON.stringify({
            name,
            slug,
            workspace_type: typeSelect.value,
            description: descInput.value.trim() || null,
          }),
        });

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        const created = await resp.json();
        close();
        selectWorkspace(created.id);
        openDropdown();
        if (window.PCUI && window.PCUI.toast) {
          window.PCUI.toast(`Workspace "${created.name}" created`, "success");
        }
      } catch (err) {
        submitBtn.disabled = false;
        submitBtn.textContent = "Create";
        if (window.PCUI && window.PCUI.toast) {
          window.PCUI.toast(err.message || "Failed to create workspace", "error");
        }
      }
    });

    nameInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") submitBtn.click();
    });

    setTimeout(() => nameInput.focus(), 50);
  }

  // ── Helpers ────────────────────────────────────────────────────────────
  function _esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  // ── Public API ─────────────────────────────────────────────────────────
  window.WorkspaceSwitcher = {
    getActiveId: () => activeWsId,
    reload: loadWorkspaces,
  };

  // Initial load
  loadWorkspaces();
})();
