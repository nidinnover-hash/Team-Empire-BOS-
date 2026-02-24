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

        const csrfToken = (document.cookie.split("; ").find((c) => c.startsWith("pc_csrf=")) || "").split("=")[1];
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
          const csrfToken = (document.cookie.split("; ").find((c) => c.startsWith("pc_csrf=")) || "").split("=")[1];
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
    if (!input || !sendBtn || !history) return;

    let selectedRole = "CEO Clone";

    roleBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        roleBtns.forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        selectedRole = btn.dataset.role || "";
        roleDisplay.textContent = selectedRole || "Auto";
      });
    });

    function esc(str) {
      return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function appendNode(html) {
      if (placeholder && placeholder.parentNode) placeholder.remove();
      const wrap = document.createElement("div");
      wrap.innerHTML = html;
      history.appendChild(wrap.firstChild);
      history.scrollTop = history.scrollHeight;
    }

    function getCsrf() {
      const pair = document.cookie.split("; ").find(function (c) { return c.startsWith("pc_csrf="); });
      return pair ? decodeURIComponent(pair.split("=")[1]) : "";
    }

    async function ensureLoggedIn() {
      const res = await fetch("/web/session");
      if (!res.ok) throw new Error("Session check failed");
      const data = await res.json();
      if (data.logged_in) return true;
      window.location.href = "/web/login";
      return false;
    }

    async function send() {
      const message = input.value.trim();
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
      input.value = "";
      sendBtn.disabled = true;

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
                  'onclick="executeAgentAction(' + msgId + ',' + i + ')">' +
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
        }
      } catch (err) {
        appendNode('<div class="chat-msg-agent"><div class="chat-role-tag">Error</div>Could not reach server.</div>');
      } finally {
        sendBtn.disabled = false;
        input.focus();
      }
    }

    // Execute a proposed agent action (TASK_CREATE or MEMORY_WRITE)
    window.executeAgentAction = async function(msgId, idx) {
      var btn = document.getElementById("aa-" + msgId + "-" + idx);
      if (btn) { btn.disabled = true; btn.textContent = "…"; }
      var actions = (window.__agentActions || {})[msgId] || [];
      var action = actions[idx];
      if (!action) { if (btn) { btn.textContent = "Error"; } return; }
      var token = window.__apiToken;
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

    sendBtn.addEventListener("click", send);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send();
    });

    // Load persistent chat history on boot
    (async function bootHistory() {
      try {
        var r = await fetch("/web/chat/history");
        if (!r.ok) return;
        var msgs = await r.json();
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
      } catch(e) {
        if (window.showToast) window.showToast("Failed to load chat history.", "warn");
      }
    })();
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
      return pair ? decodeURIComponent(pair.split("=")[1]) : "";
    }

    function apiHeaders() {
      return { "Content-Type": "application/json", "X-CSRF-Token": getCsrf() };
    }

    function fmt(iso) {
      if (!iso) return "";
      const d = new Date(iso);
      return d.toLocaleDateString("en-US", { month:"short", day:"numeric" }) + " " +
             d.toLocaleTimeString("en-US", { hour:"2-digit", minute:"2-digit" });
    }

    function esc(s) {
      return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    }

    async function loadInbox() {
      list.innerHTML = '<div class="empty">Loading…</div>';
      try {
        const r = await fetch("/api/v1/email/inbox?limit=15&unread_only=false", {
          headers: { "Authorization": "Bearer " + window.__apiToken }
        });
        if (!r.ok) { list.innerHTML = '<div class="empty">Could not load inbox.</div>'; return; }
        const emails = await r.json();
        if (!emails.length) { list.innerHTML = '<div class="empty">No emails synced yet. Click Sync Gmail.</div>'; return; }
        list.innerHTML = emails.map(function(e) {
          return '<div class="inbox-item' + (e.is_read ? "" : " unread") + '" id="email-' + e.id + '">' +
            '<div class="inbox-from">' + esc(e.from_address || "Unknown") + '</div>' +
            '<div class="inbox-subject">' + esc(e.subject || "(no subject)") + '</div>' +
            '<div class="inbox-meta">' + esc(fmt(e.received_at)) + (e.reply_sent ? ' · <span style="color:var(--ok)">replied</span>' : '') + '</div>' +
            (e.ai_summary ? '<div class="inbox-summary">' + esc(e.ai_summary) + '</div>' : '') +
            '<div class="inbox-actions">' +
              (!e.ai_summary ? '<button class="ia-btn ia-summarize" onclick="inboxAction(' + e.id + ',\'summarize\')">Summarize</button>' : '') +
              '<button class="ia-btn ia-strategy" onclick="inboxAction(' + e.id + ',\'strategize\')">Strategy</button>' +
              (!e.draft_reply ? '<button class="ia-btn ia-draft" onclick="inboxAction(' + e.id + ',\'draft\')">Draft Reply</button>' : '<button class="ia-btn ia-draft" onclick="inboxAction(' + e.id + ',\'draft\')">Re-draft</button>') +
            '</div>' +
            (e.draft_reply ? '<div class="inbox-draft" id="draft-' + e.id + '">' + esc(e.draft_reply) + '</div>' : '') +
          '</div>';
        }).join("");
      } catch(err) {
        list.innerHTML = '<div class="empty">Error loading inbox.</div>';
      }
    }

    // Expose globally so inline onclick works
    window.inboxAction = async function(emailId, action) {
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

    function esc(s) { return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

    function fmtPayload(p) {
      var parts = [];
      if (p.to)      parts.push("<strong>To:</strong> " + esc(p.to));
      if (p.subject) parts.push("<strong>Subject:</strong> " + esc(p.subject));
      if (p.body && typeof p.body === "string")
        parts.push("<strong>Preview:</strong> " + esc(p.body.slice(0,140)) + (p.body.length > 140 ? "…" : ""));
      if (!parts.length) {
        Object.keys(p).slice(0,4).forEach(function(k) {
          if (k !== "approval_type")
            parts.push("<strong>" + esc(k) + ":</strong> " + esc(String(p[k]).slice(0,80)));
        });
      }
      return parts.join("<br>");
    }

    async function loadApprovals() {
      var token = window.__apiToken;
      if (!token) { list.innerHTML = '<div class="empty">Sign in to see approvals.</div>'; return; }
      list.innerHTML = '<div class="empty">Loading…</div>';
      try {
        var r = await fetch("/api/v1/approvals?status=pending", { headers:{"Authorization":"Bearer "+token} });
        if (!r.ok) { list.innerHTML = '<div class="empty">Could not load approvals.</div>'; return; }
        var items = await r.json();
        if (countBadge) countBadge.textContent = items.length + " pending";
        if (!items.length) {
          list.innerHTML = '<div class="empty" style="color:var(--ok)">No pending approvals — all clear.</div>';
          return;
        }
        list.innerHTML = items.map(function(a) {
          var risky   = RISKY.has(a.approval_type);
          var payload = a.payload_json || {};
          var ts = new Date(a.created_at).toLocaleString("en-US",{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"});
          return '<div class="ap-item" id="ap-' + a.id + '">' +
            '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:.5rem">' +
              '<span class="ap-type ' + (risky ? "risky" : "safe") + '">' +
                esc(a.approval_type) + (risky ? " ⚠" : "") +
              '</span>' +
              '<span class="ap-meta">#' + a.id + ' · ' + ts + '</span>' +
            '</div>' +
            (Object.keys(payload).length ? '<div class="ap-payload">' + fmtPayload(payload) + '</div>' : '') +
            '<div class="ap-actions">' +
              (risky
                ? '<button class="btn-execute" onclick="approvalAction(' + a.id + ',true)">Approve &amp; Send ⚡</button>'
                : '<button class="btn-approve" onclick="approvalAction(' + a.id + ',false)">Approve</button>'
              ) +
              '<button class="btn-reject" onclick="approvalReject(' + a.id + ')">Reject</button>' +
            '</div>' +
          '</div>';
        }).join("");
      } catch(e) {
        list.innerHTML = '<div class="empty">Error loading approvals.</div>';
      }
    }

    window.approvalAction = async function(id, isRisky) {
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

    window.approvalReject = async function(id) {
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
      if (!token) { list.innerHTML = '<div class="empty">Sign in to see approvals.</div>'; return; }
      if (!window.__apiToken) window.__apiToken = token;
      await loadApprovals();
    })();

    // Auto-refresh every 60 seconds
    setInterval(function() { if (window.__apiToken) loadApprovals(); }, 60000);
  })();

  // ── Audit Log Panel ─────────────────────────────────────────────────────────
  (async function () {
    var list       = document.getElementById("audit-list");
    var countBadge = document.getElementById("audit-count");
    var refreshBtn = document.getElementById("audit-refresh-btn");
    if (!list) return;

    function esc(s) { return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

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

    async function loadAudit() {
      var token = window.__apiToken;
      if (!token) { list.innerHTML = '<div class="empty">Sign in to view activity.</div>'; return; }
      try {
        var r = await fetch("/api/v1/ops/events?limit=40", { headers:{"Authorization":"Bearer "+token} });
        if (!r.ok) { list.innerHTML = '<div class="empty">Could not load activity log.</div>'; return; }
        var events = await r.json();
        if (countBadge) countBadge.textContent = events.length + " events";
        if (!events.length) { list.innerHTML = '<div class="empty">No activity logged yet.</div>'; return; }
        list.innerHTML = events.map(function(e) {
          var detail = fmtDetail(e);
          return '<div class="audit-row">' +
            '<div class="audit-dot ' + dotClass(e.event_type) + '"></div>' +
            '<div style="flex:1;min-width:0">' +
              '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:.5rem">' +
                '<span class="audit-type">' + esc(e.event_type) + '</span>' +
                '<span class="audit-time">' + esc(fmt(e.created_at)) + '</span>' +
              '</div>' +
              (detail ? '<div class="audit-detail">' + esc(detail) + '</div>' : '') +
            '</div>' +
          '</div>';
        }).join("");
      } catch(err) {
        list.innerHTML = '<div class="empty">Error loading activity log.</div>';
      }
    }

    refreshBtn && refreshBtn.addEventListener("click", loadAudit);

    // Bootstrap: wait for shared auth, then load
    var token = await window.__bootPromise;
    if (!token) { list.innerHTML = '<div class="empty">Sign in to view activity.</div>'; return; }
    if (!window.__apiToken) window.__apiToken = token;
    await loadAudit();

    // Auto-refresh every 30 seconds
    setInterval(function() { if (window.__apiToken) loadAudit(); }, 30000);
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

    function esc(s) { return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

    async function loadMemory() {
      var token = window.__apiToken;
      if (!token) { list.innerHTML = '<div class="empty">Sign in to view memory.</div>'; return; }
      try {
        var r = await fetch("/api/v1/memory/profile", { headers:{"Authorization":"Bearer "+token} });
        if (!r.ok) { list.innerHTML = '<div class="empty">Could not load memory (CEO role required).</div>'; return; }
        var entries = await r.json();
        if (countBadge) countBadge.textContent = entries.length + " entries";
        if (!entries.length) { list.innerHTML = '<div class="empty">No memory entries yet. Click + Add to create one.</div>'; return; }
        list.innerHTML = entries.map(function(m) {
          return '<div class="mem-row" id="mem-entry-' + m.id + '">' +
            '<div style="flex:1;min-width:0">' +
              '<div style="display:flex;align-items:baseline;gap:.4rem">' +
                '<span class="mem-key">' + esc(m.key) + '</span>' +
                (m.category ? '<span class="mem-cat">[' + esc(m.category) + ']</span>' : '') +
              '</div>' +
              '<div class="mem-val">' + esc(m.value) + '</div>' +
            '</div>' +
            '<button class="btn-mem-del" title="Delete entry" onclick="memoryDelete(' + m.id + ')">✕</button>' +
          '</div>';
        }).join("");
      } catch(err) {
        list.innerHTML = '<div class="empty">Error loading memory.</div>';
      }
    }

    window.memoryDelete = async function(id) {
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
    if (!token) { list.innerHTML = '<div class="empty">Sign in to view memory.</div>'; return; }
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

    function esc(s) { return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

    async function loadTasks() {
      var token = window.__apiToken;
      if (!token) { list.innerHTML = '<div class="empty">Sign in to view tasks.</div>'; return; }
      list.innerHTML = '<div class="empty">Loading…</div>';
      try {
        var r = await fetch("/api/v1/tasks?limit=30&is_done=" + showDone, {
          headers: { "Authorization": "Bearer " + token }
        });
        if (!r.ok) { list.innerHTML = '<div class="empty">Could not load tasks.</div>'; return; }
        var tasks = await r.json();
        if (countBadge) countBadge.textContent = tasks.length + " " + (showDone ? "done" : "open");
        if (!tasks.length) {
          list.innerHTML = '<div class="empty">No ' + (showDone ? "completed" : "open") + ' tasks.</div>';
          return;
        }
        list.innerHTML = tasks.map(function(t) {
          var p = Math.max(1, Math.min(4, t.priority || 2));
          return '<div class="item" id="task-item-' + t.id + '">' +
            '<div style="display:flex;align-items:flex-start;gap:.55rem">' +
              '<input type="checkbox" class="task-check" ' + (t.is_done ? "checked" : "") + ' ' +
                'onchange="taskToggle(' + t.id + ',this.checked)" />' +
              '<div style="flex:1;min-width:0">' +
                '<div class="item-text" style="' + (t.is_done ? "text-decoration:line-through;color:var(--text-faint)" : "") + '">' +
                  esc(t.title) +
                '</div>' +
                '<div class="item-meta">' +
                  esc(t.category || "personal") +
                  (t.due_date ? " · due " + esc(t.due_date) : "") +
                  ' · <span style="color:' + (p===4?"var(--danger)":p===3?"var(--warn)":p===2?"var(--brand)":"var(--text-faint)") + ';font-size:.65rem">' + P_LABELS[p] + '</span>' +
                '</div>' +
              '</div>' +
            '</div>' +
          '</div>';
        }).join("");
      } catch(e) {
        list.innerHTML = '<div class="empty">Error loading tasks.</div>';
      }
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
    if (!token) { list.innerHTML = '<div class="empty">Sign in to view tasks.</div>'; return; }
    if (!window.__apiToken) window.__apiToken = token;
    await loadTasks();
  })();

window.showToast = function(msg, type) {
    var t = type || "info";
    var el = document.createElement("div");
    el.className = "toast toast-" + t;
    el.innerHTML = "<span>" + String(msg).replace(/</g,"&lt;") + "</span>" +
      "<button onclick=\"this.parentNode.remove()\">\u00d7</button>";
    var c = document.getElementById("toast-container");
    if (c) c.appendChild(el);
    setTimeout(function() {
      el.classList.add("toast-hide");
      setTimeout(function() { el.remove(); }, 400);
    }, 4000);
  };
  // Init Lucide icons
  if (typeof lucide !== "undefined") lucide.createIcons();
