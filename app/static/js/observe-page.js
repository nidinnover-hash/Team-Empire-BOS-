window.__bootPromise = fetch('/web/api-token')
      .then(r => { if (!r.ok) throw new Error('Session expired'); return r.json(); })
      .then(d => d.token);
    var esc = window.PCUI.escapeHtml;
    var observeState = {
      topic: '',
      correlation_id: '',
      entity_type: '',
      entity_id: ''
    };
    function formatDateTime(value) {
      return value ? new Date(value).toLocaleString() : '';
    }
    function formatDuration(ms) {
      if (ms == null || !isFinite(ms)) return 'n/a';
      if (ms < 1000) return ms + 'ms';
      if (ms < 60000) return (ms / 1000).toFixed(1) + 's';
      return (ms / 60000).toFixed(1) + 'm';
    }
    function renderSummaryList(container, items, emptyText) {
      if (!container) return;
      if (!items || !items.length) {
        container.className = 'summary-list empty';
        container.textContent = emptyText;
        return;
      }
      container.className = 'summary-list';
      container.innerHTML = items.map(function (item) {
        var when = formatDateTime(item.decided_at || item.execution_finished_at || item.requested_at);
        var meta = [
          item.approval_type || 'unknown',
          item.execution_status || item.approval_status || 'n/a',
          when || 'now'
        ].join(' · ');
        return '<div class="summary-item"><strong>#' + esc(item.approval_id) + '</strong><span>' + esc(meta) + '</span></div>';
      }).join('');
    }
    function renderAiReliabilityProviders(container, items) {
      if (!container) return;
      if (!items || !items.length) {
        container.className = 'summary-list empty';
        container.textContent = 'No AI reliability data yet.';
        return;
      }
      container.className = 'summary-list';
      container.innerHTML = items.map(function (item) {
        var meta = [
          (item.total_calls || 0) + ' calls',
          (item.error_rate || 0) + '% errors',
          (item.fallback_rate || 0) + '% fallback',
          formatDuration(item.avg_latency_ms)
        ].join(' · ');
        return '<div class="summary-item"><strong>' + esc(item.provider || 'unknown') + '</strong><span>' + esc(meta) + '</span></div>';
      }).join('');
    }
    function renderAiReliabilityFailures(container, items) {
      if (!container) return;
      if (!items || !items.length) {
        container.className = 'summary-list empty';
        container.textContent = 'No recent AI failures.';
        return;
      }
      container.className = 'summary-list';
      container.innerHTML = items.map(function (item) {
        var meta = [
          item.provider || 'unknown',
          item.error_type || 'unknown error',
          formatDateTime(item.occurred_at) || 'now'
        ].join(' · ');
        return '<div class="summary-item"><strong>' + esc(item.model_name || item.request_id || 'AI call') + '</strong><span>' + esc(meta) + '</span></div>';
      }).join('');
    }
    function renderSchedulerJobs(container, items) {
      if (!container) return;
      if (!items || !items.length) {
        container.className = 'summary-list empty';
        container.textContent = 'No scheduler activity yet.';
        return;
      }
      container.className = 'summary-list';
      container.innerHTML = items.map(function (item) {
        var meta = [
          (item.total_runs || 0) + ' runs',
          (item.failed_runs || 0) + ' failed',
          (item.success_rate || 0) + '% success',
          formatDuration(item.avg_duration_ms)
        ].join(' · ');
        return '<div class="summary-item"><strong>' + esc(item.job_name || 'unknown job') + '</strong><span>' + esc(meta) + '</span></div>';
      }).join('');
    }
    function renderSchedulerFailures(container, items) {
      if (!container) return;
      if (!items || !items.length) {
        container.className = 'summary-list empty';
        container.textContent = 'No recent scheduler failures.';
        return;
      }
      container.className = 'summary-list';
      container.innerHTML = items.map(function (item) {
        var meta = [
          item.error || 'runtime error',
          formatDuration(item.duration_ms),
          formatDateTime(item.occurred_at) || 'now'
        ].join(' · ');
        return '<div class="summary-item"><strong>' + esc(item.job_name || 'unknown job') + '</strong><span>' + esc(meta) + '</span></div>';
      }).join('');
    }
    function renderWebhookEndpoints(container, items) {
      if (!container) return;
      if (!items || !items.length) {
        container.className = 'summary-list empty';
        container.textContent = 'No webhook activity yet.';
        return;
      }
      container.className = 'summary-list';
      container.innerHTML = items.map(function (item) {
        var endpointLabel = item.endpoint_id != null ? ('Endpoint #' + item.endpoint_id) : 'Unknown endpoint';
        var meta = [
          (item.total_deliveries || 0) + ' deliveries',
          (item.failed_deliveries || 0) + ' failed',
          (item.success_rate || 0) + '% success',
          formatDuration(item.avg_duration_ms)
        ].join(' · ');
        return '<div class="summary-item"><strong>' + esc(endpointLabel) + '</strong><span>' + esc(meta) + '</span></div>';
      }).join('');
    }
    function renderWebhookFailures(container, items) {
      if (!container) return;
      if (!items || !items.length) {
        container.className = 'summary-list empty';
        container.textContent = 'No recent webhook failures.';
        return;
      }
      container.className = 'summary-list';
      container.innerHTML = items.map(function (item) {
        var label = item.event || (item.endpoint_id != null ? ('Endpoint #' + item.endpoint_id) : 'Webhook delivery');
        var meta = [
          item.error_message || 'delivery failed',
          item.response_status_code != null ? ('HTTP ' + item.response_status_code) : 'no status',
          formatDateTime(item.occurred_at) || 'now'
        ].join(' · ');
        return '<div class="summary-item"><strong>' + esc(label) + '</strong><span>' + esc(meta) + '</span></div>';
      }).join('');
    }
    function prettyJson(value) {
      try {
        return JSON.stringify(value || {}, null, 2);
      } catch (_err) {
        return '{}';
      }
    }
    function syncFiltersFromUrl() {
      var params = new URLSearchParams(window.location.search);
      observeState.topic = params.get('topic') || '';
      observeState.correlation_id = params.get('correlation_id') || '';
      observeState.entity_type = params.get('entity_type') || '';
      observeState.entity_id = params.get('entity_id') || '';
      var topicEl = document.getElementById('signal-topic');
      var corrEl = document.getElementById('signal-correlation');
      var entityTypeEl = document.getElementById('signal-entity-type');
      var entityIdEl = document.getElementById('signal-entity-id');
      if (topicEl) topicEl.value = observeState.topic;
      if (corrEl) corrEl.value = observeState.correlation_id;
      if (entityTypeEl) entityTypeEl.value = observeState.entity_type;
      if (entityIdEl) entityIdEl.value = observeState.entity_id;
    }
    function pushFilterStateToUrl() {
      var params = new URLSearchParams();
      Object.keys(observeState).forEach(function (key) {
        if (observeState[key]) params.set(key, observeState[key]);
      });
      var query = params.toString();
      var nextUrl = window.location.pathname + (query ? ('?' + query) : '');
      window.history.replaceState({}, '', nextUrl);
    }
    function buildSignalUrl() {
      var params = new URLSearchParams();
      params.set('limit', '25');
      if (observeState.topic) params.set('topic', observeState.topic);
      if (observeState.correlation_id) params.set('correlation_id', observeState.correlation_id);
      if (observeState.entity_type) params.set('entity_type', observeState.entity_type);
      if (observeState.entity_id) params.set('entity_id', observeState.entity_id);
      return '/api/v1/observability/signals?' + params.toString();
    }
    function getApprovalIdFilter() {
      if (observeState.entity_type && observeState.entity_type.toLowerCase() === 'approval' && observeState.entity_id) {
        return observeState.entity_id;
      }
      return '';
    }
    function buildDecisionSummaryUrl() {
      var params = new URLSearchParams();
      params.set('days', '7');
      params.set('limit', '100');
      if (observeState.correlation_id) params.set('correlation_id', observeState.correlation_id);
      var approvalId = getApprovalIdFilter();
      if (approvalId) params.set('approval_id', approvalId);
      return '/api/v1/observability/decision-summary?' + params.toString();
    }
    function buildDecisionTimelineUrl() {
      var params = new URLSearchParams();
      params.set('days', '7');
      params.set('limit', '20');
      if (observeState.correlation_id) params.set('correlation_id', observeState.correlation_id);
      var approvalId = getApprovalIdFilter();
      if (approvalId) params.set('approval_id', approvalId);
      return '/api/v1/observability/decision-timeline?' + params.toString();
    }
    function buildAiReliabilityUrl() {
      var params = new URLSearchParams();
      params.set('days', '7');
      params.set('limit', '200');
      return '/api/v1/observability/ai-reliability?' + params.toString();
    }
    function buildSchedulerHealthUrl() {
      var params = new URLSearchParams();
      params.set('days', '7');
      params.set('limit', '300');
      return '/api/v1/observability/scheduler-health?' + params.toString();
    }
    function buildWebhookReliabilityUrl() {
      var params = new URLSearchParams();
      params.set('days', '7');
      params.set('limit', '300');
      return '/api/v1/observability/webhook-reliability?' + params.toString();
    }
    function renderDetailPanel(title, metadata, payload) {
      var panel = document.getElementById('observe-detail-panel');
      if (!panel) return;
      panel.className = 'detail-panel';
      panel.innerHTML =
        '<div class="detail-head">' + esc(title || 'Details') + '</div>'
        + '<div class="detail-meta">' + esc(metadata || '') + '</div>'
        + '<pre class="detail-json">' + esc(prettyJson(payload)) + '</pre>';
    }
    async function fetchJsonOrThrow(url, opts) {
      const r = await fetch(url, opts);
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `Request failed (${r.status})`);
      return d;
    }

    async function loadObservability() {
      const token = await window.__bootPromise;
      if (!token) throw new Error('Session expired');
      const h = {'Authorization': 'Bearer ' + token};
      try {
        const [summary, aiReliability, schedulerHealth, webhookReliability, calls, decisions, decisionSummary, decisionTimeline, signals] = await Promise.all([
          fetchJsonOrThrow('/api/v1/observability/summary?days=7', {headers:h}),
          fetchJsonOrThrow(buildAiReliabilityUrl(), {headers:h}),
          fetchJsonOrThrow(buildSchedulerHealthUrl(), {headers:h}),
          fetchJsonOrThrow(buildWebhookReliabilityUrl(), {headers:h}),
          fetchJsonOrThrow('/api/v1/observability/ai-calls?limit=30', {headers:h}),
          fetchJsonOrThrow('/api/v1/observability/decision-traces?limit=15', {headers:h}),
          fetchJsonOrThrow(buildDecisionSummaryUrl(), {headers:h}),
          fetchJsonOrThrow(buildDecisionTimelineUrl(), {headers:h}),
          fetchJsonOrThrow(buildSignalUrl(), {headers:h}),
        ]);

        document.getElementById('k-calls').textContent = summary.total_ai_calls;
        document.getElementById('k-fb').textContent = summary.fallback_rate + '%';
        document.getElementById('k-err').textContent = summary.error_rate + '%';
        document.getElementById('k-rej').textContent = summary.rejection_rate + '%';
        document.getElementById('k-ai-success').textContent = (aiReliability.success_rate || 0) + '%';
        document.getElementById('k-ai-failed').textContent = aiReliability.failed_calls || 0;
        document.getElementById('k-ai-fallbacks').textContent = aiReliability.fallback_count || 0;
        document.getElementById('k-ai-avg-latency').textContent =
          aiReliability.avg_latency_ms != null ? formatDuration(aiReliability.avg_latency_ms) : 'n/a';
        renderAiReliabilityProviders(
          document.getElementById('ai-reliability-providers'),
          aiReliability.providers || []
        );
        renderAiReliabilityFailures(
          document.getElementById('ai-reliability-failures'),
          aiReliability.recent_failures || []
        );
        document.getElementById('k-scheduler-runs').textContent = schedulerHealth.total_runs || 0;
        document.getElementById('k-scheduler-failed').textContent = schedulerHealth.failed_runs || 0;
        document.getElementById('k-scheduler-success').textContent = (schedulerHealth.success_rate || 0) + '%';
        document.getElementById('k-scheduler-duration').textContent =
          schedulerHealth.avg_duration_ms != null ? formatDuration(schedulerHealth.avg_duration_ms) : 'n/a';
        renderSchedulerJobs(
          document.getElementById('scheduler-health-jobs'),
          schedulerHealth.jobs || []
        );
        renderSchedulerFailures(
          document.getElementById('scheduler-health-failures'),
          schedulerHealth.recent_failures || []
        );
        document.getElementById('k-webhook-total').textContent = webhookReliability.total_deliveries || 0;
        document.getElementById('k-webhook-failed').textContent = webhookReliability.failed_deliveries || 0;
        document.getElementById('k-webhook-success').textContent = (webhookReliability.success_rate || 0) + '%';
        document.getElementById('k-webhook-duration').textContent =
          webhookReliability.avg_duration_ms != null ? formatDuration(webhookReliability.avg_duration_ms) : 'n/a';
        renderWebhookEndpoints(
          document.getElementById('webhook-reliability-endpoints'),
          webhookReliability.endpoints || []
        );
        renderWebhookFailures(
          document.getElementById('webhook-reliability-failures'),
          webhookReliability.recent_failures || []
        );

        var latencyChart = document.getElementById("observe-latency-chart");
        if (latencyChart && window.PCChartsLite && summary.provider_stats && summary.provider_stats.length) {
          var sortedProviders = summary.provider_stats.slice().sort(function (a, b) {
            return Number(a.call_count || 0) > Number(b.call_count || 0) ? -1 : 1;
          }).slice(0, 6);
          window.PCChartsLite.renderLineChart(latencyChart, {
            caption: "Average latency and call volume by provider",
            ariaLabel: "Observability provider latency chart",
            series: [
              {
                name: "Avg Latency (ms)",
                values: sortedProviders.map(function (p) { return Number(p.avg_latency_ms || 0); }),
                color: "var(--brand, #0a84ff)"
              },
              {
                name: "Call Count",
                values: sortedProviders.map(function (p) { return Number(p.call_count || 0); }),
                color: "var(--ok, #34c759)"
              }
            ]
          });
        } else if (latencyChart) {
          latencyChart.innerHTML = '<p class="empty">No latency trend available</p>';
        }

        // Provider bars
        const ps = document.getElementById('provider-stats');
        if (summary.provider_stats && summary.provider_stats.length) {
          const maxLat = Math.max(...summary.provider_stats.map(p=>p.avg_latency_ms), 1);
          ps.innerHTML = summary.provider_stats.map(p => `
            <div style="margin-bottom:.7rem">
              <div style="display:flex;justify-content:space-between;font-size:.78rem">
                <span style="color:#111">${esc(p.provider)}</span>
                <span style="color:#666">${esc(p.avg_latency_ms)}ms avg / ${esc(p.call_count)} calls</span>
              </div>
              <div class="bar-wrap"><div class="bar-fill" style="width:${Math.round(p.avg_latency_ms/maxLat*100)}%"></div></div>
            </div>
          `).join('');
        }

        // AI calls table
        const tbody = document.getElementById('ai-calls-body');
        if (calls.length) {
          tbody.innerHTML = calls.map(c => {
            let status = '<span class="tag">OK</span>';
            if (c.error_type) status = '<span class="tag err">Error</span>';
            else if (c.used_fallback) status = `<span class="tag fb">Fallback from ${esc(c.fallback_from)}</span>`;
            const t = c.created_at ? new Date(c.created_at).toLocaleTimeString() : '';
            return `<tr><td>${esc(c.provider)}</td><td style="color:#999">${esc(c.model_name)}</td><td>${esc(c.latency_ms)}ms</td><td>${status}</td><td style="color:#999">${esc(t)}</td></tr>`;
          }).join('');
        }

        // Decisions table
        const dbody = document.getElementById('decisions-body');
        if (decisions.length) {
          dbody.innerHTML = decisions.map(d => {
            const conf = ((d.confidence_score || 0) * 100).toFixed(0) + '%';
            const t = d.created_at ? new Date(d.created_at).toLocaleTimeString() : '';
            return `<tr><td><span class="tag">${esc(d.trace_type)}</span></td><td>${esc(d.title)}</td><td>${esc(conf)}</td><td style="color:#999">${esc(t)}</td></tr>`;
          }).join('');
        }

        document.getElementById('k-decision-total').textContent = decisionSummary.total_requests || 0;
        document.getElementById('k-decision-approved').textContent = decisionSummary.approved_count || 0;
        document.getElementById('k-decision-stalled').textContent = decisionSummary.approved_but_not_executed_count || 0;
        document.getElementById('k-decision-failed').textContent = decisionSummary.execution_failed_count || 0;
        document.getElementById('decision-median-latency').textContent =
          decisionSummary.median_approval_to_execution_ms != null
            ? formatDuration(decisionSummary.median_approval_to_execution_ms)
            : 'No executions yet';
        renderSummaryList(
          document.getElementById('decision-stalled-list'),
          decisionSummary.recent_stalled || [],
          'No stalled approvals.'
        );
        renderSummaryList(
          document.getElementById('decision-failed-list'),
          decisionSummary.recent_failed || [],
          'No failed executions.'
        );

        var timelineBody = document.getElementById('decision-timeline-body');
        if (decisionTimeline.length) {
          timelineBody.innerHTML = decisionTimeline.map(function (item) {
            var timelineText = (item.timeline || []).map(function (event) {
              return event.topic.replace(/\./g, ' -> ');
            }).join(' / ');
            var statusTag = item.stalled
              ? '<span class="tag warn">Stalled</span>'
              : '<span class="tag">' + esc(item.approval_status || 'unknown') + '</span>';
            var execTag = item.execution_status
              ? '<span class="tag ' + (item.execution_status === 'failed' ? 'err' : 'ok') + '">' + esc(item.execution_status) + '</span>'
              : '<span class="tag muted">not started</span>';
            return '<tr>'
              + '<td><button type="button" class="detail-trigger timeline-trigger" data-approval-id="' + esc(item.approval_id) + '"><strong>#' + esc(item.approval_id) + '</strong><div class="cell-sub">' + esc(item.approval_type || 'unknown') + '</div></button></td>'
              + '<td>' + statusTag + '</td>'
              + '<td>' + execTag + '</td>'
              + '<td>' + esc(formatDuration(item.approval_to_execution_ms)) + '</td>'
              + '<td><div class="timeline-text">' + esc(timelineText || 'No timeline') + '</div></td>'
              + '</tr>';
          }).join('');
          Array.prototype.forEach.call(document.querySelectorAll('.timeline-trigger'), function (button) {
            button.addEventListener('click', function () {
              var approvalId = button.getAttribute('data-approval-id');
              var match = (decisionTimeline || []).find(function (item) {
                return String(item.approval_id) === String(approvalId);
              });
              if (!match) return;
              renderDetailPanel(
                'Approval #' + approvalId,
                [match.approval_type || 'unknown', match.approval_status || 'unknown', match.execution_status || 'not started'].join(' · '),
                match
              );
            });
          });
        }

        var signalsBody = document.getElementById('signals-body');
        if (signals.length) {
          signalsBody.innerHTML = signals.map(function (signal) {
            var entity = signal.entity_type && signal.entity_id
              ? signal.entity_type + ' #' + signal.entity_id
              : 'n/a';
            return '<tr>'
              + '<td><button type="button" class="detail-trigger signal-trigger" data-signal-id="' + esc(signal.signal_id) + '"><span class="tag">' + esc(signal.topic) + '</span></button></td>'
              + '<td>' + esc(entity) + '</td>'
              + '<td>' + esc(signal.source || 'unknown') + '</td>'
              + '<td>' + esc(signal.summary_text || '') + '</td>'
              + '<td style="color:#999">' + esc(formatDateTime(signal.occurred_at)) + '</td>'
              + '</tr>';
          }).join('');
          Array.prototype.forEach.call(document.querySelectorAll('.signal-trigger'), function (button) {
            button.addEventListener('click', function () {
              var signalId = button.getAttribute('data-signal-id');
              var match = (signals || []).find(function (item) {
                return String(item.signal_id) === String(signalId);
              });
              if (!match) return;
              renderDetailPanel(
                match.topic,
                [match.source || 'unknown', match.entity_type || 'entity', match.entity_id || 'n/a', formatDateTime(match.occurred_at)].join(' · '),
                match
              );
            });
          });
        }

        document.getElementById('loading').style.display = 'none';
        document.getElementById('content').style.display = 'block';
      } catch(e) {
        document.getElementById('loading').textContent = String(e.message || 'Failed to load metrics.');
      }
    }
    syncFiltersFromUrl();
    loadObservability();

    var signalFilterForm = document.getElementById('signal-filter-form');
    if (signalFilterForm) {
      signalFilterForm.addEventListener('submit', function (event) {
        event.preventDefault();
        observeState.topic = (document.getElementById('signal-topic').value || '').trim();
        observeState.correlation_id = (document.getElementById('signal-correlation').value || '').trim();
        observeState.entity_type = (document.getElementById('signal-entity-type').value || '').trim();
        observeState.entity_id = (document.getElementById('signal-entity-id').value || '').trim();
        pushFilterStateToUrl();
        loadObservability();
      });
    }

    var signalFilterReset = document.getElementById('signal-filter-reset');
    if (signalFilterReset) {
      signalFilterReset.addEventListener('click', function () {
        observeState.topic = '';
        observeState.correlation_id = '';
        observeState.entity_type = '';
        observeState.entity_id = '';
        syncFiltersFromUrl();
        pushFilterStateToUrl();
        var topicEl = document.getElementById('signal-topic');
        var corrEl = document.getElementById('signal-correlation');
        var entityTypeEl = document.getElementById('signal-entity-type');
        var entityIdEl = document.getElementById('signal-entity-id');
        if (topicEl) topicEl.value = '';
        if (corrEl) corrEl.value = '';
        if (entityTypeEl) entityTypeEl.value = '';
        if (entityIdEl) entityIdEl.value = '';
        loadObservability();
      });
    }

    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) logoutBtn.addEventListener('click', async () => {
      const csrf = document.cookie.split(';').map(c=>c.trim()).find(c=>c.startsWith('pc_csrf='));
      const csrfVal = csrf ? decodeURIComponent(csrf.split('=').slice(1).join('=')) : '';
      try {
        const r = await fetch('/web/logout', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrfVal}});
        if (!r.ok) throw new Error('Logout failed');
        window.location.href = '/web/login';
      } catch (e) {
        alert(String(e.message || e));
      }
    });

    if (typeof lucide !== "undefined") lucide.createIcons();
