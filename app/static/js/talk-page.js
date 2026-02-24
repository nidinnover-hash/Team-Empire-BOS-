(async function () {
    var chatLog = document.getElementById("chat-log");
    var input = document.getElementById("message-input");
    var sendBtn = document.getElementById("send-btn");
    var micBtn = document.getElementById("mic-btn");
    var logoutBtn = document.getElementById("logout-btn");
    var statusEl = document.getElementById("status");
    var apiToken = null;
    var csrfToken = null;
    var isMicOn = false;
    var recognition = null;

    function esc(s) {
      return String(s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }
    function setStatus(text, cls) {
      statusEl.textContent = text || "";
      statusEl.className = cls ? cls : "";
    }
    function mapUiError(err) {
      if (window.PCUI && window.PCUI.mapApiError) return window.PCUI.mapApiError(err);
      return String((err && err.message) || err || "Request failed");
    }
    function notifyError(msg) {
      if (window.showToast) window.showToast(msg, "error");
      else alert(msg);
    }
    function appendMessage(role, text) {
      var div = document.createElement("div");
      div.className = "msg " + (role === "user" ? "user" : "clone");
      div.innerHTML = '<span class="tag">' + (role === "user" ? "You" : "Clone") + "</span>" + esc(text);
      chatLog.appendChild(div);
      chatLog.scrollTop = chatLog.scrollHeight;
    }
    function getCsrfToken() {
      var pair = document.cookie.split("; ").find(function (c) { return c.startsWith("pc_csrf="); });
      return pair ? decodeURIComponent(pair.split("=")[1] || "") : null;
    }
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

    async function loadHistoryOrWelcome() {
      var history = await fetch("/web/chat/history").then(function (r) {
        if (!r.ok) throw new Error("Failed to load chat history");
        return r.json();
      });
      if (Array.isArray(history) && history.length) {
        history.forEach(function (m) {
          if (m.user_message) appendMessage("user", m.user_message);
          if (m.ai_response) appendMessage("clone", m.ai_response);
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
      renderPrompts(bootstrap.suggested_prompts || []);
      if (!chatLog.children.length && bootstrap.welcome) {
        appendMessage("clone", bootstrap.welcome);
      }
      setStatus("Clone is online and synced with your work.", "ok");
    }

    async function sendMessage() {
      var message = (input.value || "").trim();
      if (!message) return;
      if (!csrfToken) {
        setStatus("Missing CSRF token. Refresh and sign in again.", "err");
        return;
      }
      appendMessage("user", message);
      input.value = "";
      if (window.PCUI && window.PCUI.setButtonLoading) window.PCUI.setButtonLoading(sendBtn, true, "Sending...");
      else sendBtn.disabled = true;
      setStatus("Clone is thinking...");

      try {
        var form = new FormData();
        form.set("message", message);
        var r = await fetch("/web/agents/chat", {
          method: "POST",
          headers: { "X-CSRF-Token": csrfToken },
          body: form
        });
        var body = await r.json().catch(function () { return {}; });
        if (!r.ok) throw new Error(body.detail || "Chat request failed");
        appendMessage("clone", body.response || "Done.");
        setStatus(body.requires_approval ? "Reply generated. Some actions require approval." : "Reply ready.", "ok");
      } catch (err) {
        appendMessage("clone", "I hit an error while processing that. Please try again.");
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
          input.value = final_.trim();
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
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
    logoutBtn.addEventListener("click", async function () {
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
      csrfToken = getCsrfToken();
      setupSpeech();
      await loadApiToken();
      await loadHistoryOrWelcome();
      await loadBootstrap();
    } catch (e) {
      setStatus(mapUiError(e) || "Failed to initialize Talk Mode", "err");
      notifyError(mapUiError(e) || "Failed to initialize Talk Mode");
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
