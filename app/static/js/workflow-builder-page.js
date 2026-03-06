(function () {
  function byId(id) { return document.getElementById(id); }
  function esc(s) { return window.PCUI ? window.PCUI.escapeHtml(s) : String(s); }
  var stepCount = 0;
  var apiJson = null;

  function buildStepRow(step) {
    stepCount += 1;
    return '' +
      '<div class="builder-step" data-step-row="' + stepCount + '">' +
        '<div class="builder-step-head">' +
          '<strong>Step ' + stepCount + '</strong>' +
          '<button class="btn-danger" type="button" data-remove-step="' + stepCount + '">Remove</button>' +
        '</div>' +
        '<div class="builder-grid">' +
          '<label>Name<input type="text" data-step-name value="' + esc(step.name || '') + '" maxlength="200" /></label>' +
          '<label>Action Type<input type="text" data-step-action value="' + esc(step.action_type || '') + '" maxlength="100" /></label>' +
        '</div>' +
        '<label>Params JSON<textarea data-step-params rows="2">' + esc(JSON.stringify(step.params || {}, null, 2)) + '</textarea></label>' +
        '<label><input type="checkbox" data-step-approval ' + (step.requires_approval ? 'checked' : '') + ' /> Requires approval</label>' +
      '</div>';
  }

  function renderInitialStep() {
    var container = byId("builder-steps");
    if (!container || container.children.length) return;
    container.innerHTML = buildStepRow({ name: "Collect context", action_type: "fetch_calendar_digest", params: {}, requires_approval: false });
    bindStepActions();
  }

  function bindStepActions() {
    document.querySelectorAll("[data-remove-step]").forEach(function (btn) {
      btn.onclick = function () {
        var row = btn.closest("[data-step-row]");
        if (row) row.remove();
      };
    });
  }

  function collectSteps() {
    return Array.prototype.map.call(document.querySelectorAll("[data-step-row]"), function (row) {
      var paramsText = row.querySelector("[data-step-params]").value || "{}";
      return {
        name: row.querySelector("[data-step-name]").value.trim(),
        action_type: row.querySelector("[data-step-action]").value.trim(),
        params: JSON.parse(paramsText),
        requires_approval: row.querySelector("[data-step-approval]").checked,
      };
    });
  }

  async function onPreview() {
    var output = byId("builder-preview-output");
    try {
      var steps = collectSteps();
      var createResp = await apiJson("/api/v1/automations/workflow-definitions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: byId("builder-name").value.trim(),
          description: byId("builder-description").value.trim() || null,
          trigger_mode: byId("builder-trigger-mode").value,
          steps: steps,
        }),
      });
      var preview = await apiJson("/api/v1/automations/workflow-definitions/" + createResp.id + "/run-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input_json: {} }),
      });
      output.innerHTML = '<strong>Preview</strong><div class="step-chip-row">' +
        preview.step_plans.map(function (step) {
          return '<span class="step-chip">' + esc(step.action_type + " → " + step.decision) + '</span>';
        }).join("") +
        '</div>';
    } catch (err) {
      output.textContent = "Preview failed: " + (err.message || err);
    }
  }

  async function onSave(e) {
    e.preventDefault();
    try {
      var payload = {
        name: byId("builder-name").value.trim(),
        description: byId("builder-description").value.trim() || null,
        trigger_mode: byId("builder-trigger-mode").value,
        steps: collectSteps(),
      };
      await apiJson("/api/v1/automations/workflow-definitions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      byId("builder-preview-output").textContent = "Draft saved.";
    } catch (err) {
      byId("builder-preview-output").textContent = "Save failed: " + (err.message || err);
    }
  }

  async function onCopilot(e) {
    e.preventDefault();
    var output = byId("copilot-output");
    if (!output) return;
    try {
      var integrations = (byId("copilot-integrations").value || "").split(",").map(function (item) { return item.trim(); }).filter(Boolean);
      var payload = await apiJson("/api/v1/automations/copilot/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          intent: byId("copilot-intent").value.trim(),
          constraints: {},
          available_integrations: integrations,
        }),
      });
      output.innerHTML = '<strong>' + esc(payload.name) + '</strong><p>' + esc(payload.summary) + '</p><div class="step-chip-row">' +
        payload.steps.map(function (step) { return '<span class="step-chip">' + esc(step.name + " / " + step.action_type) + '</span>'; }).join("") +
        '</div>';
    } catch (err) {
      output.textContent = "Copilot failed: " + (err.message || err);
    }
  }

  window.WorkflowBuilderPage = {
    init: function (deps) {
      apiJson = deps.apiJson;
      if (!byId("workflow-builder-form")) return;
      renderInitialStep();
      byId("builder-add-step").onclick = function () {
        byId("builder-steps").insertAdjacentHTML("beforeend", buildStepRow({ name: "", action_type: "", params: {}, requires_approval: false }));
        bindStepActions();
      };
      byId("builder-preview").onclick = onPreview;
      byId("workflow-builder-form").onsubmit = onSave;
      if (byId("workflow-copilot-form")) {
        byId("workflow-copilot-form").onsubmit = onCopilot;
      }
    }
  };
})();
