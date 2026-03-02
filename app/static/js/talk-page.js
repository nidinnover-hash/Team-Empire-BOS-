function getCookie(name) {
    var key = name + "=";
    var parts = document.cookie.split("; ");
    for (var i = 0; i < parts.length; i++) {
      if (parts[i].indexOf(key) === 0) return decodeURIComponent(parts[i].slice(key.length));
    }
    return "";
  }
  var modePrompts = {
    professional: [
      "Prioritize my top 3 CEO tasks for today.",
      "Show integration status and biggest operational risk.",
      "Draft a strict execution plan for my team."
    ],
    personal: [
      "Help me plan a balanced day with focus and recovery.",
      "Give me a calm and clear priority reset for today.",
      "Coach me to communicate with more empathy and clarity."
    ],
    entertainment: [
      "Create 5 viral reel hooks for study abroad promotions.",
      "Write a 30-second high-energy script for Instagram.",
      "Give me a fun content calendar for 7 days."
    ]
  };
  var modeFocusCopy = {
    professional: "Professional mode: strategy, execution, approvals, and KPIs.",
    personal: "Personal mode: wellbeing, growth, relationships, and self-coaching.",
    entertainment: "Entertainment mode: creative ideas for YouTube/Audible only."
  };
(async function () {
    var chatLog = document.getElementById("chat-log");
    var input = document.getElementById("message-input");
    var sendBtn = document.getElementById("send-btn");
    var micBtn = document.getElementById("mic-btn");
    var logoutBtn = document.getElementById("logout-btn");
    var statusEl = document.getElementById("status");
    var professionalAvatarBtn = document.getElementById("avatar-professional-btn");
    var personalAvatarBtn = document.getElementById("avatar-personal-btn");
    var entertainmentAvatarBtn = document.getElementById("avatar-entertainment-btn");
    var modeFocusCopyEl = document.getElementById("mode-focus-copy");
    var providerSelect = document.getElementById("provider-select");
    var modelSelect = document.getElementById("model-select");
    var streamToggle = document.getElementById("stream-toggle");
    var apiToken = null;
    var csrfToken = null;
    var avatarMode = "professional";
    var loginPurpose = "professional";
    var isMicOn = false;
    var recognition = null;
    var aiModelsCache = null;

    var esc = window.PCUI.escapeHtml;
    function setStatus(text, cls) {
      statusEl.textContent = text || "";
      statusEl.className = cls ? cls : "";
    }
    function renderAvatarMode() {
      if (avatarMode !== "professional" && avatarMode !== "personal" && avatarMode !== "entertainment") {
        avatarMode = "professional";
      }
      if (professionalAvatarBtn) professionalAvatarBtn.classList.toggle("active", avatarMode === "professional");
      if (personalAvatarBtn) personalAvatarBtn.classList.toggle("active", avatarMode === "personal");
      if (entertainmentAvatarBtn) entertainmentAvatarBtn.classList.toggle("active", avatarMode === "entertainment");
      if (modeFocusCopyEl) modeFocusCopyEl.textContent = modeFocusCopy[avatarMode] || modeFocusCopy.professional;
      renderPrompts(modePrompts[avatarMode] || []);
    }

    function enforcePurposeBarrier() {
      if (loginPurpose !== "professional" && loginPurpose !== "personal" && loginPurpose !== "entertainment") return;
      if (loginPurpose === "professional") {
        avatarMode = "professional";
        if (professionalAvatarBtn) professionalAvatarBtn.disabled = false;
        if (personalAvatarBtn) personalAvatarBtn.disabled = true;
        if (entertainmentAvatarBtn) entertainmentAvatarBtn.disabled = true;
        return;
      }
      if (loginPurpose === "entertainment") {
        avatarMode = "entertainment";
        if (professionalAvatarBtn) professionalAvatarBtn.disabled = true;
        if (personalAvatarBtn) personalAvatarBtn.disabled = true;
        if (entertainmentAvatarBtn) entertainmentAvatarBtn.disabled = false;
        return;
      }
      // personal login: can view personal + professional lane, but not entertainment lane.
      if (avatarMode !== "personal" && avatarMode !== "professional") avatarMode = "personal";
      if (professionalAvatarBtn) professionalAvatarBtn.disabled = false;
      if (personalAvatarBtn) personalAvatarBtn.disabled = false;
      if (entertainmentAvatarBtn) entertainmentAvatarBtn.disabled = true;
    }
    var mapUiError = window.PCUI.mapApiError;
    function notifyError(msg) {
      if (window.showToast) window.showToast(msg, "error");
      else alert(msg);
    }
    function appendMessage(role, text, meta) {
      var div = document.createElement("div");
      div.className = "msg " + (role === "user" ? "user" : "agent");
      var html = '<span class="tag">' + (role === "user" ? "You" : "Agent") + "</span>" + esc(text);
      if (meta) {
        var badges = [];
        if (meta.confidence_level) {
          var cCls = meta.confidence_level === "high" ? "badge-ok" : meta.confidence_level === "low" ? "badge-warn" : "badge-info";
          badges.push('<span class="chat-badge ' + cCls + '">Confidence: ' + esc(meta.confidence_score) + ' (' + esc(meta.confidence_level) + ')</span>');
        }
        if (meta.policy_score !== undefined) {
          badges.push('<span class="chat-badge badge-info">Policy: ' + esc(meta.policy_score) + '</span>');
        }
        if (meta.blocked_by_policy) {
          badges.push('<span class="chat-badge badge-warn">Blocked by policy</span>');
        }
        if (meta.needs_human_review) {
          badges.push('<span class="chat-badge badge-warn">Needs review</span>');
        }
        if (meta.proposed_actions && meta.proposed_actions.length) {
          var actionLabels = meta.proposed_actions.map(function (a) { return esc(a.action_type); }).join(", ");
          badges.push('<span class="chat-badge badge-info">Actions: ' + actionLabels + '</span>');
        }
        if (badges.length) {
          html += '<div class="chat-meta">' + badges.join(" ") + '</div>';
        }
      }
      div.innerHTML = html;
      chatLog.appendChild(div);
      chatLog.scrollTop = chatLog.scrollHeight;
    }
    var getCsrfToken = window.PCUI.getCsrfToken;
    function renderTasks(tasks) {
      var root = document.getElementById("top-tasks");
      if (!tasks || !tasks.length) {
        root.innerHTML = '<div class="item">No open tasks yet.</div>';
        return;
      }
      root.innerHTML = tasks.map(function (t) {
        return (
          '<div class="item">' +
            esc(t.title || "Untitled task") +
            '<small>Priority ' + esc(t.priority || 2) + '</small>' +
          "</div>"
        );
      }).join("");
    }
    function renderPrompts(prompts) {
      var root = document.getElementById("prompt-list");
      if (!prompts || !prompts.length) {
        root.innerHTML = '<div class="item">No suggestions available.</div>';
        return;
      }
      root.innerHTML = prompts.map(function (p) {
        return '<button class="btn" type="button" style="text-align:left" data-prompt="' + esc(p) + '">' + esc(p) + "</button>";
      }).join("");
      Array.from(root.querySelectorAll("button[data-prompt]")).forEach(function (btn) {
        btn.addEventListener("click", function () {
          input.value = btn.getAttribute("data-prompt") || "";
          input.focus();
        });
      });
    }

    function renderLearned(items) {
      var root = document.getElementById("learned-list");
      if (!items || !items.length) {
        root.innerHTML = '<div class="item">No learned preferences yet.</div>';
        return;
      }
      root.innerHTML = items.map(function (m) {
        return (
          '<div class="item" id="learned-' + esc(m.id) + '">' +
            '<strong>' + esc(m.key || "preference") + "</strong>" +
            '<small>' + esc(m.value || "") + "</small>" +
            '<button class="btn" type="button" data-forget="' + esc(m.id) + '" style="margin-top:.35rem">Forget</button>' +
          "</div>"
        );
      }).join("");
      Array.from(root.querySelectorAll("button[data-forget]")).forEach(function (btn) {
        btn.addEventListener("click", async function () {
          var id = btn.getAttribute("data-forget");
          if (!id) return;
          if (!apiToken) {
            setStatus("Missing API token for forget action.", "err");
            return;
          }
          if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, true, "Forgetting...");
          else btn.disabled = true;
          try {
            var r = await fetch("/api/v1/memory/profile/" + encodeURIComponent(id), {
              method: "DELETE",
              headers: { "Authorization": "Bearer " + apiToken }
            });
            if (!r.ok && r.status !== 204) throw new Error("Could not remove learned memory");
            var row = document.getElementById("learned-" + id);
            if (row) row.remove();
            if (!root.children.length) {
              root.innerHTML = '<div class="item">No learned preferences yet.</div>';
            }
            setStatus("Learned item removed.", "ok");
          } catch (err) {
            setStatus(mapUiError(err), "err");
          } finally {
            if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(btn, false);
            else btn.disabled = false;
          }
        });
      });
    }

    async function loadApiToken() {
      try {
        var r = await fetch("/web/api-token");
        if (!r.ok) return;
        var data = await r.json();
        apiToken = data.token || null;
      } catch (_e) {
        apiToken = null;
      }
    }

    async function loadAiModels() {
      if (!apiToken) return;
      try {
        var r = await fetch("/api/v1/ai/models", { headers: { "Authorization": "Bearer " + apiToken } });
        if (!r.ok) return;
        aiModelsCache = await r.json();
        updateModelDropdown();
      } catch (_e) { /* ignore */ }
    }

    function updateModelDropdown() {
      if (!modelSelect || !aiModelsCache) return;
      var provider = (providerSelect ? providerSelect.value : "") || "";
      modelSelect.innerHTML = '<option value="">Default Model</option>';
      if (!provider) return;
      var entry = aiModelsCache.find(function (e) { return e.provider === provider; });
      if (!entry || !entry.configured) return;
      entry.models.forEach(function (m) {
        var opt = document.createElement("option");
        opt.value = m;
        opt.textContent = m + (m === entry.default_model ? " (default)" : "");
        modelSelect.appendChild(opt);
      });
    }

    if (providerSelect) {
      providerSelect.addEventListener("change", function () {
        updateModelDropdown();
        localStorage.setItem("pc_ai_provider", providerSelect.value);
      });
      var savedProvider = localStorage.getItem("pc_ai_provider") || "";
      if (savedProvider) providerSelect.value = savedProvider;
    }

    async function sendStreamingMessage(message) {
      if (!apiToken) {
        setStatus("Missing API token. Refresh and sign in again.", "err");
        return;
      }
      var provider = (providerSelect ? providerSelect.value : "") || undefined;
      var model = (modelSelect ? modelSelect.value : "") || undefined;

      var div = document.createElement("div");
      div.className = "msg agent";
      div.innerHTML = '<span class="tag">Agent</span>';
      var textNode = document.createTextNode("");
      div.appendChild(textNode);
      chatLog.appendChild(div);

      try {
        var r = await fetch("/api/v1/ai/chat", {
          method: "POST",
          headers: { "Authorization": "Bearer " + apiToken, "Content-Type": "application/json" },
          body: JSON.stringify({
            message: message,
            provider: provider,
            model: model,
            stream: true,
            max_tokens: 2048,
          }),
        });
        if (!r.ok) {
          var err = await r.json().catch(function () { return {}; });
          throw new Error(err.detail || "Streaming request failed");
        }
        var reader = r.body.getReader();
        var decoder = new TextDecoder();
        var fullText = "";
        while (true) {
          var result = reader.read ? await reader.read() : { done: true };
          if (result.done) break;
          var chunk = decoder.decode(result.value, { stream: true });
          var lines = chunk.split("\n");
          for (var li = 0; li < lines.length; li++) {
            var line = lines[li];
            if (line.indexOf("data: ") !== 0) continue;
            var payload = line.slice(6).trim();
            if (payload === "[DONE]") continue;
            try {
              var parsed = JSON.parse(payload);
              if (parsed.text) {
                fullText += parsed.text;
                textNode.textContent = fullText;
                chatLog.scrollTop = chatLog.scrollHeight;
              }
            } catch (_pe) { /* ignore parse errors */ }
          }
        }
        if (!fullText) textNode.textContent = "(No response)";
        setStatus("Streamed from " + (provider || "default") + ".", "ok");
      } catch (err) {
        textNode.textContent = "Error: " + (err.message || "Streaming failed");
        setStatus(mapUiError(err), "err");
      }
    }

    async function loadHistoryOrWelcome() {
      var history = await fetch("/web/chat/history?avatar_mode=" + encodeURIComponent(avatarMode)).then(function (r) {
        if (!r.ok) throw new Error("Failed to load chat history");
        return r.json();
      });
      if (Array.isArray(history) && history.length) {
        history.forEach(function (m) {
          if (m.user_message) appendMessage("user", m.user_message);
          if (m.ai_response) appendMessage("agent", m.ai_response);
        });
      }
    }

    async function loadBootstrap() {
      var bootstrap = await fetch("/web/talk/bootstrap").then(function (r) {
        if (!r.ok) throw new Error("Failed to load talk bootstrap data");
        return r.json();
      });
      var s = bootstrap.snapshot || {};
      document.getElementById("kpi-tasks").textContent = String(s.open_tasks || 0);
      document.getElementById("kpi-approvals").textContent = String(s.pending_approvals || 0);
      document.getElementById("kpi-emails").textContent = String(s.unread_emails || 0);
      renderTasks(s.tasks || []);
      renderLearned(bootstrap.learned_memory || []);
      if (!modePrompts[avatarMode] || !modePrompts[avatarMode].length) {
        renderPrompts(bootstrap.suggested_prompts || []);
      }
      if (!chatLog.children.length && bootstrap.welcome) {
        appendMessage("agent", bootstrap.welcome);
      }
      setStatus("Agent is online and synced with your work.", "ok");
    }

    async function sendMessage() {
      var message = (input.value || "").trim();
      if (!message) return;
      var useStreaming = streamToggle && streamToggle.checked && apiToken && (providerSelect && providerSelect.value);
      if (!useStreaming && !csrfToken) {
        setStatus("Missing CSRF token. Refresh and sign in again.", "err");
        return;
      }
      appendMessage("user", message);
      input.value = "";
      if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(sendBtn, true, "Sending...");
      else sendBtn.disabled = true;
      setStatus(useStreaming ? "Streaming..." : "Agent is thinking...");

      try {
        if (useStreaming) {
          await sendStreamingMessage(message);
        } else {
          var form = new FormData();
          form.set("message", message);
          form.set("avatar_mode", avatarMode);
          var r = await fetch("/web/agents/chat", {
            method: "POST",
            headers: { "X-CSRF-Token": csrfToken },
            body: form
          });
          var body = await r.json().catch(function () { return {}; });
          if (!r.ok) throw new Error(body.detail || "Chat request failed");
          appendMessage("agent", body.response || "Done.", {
            confidence_score: body.confidence_score,
            confidence_level: body.confidence_level,
            needs_human_review: body.needs_human_review,
            policy_score: body.policy_score,
            blocked_by_policy: body.blocked_by_policy,
            proposed_actions: body.proposed_actions,
          });
          var statusMsg = "Reply ready.";
          if (body.blocked_by_policy) statusMsg = "Response blocked by policy.";
          else if (body.requires_approval) statusMsg = "Reply generated. Some actions require approval.";
          else if (body.needs_human_review) statusMsg = "Reply generated. Human review recommended.";
          setStatus(statusMsg, body.blocked_by_policy ? "err" : "ok");
        }
      } catch (err) {
        appendMessage("agent", "I hit an error while processing that. Please try again.");
        setStatus(mapUiError(err), "err");
      } finally {
        if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(sendBtn, false);
        else sendBtn.disabled = false;
      }
    }

    function setupSpeech() {
      var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      var interimEl = document.getElementById("interim-display");
      if (!SR) {
        micBtn.disabled = true;
        micBtn.textContent = "Mic N/A";
        return;
      }
      recognition = new SR();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      var autoSendTimer = null;

      recognition.onresult = function (event) {
        var interim = "";
        var final_ = "";
        for (var i = event.resultIndex; i < event.results.length; i++) {
          var t = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            final_ += t;
          } else {
            interim += t;
          }
        }
        // Show interim text in faded display
        if (interimEl) interimEl.textContent = interim;
        if (final_) {
          input.value = (input.value + " " + final_).trim();
          if (interimEl) interimEl.textContent = "";
          // Auto-send after 1.5s of silence following a final result
          clearTimeout(autoSendTimer);
          autoSendTimer = setTimeout(function () {
            if (input.value.trim()) {
              sendMessage();
              if (interimEl) interimEl.textContent = "";
            }
          }, 1500);
        }
      };
      recognition.onend = function () {
        if (isMicOn) recognition.start();
      };
      micBtn.addEventListener("click", function () {
        isMicOn = !isMicOn;
        if (isMicOn) {
          micBtn.textContent = "Stop Mic";
          micBtn.classList.add("stop");
          micBtn.classList.add("mic-active");
          recognition.start();
          setStatus("Voice input active — speak naturally, auto-sends after pause.");
        } else {
          micBtn.textContent = "Start Mic";
          micBtn.classList.remove("stop");
          micBtn.classList.remove("mic-active");
          recognition.stop();
          clearTimeout(autoSendTimer);
          if (interimEl) interimEl.textContent = "";
          setStatus("Voice input stopped.");
        }
      });
    }

    sendBtn.addEventListener("click", sendMessage);
    async function switchAvatar(mode, label) {
      avatarMode = mode;
      localStorage.setItem("pc_avatar_mode:" + (getCookie("pc_theme_scope") || "professional"), avatarMode);
      renderAvatarMode();
      chatLog.innerHTML = "";
      try {
        await loadHistoryOrWelcome();
        setStatus(label + " avatar active.", "ok");
      } catch (err) {
        setStatus("Failed to load history: " + String(err.message || err), "err");
      }
    }
    if (professionalAvatarBtn) {
      professionalAvatarBtn.addEventListener("click", function () { switchAvatar("professional", "Professional"); });
    }
    if (personalAvatarBtn) {
      personalAvatarBtn.addEventListener("click", function () { switchAvatar("personal", "Personal"); });
    }
    if (entertainmentAvatarBtn) {
      entertainmentAvatarBtn.addEventListener("click", function () { switchAvatar("entertainment", "Entertainment"); });
    }
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
    if (logoutBtn) logoutBtn.addEventListener("click", async function () {
      if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(logoutBtn, true, "Signing out...");
      try {
        var r = await fetch("/web/logout", {
          method: "POST",
          headers: csrfToken ? { "X-CSRF-Token": csrfToken } : {}
        });
        if (!r.ok) throw new Error("Logout failed");
        window.location.href = "/web/login";
      } catch (e) {
        notifyError(mapUiError(e));
      } finally {
        if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(logoutBtn, false);
      }
    });

    try {
      var scope = getCookie("pc_theme_scope") || "professional";
      loginPurpose = scope;
      var fallbackAvatar = getCookie("pc_avatar_default") || "professional";
      avatarMode = localStorage.getItem("pc_avatar_mode:" + scope) || fallbackAvatar;
      csrfToken = getCsrfToken();
      enforcePurposeBarrier();
      renderAvatarMode();
      setupSpeech();
      await loadApiToken();
      await loadAiModels();
      await loadHistoryOrWelcome();
      await loadBootstrap();
    } catch (e) {
      setStatus(mapUiError(e) || "Failed to initialize Agent Chat", "err");
      notifyError(mapUiError(e) || "Failed to initialize Agent Chat");
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

