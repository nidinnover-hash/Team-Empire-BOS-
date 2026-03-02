import { APIError, QuotaExceededError, RateLimitError } from "./errors";
import type {
  AgentChatRequest,
  AgentChatResponse,
  ApprovalDecision,
  ApprovalRead,
  ApiKeyCreate,
  ApiKeyCreateResponse,
  ApiKeyListResponse,
  MultiTurnResponse,
  TaskCreate,
  TaskRead,
  TaskUpdate,
  UserMeRead,
  WebhookDeliveryListResponse,
  WebhookEndpointCreate,
  WebhookEndpointCreateResponse,
  WebhookEndpointListResponse,
} from "./types";

export interface ClientOptions {
  baseUrl: string;
  apiKey: string;
  maxRetries?: number;
  backoffMs?: number;
  onRequestEvent?: (event: RequestEvent) => void;
}

export interface RequestEvent {
  method: "GET" | "POST" | "PATCH" | "DELETE";
  path: string;
  attempt: number;
  statusCode: number;
  durationMs: number;
  requestId?: string;
  retriable: boolean;
  retried: boolean;
  errorType?: string;
}

const RETRYABLE_STATUS = new Set([429, 502, 503, 504]);

function parseRetryAfterSeconds(value: string | null): number | undefined {
  if (!value) return undefined;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) return undefined;
  return parsed;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export class NidinBOSClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly maxRetries: number;
  private readonly backoffMs: number;
  private readonly onRequestEvent?: (event: RequestEvent) => void;

  constructor(options: ClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.apiKey = options.apiKey;
    this.maxRetries = Math.max(0, options.maxRetries ?? 2);
    this.backoffMs = Math.max(0, options.backoffMs ?? 500);
    this.onRequestEvent = options.onRequestEvent;
  }

  private async request<T>(
    method: "GET" | "POST" | "PATCH" | "DELETE",
    path: string,
    opts: { body?: unknown; expectedStatus?: number[] } = {},
  ): Promise<T> {
    const expected = new Set(opts.expectedStatus ?? [200]);
    let lastError: APIError | undefined;

    for (let attempt = 0; attempt <= this.maxRetries; attempt += 1) {
      const started = Date.now();
      const response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      });

      if (expected.has(response.status)) {
        this.onRequestEvent?.({
          method,
          path,
          attempt: attempt + 1,
          statusCode: response.status,
          durationMs: Number((Date.now() - started).toFixed(3)),
          requestId: response.headers.get("x-correlation-id") ?? undefined,
          retriable: false,
          retried: attempt > 0,
          errorType: undefined,
        });
        if (response.status === 204) return undefined as T;
        const text = await response.text();
        return (text ? JSON.parse(text) : undefined) as T;
      }

      let body: unknown = undefined;
      try {
        body = await response.json();
      } catch {
        body = undefined;
      }
      const requestId = response.headers.get("x-correlation-id") ?? undefined;
      const detail =
        typeof body === "object" && body !== null && "detail" in body
          ? String((body as { detail?: unknown }).detail ?? "")
          : undefined;
      const retryAfterSeconds = parseRetryAfterSeconds(response.headers.get("retry-after"));

      if (response.status === 429) {
        const quota = (detail ?? "").toLowerCase().includes("quota");
        if (quota) {
          lastError = new QuotaExceededError(
            "Daily quota exceeded",
            429,
            detail,
            requestId,
            body,
            retryAfterSeconds,
          );
        } else {
          lastError = new RateLimitError(
            "Rate limited by API",
            429,
            detail,
            requestId,
            body,
            retryAfterSeconds,
          );
        }
      } else {
        lastError = new APIError(`API request failed with status ${response.status}`, response.status, detail, requestId, body);
      }

      this.onRequestEvent?.({
        method,
        path,
        attempt: attempt + 1,
        statusCode: response.status,
        durationMs: Number((Date.now() - started).toFixed(3)),
        requestId,
        retriable: RETRYABLE_STATUS.has(response.status),
        retried: attempt > 0,
        errorType: lastError.name,
      });

      if (!RETRYABLE_STATUS.has(response.status) || attempt >= this.maxRetries) {
        break;
      }
      const delayMs =
        retryAfterSeconds !== undefined
          ? retryAfterSeconds * 1000
          : this.backoffMs * (2 ** attempt);
      if (delayMs > 0) {
        await sleep(delayMs);
      }
    }

    throw lastError ?? new APIError("Unknown request failure", 0);
  }

  authMe(): Promise<UserMeRead> {
    return this.request<UserMeRead>("GET", "/api/v1/auth/me");
  }

  listApiKeys(): Promise<ApiKeyListResponse> {
    return this.request<ApiKeyListResponse>("GET", "/api/v1/api-keys");
  }

  createApiKey(payload: ApiKeyCreate): Promise<ApiKeyCreateResponse> {
    return this.request<ApiKeyCreateResponse>("POST", "/api/v1/api-keys", {
      body: payload,
      expectedStatus: [201],
    });
  }

  revokeApiKey(keyId: number): Promise<void> {
    return this.request<void>("DELETE", `/api/v1/api-keys/${keyId}`, {
      expectedStatus: [200, 204],
    });
  }

  listWebhooks(): Promise<WebhookEndpointListResponse> {
    return this.request<WebhookEndpointListResponse>("GET", "/api/v1/webhooks");
  }

  createWebhook(payload: WebhookEndpointCreate): Promise<WebhookEndpointCreateResponse> {
    return this.request<WebhookEndpointCreateResponse>("POST", "/api/v1/webhooks", {
      body: payload,
      expectedStatus: [201],
    });
  }

  listWebhookDeliveries(endpointId: number, limit = 50, offset = 0): Promise<WebhookDeliveryListResponse> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    return this.request<WebhookDeliveryListResponse>(
      "GET",
      `/api/v1/webhooks/${endpointId}/deliveries?${params.toString()}`,
    );
  }

  listTasks(): Promise<TaskRead[]> {
    return this.request<TaskRead[]>("GET", "/api/v1/tasks");
  }

  createTask(payload: TaskCreate): Promise<TaskRead> {
    return this.request<TaskRead>("POST", "/api/v1/tasks", {
      body: payload,
      expectedStatus: [201],
    });
  }

  updateTask(taskId: number, payload: TaskUpdate): Promise<TaskRead> {
    return this.request<TaskRead>("PATCH", `/api/v1/tasks/${taskId}`, {
      body: payload,
      expectedStatus: [200],
    });
  }

  listApprovals(): Promise<ApprovalRead[]> {
    return this.request<ApprovalRead[]>("GET", "/api/v1/approvals");
  }

  approveApproval(approvalId: number, payload: ApprovalDecision): Promise<ApprovalRead> {
    return this.request<ApprovalRead>("POST", `/api/v1/approvals/${approvalId}/approve`, {
      body: payload,
      expectedStatus: [200],
    });
  }

  listOrganizations(): Promise<Record<string, unknown>[]> {
    return this.request<Record<string, unknown>[]>("GET", "/api/v1/orgs");
  }

  listAutomationTriggers(): Promise<Record<string, unknown>[]> {
    return this.request<Record<string, unknown>[]>("GET", "/api/v1/automations/triggers");
  }

  listAutomationWorkflows(): Promise<Record<string, unknown>[]> {
    return this.request<Record<string, unknown>[]>("GET", "/api/v1/automations/workflows");
  }

  agentChat(payload: AgentChatRequest): Promise<AgentChatResponse> {
    return this.request<AgentChatResponse>("POST", "/api/v1/agents/chat", {
      body: payload,
    });
  }

  agentMultiTurn(payload: AgentChatRequest): Promise<MultiTurnResponse> {
    return this.request<MultiTurnResponse>("POST", "/api/v1/agents/multi-turn", {
      body: payload,
    });
  }

  // BEGIN GENERATED OPERATIONS
  deleteApiV1ApiKeysKeyId(key_id: string | number): Promise<unknown> {
    let path = `/api/v1/api-keys/${String(key_id)}`;
    return this.request<unknown>("DELETE", path, {
      expectedStatus: [204],
    });
  }

  deleteApiV1ApprovalsApprovalPatternsPatternId(pattern_id: string | number): Promise<unknown> {
    let path = `/api/v1/approvals/approval-patterns/${String(pattern_id)}`;
    return this.request<unknown>("DELETE", path, {
      expectedStatus: [204],
    });
  }

  deleteApiV1AutomationsTriggersTriggerId(trigger_id: string | number): Promise<unknown> {
    let path = `/api/v1/automations/triggers/${String(trigger_id)}`;
    return this.request<unknown>("DELETE", path, {
      expectedStatus: [204],
    });
  }

  deleteApiV1TasksTaskId(task_id: string | number): Promise<unknown> {
    let path = `/api/v1/tasks/${String(task_id)}`;
    return this.request<unknown>("DELETE", path, {
      expectedStatus: [204],
    });
  }

  deleteApiV1WebhooksEndpointId(endpoint_id: string | number): Promise<unknown> {
    let path = `/api/v1/webhooks/${String(endpoint_id)}`;
    return this.request<unknown>("DELETE", path, {
      expectedStatus: [204],
    });
  }

  getApiV1ApiKeys(): Promise<unknown> {
    let path = `/api/v1/api-keys`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1Approvals(status?: string | number | boolean, limit?: string | number | boolean, offset?: string | number | boolean): Promise<unknown> {
    let path = `/api/v1/approvals`;
    const query = new URLSearchParams();
    if (status !== undefined) query.set("status", String(status));
    if (limit !== undefined) query.set("limit", String(limit));
    if (offset !== undefined) query.set("offset", String(offset));
    const qs = query.toString();
    if (qs) path = `${path}?${qs}`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1ApprovalsApprovalPatterns(): Promise<unknown> {
    let path = `/api/v1/approvals/approval-patterns`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1ApprovalsTimeline(limit?: string | number | boolean, offset?: string | number | boolean): Promise<unknown> {
    let path = `/api/v1/approvals/timeline`;
    const query = new URLSearchParams();
    if (limit !== undefined) query.set("limit", String(limit));
    if (offset !== undefined) query.set("offset", String(offset));
    const qs = query.toString();
    if (qs) path = `${path}?${qs}`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1AuthMe(): Promise<unknown> {
    let path = `/api/v1/auth/me`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1AutomationsTriggers(active_only?: string | number | boolean, limit?: string | number | boolean): Promise<unknown> {
    let path = `/api/v1/automations/triggers`;
    const query = new URLSearchParams();
    if (active_only !== undefined) query.set("active_only", String(active_only));
    if (limit !== undefined) query.set("limit", String(limit));
    const qs = query.toString();
    if (qs) path = `${path}?${qs}`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1AutomationsTriggersTriggerId(trigger_id: string | number): Promise<unknown> {
    let path = `/api/v1/automations/triggers/${String(trigger_id)}`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1AutomationsWorkflows(status?: string | number | boolean, limit?: string | number | boolean): Promise<unknown> {
    let path = `/api/v1/automations/workflows`;
    const query = new URLSearchParams();
    if (status !== undefined) query.set("status", String(status));
    if (limit !== undefined) query.set("limit", String(limit));
    const qs = query.toString();
    if (qs) path = `${path}?${qs}`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1AutomationsWorkflowsWorkflowId(workflow_id: string | number): Promise<unknown> {
    let path = `/api/v1/automations/workflows/${String(workflow_id)}`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1Orgs(): Promise<unknown> {
    let path = `/api/v1/orgs`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1OrgsOrgIdFeatureFlags(org_id: string | number): Promise<unknown> {
    let path = `/api/v1/orgs/${String(org_id)}/feature-flags`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1OrgsOrgIdMembers(org_id: string | number): Promise<unknown> {
    let path = `/api/v1/orgs/${String(org_id)}/members`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1Tasks(project_id?: string | number | boolean, category?: string | number | boolean, is_done?: string | number | boolean, limit?: string | number | boolean, offset?: string | number | boolean): Promise<unknown> {
    let path = `/api/v1/tasks`;
    const query = new URLSearchParams();
    if (project_id !== undefined) query.set("project_id", String(project_id));
    if (category !== undefined) query.set("category", String(category));
    if (is_done !== undefined) query.set("is_done", String(is_done));
    if (limit !== undefined) query.set("limit", String(limit));
    if (offset !== undefined) query.set("offset", String(offset));
    const qs = query.toString();
    if (qs) path = `${path}?${qs}`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1Webhooks(limit?: string | number | boolean, offset?: string | number | boolean): Promise<unknown> {
    let path = `/api/v1/webhooks`;
    const query = new URLSearchParams();
    if (limit !== undefined) query.set("limit", String(limit));
    if (offset !== undefined) query.set("offset", String(offset));
    const qs = query.toString();
    if (qs) path = `${path}?${qs}`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1WebhooksDeliveriesAll(event?: string | number | boolean, status?: string | number | boolean, limit?: string | number | boolean, offset?: string | number | boolean): Promise<unknown> {
    let path = `/api/v1/webhooks/deliveries/all`;
    const query = new URLSearchParams();
    if (event !== undefined) query.set("event", String(event));
    if (status !== undefined) query.set("status", String(status));
    if (limit !== undefined) query.set("limit", String(limit));
    if (offset !== undefined) query.set("offset", String(offset));
    const qs = query.toString();
    if (qs) path = `${path}?${qs}`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1WebhooksDeliveriesDeadLetter(limit?: string | number | boolean, offset?: string | number | boolean): Promise<unknown> {
    let path = `/api/v1/webhooks/deliveries/dead-letter`;
    const query = new URLSearchParams();
    if (limit !== undefined) query.set("limit", String(limit));
    if (offset !== undefined) query.set("offset", String(offset));
    const qs = query.toString();
    if (qs) path = `${path}?${qs}`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1WebhooksEndpointId(endpoint_id: string | number): Promise<unknown> {
    let path = `/api/v1/webhooks/${String(endpoint_id)}`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  getApiV1WebhooksEndpointIdDeliveries(endpoint_id: string | number, limit?: string | number | boolean, offset?: string | number | boolean): Promise<unknown> {
    let path = `/api/v1/webhooks/${String(endpoint_id)}/deliveries`;
    const query = new URLSearchParams();
    if (limit !== undefined) query.set("limit", String(limit));
    if (offset !== undefined) query.set("offset", String(offset));
    const qs = query.toString();
    if (qs) path = `${path}?${qs}`;
    return this.request<unknown>("GET", path, {
      expectedStatus: [200],
    });
  }

  patchApiV1ApprovalsApprovalPatternsPatternId(pattern_id: string | number, payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/approvals/approval-patterns/${String(pattern_id)}`;
    return this.request<unknown>("PATCH", path, {
      body: payload,
      expectedStatus: [200],
    });
  }

  patchApiV1AutomationsTriggersTriggerId(trigger_id: string | number, payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/automations/triggers/${String(trigger_id)}`;
    return this.request<unknown>("PATCH", path, {
      body: payload,
      expectedStatus: [200],
    });
  }

  patchApiV1OrgsOrgId(org_id: string | number, payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/orgs/${String(org_id)}`;
    return this.request<unknown>("PATCH", path, {
      body: payload,
      expectedStatus: [200],
    });
  }

  patchApiV1OrgsOrgIdFeatureFlags(org_id: string | number, payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/orgs/${String(org_id)}/feature-flags`;
    return this.request<unknown>("PATCH", path, {
      body: payload,
      expectedStatus: [200],
    });
  }

  patchApiV1TasksTaskId(task_id: string | number, payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/tasks/${String(task_id)}`;
    return this.request<unknown>("PATCH", path, {
      body: payload,
      expectedStatus: [200],
    });
  }

  patchApiV1WebhooksEndpointId(endpoint_id: string | number, payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/webhooks/${String(endpoint_id)}`;
    return this.request<unknown>("PATCH", path, {
      body: payload,
      expectedStatus: [200],
    });
  }

  postApiV1ApiKeys(payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/api-keys`;
    return this.request<unknown>("POST", path, {
      body: payload,
      expectedStatus: [201],
    });
  }

  postApiV1ApprovalsApprovalIdApprove(approval_id: string | number, payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/approvals/${String(approval_id)}/approve`;
    return this.request<unknown>("POST", path, {
      body: payload,
      expectedStatus: [200],
    });
  }

  postApiV1ApprovalsApprovalIdReject(approval_id: string | number, payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/approvals/${String(approval_id)}/reject`;
    return this.request<unknown>("POST", path, {
      body: payload,
      expectedStatus: [200],
    });
  }

  postApiV1ApprovalsRequest(payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/approvals/request`;
    return this.request<unknown>("POST", path, {
      body: payload,
      expectedStatus: [201],
    });
  }

  postApiV1AutomationsTriggers(payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/automations/triggers`;
    return this.request<unknown>("POST", path, {
      body: payload,
      expectedStatus: [201],
    });
  }

  postApiV1AutomationsWorkflows(payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/automations/workflows`;
    return this.request<unknown>("POST", path, {
      body: payload,
      expectedStatus: [201],
    });
  }

  postApiV1AutomationsWorkflowsWorkflowIdAdvance(workflow_id: string | number, payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/automations/workflows/${String(workflow_id)}/advance`;
    return this.request<unknown>("POST", path, {
      body: payload,
      expectedStatus: [200],
    });
  }

  postApiV1AutomationsWorkflowsWorkflowIdRun(workflow_id: string | number): Promise<unknown> {
    let path = `/api/v1/automations/workflows/${String(workflow_id)}/run`;
    return this.request<unknown>("POST", path, {
      expectedStatus: [200],
    });
  }

  postApiV1AutomationsWorkflowsWorkflowIdStart(workflow_id: string | number): Promise<unknown> {
    let path = `/api/v1/automations/workflows/${String(workflow_id)}/start`;
    return this.request<unknown>("POST", path, {
      expectedStatus: [200],
    });
  }

  postApiV1Orgs(payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/orgs`;
    return this.request<unknown>("POST", path, {
      body: payload,
      expectedStatus: [201],
    });
  }

  postApiV1OrgsOrgIdMembers(org_id: string | number, payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/orgs/${String(org_id)}/members`;
    return this.request<unknown>("POST", path, {
      body: payload,
      expectedStatus: [201],
    });
  }

  postApiV1Tasks(payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/tasks`;
    return this.request<unknown>("POST", path, {
      body: payload,
      expectedStatus: [201],
    });
  }

  postApiV1Webhooks(payload?: Record<string, unknown>): Promise<unknown> {
    let path = `/api/v1/webhooks`;
    return this.request<unknown>("POST", path, {
      body: payload,
      expectedStatus: [201],
    });
  }

  postApiV1WebhooksDeliveriesDeliveryIdReplay(delivery_id: string | number): Promise<unknown> {
    let path = `/api/v1/webhooks/deliveries/${String(delivery_id)}/replay`;
    return this.request<unknown>("POST", path, {
      expectedStatus: [200],
    });
  }

  postApiV1WebhooksEndpointIdTest(endpoint_id: string | number): Promise<unknown> {
    let path = `/api/v1/webhooks/${String(endpoint_id)}/test`;
    return this.request<unknown>("POST", path, {
      expectedStatus: [200],
    });
  }
  // END GENERATED OPERATIONS
}
