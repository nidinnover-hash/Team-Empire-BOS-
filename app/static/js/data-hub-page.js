(async function () {
    var collectBtn = document.getElementById("collect-btn");
    var sourceEl = document.getElementById("source");
    var targetEl = document.getElementById("target");
    var keyEl = document.getElementById("key");
    var categoryEl = document.getElementById("category");
    var contentEl = document.getElementById("content");
    var statusEl = document.getElementById("collect-status");
    var logoutBtn = document.getElementById("logout-btn");
    var samplePriorityBtn = document.getElementById("sample-priority-btn");
    var sampleMemoryBtn = document.getElementById("sample-memory-btn");
    var storageRefreshBtn = document.getElementById("storage-refresh-btn");
    var storageStatusEl = document.getElementById("storage-status");
    var storageSummaryEl = document.getElementById("storage-summary");
    var storageTableListEl = document.getElementById("storage-table-list");
    var apiToken = null;
    var roleName = "";
    var canCollect = false;
    var canViewStorage = false;
    var canExport = false;

    function setStatus(text, cls) {
      statusEl.textContent = text || "";
      statusEl.className = "status" + (cls ? " " + cls : "");
    }
    function notifyError(msg) {
      if (window.showToast) window.showToast(msg, "error");
      else alert(msg);
    }

    function setStorageStatus(text, cls) {
      if (!storageStatusEl) return;
      storageStatusEl.textContent = text || "";
      storageStatusEl.className = "status" + (cls ? " " + cls : "");
    }

    async function loadRoleCapabilities() {
      try {
        if (window.PCUI && window.PCUI.loadRoleCapabilities) {
          var caps = await window.PCUI.loadRoleCapabilities();
          roleName = String(caps.roleName || "").toUpperCase();
          canCollect = !!caps.canCollectData;
          canViewStorage = !!caps.canViewStorage;
          canExport = !!caps.canExportData;
          return;
        }
        var r = await fetch("/web/session");
        if (!r.ok) return;
        var d = await r.json();
        roleName = String(d && d.user && d.user.role ? d.user.role : "").toUpperCase();
        canCollect = roleName === "CEO" || roleName === "ADMIN" || roleName === "MANAGER";
        canViewStorage = roleName === "CEO" || roleName === "ADMIN";
        canExport = roleName === "CEO";
      } catch (_e) {
        roleName = "";
        canCollect = false;
        canViewStorage = false;
        canExport = false;
      }
    }

    function renderStorage(payload) {
      if (!payload || !storageSummaryEl || !storageTableListEl) return;
      storageSummaryEl.textContent =
        "Total rows: " + String(payload.total_rows || 0) +
        " | Chat retention: " + String(payload.retention_days_chat || 0) + " days" +
        " | Generated: " + String(payload.generated_at || "");
      var tables = Array.isArray(payload.tables) ? payload.tables : [];
      if (!tables.length) {
        storageTableListEl.innerHTML = '<div class="item">No table metrics available.</div>';
        return;
      }
      storageTableListEl.innerHTML = tables.map(function (t) {
        var name = String(t.table || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
        return '<div class="item"><strong>' + name + '</strong><small>Rows: ' + String(t.row_count || 0) + "</small></div>";
      }).join("");
    }

    async function loadStorageSummary() {
      if (!apiToken) return;
      if (!canViewStorage) {
        setStorageStatus("Storage visibility is restricted to CEO/ADMIN.", "warn");
        if (storageSummaryEl) storageSummaryEl.textContent = "Limited access for your role.";
        if (storageTableListEl) storageTableListEl.innerHTML = '<div class="item">No table metrics available for this role.</div>';
        return;
      }
      setStorageStatus("Loading storage snapshot...");
      try {
        var r = await fetch("/api/v1/observability/storage", {
          headers: { "Authorization": "Bearer " + apiToken }
        });
        var body = await r.json().catch(function () { return {}; });
        if (!r.ok) throw new Error(body.detail || "Storage snapshot failed");
        renderStorage(body);
        setStorageStatus("Storage snapshot updated.", "ok");
      } catch (err) {
        setStorageStatus(String(err.message || err), "err");
      }
    }

    async function loadApiToken() {
      var r = await fetch("/web/api-token");
      if (!r.ok) throw new Error("Session expired");
      var d = await r.json();
      apiToken = d.token;
    }

    if (!collectBtn) return;
    collectBtn.addEventListener("click", async function () {
      if (!apiToken) {
        setStatus("No API token available. Refresh the page.", "err");
        return;
      }
      if (!canCollect) {
        setStatus("Data collection is restricted to CEO/ADMIN/MANAGER.", "warn");
        return;
      }
      var source = (sourceEl.value || "manual").trim();
      var target = targetEl.value;
      var key = (keyEl.value || "").trim();
      var category = (categoryEl.value || "").trim();
      var content = (contentEl.value || "").trim();
      if (!content) {
        setStatus("Add content before ingesting.", "warn");
        return;
      }
      var payload = {
        source: source || "manual",
        target: target,
        content: content,
        split_lines: true
      };
      if (target === "profile_memory") {
        payload.key = key;
        payload.category = category || "ingested";
      } else if (target === "daily_context") {
        payload.context_type = category || "priority";
      }

      collectBtn.disabled = true;
      setStatus("Ingesting data...");
      try {
        var r = await fetch("/api/v1/data/collect", {
          method: "POST",
          headers: {
            "Authorization": "Bearer " + apiToken,
            "Content-Type": "application/json"
          },
          body: JSON.stringify(payload)
        });
        var body = await r.json().catch(function () { return {}; });
        if (!r.ok) throw new Error(body.detail || "Data ingestion failed");
        setStatus(body.message || "Data ingested successfully.", "ok");
      } catch (err) {
        setStatus(String(err.message || err), "err");
      } finally {
        collectBtn.disabled = false;
      }
    });

    if (samplePriorityBtn) samplePriorityBtn.addEventListener("click", function () {
      targetEl.value = "daily_context";
      sourceEl.value = "meeting";
      keyEl.value = "";
      categoryEl.value = "priority";
      contentEl.value = "- Admissions follow-up backlog is rising\n- Prioritize visa compliance tickets\n- Review counselor performance by 5 PM";
      setStatus("Priority sample loaded.");
    });

    if (sampleMemoryBtn) sampleMemoryBtn.addEventListener("click", function () {
      targetEl.value = "profile_memory";
      sourceEl.value = "manual";
      keyEl.value = "preference.communication_style";
      categoryEl.value = "learned";
      contentEl.value = "Use concise, action-first responses with numeric priority order.";
      setStatus("Preference sample loaded.");
    });

    if (storageRefreshBtn) {
      storageRefreshBtn.addEventListener("click", async function () {
        storageRefreshBtn.disabled = true;
        try {
          await loadStorageSummary();
        } finally {
          storageRefreshBtn.disabled = false;
        }
      });
    }

    logoutBtn && logoutBtn.addEventListener("click", async function () {
      try {
        var csrf = window.PCUI.getCsrfToken();
        var r = await fetch("/web/logout", {
          method: "POST",
          headers: csrf ? { "X-CSRF-Token": csrf } : {}
        });
        if (!r.ok) throw new Error("Logout failed");
        window.location.href = "/web/login";
      } catch (e) {
        notifyError(String(e.message || e));
      }
    });

    try {
      await loadApiToken();
      await loadRoleCapabilities();
      setStatus("Data Hub ready.");
      await loadStorageSummary();
      if (!canCollect) {
        collectBtn.disabled = true;
        if (samplePriorityBtn) samplePriorityBtn.disabled = true;
        if (sampleMemoryBtn) sampleMemoryBtn.disabled = true;
        setStatus("Collection disabled for your role.", "warn");
      }
      if (storageRefreshBtn && !canViewStorage) {
        storageRefreshBtn.disabled = true;
      }

      // Export button
      var exportBtn = document.getElementById("export-btn");
      var exportStatus = document.getElementById("export-status");
      if (exportBtn) {
        if (!canExport) {
          exportBtn.disabled = true;
          if (exportStatus) {
            exportStatus.textContent = "Export is restricted to CEO role.";
            exportStatus.className = "status warn";
          }
        }
        exportBtn.addEventListener("click", async function () {
          if (!canExport) return;
          exportStatus.textContent = "Exporting...";
          exportStatus.className = "status";
          try {
            var res = await fetch("/api/v1/export", {
              headers: { Authorization: "Bearer " + apiToken },
            });
            if (!res.ok) throw new Error("Export failed: " + res.status);
            var blob = await res.blob();
            var url = URL.createObjectURL(blob);
            var a = document.createElement("a");
            a.href = url;
            a.download = "nidin-bos-export.json";
            a.click();
            URL.revokeObjectURL(url);
            exportStatus.textContent = "Export downloaded.";
            exportStatus.className = "status ok";
          } catch (err) {
            exportStatus.textContent = String(err.message || err);
            exportStatus.className = "status err";
          }
        });
      }
    } catch (err) {
      setStatus("Session expired. Sign in again.", "err");
      setStorageStatus("Session expired. Sign in again.", "err");
    }
  })();

window.showToast = function(msg, type) {
    var t = type || "info";
    var el = document.createElement("div");
    el.className = "toast " + t;
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    var text = document.createElement("span");
    text.textContent = String(msg);
    var btn = document.createElement("button");
    btn.setAttribute("aria-label", "Dismiss");
    btn.textContent = "\u00d7";
    btn.addEventListener("click", function() {
      el.classList.add("removing");
      setTimeout(function() { el.remove(); }, 250);
    });
    el.appendChild(text);
    el.appendChild(btn);
    var c = document.getElementById("toast-container");
    if (c) c.appendChild(el);
    setTimeout(function() {
      el.classList.add("removing");
      setTimeout(function() { el.remove(); }, 250);
    }, 4000);
  };
  if (typeof lucide !== "undefined") lucide.createIcons();
