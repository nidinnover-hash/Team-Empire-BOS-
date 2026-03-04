// ── Shared auth bootstrap ───────────────────────────────────────────────────
  // pc_session cookie is HttpOnly — JS can't read it. Fetch the token from the
  // server via /web/api-token which reads the cookie server-side and returns JWT.
  window.__bootPromise = (async function () {
    try {
      if (window.PCAPI && window.PCAPI.getApiToken) {
        return await window.PCAPI.getApiToken();
      }
      var r = await fetch("/web/api-token");
      if (!r.ok) return null;
      var d = await r.json();
      return d.token || null;
    } catch(e) { return null; }
  })();

  // ── Top Nav Tab Switching ──────────────────────────────────────────────────
  (function () {
    var tabs = document.querySelectorAll(".topnav-tab[data-view]");
    var views = {
      dashboard: document.getElementById("view-dashboard"),
      chat:      document.getElementById("view-chat")
    };
    var STORAGE_KEY = "nn_active_tab";

    function switchTab(viewName) {
      Object.keys(views).forEach(function (k) {
        if (views[k]) views[k].style.display = k === viewName ? "" : "none";
      });
      tabs.forEach(function (t) {
        t.classList.toggle("active", t.dataset.view === viewName);
      });
      try { localStorage.setItem(STORAGE_KEY, viewName); } catch(e) {}
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        switchTab(tab.dataset.view);
      });
    });

    // Restore last active tab
    try {
      var saved = localStorage.getItem(STORAGE_KEY);
      if (saved && views[saved]) switchTab(saved);
    } catch(e) {}
  })();

  (function () {
    const btn = document.getElementById("daily-run-btn");
    const status = document.getElementById("daily-run-status");
    const panel = document.getElementById("daily-run-result");
    const msg = document.getElementById("run-msg");
    const counts = document.getElementById("run-counts");
    if (!btn || !status || !panel || !msg || !counts) return;
    function notifyError(message) {
      if (window.showToast) window.showToast(message, "error");
      else window.alert(message);
    }

    btn.addEventListener("click", async function () {
      const ok = window.confirm("This creates drafts only. No sending or execution will happen. Continue?");
      if (!ok) return;

      btn.disabled = true;
      status.className = "run-status";
      status.textContent = "Running daily draft workflow...";

      try {
        const sessionRes = await fetch("/web/session");
        const sessionData = await sessionRes.json();
        if (!sessionData.logged_in) {
          window.location.href = "/web/login";
          return;
        }

        const csrfToken = (document.cookie.split("; ").find((c) => c.startsWith("pc_csrf=")) || "").split("=").slice(1).join("=");
        if (!csrfToken) throw new Error("Missing CSRF token");

        const res = await fetch("/web/ops/daily-run?draft_email_limit=3", {
          method: "POST",
          headers: { "X-CSRF-Token": decodeURIComponent(csrfToken) }
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Request failed");
        }
        panel.style.display = "block";
        msg.textContent = data.message || "Daily run completed.";
        counts.textContent =
          "Plans: " + (data.drafted_plan_count || 0) +
          " | Email drafts: " + (data.drafted_email_count || 0) +
          " | Pending approvals: " + (data.pending_approvals || 0);
        status.className = "run-status ok";
        status.textContent = "Draft-only run completed.";
      } catch (err) {
        panel.style.display = "none";
        status.className = "run-status err";
        status.textContent = "Daily run failed: " + (err && err.message ? err.message : "unknown error");
      } finally {
        btn.disabled = false;
      }
    });

    const logoutBtn = document.getElementById("logout-btn");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", async function (e) {
        e.preventDefault();
        try {
          const csrfToken = (document.cookie.split("; ").find((c) => c.startsWith("pc_csrf=")) || "").split("=").slice(1).join("=");
          const res = await fetch("/web/logout", {
            method: "POST",
            headers: csrfToken ? { "X-CSRF-Token": decodeURIComponent(csrfToken) } : {}
          });
          if (!res.ok) throw new Error("Logout failed");
          window.location.reload();
        } catch (err) {
          notifyError((err && err.message) ? err.message : "Logout failed");
        }
      });
    }

    const loginLink = document.getElementById("web-login-link");
    if (loginLink) {
      loginLink.addEventListener("click", function (e) {
        e.preventDefault();
        window.location.href = "/web/login";
      });
    }
  })();

  // ── Agent Chat ─────────────────────────────────────────────────────────────
  (function () {
    const input      = document.getElementById("chat-input");
    const sendBtn    = document.getElementById("chat-send");
    const history    = document.getElementById("chat-history");
    const placeholder = document.getElementById("chat-placeholder");
    const roleDisplay = document.getElementById("chat-role-display");
    const roleBtns   = document.querySelectorAll(".role-btn");

    // Full chat view elements
    const inputFull  = document.getElementById("chat-input-full");
    const sendBtnFull = document.getElementById("chat-send-full");
    const historyFull = document.getElementById("chat-history-full");

    if (!input || !sendBtn || !history) return;

    let selectedRole = "CEO Agent";

    roleBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        roleBtns.forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        selectedRole = btn.dataset.role || "";
        roleDisplay.textContent = selectedRole || "Auto";
      });
    });

    var esc = window.PCUI.escapeHtml;
    var getCsrf = window.PCUI.getCsrfToken;

    function appendNode(html) {
      if (placeholder && placeholder.parentNode) placeholder.remove();
      var parser = new DOMParser();
      var doc = parser.parseFromString(String(html || ""), "text/html");
      var node = doc.body.firstElementChild;
      if (!node) return;
      history.appendChild(node);
      history.scrollTop = history.scrollHeight;
      // Mirror to full chat view
      if (historyFull) {
        historyFull.appendChild(node.cloneNode(true));
        historyFull.scrollTop = historyFull.scrollHeight;
      }
    }

    async function ensureLoggedIn() {
      const res = await fetch("/web/session");
      if (!res.ok) throw new Error("Session check failed");
      const data = await res.json();
      if (data.logged_in) return true;
      window.location.href = "/web/login";
      return false;
    }

    async function send(sourceInput) {
      var activeInput = sourceInput || input;
      const message = activeInput.value.trim();
      if (!message) return;

      const loggedIn = await ensureLoggedIn();
      if (!loggedIn) {
        appendNode('<div class="chat-msg-agent"><div class="chat-role-tag">Error</div>Please sign in first.</div>');
        return;
      }

      const csrf = getCsrf();
      if (!csrf) {
        appendNode('<div class="chat-msg-agent"><div class="chat-role-tag">Error</div>Missing CSRF token — try refreshing the page after signing in.</div>');
        return;
      }

      var userDiv = document.createElement("div");
      userDiv.className = "chat-msg-user";
      userDiv.textContent = message;
      userDiv.style.whiteSpace = "pre-wrap";
      if (placeholder && placeholder.parentNode) placeholder.remove();
      history.appendChild(userDiv);
      history.scrollTop = history.scrollHeight;
      // Mirror user message to full chat
      if (historyFull) {
        historyFull.appendChild(userDiv.cloneNode(true));
        historyFull.scrollTop = historyFull.scrollHeight;
      }
      activeInput.value = "";
      if (inputFull) inputFull.value = "";
      input.value = "";
      sendBtn.disabled = true;
      if (sendBtnFull) sendBtnFull.disabled = true;

      const form = new URLSearchParams();
      form.set("message", message);
      if (selectedRole) form.set("force_role", selectedRole);

      try {
        const res = await fetch("/web/agents/chat", {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRF-Token": csrf
          },
          body: form.toString()
        });
        const data = await res.json();
        if (!res.ok) {
          appendNode('<div class="chat-msg-agent"><div class="chat-role-tag">Error</div>' + esc(data.detail || "Request failed") + '</div>');
        } else {
          const approvalHtml = data.requires_approval
            ? '<div class="chat-approval-warn">Heads up: this response involves a risky action — review before proceeding.</div>'
            : "";
          const msgId = Date.now();
          const actions = (data.proposed_actions || []).filter(function(a) { return a.action_type !== "NONE"; });
          if (actions.length) {
            window.__agentActions = window.__agentActions || {};
            window.__agentActions[msgId] = actions;
          }
          const actionsHtml = actions.length ? (function() {
            return '<div class="chat-actions">' +
              actions.map(function(a, i) {
                var label = a.action_type === "TASK_CREATE"   ? "Create Task"
                          : a.action_type === "MEMORY_WRITE"  ? "Save to Memory"
                          : a.action_type;
                var desc  = "";
                if (a.action_type === "TASK_CREATE"  && a.params && a.params.title)
                  desc = " — " + esc(String(a.params.title).slice(0, 50));
                if (a.action_type === "MEMORY_WRITE" && a.params)
                  desc = " — " + esc((a.params.key || "") + (a.params.value ? ": " + String(a.params.value).slice(0,40) : ""));
                return '<button class="btn-agent-action" id="aa-' + msgId + '-' + i + '" ' +
                  'data-agent-msg="' + msgId + '" data-agent-idx="' + i + '">' +
                  label + desc + '</button>';
              }).join("") +
            '</div>';
          })() : "";
          appendNode(
            '<div class="chat-msg-agent">' +
              '<div class="chat-role-tag">' + esc(data.role) + '</div>' +
              esc(data.response).replace(/\n/g, "<br>") +
              approvalHtml +
              actionsHtml +
            '</div>'
          );
          roleDisplay.textContent = data.role;
          try { localStorage.removeItem(_chatCacheKey); } catch(e) {}
        }
      } catch (err) {
        appendNode('<div class="chat-msg-agent"><div class="chat-role-tag">Error</div>Could not reach server.</div>');
      } finally {
        sendBtn.disabled = false;
        if (sendBtnFull) sendBtnFull.disabled = false;
        activeInput.focus();
      }
    }

    // Event delegation for agent action buttons in both chat areas
    if (historyFull) {
      historyFull.addEventListener('click', function(e) {
        var btn = e.target.closest('[data-agent-msg]');
        if (!btn) return;
        var msgId = parseInt(btn.dataset.agentMsg, 10);
        var idx = parseInt(btn.dataset.agentIdx, 10);
        executeAgentAction(msgId, idx);
      });
    }

    // Event delegation for agent action buttons (CSP-safe, no inline onclick)
    history.addEventListener('click', function(e) {
      var btn = e.target.closest('[data-agent-msg]');
      if (!btn) return;
      var msgId = parseInt(btn.dataset.agentMsg, 10);
      var idx = parseInt(btn.dataset.agentIdx, 10);
      executeAgentAction(msgId, idx);
    });

    // Execute a proposed agent action (TASK_CREATE or MEMORY_WRITE)
    async function executeAgentAction(msgId, idx) {
      var btn = document.getElementById("aa-" + msgId + "-" + idx);
      if (btn) { btn.disabled = true; btn.textContent = "…"; }
      var actions = (window.__agentActions || {})[msgId] || [];
      var action = actions[idx];
      if (!action) { if (btn) { btn.textContent = "Error"; } return; }
      var token = window.__apiToken;
      if (!token && window.__bootPromise) {
        token = await window.__bootPromise;
        if (token) window.__apiToken = token;
      }
      if (!token) {
        if (window.showToast) window.showToast("Not authenticated.", "error");
        else alert("Not authenticated.");
        if (btn) btn.disabled = false;
        return;
      }
      try {
        var r;
        if (action.action_type === "TASK_CREATE") {
          var p = action.params || {};
          r = await fetch("/api/v1/tasks", {
            method: "POST",
            headers: { "Authorization": "Bearer " + token, "Content-Type": "application/json" },
            body: JSON.stringify({
              title:    p.title    || "Agent-created task",
              category: p.category || "work",
              priority: p.priority || 2,
              notes:    p.notes    || null,
            })
          });
        } else if (action.action_type === "MEMORY_WRITE") {
          var p = action.params || {};
          r = await fetch("/api/v1/memory/profile", {
            method: "POST",
            headers: { "Authorization": "Bearer " + token, "Content-Type": "application/json" },
            body: JSON.stringify({
              key:      p.key      || "agent_note",
              value:    p.value    || "",
              category: p.category || null,
            })
          });
        } else {
          if (window.showToast) window.showToast("Unsupported action: " + action.action_type, "error");
          else alert("Unsupported action: " + action.action_type);
          if (btn) btn.disabled = false;
          return;
        }
        if (r && r.ok) {
          if (btn) { btn.textContent = "Done"; btn.style.background = "rgba(74,222,128,0.08)"; btn.style.color = "var(--ok)"; btn.style.borderColor = "rgba(74,222,128,0.25)"; }
        } else {
          var d = await r.json().catch(function(){return {};});
          if (window.showToast) window.showToast("Action failed: " + (d.detail || r.status), "error");
          else alert("Action failed: " + (d.detail || r.status));
          if (btn) { btn.disabled = false; btn.textContent = action.action_type; }
        }
      } catch(e) {
        if (window.showToast) window.showToast("Network error executing action.", "error");
        else alert("Network error executing action.");
        if (btn) { btn.disabled = false; }
      }
    };

    sendBtn.addEventListener("click", function() { send(input); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
    });

    // Full chat view send wiring
    if (sendBtnFull) sendBtnFull.addEventListener("click", function() { send(inputFull); });
    if (inputFull) inputFull.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(inputFull); }
    });

    // Suggestion chips — click to auto-send
    document.querySelectorAll(".chat-suggestion").forEach(function (chip) {
      chip.addEventListener("click", function () {
        input.value = chip.textContent;
        send(input);
      });
    });

    // Load persistent chat history on boot (with localStorage cache, 5-min TTL)
    var _chatCacheKey = "nn_chat_history";
    var _chatCacheTTL = 5 * 60 * 1000;

    function renderChatMessages(msgs) {
      if (!msgs || !msgs.length) return;
      msgs.forEach(function(m) {
        appendNode('<div class="chat-msg-user">' + esc(m.user_message) + '</div>');
        appendNode(
          '<div class="chat-msg-agent">' +
            '<div class="chat-role-tag">' + esc(m.role) + '</div>' +
            esc(m.ai_response).replace(/\n/g, "<br>") +
          '</div>'
        );
      });
    }

    (async function bootHistory() {
      try {
        var cached = localStorage.getItem(_chatCacheKey);
        if (cached) {
          var parsed = JSON.parse(cached);
          if (parsed.ts && Date.now() - parsed.ts < _chatCacheTTL) {
            renderChatMessages(parsed.data);
            return;
          }
        }
      } catch(e) { /* ignore corrupt cache */ }

      try {
        var r = await fetch("/web/chat/history");
        if (!r.ok) return;
        var msgs = await r.json();
        renderChatMessages(msgs);
        try {
          localStorage.setItem(_chatCacheKey, JSON.stringify({ ts: Date.now(), data: msgs }));
        } catch(e) { /* quota exceeded */ }
      } catch(e) {
        if (window.showToast) window.showToast("Failed to load chat history.", "warn");
      }
    })();
  })();

  // First-login onboarding checklist (client-side persistence)
  (function () {
    var list = document.getElementById("onboarding-list");
    var progress = document.getElementById("onboarding-progress");
    if (!list || !progress) return;

    var storageKey = "pc_onboarding_checklist_v1";
    var steps = [
      { id: "login", label: "Sign in and load Dashboard, Talk, Integrations, Tasks" },
      { id: "integrations", label: "Connect at least one active integration" },
      { id: "talk_prompts", label: "Run 3 Talk prompts (priority, approvals, 2-hour plan)" },
      { id: "tasks", label: "Add 3 high-impact tasks and close stale tasks" },
      { id: "memory", label: "Save 3 profile memory preferences" }
    ];

    function getState() {
      try {
        var raw = localStorage.getItem(storageKey);
        var parsed = raw ? JSON.parse(raw) : {};
        return (parsed && typeof parsed === "object") ? parsed : {};
      } catch (_e) {
        return {};
      }
    }

    function setState(state) {
      try { localStorage.setItem(storageKey, JSON.stringify(state)); } catch (_e) {}
    }

    function render() {
      var state = getState();
      var done = 0;
      list.innerHTML = "";
      steps.forEach(function (s) {
        var checked = !!state[s.id];
        if (checked) done += 1;
        var row = document.createElement("label");
        row.className = "onboarding-row" + (checked ? " done" : "");

        var input = document.createElement("input");
        input.type = "checkbox";
        input.setAttribute("data-onboarding-id", s.id);
        input.checked = checked;
        row.appendChild(input);

        var text = document.createElement("span");
        text.textContent = s.label;
        row.appendChild(text);

        list.appendChild(row);
      });
      progress.textContent = done + "/" + steps.length;
      if (done === steps.length) {
        var card = document.getElementById("first-login-card");
        if (card) card.style.display = "none";
      }
    }

    list.addEventListener("change", function (e) {
      var target = e.target;
      if (!target || !target.matches("[data-onboarding-id]")) return;
      var state = getState();
      state[target.getAttribute("data-onboarding-id")] = !!target.checked;
      setState(state);
      render();
    });

    render();
  })();

  // ── Gmail Inbox Panel ──────────────────────────────────────────────────────
  (function () {
    const list    = document.getElementById("inbox-list");
    const syncBtn = document.getElementById("inbox-sync-btn");
    const composeBtn   = document.getElementById("inbox-compose-btn");
    const composeForm  = document.getElementById("inbox-compose-form");
    const cancelBtn    = document.getElementById("compose-cancel-btn");
    const draftBtn     = document.getElementById("compose-send-btn");
    const composeStatus = document.getElementById("compose-status");

    function getCsrf() {
      const pair = document.cookie.split("; ").find(function(c){ return c.startsWith("pc_csrf="); });
      return pair ? decodeURIComponent(pair.split("=").slice(1).join("=")) : "";
    }

    function apiHeaders() {
      return { "Content-Type": "application/json", "X-CSRF-Token": getCsrf() };
    }

    function fmt(iso) {
      if (!iso) return "";
      var d = new Date(iso);
      return d.toLocaleDateString("en-US",{month:"short",day:"numeric"}) + " " +
             d.toLocaleTimeString("en-US",{hour:"2-digit",minute:"2-digit"});
    }

    function esc(s) {
      return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    }

    function mk(tag, className, text) {
      var node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined && text !== null) node.textContent = String(text);
      return node;
    }

    function setInboxEmpty(text) {
      list.innerHTML = "";
      list.appendChild(mk("div", "empty", text));
    }

    function renderInboxItem(e) {
      var item = mk("div", "inbox-item" + (e.is_read ? "" : " unread"));
      item.id = "email-" + e.id;
      item.appendChild(mk("div", "inbox-from", e.from_address || "Unknown"));
      item.appendChild(mk("div", "inbox-subject", e.subject || "(no subject)"));
      var meta = mk("div", "inbox-meta", fmt(e.received_at));
      if (e.reply_sent) {
        meta.appendChild(document.createTextNode(" · "));
        var replied = mk("span", "", "replied");
        replied.style.color = "var(--ok)";
        meta.appendChild(replied);
      }
      item.appendChild(meta);
      if (e.ai_summary) item.appendChild(mk("div", "inbox-summary", e.ai_summary));
      var actions = mk("div", "inbox-actions");
      if (!e.ai_summary) {
        var summarizeBtn = mk("button", "ia-btn ia-summarize", "Summarize");
        summarizeBtn.setAttribute("data-inbox-id", String(e.id));
        summarizeBtn.setAttribute("data-inbox-action", "summarize");
        actions.appendChild(summarizeBtn);
      }
      var strategyBtn = mk("button", "ia-btn ia-strategy", "Strategy");
      strategyBtn.setAttribute("data-inbox-id", String(e.id));
      strategyBtn.setAttribute("data-inbox-action", "strategize");
      actions.appendChild(strategyBtn);
      var draftBtn = mk("button", "ia-btn ia-draft", e.draft_reply ? "Re-draft" : "Draft Reply");
      draftBtn.setAttribute("data-inbox-id", String(e.id));
      draftBtn.setAttribute("data-inbox-action", "draft");
      actions.appendChild(draftBtn);
      item.appendChild(actions);
      if (e.draft_reply) {
        var draft = mk("div", "inbox-draft", e.draft_reply);
        draft.id = "draft-" + e.id;
        item.appendChild(draft);
      }
      return item;
    }

    async function loadInbox() {
      setInboxEmpty("Loading...");
      try {
        const r = await fetch("/api/v1/email/inbox?limit=15&unread_only=false", {
          headers: { "Authorization": "Bearer " + window.__apiToken }
        });
        if (!r.ok) { setInboxEmpty("Could not load inbox."); return; }
        const emails = await r.json();
        if (!emails.length) { setInboxEmpty("No emails synced yet. Click Sync Gmail."); return; }
        list.innerHTML = "";
        emails.forEach(function(e) {
          list.appendChild(renderInboxItem(e));
        });
      } catch(err) {
        setInboxEmpty("Error loading inbox.");
      }
    }

    // Event delegation for inbox action buttons (CSP-safe)
    document.getElementById("inbox-list").addEventListener("click", function(e) {
      var btn = e.target.closest("[data-inbox-id]");
      if (!btn) return;
      inboxAction(parseInt(btn.dataset.inboxId, 10), btn.dataset.inboxAction);
    });

    async function inboxAction(emailId, action) {
      const item = document.getElementById("email-" + emailId);
      const btn = item ? item.querySelector(".ia-" + (action === "draft" ? "draft" : action === "strategize" ? "strategy" : "summarize")) : null;
      if (btn) { btn.disabled = true; btn.textContent = "…"; }

      const token = window.__apiToken;
      const readError = async function(resp) {
        try {
          const body = await resp.json();
          if (typeof body?.detail === "string") return body.detail;
          if (body && body.detail) return JSON.stringify(body.detail);
        } catch (_e) {}
        return "Request failed (" + resp.status + ")";
      };
      if (!token) {
        const msg = "Session missing. Please refresh and sign in again.";
        if (window.showToast) window.showToast(msg, "error"); else alert(msg);
        if (btn) { btn.disabled = false; btn.textContent = action === "summarize" ? "Summarize" : action === "strategize" ? "Strategy" : "Re-draft"; }
        return;
      }
      try {
        if (action === "summarize") {
          const r = await fetch("/api/v1/email/" + emailId + "/summarize", { method:"POST", headers:{"Authorization":"Bearer "+token} });
          if (!r.ok) throw new Error(await readError(r));
          const d = await r.json();
          let el = item.querySelector(".inbox-summary");
          if (!el) { el = document.createElement("div"); el.className = "inbox-summary"; item.querySelector(".inbox-actions").before(el); }
          el.textContent = d.summary || "No summary returned.";
          if (btn) btn.remove();
        } else if (action === "strategize") {
          const r = await fetch("/api/v1/email/" + emailId + "/strategize", { method:"POST", headers:{"Authorization":"Bearer "+token} });
          if (!r.ok) throw new Error(await readError(r));
          const d = await r.json();
          let el = item.querySelector(".inbox-strategy");
          if (!el) { el = document.createElement("div"); el.className = "inbox-strategy"; item.appendChild(el); }
          el.textContent = d.strategy || "No strategy returned.";
        } else if (action === "draft") {
          const r = await fetch("/api/v1/email/" + emailId + "/draft-reply", { method:"POST", headers:{"Authorization":"Bearer "+token, "Content-Type":"application/json"}, body:"{}" });
          if (!r.ok) throw new Error(await readError(r));
          const d = await r.json();
          let el = item.querySelector(".inbox-draft");
          if (!el) { el = document.createElement("div"); el.className = "inbox-draft"; item.appendChild(el); }
          el.textContent = d.draft || "No draft returned.";
        }
      } catch(e) {
        const msg = (e && e.message) ? e.message : "Action failed.";
        if (window.showToast) window.showToast(msg, "error"); else alert(msg);
      }
      if (btn) { btn.disabled = false; btn.textContent = action === "summarize" ? "Summarize" : action === "strategize" ? "Strategy" : "Re-draft"; }
    };

    // Sync Gmail
    syncBtn && syncBtn.addEventListener("click", async function() {
      syncBtn.disabled = true; syncBtn.textContent = "Syncing…";
      try {
        const r = await fetch("/api/v1/email/sync", { method:"POST", headers:{"Authorization":"Bearer "+window.__apiToken} });
        if (!r.ok) {
          const d = await r.json().catch(function(){ return {}; });
          throw new Error(d.detail || "Gmail sync failed");
        }
        await loadInbox();
      } catch (e) {
        if (window.showToast) window.showToast((e && e.message) ? e.message : "Gmail sync failed", "error");
      } finally { syncBtn.disabled = false; syncBtn.textContent = "Sync Gmail"; }
    });

    // Compose
    composeBtn && composeBtn.addEventListener("click", function() { composeForm.style.display = "block"; });
    cancelBtn  && cancelBtn.addEventListener("click",  function() { composeForm.style.display = "none"; composeStatus.textContent = ""; });
    draftBtn   && draftBtn.addEventListener("click", async function() {
      const to      = document.getElementById("compose-to").value.trim();
      const subject = document.getElementById("compose-subject").value.trim();
      const instr   = document.getElementById("compose-instruction").value.trim();
      if (!to || !subject || !instr) { composeStatus.textContent = "Fill in all fields."; composeStatus.className = "run-status err"; return; }
      draftBtn.disabled = true; composeStatus.textContent = "ChatGPT is drafting…"; composeStatus.className = "run-status";
      try {
        const r = await fetch("/api/v1/email/compose", {
          method:"POST",
          headers:{"Authorization":"Bearer "+window.__apiToken,"Content-Type":"application/json"},
          body:JSON.stringify({ to, subject, instruction: instr })
        });
        const d = await r.json();
        if (r.ok) {
          composeStatus.textContent = "Draft ready — check Approvals to review before sending.";
          composeStatus.className = "run-status ok";
          document.getElementById("compose-to").value = "";
          document.getElementById("compose-subject").value = "";
          document.getElementById("compose-instruction").value = "";
        } else {
          composeStatus.textContent = d.detail || "Failed."; composeStatus.className = "run-status err";
        }
      } catch(e) { composeStatus.textContent = "Error."; composeStatus.className = "run-status err"; }
      draftBtn.disabled = false;
    });

    // Bootstrap: get Bearer token via server endpoint (pc_session is HttpOnly)
    (async function bootstrap() {
      var token = await window.__bootPromise;
      if (!token) return;
      window.__apiToken = token;
      await loadInbox();
    })();
  })();

  // ── Pending Approvals Panel ─────────────────────────────────────────────────
  (function () {
    const RISKY = new Set(["send_message","assign_task","assign_leads","change_crm_status","spend_money","spend"]);
    const list       = document.getElementById("approvals-list");
    const countBadge = document.getElementById("approvals-pending-count");
    const refreshBtn = document.getElementById("approvals-refresh-btn");
    if (!list) return;

    var esc = window.PCUI.escapeHtml;

    function mk(tag, className, text) {
      var node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined && text !== null) node.textContent = String(text);
      return node;
    }

    function payloadRow(label, value) {
      var row = document.createElement("div");
      var strong = document.createElement("strong");
      strong.textContent = label + ":";
      row.appendChild(strong);
      row.appendChild(document.createTextNode(" " + value));
      return row;
    }

    function renderPayload(payloadDiv, p) {
      if (p.to) payloadDiv.appendChild(payloadRow("To", String(p.to)));
      if (p.subject) payloadDiv.appendChild(payloadRow("Subject", String(p.subject)));
      if (p.body && typeof p.body === "string") {
        var preview = p.body.slice(0, 140) + (p.body.length > 140 ? "..." : "");
        payloadDiv.appendChild(payloadRow("Preview", preview));
      }
      if (!payloadDiv.childNodes.length) {
        Object.keys(p).slice(0, 4).forEach(function(k) {
          if (k !== "approval_type") {
            payloadDiv.appendChild(payloadRow(k, String(p[k]).slice(0, 80)));
          }
        });
      }
    }

    function setApprovalsEmpty(text, color) {
      list.innerHTML = "";
      var node = mk("div", "empty", text);
      if (color) node.style.color = color;
      list.appendChild(node);
    }

    function renderApprovalItem(a) {
      var risky = RISKY.has(a.approval_type);
      var payload = a.payload_json || {};
      var ts = new Date(a.created_at).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      });

      var item = mk("div", "ap-item");
      item.id = "ap-" + a.id;

      var head = mk("div", "");
      head.style.display = "flex";
      head.style.justifyContent = "space-between";
      head.style.alignItems = "flex-start";
      head.style.gap = ".5rem";

      var type = mk("span", "ap-type " + (risky ? "risky" : "safe"), (a.approval_type || "") + (risky ? " [RISK]" : ""));
      var meta = mk("span", "ap-meta", "#" + a.id + " - " + ts);
      head.appendChild(type);
      head.appendChild(meta);
      item.appendChild(head);

      if (Object.keys(payload).length) {
        var payloadDiv = mk("div", "ap-payload");
        renderPayload(payloadDiv, payload);
        item.appendChild(payloadDiv);
      }

      var actions = mk("div", "ap-actions");
      var approveBtn = mk("button", risky ? "btn-execute" : "btn-approve", risky ? "Approve & Send" : "Approve");
      approveBtn.setAttribute("data-approval-id", String(a.id));
      approveBtn.setAttribute("data-approval-execute", risky ? "true" : "false");
      actions.appendChild(approveBtn);

      var rejectBtn = mk("button", "btn-reject", "Reject");
      rejectBtn.setAttribute("data-approval-reject", String(a.id));
      actions.appendChild(rejectBtn);

      item.appendChild(actions);
      return item;
    }

    async function loadApprovals() {
      var token = window.__apiToken;
      if (!token) { setApprovalsEmpty("Sign in to see approvals."); return; }
      setApprovalsEmpty("Loading...");
      try {
        var r = await fetch("/api/v1/approvals?status=pending", { headers:{"Authorization":"Bearer "+token} });
        if (!r.ok) { setApprovalsEmpty("Could not load approvals."); return; }
        var items = await r.json();
        if (countBadge) countBadge.textContent = items.length + " pending";
        if (!items.length) {
          setApprovalsEmpty("No pending approvals - all clear.", "var(--ok)");
          return;
        }
        list.innerHTML = "";
        items.forEach(function(a) {
          list.appendChild(renderApprovalItem(a));
        });
      } catch(e) {
        setApprovalsEmpty("Error loading approvals.");
      }
    }

    // Event delegation for approval action buttons (CSP-safe)
    document.getElementById("approvals-list").addEventListener("click", function(e) {
      var approveBtn = e.target.closest("[data-approval-id]");
      if (approveBtn) {
        approvalAction(parseInt(approveBtn.dataset.approvalId, 10), approveBtn.dataset.approvalExecute === "true");
        return;
      }
      var rejectBtn = e.target.closest("[data-approval-reject]");
      if (rejectBtn) {
        approvalReject(parseInt(rejectBtn.dataset.approvalReject, 10));
      }
    });

    async function approvalAction(id, isRisky) {
      if (isRisky) {
        var ok = window.confirm("This will SEND the email / execute the action.\nAre you absolutely sure?");
        if (!ok) return;
      }
      var item = document.getElementById("ap-" + id);
      var btns = item ? item.querySelectorAll("button") : [];
      btns.forEach(function(b) { b.disabled = true; });
      var note = isRisky ? "YES EXECUTE" : null;
      try {
        var r = await fetch("/api/v1/approvals/" + id + "/approve", {
          method:"POST",
          headers:{"Authorization":"Bearer "+window.__apiToken,"Content-Type":"application/json"},
          body:JSON.stringify({ note: note })
        });
        if (r.ok) {
          if (item) { item.style.opacity="0.35"; item.style.pointerEvents="none"; }
          setTimeout(loadApprovals, 700);
        } else {
          var d = await r.json().catch(function(){return {};});
          if (window.showToast) window.showToast("Error: " + (d.detail || "Approval failed"), "error");
          else alert("Error: " + (d.detail || "Approval failed"));
          btns.forEach(function(b) { b.disabled = false; });
        }
      } catch(e) {
        if (window.showToast) window.showToast("Network error.", "error");
        else alert("Network error.");
        btns.forEach(function(b) { b.disabled = false; });
      }
    };

    async function approvalReject(id) {
      var ok = window.confirm("Reject this approval? This cannot be undone.");
      if (!ok) return;
      var item = document.getElementById("ap-" + id);
      var btns = item ? item.querySelectorAll("button") : [];
      btns.forEach(function(b) { b.disabled = true; });
      try {
        var r = await fetch("/api/v1/approvals/" + id + "/reject", {
          method:"POST",
          headers:{"Authorization":"Bearer "+window.__apiToken,"Content-Type":"application/json"},
          body:JSON.stringify({ note: null })
        });
        if (r.ok) {
          if (item) { item.style.opacity="0.35"; item.style.pointerEvents="none"; }
          setTimeout(loadApprovals, 700);
        } else {
          var d = await r.json().catch(function(){return {};});
          if (window.showToast) window.showToast("Error: " + (d.detail || "Reject failed"), "error");
          else alert("Error: " + (d.detail || "Reject failed"));
          btns.forEach(function(b) { b.disabled = false; });
        }
      } catch(e) {
        if (window.showToast) window.showToast("Network error.", "error");
        else alert("Network error.");
        btns.forEach(function(b) { b.disabled = false; });
      }
    };

    refreshBtn && refreshBtn.addEventListener("click", loadApprovals);

    // Bootstrap: wait for shared auth token then load approvals
    (async function init() {
      var token = await window.__bootPromise;
      if (!token) { setApprovalsEmpty("Sign in to see approvals."); return; }
      if (!window.__apiToken) window.__apiToken = token;
      await loadApprovals();
    })();

    // Auto-refresh every 60 seconds (tracked for cleanup)
    var _approvalTimer = setInterval(function() { if (window.__apiToken) loadApprovals(); }, 60000);
    window.addEventListener("beforeunload", function() { clearInterval(_approvalTimer); });
  })();

  // ── Audit Log Panel ─────────────────────────────────────────────────────────
  (async function () {
    var list       = document.getElementById("audit-list");
    var countBadge = document.getElementById("audit-count");
    var refreshBtn = document.getElementById("audit-refresh-btn");
    if (!list) return;

    var esc = window.PCUI.escapeHtml;

    // Colour-code the dot based on outcome
    function dotClass(t) {
      if (!t) return "a-gray";
      t = t.toLowerCase();
      if (t.includes("failed") || t.includes("blocked") || t.includes("denied") || t.includes("error")) return "a-red";
      if (t.includes("rejected")) return "a-orange";
      if (t.includes("sent") || t.includes("succeeded") || t.includes("granted") || t.includes("passed") || t.includes("connected")) return "a-green";
      if (t.includes("sync") || t.includes("daily_run") || t.includes("draft") || t.includes("briefing") || t.includes("composed") || t.includes("strategize")) return "a-purple";
      return "a-gray";
    }

    // Build a human-readable one-liner from the event
    function fmtDetail(e) {
      var parts = [];
      if (e.entity_type) parts.push(e.entity_type + (e.entity_id ? " #" + e.entity_id : ""));
      if (e.actor_user_id) parts.push("user #" + e.actor_user_id);
      var p = e.payload_json || {};
      if (p.username)             parts.push("login: " + String(p.username).slice(0, 50));
      if (p.ip)                   parts.push("ip: " + p.ip);
      if (p.subject)              parts.push(String(p.subject).slice(0, 60));
      if (p.to)                   parts.push("to: " + String(p.to).slice(0, 50));
      if (p.error)                parts.push("error: " + String(p.error).slice(0, 80));
      if (p.new_emails !== undefined) parts.push("new emails: " + p.new_emails);
      if (p.drafted_plan_count !== undefined)
        parts.push("plans: " + p.drafted_plan_count + " · email drafts: " + (p.drafted_email_count || 0));
      if (p.provider)             parts.push(p.provider);
      if (p.type)                 parts.push(p.type);
      return parts.join(" · ");
    }

    function fmt(iso) {
      if (!iso) return "";
      var d = new Date(iso);
      return d.toLocaleDateString("en-US",{month:"short",day:"numeric"}) + " " +
             d.toLocaleTimeString("en-US",{hour:"2-digit",minute:"2-digit"});
    }

    function setAuditEmpty(text) {
      list.innerHTML = "";
      var el = document.createElement("div");
      el.className = "empty";
      el.textContent = text;
      list.appendChild(el);
    }

    function renderAuditRow(e) {
      var row = document.createElement("div");
      row.className = "audit-row";

      var dot = document.createElement("div");
      dot.className = "audit-dot " + dotClass(e.event_type);
      row.appendChild(dot);

      var body = document.createElement("div");
      body.style.flex = "1";
      body.style.minWidth = "0";

      var head = document.createElement("div");
      head.style.display = "flex";
      head.style.justifyContent = "space-between";
      head.style.alignItems = "baseline";
      head.style.gap = ".5rem";

      var type = document.createElement("span");
      type.className = "audit-type";
      type.textContent = e.event_type || "";
      head.appendChild(type);

      var time = document.createElement("span");
      time.className = "audit-time";
      time.textContent = fmt(e.created_at);
      head.appendChild(time);
      body.appendChild(head);

      var detailText = fmtDetail(e);
      if (detailText) {
        var detail = document.createElement("div");
        detail.className = "audit-detail";
        detail.textContent = detailText;
        body.appendChild(detail);
      }

      row.appendChild(body);
      return row;
    }

    async function loadAudit() {
      var token = window.__apiToken;
      if (!token) { setAuditEmpty("Sign in to view activity."); return; }
      try {
        var r = await fetch("/api/v1/ops/events?limit=40", { headers:{"Authorization":"Bearer "+token} });
        if (!r.ok) { setAuditEmpty("Could not load activity log."); return; }
        var events = await r.json();
        if (countBadge) countBadge.textContent = events.length + " events";
        if (!events.length) { setAuditEmpty("No activity logged yet."); return; }
        list.innerHTML = "";
        events.forEach(function(e) {
          list.appendChild(renderAuditRow(e));
        });
      } catch(err) {
        setAuditEmpty("Error loading activity log.");
      }
    }
    refreshBtn && refreshBtn.addEventListener("click", loadAudit);

    // Bootstrap: wait for shared auth, then load
    var token = await window.__bootPromise;
    if (!token) { setAuditEmpty("Sign in to view activity."); return; }
    if (!window.__apiToken) window.__apiToken = token;
    await loadAudit();

    // Auto-refresh every 30 seconds (tracked for cleanup)
    var _auditTimer = setInterval(function() { if (window.__apiToken) loadAudit(); }, 30000);
    window.addEventListener("beforeunload", function() { clearInterval(_auditTimer); });
  })();

  // ── Memory Editor Panel ──────────────────────────────────────────────────────
  (async function () {
    var list       = document.getElementById("mem-list");
    var countBadge = document.getElementById("mem-count");
    var refreshBtn = document.getElementById("mem-refresh-btn");
    var addToggle  = document.getElementById("mem-add-toggle");
    var addForm    = document.getElementById("mem-add-form");
    var saveBtn    = document.getElementById("mem-save-btn");
    var formStatus = document.getElementById("mem-form-status");
    if (!list) return;

    var esc = window.PCUI.escapeHtml;

    function setMemoryEmpty(text) {
      list.innerHTML = "";
      var el = document.createElement("div");
      el.className = "empty";
      el.textContent = text;
      list.appendChild(el);
    }

    function renderMemoryItem(m) {
      var row = document.createElement("div");
      row.className = "mem-row";
      row.id = "mem-entry-" + m.id;

      var body = document.createElement("div");
      body.style.flex = "1";
      body.style.minWidth = "0";

      var head = document.createElement("div");
      head.style.display = "flex";
      head.style.alignItems = "baseline";
      head.style.gap = ".4rem";

      var key = document.createElement("span");
      key.className = "mem-key";
      key.textContent = m.key || "";
      head.appendChild(key);

      if (m.category) {
        var cat = document.createElement("span");
        cat.className = "mem-cat";
        cat.textContent = "[" + m.category + "]";
        head.appendChild(cat);
      }
      body.appendChild(head);

      var val = document.createElement("div");
      val.className = "mem-val";
      val.textContent = m.value || "";
      body.appendChild(val);

      row.appendChild(body);

      var del = document.createElement("button");
      del.className = "btn-mem-del";
      del.title = "Delete entry";
      del.setAttribute("data-memory-delete", String(m.id));
      del.textContent = "x";
      row.appendChild(del);

      return row;
    }

    async function loadMemory() {
      var token = window.__apiToken;
      if (!token) { setMemoryEmpty("Sign in to view memory."); return; }
      try {
        var r = await fetch("/api/v1/memory/profile", { headers:{"Authorization":"Bearer "+token} });
        if (!r.ok) { setMemoryEmpty("Could not load memory (CEO role required)."); return; }
        var entries = await r.json();
        if (countBadge) countBadge.textContent = entries.length + " entries";
        if (!entries.length) { setMemoryEmpty("No memory entries yet. Click + Add to create one."); return; }
        list.innerHTML = "";
        entries.forEach(function(m) {
          list.appendChild(renderMemoryItem(m));
        });
      } catch(err) {
        setMemoryEmpty("Error loading memory.");
      }
    }

    // Event delegation for memory delete buttons (CSP-safe)
    document.getElementById("mem-list").addEventListener("click", function(e) {
      var btn = e.target.closest("[data-memory-delete]");
      if (btn) memoryDelete(parseInt(btn.dataset.memoryDelete, 10));
    });

    async function memoryDelete(id) {
      var ok = window.confirm("Delete this memory entry?");
      if (!ok) return;
      var token = window.__apiToken;
      try {
        var r = await fetch("/api/v1/memory/profile/" + id, {
          method: "DELETE",
          headers: {"Authorization":"Bearer "+token}
        });
        if (r.ok || r.status === 204) {
          await loadMemory();
        } else {
          if (window.showToast) window.showToast("Delete failed.", "error");
          else alert("Delete failed.");
        }
      } catch(e) {
        if (window.showToast) window.showToast("Network error.", "error");
        else alert("Network error.");
      }
    };

    addToggle && addToggle.addEventListener("click", function() {
      addForm.style.display = addForm.style.display === "block" ? "none" : "block";
    });

    saveBtn && saveBtn.addEventListener("click", async function() {
      var key = document.getElementById("mem-input-key").value.trim();
      var val = document.getElementById("mem-input-val").value.trim();
      var cat = document.getElementById("mem-input-cat").value.trim();
      if (!key || !val) { formStatus.textContent = "Key and Value are required."; formStatus.className = "run-status err"; return; }
      saveBtn.disabled = true;
      formStatus.textContent = "Saving…"; formStatus.className = "run-status";
      var token = window.__apiToken;
      try {
        var r = await fetch("/api/v1/memory/profile", {
          method: "POST",
          headers: {"Authorization":"Bearer "+token,"Content-Type":"application/json"},
          body: JSON.stringify({ key: key, value: val, category: cat || null })
        });
        if (r.ok) {
          formStatus.textContent = "Saved!"; formStatus.className = "run-status ok";
          document.getElementById("mem-input-key").value = "";
          document.getElementById("mem-input-val").value = "";
          document.getElementById("mem-input-cat").value = "";
          await loadMemory();
        } else {
          var d = await r.json().catch(function(){return {};});
          formStatus.textContent = d.detail || "Save failed."; formStatus.className = "run-status err";
        }
      } catch(e) { formStatus.textContent = "Error saving."; formStatus.className = "run-status err"; }
      saveBtn.disabled = false;
    });

    refreshBtn && refreshBtn.addEventListener("click", loadMemory);

    var token = await window.__bootPromise;
    if (!token) { setMemoryEmpty("Sign in to view memory."); return; }
    if (!window.__apiToken) window.__apiToken = token;
    await loadMemory();
  })();

  // ── Task Manager Panel ──────────────────────────────────────────────────────
  (async function () {
    var list       = document.getElementById("tasks-list");
    var countBadge = document.getElementById("tasks-count");
    var tabOpen    = document.getElementById("tasks-tab-open");
    var tabDone    = document.getElementById("tasks-tab-done");
    var newTitle   = document.getElementById("tasks-new-title");
    var addBtn     = document.getElementById("tasks-add-btn");
    if (!list) return;

    var showDone = false;
    var P_LABELS  = ["", "Low", "Med", "High", "Urgent"];
    var P_CLASSES = ["", "p1",  "p2",  "p3",  "p4"];

    var esc = window.PCUI.escapeHtml;

    function setTasksEmpty(text) {
      list.innerHTML = "";
      var el = document.createElement("div");
      el.className = "empty";
      el.textContent = text;
      list.appendChild(el);
    }

    function renderTaskItem(t) {
      var p = Math.max(1, Math.min(4, t.priority || 2));
      var item = document.createElement("div");
      item.className = "item";
      item.id = "task-item-" + t.id;

      var row = document.createElement("div");
      row.style.display = "flex";
      row.style.alignItems = "flex-start";
      row.style.gap = ".55rem";

      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "task-check";
      cb.setAttribute("data-task-id", String(t.id));
      cb.checked = !!t.is_done;
      row.appendChild(cb);

      var content = document.createElement("div");
      content.style.flex = "1";
      content.style.minWidth = "0";

      var title = document.createElement("div");
      title.className = "item-text";
      title.textContent = t.title || "";
      if (t.is_done) {
        title.style.textDecoration = "line-through";
        title.style.color = "var(--text-faint)";
      }
      content.appendChild(title);

      var meta = document.createElement("div");
      meta.className = "item-meta";
      meta.appendChild(document.createTextNode((t.category || "personal") + (t.due_date ? " · due " + t.due_date : "") + " · "));
      var pri = document.createElement("span");
      pri.style.fontSize = ".65rem";
      pri.style.color = p===4 ? "var(--danger)" : p===3 ? "var(--warn)" : p===2 ? "var(--brand)" : "var(--text-faint)";
      pri.textContent = P_LABELS[p];
      meta.appendChild(pri);
      content.appendChild(meta);

      row.appendChild(content);
      item.appendChild(row);
      return item;
    }

    async function loadTasks() {
      var token = window.__apiToken;
      if (!token) { setTasksEmpty("Sign in to view tasks."); return; }
      setTasksEmpty("Loading...");
      try {
        var r = await fetch("/api/v1/tasks?limit=30&is_done=" + showDone, {
          headers: { "Authorization": "Bearer " + token }
        });
        if (!r.ok) { setTasksEmpty("Could not load tasks."); return; }
        var tasks = await r.json();
        if (countBadge) countBadge.textContent = tasks.length + " " + (showDone ? "done" : "open");
        if (!tasks.length) {
          setTasksEmpty("No " + (showDone ? "completed" : "open") + " tasks.");
          return;
        }
        list.innerHTML = "";
        tasks.forEach(function(task) {
          list.appendChild(renderTaskItem(task));
        });
      } catch(e) {
        setTasksEmpty("Error loading tasks.");
      }
    }

    // Event delegation for task checkboxes (CSP-safe, no inline handlers)
    var tasksList = document.getElementById("tasks-list");
    if (tasksList) {
      tasksList.addEventListener("change", function(e) {
        var cb = e.target;
        if (!(cb instanceof HTMLElement)) return;
        if (!cb.classList.contains("task-check") || !cb.dataset.taskId) return;
        var taskId = Number(cb.dataset.taskId);
        if (!Number.isFinite(taskId) || taskId <= 0) return;
        window.taskToggle(taskId, !!cb.checked);
      });
    }

    window.taskToggle = async function(id, isDone) {
      var token = window.__apiToken;
      try {
        var r = await fetch("/api/v1/tasks/" + id, {
          method: "PATCH",
          headers: { "Authorization": "Bearer " + token, "Content-Type": "application/json" },
          body: JSON.stringify({ is_done: isDone })
        });
        if (r.ok) {
          setTimeout(loadTasks, 250);
        } else {
          var d = await r.json().catch(function(){return {};});
          if (window.showToast) window.showToast("Update failed: " + (d.detail || r.status), "error");
          else alert("Update failed: " + (d.detail || r.status));
          await loadTasks();
        }
      } catch(e) {
        if (window.showToast) window.showToast("Network error.", "error");
        else alert("Network error.");
      }
    };

    tabOpen && tabOpen.addEventListener("click", function() {
      showDone = false;
      tabOpen.classList.add("tab-active"); tabDone.classList.remove("tab-active");
      loadTasks();
    });
    tabDone && tabDone.addEventListener("click", function() {
      showDone = true;
      tabDone.classList.add("tab-active"); tabOpen.classList.remove("tab-active");
      loadTasks();
    });

    addBtn && addBtn.addEventListener("click", async function() {
      var title = newTitle ? newTitle.value.trim() : "";
      if (!title) return;
      var token = window.__apiToken;
      addBtn.disabled = true;
      try {
        var r = await fetch("/api/v1/tasks", {
          method: "POST",
          headers: { "Authorization": "Bearer " + token, "Content-Type": "application/json" },
          body: JSON.stringify({ title: title, priority: 2, category: "personal" })
        });
        if (r.ok) {
          newTitle.value = "";
          await loadTasks();
        } else {
          var d = await r.json().catch(function(){return {};});
          if (window.showToast) window.showToast("Create failed: " + (d.detail || r.status), "error");
          else alert("Create failed: " + (d.detail || r.status));
        }
      } catch(e) {
        if (window.showToast) window.showToast("Network error.", "error");
        else alert("Network error.");
      }
      addBtn.disabled = false;
    });

    newTitle && newTitle.addEventListener("keydown", function(e) {
      if (e.key === "Enter") addBtn && addBtn.click();
    });

    // Bootstrap
    var token = await window.__bootPromise;
    if (!token) { setTasksEmpty("Sign in to view tasks."); return; }
    if (!window.__apiToken) window.__apiToken = token;
    await loadTasks();
  })();

