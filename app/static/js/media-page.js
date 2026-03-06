/* Media Library — Nidin BOS */
(async function () {
  "use strict";

  window.__bootPromise = fetch("/web/api-token", { credentials: "same-origin" })
    .then(function(r) { return r.json(); })
    .then(function(d) { return d.token; });

  const token = await window.__bootPromise;
  const H = { Authorization: "Bearer " + token };
  const HJ = { Authorization: "Bearer " + token, "Content-Type": "application/json" };
  var userRole = "";
  var canManageMedia = false;

  async function loadRoleCaps() {
    try {
      var r = await fetch("/web/session");
      if (!r.ok) return;
      var d = await r.json();
      userRole = String(d && d.user && d.user.role ? d.user.role : "").toUpperCase();
      canManageMedia = userRole === "CEO" || userRole === "ADMIN";
    } catch (_e) {
      userRole = "";
      canManageMedia = false;
    }
  }

  async function api(p, o) {
    const r = await fetch("/api/v1" + p, { headers: HJ, ...o });
    if (!r.ok) {
      const err = await r.json().catch(function() { return { detail: r.statusText }; });
      throw new Error(err.detail || r.statusText);
    }
    return r.json();
  }

  function toast(msg, type) {
    if (window.PCUI && window.PCUI.toast) { window.PCUI.toast(msg, type); return; }
    var el = document.createElement("div");
    el.textContent = msg;
    Object.assign(el.style, {
      position: "fixed", bottom: "1rem", right: "1rem", padding: ".6rem 1.2rem",
      borderRadius: ".35rem", fontSize: ".8rem", zIndex: "9999", color: "#fff",
      background: type === "error" ? "#ef4444" : type === "success" ? "#22c55e" : "#3b82f6",
    });
    document.body.appendChild(el);
    setTimeout(function() { el.remove(); }, 4000);
  }

  function esc(s) { var d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

  function fileIcon(mime) {
    if (mime.startsWith("image/")) return "image";
    if (mime.startsWith("video/")) return "video";
    if (mime.startsWith("audio/")) return "music";
    if (mime.includes("pdf")) return "file-text";
    if (mime.includes("spreadsheet") || mime.includes("excel")) return "table";
    if (mime.includes("presentation") || mime.includes("powerpoint")) return "presentation";
    return "file";
  }

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1048576).toFixed(1) + " MB";
  }

  /* ── Load Stats ──────────────────────────────────────────────────── */
  async function loadStats() {
    try {
      var d = await api("/media/stats");
      document.getElementById("k-files").textContent = d.total_files;
      document.getElementById("k-storage").textContent = d.total_mb + " MB";
      document.getElementById("k-processed").textContent = d.processed_count;
      document.getElementById("k-unprocessed").textContent = d.unprocessed_count;
    } catch (_e) { /* stats may fail if no data */ }
  }

  /* ── Load Media Grid ─────────────────────────────────────────────── */
  async function loadMedia(searchQuery) {
    var grid = document.getElementById("media-grid");
    grid.innerHTML = '<div class="empty" style="opacity:.5">Loading...</div>';

    try {
      var url;
      if (searchQuery) {
        url = "/media/search?q=" + encodeURIComponent(searchQuery);
      } else {
        var mimeFilter = document.getElementById("filter-type").value;
        url = "/media?limit=100";
        if (mimeFilter) url += "&mime_prefix=" + encodeURIComponent(mimeFilter);
      }
      var data = await api(url);

      if (!data || data.length === 0) {
        grid.innerHTML = '<div class="empty">No media files found</div>';
        return;
      }

      grid.innerHTML = data.map(function(m) {
        var isImage = m.mime_type && m.mime_type.startsWith("image/");
        var tags = (m.ai_tags && m.ai_tags.tags) || [];

        return '<div class="media-card" data-mid="' + m.id + '">' +
          '<div class="media-card-preview">' +
            (isImage
              ? '<img src="/api/v1/media/' + m.id + '/download" alt="' + esc(m.original_name) + '" loading="lazy" />'
              : '<div class="file-icon"><i data-lucide="' + fileIcon(m.mime_type) + '"></i></div>') +
          '</div>' +
          '<div class="media-card-body">' +
            '<div class="media-card-name">' + esc(m.original_name) + '</div>' +
            '<div class="media-card-meta">' + formatSize(m.file_size_bytes) +
              (m.is_processed ? ' | AI analyzed' : '') + '</div>' +
            (tags.length > 0
              ? '<div class="media-card-tags">' +
                tags.slice(0, 4).map(function(t) { return '<span class="media-tag">' + esc(t) + '</span>'; }).join("") +
                '</div>'
              : '') +
          '</div>' +
          '<div class="media-card-actions">' +
            (canManageMedia
              ? '<button class="btn-analyze" title="AI Analyze">Analyze</button>' +
                '<button class="btn-delete" title="Delete">Delete</button>'
              : '<span class="media-card-meta">View only</span>') +
          '</div>' +
        '</div>';
      }).join("");

      // Event handlers
      if (!canManageMedia) {
        if (typeof lucide !== "undefined") lucide.createIcons();
        return;
      }
      grid.querySelectorAll(".btn-analyze").forEach(function(btn) {
        btn.addEventListener("click", async function(e) {
          e.stopPropagation();
          var card = btn.closest("[data-mid]");
          var mid = card.dataset.mid;
          btn.disabled = true; btn.textContent = "...";
          try {
            await api("/media/" + mid + "/analyze", { method: "POST" });
            toast("AI analysis complete", "success");
            loadMedia();
            loadStats();
          } catch (err) { toast("Analysis failed: " + err.message, "error"); }
          finally { btn.disabled = false; btn.textContent = "Analyze"; }
        });
      });

      grid.querySelectorAll(".btn-delete").forEach(function(btn) {
        btn.addEventListener("click", async function(e) {
          e.stopPropagation();
          var card = btn.closest("[data-mid]");
          var mid = card.dataset.mid;
          if (!confirm("Delete this file?")) return;
          try {
            await api("/media/" + mid, { method: "DELETE" });
            toast("File deleted", "success");
            loadMedia();
            loadStats();
          } catch (err) { toast("Delete failed: " + err.message, "error"); }
        });
      });

      if (typeof lucide !== "undefined") lucide.createIcons();
    } catch (e) { grid.innerHTML = '<div class="empty">Failed to load: ' + esc(e.message) + '</div>'; }
  }

  /* ── Search ──────────────────────────────────────────────────────── */
  document.getElementById("btn-search").addEventListener("click", function() {
    var q = document.getElementById("search-input").value.trim();
    loadMedia(q || null);
  });
  document.getElementById("search-input").addEventListener("keydown", function(e) {
    if (e.key === "Enter") document.getElementById("btn-search").click();
  });
  document.getElementById("filter-type").addEventListener("change", function() { loadMedia(); });

  /* ── Upload Modal ────────────────────────────────────────────────── */
  await loadRoleCaps();
  var modal = document.getElementById("modal-upload");
  var zone = document.getElementById("upload-zone");
  var fileInput = document.getElementById("file-input");
  var uploadBtn = document.getElementById("btn-upload");

  if (canManageMedia) {
    uploadBtn.addEventListener("click", function() { modal.style.display = "flex"; });
    document.getElementById("modal-upload-close").addEventListener("click", function() { modal.style.display = "none"; });
    modal.addEventListener("click", function(e) { if (e.target === modal) modal.style.display = "none"; });

    zone.addEventListener("click", function() { fileInput.click(); });
    zone.addEventListener("dragover", function(e) { e.preventDefault(); zone.classList.add("dragover"); });
    zone.addEventListener("dragleave", function() { zone.classList.remove("dragover"); });
    zone.addEventListener("drop", function(e) {
      e.preventDefault();
      zone.classList.remove("dragover");
      if (e.dataTransfer.files.length > 0) uploadFiles(e.dataTransfer.files);
    });
    fileInput.addEventListener("change", function() {
      if (fileInput.files.length > 0) uploadFiles(fileInput.files);
    });
  } else {
    uploadBtn.disabled = true;
    uploadBtn.title = "Upload is restricted to CEO/ADMIN";
    modal.style.display = "none";
  }

  async function uploadFiles(files) {
    var progress = document.getElementById("upload-progress");
    progress.innerHTML = "";

    for (var i = 0; i < Math.min(files.length, 20); i++) {
      var file = files[i];
      var item = document.createElement("div");
      item.className = "upload-item";
      item.innerHTML = '<span>' + esc(file.name) + '</span><span class="status">uploading...</span>';
      progress.appendChild(item);

      var fd = new FormData();
      fd.append("file", file);

      try {
        var resp = await fetch("/api/v1/media/upload", { method: "POST", headers: H, body: fd });
        if (!resp.ok) throw new Error((await resp.json().catch(function() { return {}; })).detail || "Upload failed");
        item.querySelector(".status").textContent = "done";
        item.querySelector(".status").className = "status done";
      } catch (err) {
        item.querySelector(".status").textContent = err.message;
        item.querySelector(".status").className = "status err";
      }
    }

    toast("Upload complete", "success");
    loadMedia();
    loadStats();
  }

  /* ── Init ────────────────────────────────────────────────────────── */
  loadStats();
  loadMedia();

  if (typeof lucide !== "undefined") lucide.createIcons();
})();
