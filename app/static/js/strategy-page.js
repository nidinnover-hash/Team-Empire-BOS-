// ── Strategy Workspace ──────────────────────────────────────────────────────
(function () {
  "use strict";

  var chatLog = document.getElementById("chat-log");
  var input = document.getElementById("message-input");
  var sendBtn = document.getElementById("send-btn");
  var decisionInput = document.getElementById("decision-input");
  var pushDecisionBtn = document.getElementById("push-decision-btn");
  var ruleKey = document.getElementById("rule-key");
  var ruleValue = document.getElementById("rule-value");
  var saveRuleBtn = document.getElementById("save-rule-btn");
  var rulesList = document.getElementById("rules-list");
  var memoryList = document.getElementById("memory-list");
  var promptList = document.getElementById("prompt-list");

  if (!chatLog || !input || !sendBtn) return;

  var getCsrf = window.PCUI && window.PCUI.getCsrfToken ? window.PCUI.getCsrfToken : function () { return ""; };
  var esc = window.PCUI && window.PCUI.escapeHtml ? window.PCUI.escapeHtml : function (s) { return String(s || ""); };

  // ── Show Toast ──────────────────────────────────────────────────────────
  window.showToast = window.showToast || function (msg, type) {
    var t = type || "info";
    var el = document.createElement("div");
    el.className = "toast " + t;
    el.setAttribute("role", "status");
    var span = document.createElement("span");
    span.textContent = String(msg);
    el.appendChild(span);
    var c = document.getElementById("toast-container");
    if (c) c.appendChild(el);
    setTimeout(function () { el.remove(); }, 4000);
  };

  // ── Helpers ─────────────────────────────────────────────────────────────

  function appendMessage(role, text) {
    var div = document.createElement("div");
    if (role === "user") {
      div.className = "strat-msg strat-msg-user";
      div.textContent = text;
    } else {
      div.className = "strat-msg strat-msg-agent";
      var tag = document.createElement("div");
      tag.className = "strat-role-tag";
      tag.textContent = "Strategist";
      div.appendChild(tag);
      var body = document.createElement("div");
      body.innerHTML = esc(text).replace(/\n/g, "<br>");
      div.appendChild(body);
    }
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function renderRules(rules) {
    if (!rulesList) return;
    if (!rules.length) {
      rulesList.innerHTML = '<div class="strategy-list-empty">No rules yet</div>';
      return;
    }
    rulesList.innerHTML = rules.map(function (r) {
      var name = esc(r.key.replace(/^rule\./, ""));
      return '<div class="strategy-list-item"><strong>' + name + ':</strong> ' + esc(r.value) + '</div>';
    }).join("");
  }

  function renderMemories(memories) {
    if (!memoryList) return;
    if (!memories.length) {
      memoryList.innerHTML = '<div class="strategy-list-empty">No strategy memories yet</div>';
      return;
    }
    memoryList.innerHTML = memories.map(function (m) {
      return '<div class="strategy-list-item"><strong>' + esc(m.key) + ':</strong> ' + esc(m.value) + '</div>';
    }).join("");
  }

  function renderPrompts(prompts) {
    if (!promptList) return;
    promptList.innerHTML = prompts.map(function (p) {
      return '<button class="strategy-prompt-chip" type="button">' + esc(p) + '</button>';
    }).join("");
  }

  // ── Bootstrap ───────────────────────────────────────────────────────────

  (async function boot() {
    try {
      var bootRes = await fetch("/web/strategy/bootstrap");
      if (bootRes.ok) {
        var boot = await bootRes.json();
        renderRules(boot.rules || []);
        renderMemories(boot.memories || []);
        renderPrompts(boot.suggested_prompts || []);
      }
    } catch (e) { console.error("Strategy bootstrap failed:", e); }

    try {
      var histRes = await fetch("/web/chat/history?avatar_mode=strategy");
      if (histRes.ok) {
        var hist = await histRes.json();
        hist.forEach(function (m) {
          appendMessage("user", m.user_message);
          appendMessage("agent", m.ai_response);
        });
      }
    } catch (e) { console.error("Strategy history failed:", e); }
  })();

  // ── Send Message ────────────────────────────────────────────────────────

  async function sendMessage() {
    var message = (input.value || "").trim();
    if (!message) return;
    var csrf = getCsrf();
    if (!csrf) {
      window.showToast("Missing CSRF token — try refreshing.", "error");
      return;
    }

    appendMessage("user", message);
    input.value = "";
    sendBtn.disabled = true;

    try {
      var form = new URLSearchParams();
      form.set("message", message);
      form.set("avatar_mode", "strategy");

      var res = await fetch("/web/agents/chat", {
        method: "POST",
        headers: { "X-CSRF-Token": csrf, "Content-Type": "application/x-www-form-urlencoded" },
        body: form.toString(),
      });

      if (!res.ok) {
        var err = await res.json().catch(function () { return {}; });
        appendMessage("agent", "Error: " + (err.detail || "Request failed"));
        return;
      }

      var data = await res.json();
      appendMessage("agent", data.response || "Done.");
    } catch (e) {
      appendMessage("agent", "Network error: " + (e.message || "unknown"));
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  sendBtn.addEventListener("click", sendMessage);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // ── Push Decision ───────────────────────────────────────────────────────

  if (pushDecisionBtn && decisionInput) {
    pushDecisionBtn.addEventListener("click", async function () {
      var decision = (decisionInput.value || "").trim();
      if (!decision) return;
      var csrf = getCsrf();
      if (!csrf) return;

      pushDecisionBtn.disabled = true;
      try {
        var form = new URLSearchParams();
        form.set("decision", decision);
        var res = await fetch("/web/strategy/push-decision", {
          method: "POST",
          headers: { "X-CSRF-Token": csrf, "Content-Type": "application/x-www-form-urlencoded" },
          body: form.toString(),
        });
        if (res.ok) {
          window.showToast("Decision pushed to business agent.", "success");
          decisionInput.value = "";
        } else {
          var err = await res.json().catch(function () { return {}; });
          window.showToast(err.detail || "Failed to push decision.", "error");
        }
      } catch (e) {
        window.showToast("Network error.", "error");
      } finally {
        pushDecisionBtn.disabled = false;
      }
    });
  }

  // ── Save Rule ───────────────────────────────────────────────────────────

  if (saveRuleBtn && ruleKey && ruleValue) {
    saveRuleBtn.addEventListener("click", async function () {
      var key = (ruleKey.value || "").trim();
      var value = (ruleValue.value || "").trim();
      if (!key || !value) return;
      var csrf = getCsrf();
      if (!csrf) return;

      saveRuleBtn.disabled = true;
      try {
        var form = new URLSearchParams();
        form.set("rule_key", key);
        form.set("rule_value", value);
        var res = await fetch("/web/strategy/rules", {
          method: "POST",
          headers: { "X-CSRF-Token": csrf, "Content-Type": "application/x-www-form-urlencoded" },
          body: form.toString(),
        });
        if (res.ok) {
          window.showToast("Rule saved.", "success");
          ruleKey.value = "";
          ruleValue.value = "";
          // Refresh rules
          var bootRes = await fetch("/web/strategy/bootstrap");
          if (bootRes.ok) {
            var boot = await bootRes.json();
            renderRules(boot.rules || []);
          }
        } else {
          var err = await res.json().catch(function () { return {}; });
          window.showToast(err.detail || "Failed to save rule.", "error");
        }
      } catch (e) {
        window.showToast("Network error.", "error");
      } finally {
        saveRuleBtn.disabled = false;
      }
    });
  }

  // ── Suggested Prompt Clicks ─────────────────────────────────────────────

  if (promptList) {
    promptList.addEventListener("click", function (e) {
      var chip = e.target.closest(".strategy-prompt-chip");
      if (!chip) return;
      input.value = chip.textContent;
      input.focus();
    });
  }
})();