window.showToast = function(msg, type) {
    var t = type || "info";
    var el = document.createElement("div");
    el.className = "toast " + t;
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    var span = document.createElement("span");
    span.textContent = String(msg);
    var dismissBtn = document.createElement("button");
    dismissBtn.setAttribute("aria-label", "Dismiss");
    dismissBtn.textContent = "\u00d7";
    dismissBtn.addEventListener("click", function() {
      el.classList.add("removing");
      setTimeout(function() { el.remove(); }, 250);
    });
    el.appendChild(span);
    el.appendChild(dismissBtn);
    var c = document.getElementById("toast-container");
    if (c) c.appendChild(el);
    setTimeout(function() {
      el.classList.add("removing");
      setTimeout(function() { el.remove(); }, 250);
    }, 4000);
  };
  // ── KPI Auto-Refresh (polls every 60s) ──────────────────────────────────
  (function () {
    var KPI_POLL_INTERVAL = 60000;
    var paused = false;

    async function refreshKPIs() {
      if (paused) return;
      try {
        var token = await window.__bootPromise;
        if (!token) return;
        var data = await fetch("/api/v1/dashboard/kpis", {
          headers: { "Authorization": "Bearer " + token },
        }).then(function (r) { return r.ok ? r.json() : null; });
        if (!data) return;

        Object.keys(data).forEach(function (key) {
          var el = document.querySelector("[data-kpi=\"" + key + "\"]");
          if (el && String(el.textContent) !== String(data[key])) {
            el.textContent = data[key];
            el.classList.add("kpi-pulse");
            setTimeout(function () { el.classList.remove("kpi-pulse"); }, 1500);
          }
        });
      } catch (_e) { /* silent */ }
    }

    setInterval(refreshKPIs, KPI_POLL_INTERVAL);

    // Pause when tab hidden, resume when visible
    document.addEventListener("visibilitychange", function () {
      paused = document.hidden;
    });
  })();

  // ── CRM Pipeline Funnel on Dashboard ──────────────────────────────
  (async function () {
    try {
      var token = await window.__bootPromise;
      if (!token) return;
      var authHeaders = { Authorization: "Bearer " + token };

      // Load pipeline summary
      var pipeResp = await fetch("/api/v1/contacts/pipeline-summary", { headers: authHeaders });
      if (pipeResp.ok) {
        var stages = await pipeResp.json();
        var totalVal = 0;
        stages.forEach(function (s) {
          var el = document.getElementById("dash-pf-" + s.stage);
          if (el) el.textContent = String(s.count);
          totalVal += s.total_deal_value || 0;
        });
        var valEl = document.getElementById("dash-pipeline-val");
        if (valEl) valEl.textContent = "$" + totalVal.toLocaleString();
      }

      // Load follow-up due count
      var fuResp = await fetch("/api/v1/contacts/follow-up-due?limit=200", { headers: authHeaders });
      if (fuResp.ok) {
        var duContacts = await fuResp.json();
        var fuEl = document.getElementById("dash-followup-count");
        if (fuEl) fuEl.textContent = String(duContacts.length);
      }
    } catch (_e) { /* silent */ }
  })();

  // Wire topnav search to Ctrl+K palette
  (function () {
    var searchInput = document.querySelector(".topnav-search-input");
    if (searchInput) {
      searchInput.addEventListener("click", function () {
        var overlay = document.getElementById("search-overlay");
        if (overlay) overlay.classList.add("open");
        var paletteInput = document.getElementById("search-input");
        if (paletteInput) paletteInput.focus();
      });
    }
  })();

  // Init Lucide icons
  if (typeof lucide !== "undefined") lucide.createIcons();
