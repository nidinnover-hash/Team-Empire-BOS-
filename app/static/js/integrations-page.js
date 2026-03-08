(async function () {
  var token = null;
  var integrations = [];
  var gmailHealth = null;
  var integrationHealth = null;
  var securityCenter = null;
  var securityCenterTrend = [];
  var securityTrendDays = 14;
  var autoRefreshTimer = null;
  var autoRefreshEnabled = false;
  var AUTO_REFRESH_MS = 60000;
  var AUTO_REFRESH_STORAGE_KEY = "pc.integrations.autoRefresh";
  var inflight = {};
  function byId(id) { return document.getElementById(id); }
  function mk(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
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
  function setLastUpdatedNow() {
    var el = byId("integrations-last-updated");
    if (!el) return;
    var now = new Date();
    el.textContent = "Last updated: " + now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
  function stopAutoRefresh() {
    if (autoRefreshTimer) {
      clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
    }
  }
  function syncAutoRefreshToggleUi() {
    var input = byId("auto-refresh-toggle");
    if (input) input.checked = autoRefreshEnabled;
  }
  function saveAutoRefreshPreference() {
    try {
      window.localStorage.setItem(AUTO_REFRESH_STORAGE_KEY, autoRefreshEnabled ? "1" : "0");
    } catch (_err) {}
  }
  function loadAutoRefreshPreference() {
    try {
      autoRefreshEnabled = window.localStorage.getItem(AUTO_REFRESH_STORAGE_KEY) === "1";
    } catch (_err) {
      autoRefreshEnabled = false;
    }
    syncAutoRefreshToggleUi();
  }

  async function fetchGmailHealth() {
    try {
      gmailHealth = await apiJson("/api/v1/email/health");
    } catch (_err) {
      gmailHealth = { status: "error", code: "health_unavailable" };
    }
    renderHealthAlert();
  }
  async function refreshIntegrationPanels() {
    await fetchIntegrations();
    await fetchIntegrationHealth();
    await fetchSecurityCenter();
    await fetchGmailHealth();
    setLastUpdatedNow();
  }
  function startAutoRefresh() {
    stopAutoRefresh();
    if (!autoRefreshEnabled) return;
    autoRefreshTimer = setInterval(function() {
      refreshIntegrationPanels().catch(function(){});
    }, AUTO_REFRESH_MS);
  }

  // ── config templates per type ──────────────────────────────────────────────
  var CONFIG_TEMPLATES = {
    whatsapp_business: '{\n  "access_token": "",\n  "refresh_token": "",\n  "phone_number_id": ""\n}',
    google_calendar:   '{\n  "access_token": "",\n  "refresh_token": "",\n  "token_uri": "https://oauth2.googleapis.com/token"\n}',
    gmail:             '{\n  "access_token": "",\n  "refresh_token": ""\n}',
    github:            '{\n  "access_token": "ghp_XXXX"\n}',
    clickup:           '{\n  "access_token": "pk_XXXX_YYYY"\n}',
    slack:             '{\n  "access_token": "xoxb-XXXX-YYYY"\n}',
    digitalocean:      '{\n  "api_token": "dop_v1_xxxxxxxx"\n}',
  };
  var MODAL_CONNECT_ENDPOINTS = {
    github: "/api/v1/integrations/github/connect",
    clickup: "/api/v1/integrations/clickup/connect",
    slack: "/api/v1/integrations/slack/connect",
    digitalocean: "/api/v1/integrations/digitalocean/connect",
    perplexity: "/api/v1/integrations/perplexity/connect",
    linkedin: "/api/v1/integrations/linkedin/connect",
    notion: "/api/v1/integrations/notion/connect",
    stripe: "/api/v1/integrations/stripe/connect",
    google_analytics: "/api/v1/integrations/google-analytics/connect",
    calendly: "/api/v1/integrations/calendly/connect",
    elevenlabs: "/api/v1/integrations/elevenlabs/connect",
    hubspot: "/api/v1/integrations/hubspot/connect"
  };

  function buildModalProviderPayload(type, config) {
    if (type === "github" || type === "clickup") return { api_token: config.api_token || config.access_token || "" };
    if (type === "slack") return { bot_token: config.bot_token || config.access_token || "" };
    if (type === "digitalocean") return { api_token: config.api_token || config.access_token || "" };
    if (type === "perplexity" || type === "elevenlabs") return { api_key: config.api_key || config.access_token || "" };
    if (type === "linkedin" || type === "hubspot") return { access_token: config.access_token || "" };
    if (type === "notion" || type === "calendly") return { api_token: config.api_token || config.access_token || "" };
    if (type === "stripe") return { secret_key: config.secret_key || config.api_key || "" };
    if (type === "google_analytics") return {
      access_token: config.access_token || "",
      property_id: config.property_id || ""
    };
    return { type: type, config_json: config };
  }

  var esc = window.PCUI.escapeHtml;
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
  var mapUiError = window.PCUI.mapApiError;
  function providerLabel(name) {
    var n = String(name || "").toLowerCase();
    if (n === "anthropic") return "Claude (Anthropic)";
    if (n === "openai") return "OpenAI";
    if (n === "groq") return "Groq";
    if (n === "gemini") return "Gemini";
    return name;
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
  function healthStateMeta(state) {
    if (state === "healthy") return { cls: "health-ok", label: "healthy", rank: 1 };
    if (state === "degraded") return { cls: "health-warn", label: "degraded", rank: 2 };
    if (state === "stale") return { cls: "health-warn", label: "stale", rank: 3 };
    return { cls: "health-bad", label: "down", rank: 4 };
  }
  function renderIntegrationHealthSummary() {
    var host = byId("integrations-health-summary");
    if (!host) return;
    if (!integrationHealth) {
      host.innerHTML = (
        '<div class="integration-health-summary__title">Integration Health Summary</div>' +
        '<div class="small">Health diagnostics are temporarily unavailable.</div>'
      );
      return;
    }
    var items = Array.isArray(integrationHealth.items) ? integrationHealth.items : [];
    if (!items.length) {
      host.innerHTML = (
        '<div class="integration-health-summary__title">Integration Health Summary</div>' +
        '<div class="small">No connected integrations yet. Connect one to enable diagnostics.</div>'
      );
      return;
    }
    var score = Number(integrationHealth.overall_health_score || 0);
    var failing = Number(integrationHealth.failing_count || 0);
    var stale = Number(integrationHealth.stale_count || 0);
    var unhealthy = items.filter(function(item) { return item.state !== "healthy"; });
    unhealthy.sort(function(a, b) {
      return healthStateMeta(b.state).rank - healthStateMeta(a.state).rank;
    });
    var topItems = unhealthy.slice(0, 3).map(function(item) {
      var meta = healthStateMeta(item.state);
      var ageLabel = item.age_hours == null ? "age unknown" : (item.age_hours + "h old");
      return (
        '<li><span class="health-badge ' + meta.cls + '">' + esc(meta.label) + '</span> ' +
        '<strong>' + esc(item.type) + '</strong> - ' + esc(ageLabel) + '</li>'
      );
    }).join("");
    var actionSet = {};
    unhealthy.forEach(function(item) {
      (item.suggested_actions || []).forEach(function(action) {
        if (action && !actionSet[action]) actionSet[action] = true;
      });
    });
    var actions = Object.keys(actionSet).slice(0, 3);
    var actionHtml = actions.length
      ? ('<ul class="integration-health-summary__actions">' + actions.map(function(action) {
          return '<li>' + esc(action) + '</li>';
        }).join("") + '</ul>')
      : '<div class="small">No action needed. All integrations are healthy.</div>';
    host.innerHTML = (
      '<div class="integration-health-summary__title">Integration Health Summary</div>' +
      '<div class="integration-health-summary__metrics">' +
        '<span class="metric-pill">Health score: <strong>' + esc(String(score)) + '/100</strong></span>' +
        '<span class="metric-pill">Failing: <strong>' + esc(String(failing)) + '</strong></span>' +
        '<span class="metric-pill">Stale: <strong>' + esc(String(stale)) + '</strong></span>' +
      '</div>' +
      (topItems ? ('<ul class="integration-health-summary__top">' + topItems + '</ul>') : "") +
      actionHtml
    );
  }
  function renderSecurityCenterSummary() {
    var host = byId("security-center-summary");
    if (!host) return;
    if (!securityCenter) {
      host.innerHTML = (
        '<div class="integration-health-summary__title">Security Center</div>' +
        '<div class="small">Token security diagnostics are temporarily unavailable.</div>'
      );
      return;
    }
    var summary = securityCenter.summary || {};
    var level = String(securityCenter.risk_level || "low").toLowerCase();
    if (["low", "medium", "high"].indexOf(level) === -1) level = "low";
    var actions = Array.isArray(securityCenter.next_actions) ? securityCenter.next_actions : [];
    var riskBase = level === "high" ? 70 : (level === "medium" ? 40 : 15);
    var riskScore = Math.min(
      100,
      riskBase +
      Number(summary.rotation_overdue || 0) * 6 +
      Number(summary.rotation_due_soon || 0) * 2 +
      Number(summary.manual_required || 0) * 8
    );
    var trend = Array.isArray(securityCenterTrend) ? securityCenterTrend : [];
    host.innerHTML = (
      '<div class="integration-health-summary__title">Security Center</div>' +
      '<div style="margin-bottom:.35rem">' +
        '<span class="risk-pill ' + level + '">' + esc(level) + ' risk</span>' +
        '<span class="small">Overdue: ' + esc(String(summary.rotation_overdue || 0)) + ' | ' +
        'Due soon: ' + esc(String(summary.rotation_due_soon || 0)) + ' | ' +
        'Manual OAuth fix: ' + esc(String(summary.manual_required || 0)) + '</span>' +
      '</div>' +
      renderTrendCard(trend, {
        title: "Risk Trend (Org Shared)",
        valueLabel: "Score " + String(Math.round(riskScore)),
        lineClass: level === "high" ? "danger" : (level === "medium" ? "warn" : "ok"),
        panel: "security",
        days: securityTrendDays
      }) +
      (actions.length
        ? ('<ul class="integration-health-summary__actions">' + actions.slice(0, 3).map(function(a){ return '<li>' + esc(a) + '</li>'; }).join("") + '</ul>')
        : '<div class="small">No urgent token actions required.</div>')
    );
  }
  function normalizeTrendPoints(raw) {
    if (!Array.isArray(raw)) return [];
    return raw.map(function(point) {
      if (!point || typeof point !== "object") return null;
      var v = Number(point.risk_score);
      if (!isFinite(v)) return null;
      return { value: v, timestamp: point.timestamp || null };
    }).filter(function(v) { return v !== null; });
  }
  function renderTrendCard(points, opts) {
    var title = (opts && opts.title) || "Trend";
    var valueLabel = (opts && opts.valueLabel) || "";
    var lineClass = (opts && opts.lineClass) || "";
    var panel = (opts && opts.panel) || "";
    var days = Number((opts && opts.days) || 14);
    var controls = (
      '<span class="trend-controls">' +
      [7, 14, 30].map(function(d) {
        return '<button type="button" class="trend-btn ' + (d === days ? "active" : "") + '" data-trend-panel="' + esc(panel) + '" data-trend-days="' + d + '">' + d + "d</button>";
      }).join("") +
      '</span>'
    );
    if (!Array.isArray(points) || points.length < 2) {
      return (
        '<div class="mini-trend">' +
          '<div class="mini-trend__head"><span>' + esc(title) + '</span><span>' + controls + "</span></div>" +
          '<div class="mini-trend__subhead"><span>' + esc(valueLabel) + '</span><span>No snapshots in selected window.</span></div>' +
          '<div class="mini-trend__empty">Wait for scheduler snapshots or refresh later.</div>' +
        '</div>'
      );
    }
    var values = points.map(function(p) { return Number(p.value || 0); });
    var min = Math.min.apply(null, values);
    var max = Math.max.apply(null, values);
    var range = (max - min) || 1;
    var w = 260;
    var h = 56;
    var step = values.length > 1 ? (w / (values.length - 1)) : w;
    var coords = values.map(function(v, idx) {
      var x = Math.round(idx * step * 100) / 100;
      var y = Math.round((h - ((v - min) / range) * h) * 100) / 100;
      return x + "," + y;
    }).join(" ");
    var lastPoint = points[points.length - 1] || {};
    var lastTs = lastPoint.timestamp ? new Date(lastPoint.timestamp) : null;
    var lastLabel = lastTs && !isNaN(lastTs.getTime())
      ? ("Updated " + lastTs.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }))
      : "Updated --";
    return (
      '<div class="mini-trend">' +
        '<div class="mini-trend__head"><span>' + esc(title) + '</span><span>' + controls + "</span></div>" +
        '<div class="mini-trend__subhead"><span>' + esc(valueLabel) + '</span><span>' + esc(lastLabel) + '</span></div>' +
        '<svg class="mini-trend__svg" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none" role="img" aria-label="' + esc(title) + '">' +
          '<polyline class="mini-trend__line ' + esc(lineClass) + '" points="' + coords + '"></polyline>' +
        '</svg>' +
      '</div>'
    );
  }
  async function fetchSecurityCenter() {
    try {
      securityCenter = await apiJson("/api/v1/integrations/security-center");
      var trendBody = await apiJson("/api/v1/integrations/security-center/trend?limit=" + encodeURIComponent(String(securityTrendDays)));
      securityCenterTrend = normalizeTrendPoints(trendBody && trendBody.points);
    } catch (_err) {
      securityCenter = null;
      securityCenterTrend = [];
    }
    renderSecurityCenterSummary();
  }
  async function fetchIntegrationHealth() {
    try {
      integrationHealth = await apiJson("/api/v1/control/integrations/health");
    } catch (_err) {
      integrationHealth = null;
    }
    renderIntegrationHealthSummary();
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
      list.innerHTML = "";
      var table = mk("table", "table");
      var thead = document.createElement("thead");
      var headTr = document.createElement("tr");
      ["Type", "Status", "Last Sync", "Actions"].forEach(function(label) {
        headTr.appendChild(mk("th", "", label));
      });
      thead.appendChild(headTr);
      table.appendChild(thead);
      var tbody = document.createElement("tbody");

      sorted.forEach(function(i) {
        var isConnected = i.status === "connected";
        var hasSyncBtn = ["clickup", "github", "slack", "digitalocean", "google_calendar"].includes(i.type);
        var isOAuth = ["gmail", "google_calendar"].includes(i.type);
        var health = getHealth(i);
        var tr = document.createElement("tr");

        var typeTd = document.createElement("td");
        typeTd.appendChild(mk("strong", "", i.type || ""));
        tr.appendChild(typeTd);

        var statusTd = document.createElement("td");
        var pill = mk("span", "pill " + (isConnected ? "connected" : "disconnected"), i.status || "");
        var healthBadge = mk("span", "health-badge " + health.cls, health.label);
        statusTd.appendChild(pill);
        statusTd.appendChild(document.createTextNode(" "));
        statusTd.appendChild(healthBadge);
        tr.appendChild(statusTd);

        var syncTd = mk("td", "muted");
        syncTd.appendChild(document.createTextNode(fmtDate(i.last_sync_at)));
        var age = mk("span", "", "(" + fmtSyncAge(i.last_sync_at) + ")");
        age.style.fontSize = ".68rem";
        age.style.opacity = ".85";
        syncTd.appendChild(document.createTextNode(" "));
        syncTd.appendChild(age);
        if (i.last_sync_status === "error") {
          var failed = mk("span", "", "FAILED");
          failed.style.color = "var(--danger)";
          failed.style.fontSize = ".7rem";
          syncTd.appendChild(document.createTextNode(" "));
          syncTd.appendChild(failed);
        }
        tr.appendChild(syncTd);

        var actionTd = document.createElement("td");
        actionTd.style.display = "flex";
        actionTd.style.gap = "0.35rem";
        actionTd.style.flexWrap = "wrap";
        actionTd.style.padding = "0.35rem 0.4rem";

        function addAction(label, className, attrs) {
          var btn = mk("button", "btn " + className, label);
          btn.type = "button";
          Object.keys(attrs).forEach(function(key) {
            btn.setAttribute(key, attrs[key]);
          });
          actionTd.appendChild(btn);
        }

        if (isConnected) {
          if (hasSyncBtn) {
            var syncTarget = i.type === "google_calendar" ? "calendar" : String(i.type || "");
            addAction("Sync", "sync", { "data-sync": syncTarget });
          }
          addAction("Test", "subtle", { "data-int-action": "test", "data-int-id": String(Number(i.id)) });
          addAction("Disconnect", "danger", { "data-int-action": "disconnect", "data-int-id": String(Number(i.id)) });
        } else {
          if (isOAuth) {
            addAction("Reconnect", "sync", { "data-int-action": "oauth-reconnect", "data-oauth-type": String(i.type || "") });
          } else {
            addAction("Connect", "sync", { "data-int-action": "token-connect", "data-int-type": String(i.type || "") });
          }
          addAction("Remove", "danger", { "data-int-action": "disconnect", "data-int-id": String(Number(i.id)) });
        }

        tr.appendChild(actionTd);
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      list.appendChild(table);
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
    var syncBtnOverrides = { google_analytics: "ga-sync-btn" };
    ["clickup","github","slack","digitalocean","linkedin","perplexity","google_analytics"].forEach(function(name) {
      var found = list.find(function(i){ return i.type === name && i.status === "connected"; });
      var badge = document.getElementById(name + "-badge");
      var syncBtn = document.getElementById(syncBtnOverrides[name] || (name + "-sync-btn"));
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
    digitalocean: "/api/v1/integrations/digitalocean/sync",
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
      var endpoint = MODAL_CONNECT_ENDPOINTS[type] || "/api/v1/integrations/connect";
      await apiJson(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildModalProviderPayload(type, config))
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
    if (!list) return;
    setStatus("ai-status","Refreshing AI provider status...");
    try {
      var data = await apiJson("/api/v1/integrations/ai/status", { signal: controller.signal });
      list.innerHTML = "";
      data.forEach(function(p) {
        var roles = [];
        if (p.active) roles.push("default");
        if (p.email_active) roles.push("email");
        var card = mk("div", "ai-card");
        var head = mk("div", "ai-head");
        var name = mk("div", "ai-name", providerLabel(p.provider));
        if (roles.length) {
          name.appendChild(document.createTextNode(" "));
          var roleTag = mk("span", "", roles.join(" + ").toUpperCase());
          roleTag.style.color = "var(--brand)";
          roleTag.style.fontSize = ".65rem";
          roleTag.style.fontWeight = "600";
          name.appendChild(roleTag);
        }
        var pill = mk("span", "pill " + (p.active || p.email_active ? "connected" : "disconnected"), p.active ? "active" : "idle");
        head.appendChild(name);
        head.appendChild(pill);
        card.appendChild(head);
        card.appendChild(mk("div", "small", "Configured: " + (p.configured ? "Yes" : "No")));
        card.appendChild(mk("div", "small", "Model: " + (p.model || "-")));

        if (!p.configured) {
          var connectRow = mk("div", "qc-token-row");
          connectRow.style.marginTop = "0.4rem";
          var input = mk("input", "input");
          input.type = "password";
          input.id = "ai-key-" + String(p.provider || "");
          input.placeholder = "API key";
          input.autocomplete = "off";
          input.style.fontSize = ".78rem";
          connectRow.appendChild(input);
          card.appendChild(connectRow);
        }

        var statusEl = mk("div", "qc-status");
        statusEl.id = "ai-status-" + String(p.provider || "");
        card.appendChild(statusEl);

        var row = mk("div", "row");
        row.style.marginTop = "0.5rem";
        row.style.marginBottom = "0";
        row.style.gap = "0.35rem";
        var connectBtn = mk("button", "btn " + (p.configured ? "subtle" : "success"), p.configured ? "Clear Key" : "Connect");
        connectBtn.type = "button";
        connectBtn.setAttribute("data-ai-action", p.configured ? "disconnect" : "connect");
        connectBtn.setAttribute("data-ai-provider", String(p.provider || ""));
        row.appendChild(connectBtn);
        var testBtn = mk("button", "btn subtle", "Test");
        testBtn.type = "button";
        testBtn.setAttribute("data-ai-action", "test");
        testBtn.setAttribute("data-ai-provider", String(p.provider || ""));
        row.appendChild(testBtn);
        card.appendChild(row);
        list.appendChild(card);
      });
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

  window.connectAI = async function(provider) {
    var input = byId("ai-key-" + provider);
    var statusEl = "ai-status-" + provider;
    if (!input || !input.value.trim()) {
      setQcStatus(statusEl, "Enter an API key first.", "err");
      return;
    }
    setQcStatus(statusEl, "Connecting " + providerLabel(provider) + "...", "info");
    try {
      var body = await apiJson("/api/v1/integrations/ai/" + encodeURIComponent(provider) + "/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: input.value.trim() }),
      });
      setQcStatus(statusEl, body.message || "Connected!", "ok");
      input.value = "";
      await fetchAiStatus();
    } catch (err) {
      setQcStatus(statusEl, mapUiError(err), "err");
    }
  };

  window.disconnectAI = async function(provider) {
    var ok = window.PCUI && window.PCUI.confirmDanger
      ? await window.PCUI.confirmDanger("Clear " + providerLabel(provider) + " key?", "The cached API key will be removed.")
      : window.confirm("Clear " + providerLabel(provider) + " API key?");
    if (!ok) return;
    setStatus("ai-status", "Clearing " + provider + " key...");
    try {
      await apiJson("/api/v1/integrations/ai/" + encodeURIComponent(provider) + "/disconnect", {
        method: "POST",
      });
      setStatus("ai-status", providerLabel(provider) + " key cleared.", "ok");
      await fetchAiStatus();
    } catch (err) {
      setStatus("ai-status", mapUiError(err), "err");
    }
  };

  bindClick("digitalocean-connect-btn", async function() {
    var btn = byId("digitalocean-connect-btn");
    var apiToken = document.getElementById("digitalocean-token").value.trim();
    if (!apiToken) { setQcStatus("digitalocean-status","Enter your DigitalOcean token first.","err"); return; }
    if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, true, "Connecting...");
    setQcStatus("digitalocean-status","Connecting to DigitalOcean...","info");
    try {
      await apiJson("/api/v1/integrations/digitalocean/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_token: apiToken })
      });
      setQcStatus("digitalocean-status","Connected! Syncing infrastructure now...","ok");
      document.getElementById("digitalocean-token").value = "";
      await fetchIntegrations();
      await window.syncIntegration("digitalocean","sync-status");
    } catch (err) {
      setQcStatus("digitalocean-status", mapUiError(err), "err");
    } finally {
      if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, false);
    }
  });
  bindClick("digitalocean-sync-btn", function() {
    window.syncIntegration("digitalocean","sync-status");
  });

  // ── Quick Connect: LinkedIn ─────────────────────────────────────────────────
  bindClick("linkedin-connect-btn", async function() {
    var btn = byId("linkedin-connect-btn");
    var accessToken = document.getElementById("linkedin-token").value.trim();
    if (!accessToken) { setQcStatus("linkedin-status","Enter your LinkedIn access token first.","err"); return; }
    if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, true, "Connecting...");
    setQcStatus("linkedin-status","Connecting to LinkedIn...","info");
    try {
      await apiJson("/api/v1/integrations/linkedin/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ access_token: accessToken })
      });
      setQcStatus("linkedin-status","Connected!","ok");
      document.getElementById("linkedin-token").value = "";
      await fetchIntegrations();
    } catch (err) {
      setQcStatus("linkedin-status", mapUiError(err), "err");
    } finally {
      if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, false);
    }
  });

  // ── Quick Connect: Perplexity ───────────────────────────────────────────────
  bindClick("perplexity-connect-btn", async function() {
    var btn = byId("perplexity-connect-btn");
    var apiKey = document.getElementById("perplexity-token").value.trim();
    if (!apiKey) { setQcStatus("perplexity-status","Enter your Perplexity API key first.","err"); return; }
    if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, true, "Connecting...");
    setQcStatus("perplexity-status","Connecting to Perplexity...","info");
    try {
      await apiJson("/api/v1/integrations/perplexity/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey })
      });
      setQcStatus("perplexity-status","Connected!","ok");
      document.getElementById("perplexity-token").value = "";
      await fetchIntegrations();
    } catch (err) {
      setQcStatus("perplexity-status", mapUiError(err), "err");
    } finally {
      if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, false);
    }
  });

  // ── Quick Connect: Google Analytics ─────────────────────────────────────────
  bindClick("ga-connect-btn", async function() {
    var btn = byId("ga-connect-btn");
    var accessToken = document.getElementById("ga-token").value.trim();
    var propertyId = document.getElementById("ga-property-id").value.trim();
    if (!accessToken) { setQcStatus("ga-status","Enter your Google Analytics access token first.","err"); return; }
    if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, true, "Connecting...");
    setQcStatus("ga-status","Connecting to Google Analytics...","info");
    try {
      var payload = { access_token: accessToken };
      if (propertyId) payload.property_id = propertyId;
      await apiJson("/api/v1/integrations/google-analytics/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      setQcStatus("ga-status","Connected!","ok");
      document.getElementById("ga-token").value = "";
      document.getElementById("ga-property-id").value = "";
      await fetchIntegrations();
      byId("ga-sync-btn").style.display = "";
    } catch (err) {
      setQcStatus("ga-status", mapUiError(err), "err");
    } finally {
      if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, false);
    }
  });
  bindClick("ga-sync-btn", async function() {
    setQcStatus("ga-status","Syncing analytics...","info");
    try {
      var body = await apiJson("/api/v1/integrations/google-analytics/sync", { method: "POST" });
      setQcStatus("ga-status","Synced: " + (body.sessions_30d||0) + " sessions, " + (body.active_users_30d||0) + " users.","ok");
      await fetchIntegrations();
    } catch (err) {
      setQcStatus("ga-status", mapUiError(err), "err");
    }
  });

  bindClick("refresh-integrations-btn", async function() {
    await refreshIntegrationPanels();
  });
  var securityHost = byId("security-center-summary");
  if (securityHost) {
    securityHost.addEventListener("click", function(e) {
      var btn = e.target.closest("[data-trend-panel='security'][data-trend-days]");
      if (!btn) return;
      var nextDays = Number(btn.getAttribute("data-trend-days"));
      if (!Number.isFinite(nextDays) || nextDays <= 0 || nextDays === securityTrendDays) return;
      securityTrendDays = nextDays;
      fetchSecurityCenter().catch(function() {});
    });
  }
  var autoRefreshToggle = byId("auto-refresh-toggle");
  if (autoRefreshToggle) {
    autoRefreshToggle.addEventListener("change", function() {
      autoRefreshEnabled = !!autoRefreshToggle.checked;
      saveAutoRefreshPreference();
      startAutoRefresh();
    });
  }
  bindClick("refresh-ai-btn", fetchAiStatus);
  bindClick("coding-discovery-btn", async function() {
    var project = (byId("coding-project-name") && byId("coding-project-name").value || "").trim();
    var language = (byId("coding-language") && byId("coding-language").value || "").trim();
    var stage = (byId("coding-stage") && byId("coding-stage").value || "").trim();
    var out = byId("coding-discovery-output");
    if (out) out.textContent = "Generating coding discovery questions...";
    try {
      var qs = [];
      if (project) qs.push("project_name=" + encodeURIComponent(project));
      if (language) qs.push("language=" + encodeURIComponent(language));
      if (stage) qs.push("stage=" + encodeURIComponent(stage));
      var path = "/api/v1/integrations/ai/coding-discovery" + (qs.length ? ("?" + qs.join("&")) : "");
      var body = await apiJson(path, { method: "GET" });
      if (!out) return;
      var questions = (body.questions || []).map(function(q){ return "<li>" + esc(q) + "</li>"; }).join("");
      out.innerHTML = (
        '<div style="margin-bottom:.45rem"><strong>Providers:</strong> ' + esc((body.provider_options || []).join(", ")) + '</div>' +
        '<ol style="margin:0 0 .55rem 1rem;padding-left:.6rem">' + questions + '</ol>' +
        '<div><strong>Ready Prompt:</strong><br><code style="white-space:pre-wrap;display:block;margin-top:.25rem">' + esc(body.next_prompt || "") + '</code></div>'
      );
    } catch (err) {
      if (out) out.textContent = mapUiError(err);
    }
  });

  var logoutBtn = byId("logout-btn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async function() {
      try {
        if (window.PCAPI && window.PCAPI.safeFetchJson) {
          await window.PCAPI.safeFetchJson("/web/logout", { method: "POST", csrf: true });
        } else {
          var csrfPair = document.cookie.split("; ").find(function(c){ return c.startsWith("pc_csrf="); });
          var csrf = csrfPair ? decodeURIComponent(csrfPair.split("=").slice(1).join("=")) : "";
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
    var syncBtn = e.target.closest("[data-sync]");
    if (syncBtn) {
      var name = syncBtn.getAttribute("data-sync");
      if (name === "calendar") { window.syncCalendar(); }
      else { window.syncIntegration(name); }
      return;
    }

    var integrationBtn = e.target.closest("[data-int-action]");
    if (integrationBtn) {
      var intAction = integrationBtn.getAttribute("data-int-action");
      if (intAction === "test") {
        var testId = Number(integrationBtn.getAttribute("data-int-id"));
        if (Number.isFinite(testId) && testId > 0) window.integrationTest(testId);
        return;
      }
      if (intAction === "disconnect") {
        var disconnectId = Number(integrationBtn.getAttribute("data-int-id"));
        if (Number.isFinite(disconnectId) && disconnectId > 0) window.integrationDisconnect(disconnectId);
        return;
      }
      if (intAction === "token-connect") {
        var reconnectType = integrationBtn.getAttribute("data-int-type");
        if (reconnectType) window.reconnectToken(reconnectType);
        return;
      }
      if (intAction === "oauth-reconnect") {
        var oauthType = integrationBtn.getAttribute("data-oauth-type");
        var oauthBtn = oauthType === "gmail" ? byId("gmail-auth-btn") : byId("gcal-auth-btn");
        if (oauthBtn) oauthBtn.click();
        return;
      }
    }

    var aiBtn = e.target.closest("[data-ai-action]");
    if (aiBtn) {
      var aiAction = aiBtn.getAttribute("data-ai-action");
      var provider = aiBtn.getAttribute("data-ai-provider");
      if (!provider) return;
      if (aiAction === "test") { window.testAI(provider); return; }
      if (aiAction === "connect") { window.connectAI(provider); return; }
      if (aiAction === "disconnect") { window.disconnectAI(provider); return; }
      return;
    }

    var dismissBtn = e.target.closest("[data-toast-dismiss]");
    if (dismissBtn) {
      var toast = dismissBtn.closest(".toast");
      if (!toast) return;
      toast.classList.add("removing");
      setTimeout(function() { toast.remove(); }, 250);
    }
  });

  // ── Health Dashboard ─────────────────────────────────────────────────────
  async function fetchHealthDashboard() {
    var loading = byId("health-dashboard-loading");
    var dashboard = byId("health-dashboard");
    if (!loading || !dashboard) return;
    try {
      var data = await apiJson("/api/v1/integrations/health-dashboard");
      if (!data || !data.summary) return;
      loading.style.display = "none";
      dashboard.style.display = "";
      renderHealthKpis(data.summary);
      renderHealthScore(data.summary.health_score);
      renderHealthDetails(data.integrations || []);
    } catch (_e) {
      loading.textContent = "Could not load health dashboard.";
    }
  }

  function renderHealthKpis(s) {
    var kpis = byId("health-kpis");
    if (!kpis) return;
    var items = [
      { label: "Total", val: s.total, cls: "" },
      { label: "Connected", val: s.connected, cls: "" },
      { label: "Healthy", val: s.healthy, cls: "ok" },
      { label: "Degraded", val: s.degraded, cls: s.degraded > 0 ? "warn" : "" },
      { label: "Errors", val: s.errored, cls: s.errored > 0 ? "bad" : "" },
      { label: "Disconnected", val: s.disconnected, cls: s.disconnected > 0 ? "bad" : "" },
    ];
    kpis.innerHTML = items.map(function (it) {
      return '<div class="health-kpi ' + it.cls + '">' +
        '<div class="hk-val">' + it.val + '</div>' +
        '<div class="hk-label">' + it.label + '</div></div>';
    }).join("");
  }

  function renderHealthScore(score) {
    var bar = byId("health-score-bar");
    if (!bar) return;
    var pct = Math.round(score * 100);
    var color = pct >= 80 ? "var(--ok)" : pct >= 50 ? "var(--warn)" : "var(--danger)";
    bar.innerHTML =
      '<span class="hsb-label" style="color:' + color + '">' + pct + '%</span>' +
      '<div class="hsb-track"><div class="hsb-fill" style="width:' + pct + '%;background:' + color + '"></div></div>';
  }

  function renderHealthDetails(integrations) {
    var tbody = byId("health-detail-tbody");
    if (!tbody) return;
    if (!integrations.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;opacity:.5">No integrations</td></tr>';
      return;
    }
    tbody.innerHTML = integrations.map(function (it) {
      var healthCls = it.health || "disconnected";
      return '<tr>' +
        '<td>' + esc(it.type) + '</td>' +
        '<td><span class="pill ' + (it.status === "connected" ? "connected" : "disconnected") + '">' + esc(it.status) + '</span></td>' +
        '<td><span class="health-pill ' + healthCls + '">' + esc(it.health) + '</span></td>' +
        '<td>' + (it.last_sync_at ? new Date(it.last_sync_at).toLocaleString() : '--') + '</td>' +
        '<td>' + (it.sync_error_count || 0) + '</td>' +
        '<td>' + (it.age_hours != null ? it.age_hours : '--') + '</td>' +
        '</tr>';
    }).join("");
  }

  function esc(val) {
    var s = String(val == null ? "" : val);
    return s.replace(/[&<>"']/g, function (c) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];
    });
  }

  bindClick("refresh-health-btn", function () { fetchHealthDashboard(); });

  // ── Boot ───────────────────────────────────────────────────────────────────
  try {
    if (window.PCUI && window.PCUI.loadRoleCapabilities) {
      var caps = await window.PCUI.loadRoleCapabilities();
      if (!caps.canManageIntegrations) {
        setStatus("integrations-status", "Integrations access is restricted for your role.", "warn");
        return;
      }
    }
    loadAutoRefreshPreference();
    await bootToken();
    await refreshIntegrationPanels();
    await fetchAiStatus();
    await fetchHealthDashboard();
    startAutoRefresh();
    // Show success toast if redirected from Gmail OAuth callback
    var params = new URLSearchParams(window.location.search);
    if (params.get("gmail") === "connected") {
      setStatus("connect-status", "Gmail connected successfully. You can now sync emails.", "ok");
      history.replaceState(null, "", window.location.pathname);
    }
  } catch (err) {
    stopAutoRefresh();
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
    var text = document.createElement("span");
    text.textContent = String(msg);
    var dismiss = document.createElement("button");
    dismiss.setAttribute("type", "button");
    dismiss.setAttribute("aria-label", "Dismiss");
    dismiss.setAttribute("data-toast-dismiss", "1");
    dismiss.textContent = "\u00d7";
    el.appendChild(text);
    el.appendChild(dismiss);
    var c = document.getElementById("toast-container");
    if (c) c.appendChild(el);
    setTimeout(function() {
      el.classList.add("removing");
      setTimeout(function() { el.remove(); }, 250);
    }, 4000);
  };
  if (typeof lucide !== "undefined") lucide.createIcons();
