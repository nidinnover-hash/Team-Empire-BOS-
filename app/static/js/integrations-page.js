(async function () {
  var token = null;
  var integrations = [];
  var gmailHealth = null;
  var inflight = {};
  function byId(id) { return document.getElementById(id); }
  function bindClick(id, handler) {
    var el = byId(id);
    if (!el) return false;
    el.addEventListener("click", handler);
    return true;
  }
  async function apiJson(path, options) {
    if (window.PCAPI && window.PCAPI.safeFetchJson) {
      return window.PCAPI.safeFetchJson(path, {
        method: (options && options.method) || "GET",
        headers: (options && options.headers) || {},
        body: options && options.body,
        signal: options && options.signal,
        auth: true,
        token: token,
      });
    }
    var opts = options || {};
    var headers = opts.headers || {};
    if (!headers.Authorization && token) {
      headers.Authorization = "Bearer " + token;
    }
    opts.headers = headers;
    var r = await fetch(path, opts);
    var body = await r.json().catch(function(){ return {}; });
    if (!r.ok) {
      var err = new Error(body.detail || ("Request failed (" + r.status + ")"));
      err.status = r.status;
      throw err;
    }
    return body;
  }
  function startAbortableRequest(key) {
    if (inflight[key]) inflight[key].abort();
    var controller = new AbortController();
    inflight[key] = controller;
    return controller;
  }
  function finishAbortableRequest(key, controller) {
    if (inflight[key] === controller) delete inflight[key];
  }
  function renderHealthAlert() {
    var el = byId("gmail-health-alert");
    if (!el) return;
    var integration = integrations.find(function(i){ return i.type === "gmail"; });
    if (!integration) {
      el.style.display = "none";
      return;
    }
    if (!gmailHealth || gmailHealth.status === "ok") {
      el.className = "health-alert ok";
      el.textContent = "Gmail connection healthy.";
      el.style.display = "block";
      return;
    }
    var message = "Gmail requires reconnect. Click 'Connect Gmail OAuth' and complete consent again.";
    if (gmailHealth.code === "gmail_reconnect_required") {
      message = "Gmail token expired or invalid. Reconnect Gmail OAuth now.";
    }
    if (integration.status === "disconnected") {
      message = "Gmail is disconnected due to token issues. Reconnect Gmail OAuth to enable sync.";
    }
    el.className = "health-alert";
    el.textContent = message;
    el.style.display = "block";
  }

  async function fetchGmailHealth() {
    try {
      gmailHealth = await apiJson("/api/v1/email/health");
    } catch (_err) {
      gmailHealth = { status: "error", code: "health_unavailable" };
    }
    renderHealthAlert();
  }

  // ── config templates per type ──────────────────────────────────────────────
  var CONFIG_TEMPLATES = {
    whatsapp_business: '{\n  "access_token": "",\n  "refresh_token": "",\n  "phone_number_id": ""\n}',
    google_calendar:   '{\n  "access_token": "",\n  "refresh_token": "",\n  "token_uri": "https://oauth2.googleapis.com/token"\n}',
    gmail:             '{\n  "access_token": "",\n  "refresh_token": ""\n}',
    github:            '{\n  "access_token": "ghp_XXXX"\n}',
    clickup:           '{\n  "access_token": "pk_XXXX_YYYY"\n}',
    slack:             '{\n  "access_token": "xoxb-XXXX-YYYY"\n}',
  };

  function esc(s) {
    return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  }
  function fmtDate(v) {
    if (!v) return "never";
    var d = new Date(v);
    if (isNaN(d.getTime())) return "never";
    return d.toLocaleDateString("en-US",{month:"short",day:"numeric"}) + " " +
           d.toLocaleTimeString("en-US",{hour:"2-digit",minute:"2-digit"});
  }
  function setStatus(id, text, klass) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = text || "";
    el.className = "status" + (klass ? " " + klass : "");
  }
  function setQcStatus(id, text, klass) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = text || "";
    el.className = "qc-status" + (klass ? " " + klass : "");
  }
  function setModalStatus(text, klass) {
    var el = byId("modal-status");
    if (!el) return;
    el.textContent = text || "";
    el.className = "status" + (klass ? " " + klass : "");
  }
  function mapUiError(err) {
    if (window.PCUI && window.PCUI.mapApiError) return window.PCUI.mapApiError(err);
    return String((err && err.message) || err || "Request failed");
  }
  function fmtSyncAge(v) {
    if (!v) return "never";
    var d = new Date(v);
    if (isNaN(d.getTime())) return "unknown";
    var mins = Math.floor((Date.now() - d.getTime()) / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return mins + "m ago";
    var hours = Math.floor(mins / 60);
    if (hours < 24) return hours + "h ago";
    var days = Math.floor(hours / 24);
    return days + "d ago";
  }
  function getHealth(i) {
    if (i.status !== "connected") return { cls: "health-bad", label: "offline", rank: 3 };
    if (i.last_sync_status === "error") return { cls: "health-bad", label: "failing", rank: 3 };
    if (!i.last_sync_at) return { cls: "health-warn", label: "pending sync", rank: 2 };
    var ageMins = Math.floor((Date.now() - new Date(i.last_sync_at).getTime()) / 60000);
    if (isNaN(ageMins)) return { cls: "health-warn", label: "unknown", rank: 2 };
    if (ageMins >= 72 * 60) return { cls: "health-bad", label: "stale 72h+", rank: 3 };
    if (ageMins >= 24 * 60) return { cls: "health-warn", label: "stale 24h+", rank: 2 };
    return { cls: "health-ok", label: "healthy", rank: 1 };
  }

  async function bootToken() {
    if (window.PCAPI && window.PCAPI.getApiToken) {
      token = await window.PCAPI.getApiToken();
      if (!token) throw new Error("session_expired");
      return;
    }
    var r = await fetch("/web/api-token");
    if (!r.ok) throw new Error("session_expired");
    token = (await r.json()).token;
  }

  // ── Connected integrations table ──────────────────────────────────────────
  async function fetchIntegrations() {
    var controller = startAbortableRequest("fetchIntegrations");
    setStatus("integrations-status", "Refreshing...");
    var list = byId("integrations-list");
    if (!list) return;
    try {
      integrations = await apiJson("/api/v1/integrations", { signal: controller.signal });
      if (!integrations.length) {
        list.innerHTML = '<div class="empty">No integrations connected yet.</div>';
        setStatus("integrations-status", "No integrations found.", "warn");
        updateQcBadges([]);
        finishAbortableRequest("fetchIntegrations", controller);
        return;
      }
      var sorted = integrations.slice().sort(function(a, b) {
        var ah = getHealth(a);
        var bh = getHealth(b);
        if (ah.rank !== bh.rank) return bh.rank - ah.rank;
        return String(a.type || "").localeCompare(String(b.type || ""));
      });
      list.innerHTML = (
        '<table class="table"><thead><tr>' +
          '<th>Type</th><th>Status</th><th>Last Sync</th><th>Actions</th>' +
        '</tr></thead><tbody>' +
        sorted.map(function(i) {
          var isConnected = i.status === "connected";
          var hasSyncBtn = ["clickup","github","slack","google_calendar"].includes(i.type);
          var isOAuth = ["gmail","google_calendar"].includes(i.type);
          var bs = 'style="padding:0.28rem 0.5rem" type="button"';
          var health = getHealth(i);
          var actions = '';
          if (isConnected) {
            if (hasSyncBtn) {
              var syncCall = i.type === 'google_calendar' ? 'window.syncCalendar()' : 'window.syncIntegration(\'' + esc(i.type) + '\')';
              actions += '<button class="btn sync" ' + bs + ' onclick="' + syncCall + '">Sync</button>';
            }
            actions += '<button class="btn subtle" ' + bs + ' onclick="window.integrationTest(' + i.id + ')">Test</button>';
            actions += '<button class="btn danger" ' + bs + ' onclick="window.integrationDisconnect(' + i.id + ')">Disconnect</button>';
          } else {
            if (isOAuth) {
              var oauthClick = i.type === 'gmail' ? 'document.getElementById(\'gmail-auth-btn\').click()' : 'document.getElementById(\'gcal-auth-btn\').click()';
              actions += '<button class="btn sync" ' + bs + ' onclick="' + oauthClick + '">Reconnect</button>';
            } else {
              actions += '<button class="btn sync" ' + bs + ' onclick="window.reconnectToken(\'' + esc(i.type) + '\')">Connect</button>';
            }
            actions += '<button class="btn danger" ' + bs + ' onclick="window.integrationDisconnect(' + i.id + ')">Remove</button>';
          }
          return (
            '<tr>' +
              '<td><strong>' + esc(i.type) + '</strong></td>' +
              '<td><span class="pill ' + (isConnected?"connected":"disconnected") + '">' + esc(i.status) + '</span> <span class="health-badge ' + health.cls + '">' + health.label + '</span></td>' +
              '<td class="muted">' + esc(fmtDate(i.last_sync_at)) + ' <span style="font-size:.68rem;opacity:.85">(' + esc(fmtSyncAge(i.last_sync_at)) + ')</span>' + (i.last_sync_status === "error" ? ' <span style="color:var(--danger);font-size:.7rem">FAILED</span>' : '') + '</td>' +
              '<td style="display:flex;gap:0.35rem;flex-wrap:wrap;padding:0.35rem 0.4rem">' + actions + '</td>' +
            '</tr>'
          );
        }).join("") +
        '</tbody></table>'
      );
      setStatus("integrations-status", "Integration status is up to date.", "ok");
      updateQcBadges(integrations);
      renderHealthAlert();
    } catch (err) {
      if (err && err.name === "AbortError") return;
      list.innerHTML = '<div class="empty">Failed to load integrations.</div>';
      setStatus("integrations-status", mapUiError(err), "err");
    } finally {
      finishAbortableRequest("fetchIntegrations", controller);
    }
  }

  function updateQcBadges(list) {
    ["clickup","github","slack"].forEach(function(name) {
      var found = list.find(function(i){ return i.type === name && i.status === "connected"; });
      var badge = document.getElementById(name + "-badge");
      var syncBtn = document.getElementById(name + "-sync-btn");
      if (badge) {
        badge.textContent = found ? "connected" : "not connected";
        badge.className = found ? "qc-badge" : "qc-badge none";
      }
      if (syncBtn) syncBtn.style.display = found ? "inline-block" : "none";
    });
  }

  // ── Test / Disconnect ─────────────────────────────────────────────────────
  window.integrationTest = async function(id) {
    setStatus("integrations-status", "Running connection test...");
    try {
      var body = await apiJson("/api/v1/integrations/" + id + "/test", {
        method: "POST",
      });
      setStatus("integrations-status", body.message || "Connection test passed.", body.status==="ok"?"ok":"warn");
      await fetchIntegrations();
    } catch (err) {
      setStatus("integrations-status", mapUiError(err), "err");
    }
  };

  window.integrationDisconnect = async function(id) {
    var ok = window.PCUI && window.PCUI.confirmDanger
      ? await window.PCUI.confirmDanger("Disconnect this integration?", "Sync and send actions will stop until reconnect.")
      : window.confirm("Disconnect this integration?");
    if (!ok) return;
    setStatus("integrations-status", "Disconnecting...");
    try {
      await apiJson("/api/v1/integrations/" + id + "/disconnect", { method: "POST" });
      setStatus("integrations-status", "Integration disconnected.", "ok");
      await fetchIntegrations();
    } catch (err) {
      setStatus("integrations-status", mapUiError(err), "err");
    }
  };

  // ── Reconnect (token-based integrations) ─────────────────────────────────
  window.reconnectToken = function(type) {
    // Scroll to the matching quick-connect card and focus its input
    var inputId = type + "-token";
    var el = document.getElementById(inputId);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.focus();
      setQcStatus(type + "-status", "Paste your new token and click Connect.", "info");
    } else {
      // Fallback: open the generic Add New modal
      var addModal = document.getElementById("add-modal");
      if (addModal) addModal.classList.add("open");
    }
  };

  // ── Sync helpers ──────────────────────────────────────────────────────────
  var SYNC_ENDPOINTS = {
    clickup: "/api/v1/integrations/clickup/sync",
    github:  "/api/v1/integrations/github/sync",
    slack:   "/api/v1/integrations/slack/sync",
  };

  window.syncIntegration = async function(name, statusElemId) {
    var ep = SYNC_ENDPOINTS[name];
    if (!ep) return;
    var controller = startAbortableRequest("syncIntegration:" + name);
    var sid = statusElemId || "sync-status";
    setStatus(sid, "Syncing " + name + "...", "info");
    setQcStatus(name + "-status", "Syncing...", "info");
    try {
      var body = await apiJson(ep, { method: "POST", signal: controller.signal });
      var msg = name + " synced.";
      if (body.synced !== undefined)       msg = name + ": " + body.synced + " tasks synced.";
      if (body.channels_synced !== undefined) msg = "Slack: " + body.channels_synced + " channels, " + (body.messages_read||0) + " messages.";
      setStatus(sid, msg, "ok");
      setQcStatus(name + "-status", msg, "ok");
      await fetchIntegrations();
    } catch (err) {
      if (err && err.name === "AbortError") return;
      var e = mapUiError(err);
      setStatus(sid, e, "err");
      setQcStatus(name + "-status", e, "err");
    } finally {
      finishAbortableRequest("syncIntegration:" + name, controller);
    }
  };

  // ── Quick Connect: ClickUp ─────────────────────────────────────────────────
  bindClick("clickup-connect-btn", async function() {
    var btn = byId("clickup-connect-btn");
    var apiToken = document.getElementById("clickup-token").value.trim();
    if (!apiToken) { setQcStatus("clickup-status","Enter your ClickUp Personal API Token first.","err"); return; }
    if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, true, "Connecting...");
    setQcStatus("clickup-status","Connecting to ClickUp...","info");
    try {
      await apiJson("/api/v1/integrations/clickup/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_token: apiToken })
      });
      setQcStatus("clickup-status","Connected! Syncing tasks now...","ok");
      document.getElementById("clickup-token").value = "";
      await fetchIntegrations();
      await window.syncIntegration("clickup","sync-status");
    } catch (err) {
      setQcStatus("clickup-status", mapUiError(err), "err");
    } finally {
      if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, false);
    }
  });
  bindClick("clickup-sync-btn", function() {
    window.syncIntegration("clickup","sync-status");
  });

  // ── Quick Connect: GitHub ─────────────────────────────────────────────────
  bindClick("github-connect-btn", async function() {
    var btn = byId("github-connect-btn");
    var pat = document.getElementById("github-token").value.trim();
    if (!pat) { setQcStatus("github-status","Enter your GitHub Personal Access Token first.","err"); return; }
    if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, true, "Connecting...");
    setQcStatus("github-status","Connecting to GitHub...","info");
    try {
      await apiJson("/api/v1/integrations/github/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_token: pat })
      });
      setQcStatus("github-status","Connected! Syncing repos now...","ok");
      document.getElementById("github-token").value = "";
      await fetchIntegrations();
      await window.syncIntegration("github","sync-status");
    } catch (err) {
      setQcStatus("github-status", mapUiError(err), "err");
    } finally {
      if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, false);
    }
  });
  bindClick("github-sync-btn", function() {
    window.syncIntegration("github","sync-status");
  });

  // ── Quick Connect: Slack ──────────────────────────────────────────────────
  bindClick("slack-connect-btn", async function() {
    var btn = byId("slack-connect-btn");
    var botToken = document.getElementById("slack-token").value.trim();
    if (!botToken) { setQcStatus("slack-status","Enter your Slack Bot Token first.","err"); return; }
    if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, true, "Connecting...");
    setQcStatus("slack-status","Connecting to Slack...","info");
    try {
      await apiJson("/api/v1/integrations/slack/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bot_token: botToken })
      });
      setQcStatus("slack-status","Connected! Syncing channels now...","ok");
      document.getElementById("slack-token").value = "";
      await fetchIntegrations();
      await window.syncIntegration("slack","sync-status");
    } catch (err) {
      setQcStatus("slack-status", mapUiError(err), "err");
    } finally {
      if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, false);
    }
  });
  bindClick("slack-sync-btn", function() {
    window.syncIntegration("slack","sync-status");
  });

  // ── Gmail OAuth ────────────────────────────────────────────────────────────
  bindClick("gmail-auth-btn", async function() {
    var btn = byId("gmail-auth-btn");
    setStatus("connect-status","Requesting Gmail OAuth URL...","info");
    if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, true, "Preparing...");
    // Open immediately to avoid popup blockers, then update location once URL arrives.
    var popup = window.open("about:blank", "_blank", "noopener,noreferrer");
    try {
      var body = await apiJson("/api/v1/email/auth-url");
      if (!body.auth_url) throw new Error("Could not get OAuth URL");
      setStatus("connect-status","Opening Gmail OAuth in a new tab.","ok");
      if (popup) popup.location.href = body.auth_url;
      else window.location.href = body.auth_url;
    } catch (err) {
      if (popup) popup.close();
      setStatus("connect-status", mapUiError(err), "err");
    } finally {
      if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, false);
    }
  });

  // ── Google Calendar OAuth ─────────────────────────────────────────────────
  bindClick("gcal-auth-btn", async function() {
    var btn = byId("gcal-auth-btn");
    setStatus("connect-status","Requesting Google Calendar OAuth URL...","info");
    if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, true, "Preparing...");
    // Open immediately to avoid popup blockers, then update location once URL arrives.
    var popup = window.open("about:blank", "_blank", "noopener,noreferrer");
    try {
      var body = await apiJson("/api/v1/integrations/google-calendar/auth-url");
      if (!body.auth_url) throw new Error("Could not get OAuth URL");
      setStatus("connect-status","Opening Google Calendar OAuth in a new tab.","ok");
      if (popup) popup.location.href = body.auth_url;
      else window.location.href = body.auth_url;
    } catch (err) {
      if (popup) popup.close();
      setStatus("connect-status", mapUiError(err), "err");
    } finally {
      if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, false);
    }
  });

  // ── Calendar Sync ─────────────────────────────────────────────────────────
  window.syncCalendar = async function() {
    var controller = startAbortableRequest("syncCalendar");
    setStatus("sync-status","Syncing Google Calendar...","info");
    try {
      var body = await apiJson("/api/v1/integrations/google-calendar/sync", { method: "POST", signal: controller.signal });
      setStatus("sync-status","Calendar: " + (body.synced||0) + " events synced for " + (body.date||"today") + ".", "ok");
      await fetchIntegrations();
    } catch (err) {
      if (err && err.name === "AbortError") return;
      setStatus("sync-status", mapUiError(err), "err");
    } finally {
      finishAbortableRequest("syncCalendar", controller);
    }
  };

  // ── Add New modal ─────────────────────────────────────────────────────────
  var addModal = document.getElementById("add-modal");
  var modalType = document.getElementById("modal-type");
  var modalConfig = document.getElementById("modal-config");

  bindClick("add-integration-btn", function() {
    addModal.classList.add("open");
    setModalStatus("","");
  });
  bindClick("modal-cancel-btn", function() {
    addModal.classList.remove("open");
  });
  if (addModal) {
    addModal.addEventListener("click", function(e) {
      if (e.target === addModal) addModal.classList.remove("open");
    });
  }
  if (modalType && modalConfig) {
    modalType.addEventListener("change", function() {
      modalConfig.value = CONFIG_TEMPLATES[modalType.value] || '{\n  "access_token": ""\n}';
    });
  }
  bindClick("modal-save-btn", async function() {
    var btn = byId("modal-save-btn");
    var type = modalType.value;
    var rawConfig = modalConfig.value.trim();
    var config = {};
    setModalStatus("Saving...","info");
    try { config = rawConfig ? JSON.parse(rawConfig) : {}; }
    catch (err) { setModalStatus("Invalid JSON in config_json.", "err"); return; }
    try {
      if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, true, "Saving...");
      await apiJson("/api/v1/integrations/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: type, config_json: config })
      });
      setModalStatus("Saved: " + type, "ok");
      await fetchIntegrations();
      setTimeout(function(){ addModal.classList.remove("open"); }, 900);
    } catch (err) {
      setModalStatus(mapUiError(err), "err");
    } finally {
      if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, false);
    }
  });

  // ── AI Providers ───────────────────────────────────────────────────────────
  async function fetchAiStatus() {
    var controller = startAbortableRequest("fetchAiStatus");
    var list = document.getElementById("ai-list");
    setStatus("ai-status","Refreshing AI provider status...");
    try {
      var data = await apiJson("/api/v1/integrations/ai/status", { signal: controller.signal });
      list.innerHTML = data.map(function(p) {
        var roles = [];
        if (p.active) roles.push("default");
        if (p.email_active) roles.push("email");
        var roleTag = roles.length ? ' <span style="color:var(--brand);font-size:.65rem;font-weight:600">' + roles.join(" + ").toUpperCase() + '</span>' : '';
        return (
          '<div class="ai-card">' +
            '<div class="ai-head">' +
              '<div class="ai-name">' + esc(p.provider) + roleTag + '</div>' +
              '<span class="pill ' + (p.active||p.email_active?"connected":"disconnected") + '">' + (p.active?"active":"idle") + '</span>' +
            '</div>' +
            '<div class="small">Configured: ' + (p.configured?"Yes":"No") + '</div>' +
            '<div class="small">Model: ' + esc(p.model||"-") + '</div>' +
            '<div class="row" style="margin-top:0.5rem;margin-bottom:0">' +
              '<button class="btn subtle" type="button" onclick="window.testAI(\'' + esc(p.provider) + '\')">Test</button>' +
            '</div>' +
          '</div>'
        );
      }).join("");
      setStatus("ai-status","AI provider status loaded.","ok");
    } catch (err) {
      if (err && err.name === "AbortError") return;
      list.innerHTML = '<div class="empty">Failed to load AI providers.</div>';
      setStatus("ai-status", mapUiError(err), "err");
    } finally {
      finishAbortableRequest("fetchAiStatus", controller);
    }
  }

  window.testAI = async function(provider) {
    setStatus("ai-status","Testing " + provider + "...");
    try {
      var body = await apiJson("/api/v1/integrations/ai/test?provider=" + encodeURIComponent(provider), {
        method: "POST",
      });
      setStatus("ai-status", body.message || "Provider test complete.", body.status==="ok"?"ok":"warn");
    } catch (err) {
      setStatus("ai-status", mapUiError(err), "err");
    }
  };

  bindClick("refresh-integrations-btn", fetchIntegrations);
  bindClick("refresh-ai-btn", fetchAiStatus);

  var logoutBtn = byId("logout-btn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async function() {
      try {
        if (window.PCAPI && window.PCAPI.safeFetchJson) {
          await window.PCAPI.safeFetchJson("/web/logout", { method: "POST", csrf: true });
        } else {
          var csrfPair = document.cookie.split("; ").find(function(c){ return c.startsWith("pc_csrf="); });
          var csrf = csrfPair ? decodeURIComponent(csrfPair.split("=")[1]) : "";
          var r = await fetch("/web/logout", {
            method: "POST",
            headers: csrf ? { "X-CSRF-Token": csrf } : {}
          });
          if (!r.ok) throw new Error("Logout failed");
        }
        window.location.href = "/web/login";
      } catch (e) {
        setStatus("integrations-status", mapUiError(e), "err");
      }
    });
  }

  // ── Delegate sync button clicks via data-sync attributes ─────────────────
  document.addEventListener("click", function(e) {
    var btn = e.target.closest("[data-sync]");
    if (!btn) return;
    var name = btn.getAttribute("data-sync");
    if (name === "calendar") { window.syncCalendar(); }
    else { window.syncIntegration(name); }
  });

  // ── Boot ───────────────────────────────────────────────────────────────────
  try {
    await bootToken();
    await fetchIntegrations();
    await fetchGmailHealth();
    await fetchAiStatus();
    // Show success toast if redirected from Gmail OAuth callback
    var params = new URLSearchParams(window.location.search);
    if (params.get("gmail") === "connected") {
      setStatus("connect-status", "Gmail connected successfully. You can now sync emails.", "ok");
      history.replaceState(null, "", window.location.pathname);
    }
  } catch (err) {
    setStatus("integrations-status","Your web session expired. Sign in again.","err");
    setStatus("ai-status","Sign in again to load provider status.","warn");
    setStatus("connect-status","Sign in again before updating integrations.","warn");
  }
})();

window.showToast = function(msg, type) {
    var t = type || "info";
    var el = document.createElement("div");
    el.className = "toast " + t;
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.innerHTML = "<span>" + String(msg).replace(/</g,"&lt;") + "</span>" +
      '<button aria-label="Dismiss" onclick="this.parentNode.classList.add(\'removing\');setTimeout(function(){this.parentNode.remove()}.bind(this),250)">\u00d7</button>';
    var c = document.getElementById("toast-container");
    if (c) c.appendChild(el);
    setTimeout(function() {
      el.classList.add("removing");
      setTimeout(function() { el.remove(); }, 250);
    }, 4000);
  };
  if (typeof lucide !== "undefined") lucide.createIcons();
